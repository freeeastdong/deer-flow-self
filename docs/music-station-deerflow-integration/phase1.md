# Phase 1: 统一认证 + DeerFlow Client 集成

## 目标
1. 音乐电台后端接入 DeerFlow 认证（Session Cookie 代理验证）
2. 添加 DeerFlow API Client，支持 memory 读写
3. Agent 聊天时注入 DeerFlow memory，聊天后同步用户喜好回写

## 修改文件清单

### 1. 新增文件
- `music-station/backend/app/core/deerflow_client.py`
  - `DeerFlowClient` 类：封装 DeerFlow Gateway 的 API 调用
  - `get_current_user()`：验证 session cookie，返回用户信息
  - `get_memory()`：读取 DeerFlow memory 数据
  - `create_memory_fact()`：创建 memory fact

### 2. 修改文件

#### `music-station/backend/app/core/config.py`
- 新增配置项：`DEERFLOW_GATEWAY_URL = "http://deer-flow-gateway:8001"`

#### `music-station/backend/app/core/security.py`
- 新增 `get_current_user_from_deerflow()` 函数
- 认证优先级：① DeerFlow session cookie → ② 自建 JWT token
- 如果 DeerFlow 认证成功，返回 `{"id": ..., "email": ..., "name": ..., "source": "deerflow"}`

#### `music-station/backend/app/api/agent.py`
- `get_current_user_id()` 添加 `request: Request` 参数
- 优先从 cookie 读取 DeerFlow session，验证成功后同步到本地数据库（创建/复用用户映射）
- `agent_chat()` 创建 `DeerFlowClient`，传入 `MusicAgent`

#### `music-station/backend/app/services/agent_core.py`
- `MusicAgent.__init__` 添加 `deerflow_client` 参数
- `_llm_chat()` 聊天前读取 DeerFlow memory facts，注入 system prompt
- `chat()` 聊天后调用 `_sync_memory_to_deerflow()`
- 新增 `_sync_memory_to_deerflow()`：调用 LLM 总结本轮对话中的用户偏好，写回 DeerFlow memory

#### `docker/docker-compose-dev.yaml`
- `music-station-backend` 环境变量新增：`DEERFLOW_GATEWAY_URL: http://deer-flow-gateway:8001`

## 认证流程

```
浏览器(已登录DeerFlow)
  │
  │ iframe 加载 /workspace/applications/music-station
  │ (同源，自动携带 deer-flow cookie)
  │
  ▼
音乐电台前端 → 请求 /api/music-station/v1/agent/chat
  │
  │ cookie 自动携带
  ▼
nginx → 转发到 music-station-backend:8000
  │
  ▼
get_current_user_id()
  ├── 1. 提取 Cookie header
  ├── 2. DeerFlowClient 调用 GET http://deer-flow-gateway:8001/api/v1/auth/me
  ├── 3. 返回 200 → 获取 user_id，同步到本地数据库
  └── 4. 失败 → fallback 到自建 JWT
```

## 数据流

```
聊天前:
  MusicAgent._llm_chat() → DeerFlowClient.get_memory()
  → 提取 facts → 注入 system prompt

聊天后:
  MusicAgent.chat() → _sync_memory_to_deerflow()
  → LLM 总结偏好 → DeerFlowClient.create_memory_fact()
  → POST /api/memory/facts → 写回 DeerFlow
```

## 待构建

需要重新构建 `music-station-backend` Docker 镜像，因为后端代码已修改。

```bash
docker compose -f docker/docker-compose-dev.yaml up --build -d music-station-backend
```
