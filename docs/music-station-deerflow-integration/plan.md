# 音乐电台与 DeerFlow Memory 互通方案

## 背景

音乐电台作为 DeerFlow 的应用子模块嵌入运行，但其用户体系、记忆系统完全独立：
- 音乐电台自建 JWT 认证，DeerFlow 用户登录后音乐电台仍需独立登录
- 音乐电台没有读取 DeerFlow `memory` 的能力，agent 聊天时无法获取用户喜好
- 音乐电台 agent 聊天总结的用户喜好无法写回 DeerFlow memory

## 目标

1. **统一用户身份**：音乐电台复用 DeerFlow 的 JWT token，无需二次登录
2. **读取 memory**：音乐电台 agent 聊天前读取 DeerFlow memory，注入 system prompt
3. **写入 memory**：音乐电台 agent 聊天后，LLM 总结用户喜好并写回 DeerFlow memory
4. **数据互通**：用户喜好/记忆在 DeerFlow 和音乐电台之间双向流动

## 架构设计

```
┌─────────────────┐     iframe (?token=xxx)      ┌─────────────────────────┐
│  DeerFlow 前端   │ ─────────────────────────→ │  音乐电台前端 (iframe)   │
│                 │                          │                         │
│  localStorage   │                          │  从 URL 读取 token      │
│  token: xxx     │                          │  存入 localStorage      │
└─────────────────┘                          └─────────────────────────┘
         │                                              │
         │ JWT Bearer                                  │ JWT Bearer
         ▼                                              ▼
┌─────────────────┐                              ┌─────────────┐
│ DeerFlow Gateway │                              │ 音乐电台后端 │
│   Port 8001     │ ←──── memory CRUD ─────────── │             │
│                 │                               │ 1. 代理请求到 │
│  /api/memory    │                               │    DeerFlow │
│  /api/memory/   │                               │ 2. Agent 注入 │
│    facts        │                               │    memory   │
└─────────────────┘                               └─────────────┘
```

## 实施阶段

### Phase 1: 统一认证 — iframe Token 传递

**目标**：DeerFlow 前端将 JWT token 传递给音乐电台 iframe，音乐电台前端接收并保存。

**修改文件**：
1. `frontend/src/app/workspace/applications/music-station/page.tsx`
   - 从 localStorage/cookie 读取 DeerFlow token
   - iframe `src` 附加 `?token=xxx`

2. `frontend/public/applications/music-station/index.html`
   - 添加内联脚本：从 URL query param 读取 token
   - 存入 `localStorage.setItem("ms_df_token", token)`
   - 拦截所有 `fetch`/`XMLHttpRequest`，自动添加 `Authorization: Bearer token`

**验收标准**：
- 打开音乐电台页面后，`localStorage.ms_df_token` 有值
- 音乐电台前端发出的 API 请求携带正确的 `Authorization` header

---

### Phase 2: 音乐电台后端 — DeerFlow Client

**目标**：在音乐电台后端添加 DeerFlow API 客户端，支持 memory 读写。

**修改文件**：
1. `music-station/backend/app/core/deerflow_client.py` (新增)
   - 封装 `GET /api/memory`、`POST /api/memory/facts`
   - 支持 Bearer token 认证

2. `music-station/backend/app/core/config.py`
   - 添加 `DEERFLOW_GATEWAY_URL` 配置项

3. `music-station/backend/app/main.py`
   - 从请求头提取 `Authorization: Bearer token`
   - 创建 `DeerFlowClient` 实例并挂载到 app state 或依赖注入

4. `docker-compose-dev.yaml`
   - `music-station-backend` 环境变量添加 `DEERFLOW_GATEWAY_URL=http://deer-flow-gateway:8001`

**验收标准**：
- 音乐电台后端能成功调用 `GET /api/memory` 并返回 DeerFlow memory 数据
- 能成功调用 `POST /api/memory/facts` 创建 fact

---

### Phase 3: Agent 集成 — Memory 注入与回写

**目标**：音乐电台 agent 聊天时读取 DeerFlow memory 注入 prompt，聊天结束后总结并写回 memory。

