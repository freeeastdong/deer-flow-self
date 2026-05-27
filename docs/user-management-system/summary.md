# DeerFlow 用户管理系统开发总结

> **开发周期**：Day 1 ~ Day 7（2026-04-30 完成）  
> **核心目标**：为 DeerFlow 添加完整的用户认证、角色权限与对话隔离体系  
> **技术栈**：better-auth（前端）+ FastAPI + SQLite（共享）+ Docker Compose

---

## 一、功能总览

### 1.1 已完成功能

| 模块 | 功能点 | 说明 |
|------|--------|------|
| **用户认证** | 注册 / 登录 / 登出 | 基于 better-auth，使用邮箱+密码，Cookie 会话保持 |
| **用户资料** | 昵称 / 头像 / 角色 | 通过 `additionalFields` 扩展用户表，支持昵称修改 |
| **角色权限** | admin / user | `role` 字段默认 `user`，管理员可查看所有用户 |
| **对话隔离** | 用户只能看自己的对话 | `search_threads` 按 `metadata.user_id` 过滤 |
| **对话隔离** | 管理员可看所有对话 | admin 角色在搜索和单对话操作中自动绕过隔离 |
| **对话隔离** | 老数据兼容 | 单对话读取仍兼容无 `user_id` 的历史数据（不 403） |
| **后端鉴权** | 401 / 403 响应 | 未登录返回 401，越权访问返回 403 |
| **前端守卫** | 路由级拦截 | `/admin/users` 非 admin 自动跳回 `/profile` |

### 1.2 核心流程图

```
┌─────────────┐     注册/登录      ┌──────────────────┐
│   浏览器    │ ────────────────> │  better-auth     │
│             │                   │  (frontend)      │
└──────┬──────┘                   └────────┬─────────┘
       │                                   │ 写入 SQLite
       │ 携带 Cookie                       │ (auth.db)
       │                                   │
       │         ┌─────────────────────────┘
       │         │ 共享 Volume
       │         ↓
       │   ┌─────────────┐
       └──>│   Gateway   │
           │  (FastAPI)  │
           └──────┬──────┘
                  │ 读取 Cookie → 查 session 表 → 验证身份
                  │
                  ↓
           ┌─────────────┐
           │  对话隔离    │
           │ metadata    │
           │ user_id     │
           └─────────────┘
```

---

## 二、新增文件清单

### 前端

```
frontend/src/app/register/page.tsx          # 用户注册页
frontend/src/app/login/page.tsx             # 用户登录页
frontend/src/app/profile/page.tsx           # 个人资料页（昵称修改、对话数统计）
frontend/src/app/admin/users/page.tsx       # 管理员用户列表页
```

### 后端

```
backend/app/gateway/auth_deps.py            # better-auth Session 验证工具
backend/app/gateway/routers/admin.py        # 管理员接口（/api/admin/users）
backend/tests/test_thread_isolation.py      # 对话隔离自动化测试（7 个用例）
```

### 自动生成

```
data/auth.db                                # better-auth SQLite 数据库
```

---

## 三、修改文件清单

### 前端

| 文件 | 修改内容 |
|------|---------|
| `frontend/src/server/better-auth/config.ts` | 增加 `additionalFields`（nickname、avatar、role），数据库路径指向 `/app/data/auth.db` |
| `frontend/src/components/workspace/workspace-nav-menu.tsx` | 集成 `useSession()`，显示用户昵称/登出按钮，增加个人资料入口 |
| `frontend/.env` | 增加 `BETTER_AUTH_SECRET`、`BETTER_AUTH_URL` |
| `frontend/.env.example` | 同上（模板同步） |

### 后端

| 文件 | 修改内容 |
|------|---------|
| `backend/app/gateway/deps.py` | 新增 `get_current_user`（401 鉴权）和 `require_admin`（403 管理员检查） |
| `backend/app/gateway/routers/threads.py` | `search_threads` 增加 `user_id` 过滤；`_require_thread_access` 增加权限检查；各端点注入 `get_current_user` |
| `backend/app/gateway/routers/thread_runs.py` | 所有 runs 端点注入 `get_current_user` 并调用 `_require_thread_access` |
| `backend/app/gateway/routers/runs.py` | stateless runs 端点在复用已有 thread 时检查权限 |
| `backend/app/gateway/services.py` | `start_run` 中自动将当前用户 `user_id` 写入 Store metadata |
| `backend/app/gateway/app.py` | 注册 `admin` router |

### 部署配置

| 文件 | 修改内容 |
|------|---------|
| `docker/docker-compose-dev.yaml` | frontend / gateway 新增 Volume 挂载 `../data:/app/data` |
| `docker/docker-compose.yaml` | 同上（生产环境） |
| `.env` | 增加 `BETTER_AUTH_SECRET`、`LANGGRAPH_UPSTREAM=gateway:8001`、`LANGGRAPH_REWRITE=/api/` |