**修改文件**：
1. `music-station/backend/app/api/agent.py` (或聊天相关路由)
   - **聊天前**：调用 `deerflow_client.get_memory()` 获取 facts
   - 将 facts 拼接为字符串，注入 LLM system prompt
   - **聊天后**：调用 LLM 总结本次对话中的用户喜好
   - 调用 `deerflow_client.create_fact(summary, category="preference")` 写回 DeerFlow

2. `music-station/backend/app/services/llm.py` (或现有 LLM 调用逻辑)
   - 添加 `summarize_user_preference(chat_history)` 方法
   - Prompt 示例："请总结用户在本次对话中表现出的音乐偏好（风格、艺人、情绪等），用一句话描述"

**验收标准**：
- Agent 聊天时 system prompt 包含 DeerFlow memory 中的用户喜好
- 聊天结束后，DeerFlow memory 新增一条 preference fact

---

### Phase 4: 废弃音乐电台自建认证

**目标**：音乐电台不再使用自建用户体系，完全复用 DeerFlow 用户。

**修改文件**：
1. `music-station/backend/app/api/users.py` (或认证路由)
   - 注册/登录接口改为：接收 DeerFlow token，解码 `sub` 作为 user_id
   - 不再生成自建 JWT，直接返回 DeerFlow token

2. `music-station/backend/app/core/security.py`
   - `get_current_user` 依赖改为：验证 DeerFlow token，返回 `sub` 作为 user_id

3. 前端所有 API 调用统一使用 `ms_df_token`

**验收标准**：
- 用户无需在音乐电台内再次登录
- 所有 API 鉴权通过 DeerFlow token 完成

---

## 文件清单汇总

| # | 文件路径 | Phase | 操作 |
|---|---------|-------|------|
| 1 | `frontend/src/app/workspace/applications/music-station/page.tsx` | 1 | 修改 |
| 2 | `frontend/public/applications/music-station/index.html` | 1 | 修改 |
| 3 | `music-station/backend/app/core/deerflow_client.py` | 2 | 新增 |
| 4 | `music-station/backend/app/core/config.py` | 2 | 修改 |
| 5 | `music-station/backend/app/main.py` | 2 | 修改 |
| 6 | `docker-compose-dev.yaml` | 2 | 修改 |
| 7 | `music-station/backend/app/api/agent.py` | 3 | 修改 |
| 8 | `music-station/backend/app/services/llm.py` | 3 | 修改 |
| 9 | `music-station/backend/app/api/users.py` | 4 | 修改 |
| 10 | `music-station/backend/app/core/security.py` | 4 | 修改 |

## 验收标准（总体）

1. [x] 用户登录 DeerFlow 后，进入音乐电台无需再次登录 ✅ Phase 4 验证通过
2. [x] 音乐电台 agent 能读取 DeerFlow memory 中的用户喜好并用于推荐 ✅ Phase 3 验证通过
3. [x] 用户在音乐电台 agent 聊天后，新产生的喜好自动写回 DeerFlow memory ✅ Phase 3 验证通过
4. [x] 刷新页面后，记忆保持一致（不丢失）✅ Phase 4 前端背景持久化已验证
5. [x] 音乐电台原有功能（歌曲推荐、播放、背景更换）不受影响 ✅ 基础功能已验证

---

## Phase 4 实施报告

详见 [`phase4-test-report.md`](./phase4-test-report.md)

**关键变更**：
- 后端 `get_current_user_id` 移除所有 fallback，强制 DeerFlow cookie 认证
- 前端 `api/client.ts` 移除 `localStorage.getItem('token')` 及 `Authorization` header 注入
- 无 DeerFlow session 时 API 统一返回 401，前端聊天界面显示错误提示

---

## Phase 3 测试报告

详见 [`phase3-test-report.md`](./phase3-test-report.md)

**关键发现**：
- `DeerFlowClient` 必须携带 `X-CSRF-Token` 才能成功写入 memory（已修复）
- Prompt 中两个 `system` message 会稀释 memory 上下文，合并为单个后利用率显著提升
- Agent 能在多轮对话中准确引用 DeerFlow memory 中的用户偏好