---

## 四、关键设计决策

### 4.1 为什么用 better-auth + SQLite？

- **零配置**：better-auth 自带 SQLite 支持，无需额外部署 PostgreSQL
- **共享简单**：通过 Docker Compose Volume 将 `./data` 挂载到前后端容器，实现零网络共享
- **过渡性**：upstream `release/2.0-rc` 正在推进官方认证插件，better-auth 是当前 main 分支最务实的选择

### 4.2 对话隔离为什么不改数据库表结构？

- **最小侵入**：利用 LangGraph Store / Checkpointer 已有的 `metadata` 字段存储 `user_id`
- **兼容老数据**：无 `user_id` 的历史对话在单对话操作中仍允许访问，避免升级后数据丢失
- **搜索过滤**：`search_threads` 中按 `metadata.user_id` 过滤，普通用户看不到他人对话

### 4.3 Gateway 代理模式

- 通过 `.env` 切换 `LANGGRAPH_UPSTREAM=gateway:8001`，让 nginx 将 `/api/langgraph/*` 转发到 FastAPI Gateway
- 前端 `LangGraphClient` **无需修改任何代码**，自动经过 Gateway 完成鉴权

---

## 五、测试覆盖

### 5.1 自动化测试

`backend/tests/test_thread_isolation.py` 包含 7 个用例：

1. `test_user_only_sees_own_threads` —— 搜索隔离
2. `test_user_cannot_see_legacy_threads` —— 历史数据对普通用户隐藏
3. `test_admin_can_see_all_threads` —— 管理员全量访问
4. `test_unauthenticated_search_returns_401` —— 未登录拦截
5. `test_get_other_user_thread_forbidden` —— 单对话越权 403
6. `test_get_legacy_thread_allowed` —— 老数据单对话兼容
7. `test_run_on_other_user_thread_forbidden` —— runs 端点越权 403

### 5.2 手动测试清单（Day 7.1）

已覆盖：注册 → 登录 → 资料修改 → 对话创建 → 切换用户验证隔离 → 管理员全量访问 → 登出

---

## 六、已知问题与注意事项

| 问题 | 说明 | 优先级 |
|------|------|--------|
| 生产 compose 需确认 data volume | 生产环境 `docker-compose.yaml` 已添加 `../data:/app/data` 挂载 | 已处理 |
| 未登录用户访问 `/admin/users` | 前端守卫已拦截，跳转 `/login` | 已处理 |
| 注册昵称同步 | 注册后调用 `updateUser` 同步 `nickname` 字段 | 已处理 |

---

## 七、后续可扩展方向

### 7.1 迁移到 upstream 官方认证

- DeerFlow `release/2.0-rc` 正在推进 `app/plugins/auth` 插件体系和 `actor_context` 请求级用户上下文
- 未来可将 better-auth 方案迁移到官方认证体系
- **核心隔离逻辑**（metadata 存 `user_id` + 搜索过滤 + 权限检查）可以保留，只需替换 `get_current_user` 的实现（从 `actor_context` 读取）

### 7.2 多副本部署支持

- 配合 upstream RFC #2471（Multi-replica deployment）
- 当前方案天然支持多副本，因为 `user_id` 存储在共享的 checkpointer/store 中，不依赖单机内存

### 7.3 更细粒度的权限

- 当前仅区分 `admin` / `user`
- 未来可扩展为基于 capabilities 的细粒度授权（与 upstream `authorization/` 模块对齐）
- 例如：`thread:read:all`、`thread:write:own`、`user:manage` 等细粒度权限

### 7.4 头像上传

- `additionalFields` 中已预留 `avatar` 字段
- 未来可对接对象存储（OSS/S3）实现头像上传功能

---

## 八、项目文档索引

| 文档 | 内容 |
|------|------|
| `docs/user-management-system/plan.md` | 完整 7 天开发计划 |
| `docs/user-management-system/summary.md` | 本总结文档 |
| `docs/user-management-system/day1/` ~ `day7/` | 每日 Phase 执行记录 |
| `day7/phase-7-1.md` | 全链路手动测试清单 |
| `day7/phase-7-2.md` | Bug 修复记录 |
| `day7/phase-7-3.md` | 自动化测试说明 |
| `day7/phase-7-4.md` | 代码清理与格式化记录 |
| `day7/phase-7-5.md` | Phase 7.5 记录 |

---

**开发完成时间**：2026-04-30  
**总涉及代码文件**：约 15+ 个（新增 7 个，修改 10+ 个）  
**测试用例**：7 个自动化 + 17 项手动测试
