# 用户管理系统开发计划

> **任务目标**：为 DeerFlow 项目添加一套完整的用户管理系统  
> **预计周期**：7 天  
> **难度定位**：面向小白，每个 Phase 都尽量简单、独立、可验证  
> **记录要求**：每完成一个 Phase，在对应 `dayX/` 目录下新建 `phase-X-Y.md` 做记录

---

## 一、技术方案总览（先读懂，再动手）

### 1.1 现有基础
- **前端**：Next.js 16 + React 19，已安装 `better-auth`（一个开箱即用的认证库）
- **后端**：FastAPI（Python），目前**没有任何认证保护**，所有接口公开可访问
- **数据库**：项目原本没有传统数据库，但 `better-auth` 自带 SQLite 支持，零配置即可使用  
- **部署方式**：本项目使用 **Docker Compose** 部署（`docker-compose.yaml` / `docker-compose-dev.yaml`），前端、后端、nginx 分属不同容器，必须通过 **共享 Volume** 才能让前后端访问同一个 SQLite 文件

### 1.2 我们要做什么
| 模块 | 说明 |
|------|------|
| 数据库 | 用 SQLite 存储用户、会话、角色等信息（better-auth 自动管） |
| 前端认证 | 注册页、登录页、登出按钮、better-auth 客户端对接 |
| 后端认证 | FastAPI 读取 Cookie 中的 session，验证用户身份 |
| 用户资料 | 昵称、头像、个人主页、资料修改 |
| 角色权限 | 区分 `admin` 和 `user`，管理员可看用户列表 |

### 1.3 核心流程图
```
用户访问 nginx:2026 → 需要登录？→ 跳转到 /login
    ↓
登录/注册 → better-auth 写入 SQLite 数据库（/app/data/auth.db）
    ↓
前端携带 Cookie 请求后端 → nginx 转发 → FastAPI 读 Cookie 查共享数据库 → 返回数据
```

### 1.4 Docker 部署关键点（必读）

| 问题 | 解决方案 |
|------|---------|
| 前后端容器互相隔离，如何共享数据库？ | 在项目根目录创建 `data/` 文件夹，两个 docker-compose 都给 frontend + gateway 挂载 `- ../data:/app/data` |
| 用户最终访问地址是什么？ | `http://localhost:2026`（nginx 统一入口），不是 `localhost:3000` |
| better-auth 的数据库文件放哪？ | 容器内统一放在 `/app/data/auth.db`，宿主机对应 `./data/auth.db` |
| Cookie 跨容器问题 | 不需要担心，因为前后端都走同一域名（nginx 代理），Cookie 会自动携带 |

---

## 二、前置准备（动手前先检查）

1. 确保你在项目根目录 `deer-flow-0417/`
2. 前端依赖使用 `pnpm`，后端使用 `uv`
3. 每天开始前，先 `git status` 确认工作区干净（或已提交）
4. **Docker 用户特别注意**：修改代码后需要重新构建/重启容器才能生效（开发环境可用 `$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up --build`）

---

## 三、每日计划详解

---

### ✅ Day 1：环境准备与数据库配置（已完成）
> **今日目标**：让 better-auth 真正连上数据库，能存用户数据

#### Phase 1.1 — 安装 SQLite 驱动
- **做什么**：给前端（Next.js）安装 `better-sqlite3`，这是 better-auth 推荐的 SQLite 驱动
- **命令**：
  ```bash
  cd frontend
  pnpm add better-sqlite3
  pnpm add -D @types/better-sqlite3
  ```
- **验证**：`frontend/package.json` 中出现 `better-sqlite3` 依赖
- **⚠️ 必须重新构建前端镜像**：修改了 `package.json`，需要重新构建镜像才能让容器内获得新依赖。如果构建时报 `better-sqlite3` 编译错误，说明 Alpine 镜像缺少 C++ 编译工具，需要在 `frontend/Dockerfile` 的 `base` 阶段添加：
  ```dockerfile
  RUN apk add --no-cache python3 make g++
  ```
  然后重新构建：
  ```powershell
  $env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d --build frontend
  ```
- **记录文件**：`docs/user-management-system/day1/phase-1-1.md`

#### Phase 1.2 — 配置 better-auth 使用 SQLite（Docker 路径）
- **做什么**：修改 better-auth 配置文件，指定数据库文件路径（使用容器内共享路径）
- **涉及文件**：
  - `frontend/src/server/better-auth/config.ts`
- **预期结果**：配置后大致如下：
  ```ts
  import { betterAuth } from "better-auth";
  import Database from "better-sqlite3";

  export const auth = betterAuth({
    database: new Database("/app/data/auth.db"),  // Docker 容器内共享路径
    emailAndPassword: {
      enabled: true,
    },
  });
  ```
- **注意**：`/app/data/auth.db` 是容器内的绝对路径。稍后通过 docker-compose Volume 挂载，宿主机对应 `./data/auth.db`
- **记录文件**：`docs/user-management-system/day1/phase-1-2.md`

#### Phase 1.3 — 创建共享数据目录并修改 docker-compose
- **做什么**：
  1. 在项目根目录创建 `data/` 目录（宿主机持久化目录）
  2. 修改两个 docker-compose 文件，给 frontend 和 gateway 都挂载这个目录
  3. 使用 better-auth CLI 生成/迁移数据库表结构
- **步骤 1：创建目录**：
  ```bash
  # 在项目根目录执行
  mkdir -p data
  ```
- **步骤 2：修改 docker-compose**（在 `docker/docker-compose-dev.yaml` 和 `docker/docker-compose.yaml` 中，找到 frontend 和 gateway 的 `volumes` 段落，各添加一行）：
  ```yaml
  # frontend 服务下的 volumes 添加：
  - ../data:/app/data

  # gateway 服务下的 volumes 添加：
  - ../data:/app/data
  ```
  **具体位置示例**（dev 环境的 frontend）：
  ```yaml
  frontend:
    # ...
    volumes:
      - ../frontend/src:/app/frontend/src
      - ../frontend/public:/app/frontend/public
      # ... 其他已有挂载 ...
      - ../data:/app/data   # ← 新增这一行
  ```
- **⚠️ 修改 docker-compose 后必须重建容器**：新增 Volume 挂载对已在运行的容器不会自动生效，需要重建：
  ```powershell
  $env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d --force-recreate frontend gateway
  ```
- **步骤 3：运行迁移**（推荐在容器内运行，避免宿主机环境差异问题）：
  ```powershell
  # 确保前端容器已重建并启动
  $env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d --force-recreate frontend

  # 方式一：一条命令直接执行
  docker exec -it deer-flow-frontend sh -c "cd /app/frontend && npx @better-auth/cli migrate --config src/server/better-auth/config.ts"

  # 方式二：进入容器交互式执行
  docker exec -it deer-flow-frontend sh
  cd /app/frontend
  npx @better-auth/cli migrate --config src/server/better-auth/config.ts
  # 或者：npx better-auth migrate --config src/server/better-auth/config.ts
  exit
  ```
- **验证**：
  - 宿主机出现 `data/auth.db` 文件
  - 用 SQLite 工具（如 DB Browser）打开，能看到 `user`, `session`, `account`, `verification` 表
- **记录文件**：`docs/user-management-system/day1/phase-1-3.md`

#### Phase 1.4 — 更新环境变量配置
- **做什么**：确保 `.env` 和 `.env.example` 包含认证所需的环境变量（Docker 部署下要特别注意 Base URL）
- **涉及文件**：
  - `frontend/.env`
  - `frontend/.env.example`
  - 检查 `docker/docker-compose.yaml` 和 `docker/docker-compose-dev.yaml` 中是否已传入 `BETTER_AUTH_SECRET`
- **需要添加/修改**：
  ```env
  # frontend/.env
  BETTER_AUTH_SECRET=your-super-secret-key-at-least-32-chars-long
  BETTER_AUTH_URL=http://localhost:2026   # Docker 下走 nginx 入口，不是 3000
  ```
- **关于 `BETTER_AUTH_SECRET`**：
  - 生产 compose 文件里已写了 `BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET}`，所以只需要在**宿主机**的 `.env` 文件里设置即可
  - 开发 compose 文件通过 `env_file: - ../frontend/.env` 加载，同样生效
- **⚠️ 修改环境变量后必须重启 frontend 容器**：`env_file` 只在容器启动时读取，修改 `.env` 后需要重启才能生效：
  ```powershell
  $env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml restart frontend
  ```
- **验证**：重启后容器日志不报错，前端能正常访问
- **记录文件**：`docs/user-management-system/day1/phase-1-4.md`

---

### ✅ Day 2：用户注册功能（前端）
> **今日目标**：用户能在网页上填写信息，成功注册账号

#### Phase 2.1 — 创建注册页面路由
- **做什么**：新建 Next.js 页面 `/register`
- **涉及文件**：
  - `frontend/src/app/register/page.tsx`
- **要求**：先只放一个最简单的骨架（`<h1>注册</h1>`），能访问就行
- **验证**：浏览器访问 `http://localhost:2026/register` 能看到标题（Docker 下走 nginx）
- **记录文件**：`docs/user-management-system/day2/phase-2-1.md`

#### Phase 2.2 — 创建注册表单 UI
- **做什么**：在注册页中加入表单（邮箱、密码、确认密码、昵称）
- **涉及文件**：
  - `frontend/src/app/register/page.tsx`
- **要求**：使用原生 `<form>` 或项目已有的 UI 组件（如 Radix + Tailwind），先不做提交逻辑
- **验证**：页面上能看到输入框和"注册"按钮
- **记录文件**：`docs/user-management-system/day2/phase-2-2.md`

#### Phase 2.3 — 添加表单校验（zod）
- **做什么**：用 `zod` 定义注册数据的校验规则，密码至少 8 位，邮箱格式正确，两次密码一致
- **涉及文件**：
  - `frontend/src/app/register/page.tsx`（或拆出 `schema.ts`）
- **要求**：校验失败时在对应输入框下方显示红色错误提示
- **验证**：输入错误内容点击注册，能看到提示；输入正确内容，提示消失
- **记录文件**：`docs/user-management-system/day2/phase-2-3.md`

#### Phase 2.4 — 接入 better-auth 注册 API
- **做什么**：点击注册按钮后，调用 `authClient.signUp.email()` 发送请求
- **涉及文件**：
  - `frontend/src/app/register/page.tsx`
- **要求**：
  - 注册成功：显示成功提示，自动跳转到 `/workspace` 或 `/login`
  - 注册失败（如邮箱已存在）：显示错误提示
- **验证**：用真实邮箱密码注册一次，去 `./data/auth.db`（宿主机）里能看到新增的用户记录。如果容器内验证，文件在 `/app/data/auth.db`
- **记录文件**：`docs/user-management-system/day2/phase-2-4.md`

---

### ✅ Day 3：登录与登出
> **今日目标**：用户能登录、登出，并在页面上看到自己的登录状态

#### Phase 3.1 — 创建登录页面路由
- **做什么**：新建 Next.js 页面 `/login`
- **涉及文件**：
  - `frontend/src/app/login/page.tsx`
- **要求**：先放骨架，能访问
- **验证**：浏览器访问 `http://localhost:2026/login` 正常（Docker 下走 nginx）
- **记录文件**：`docs/user-management-system/day3/phase-3-1.md`

#### Phase 3.2 — 创建登录表单 UI
- **做什么**：在登录页中加入邮箱、密码输入框和登录按钮
- **涉及文件**：
  - `frontend/src/app/login/page.tsx`
- **要求**：样式和注册页保持一致
- **记录文件**：`docs/user-management-system/day3/phase-3-2.md`

#### Phase 3.3 — 接入 better-auth 登录 API
- **做什么**：点击登录后调用 `authClient.signIn.email()`
- **涉及文件**：
  - `frontend/src/app/login/page.tsx`
- **要求**：
  - 登录成功：跳转到 `/workspace`
  - 登录失败：显示"邮箱或密码错误"
- **验证**：用 Day 2 注册的账号能正常登录
- **记录文件**：`docs/user-management-system/day3/phase-3-3.md`

#### Phase 3.4 — 导航栏显示用户状态 + 登出
- **做什么**：在顶部导航栏或侧边栏显示当前用户头像/邮箱，并提供"登出"按钮
- **涉及文件**：
  - 找到项目现有的布局/导航组件（通常在 `frontend/src/components/layout/` 或 `frontend/src/app/workspace/layout.tsx`）
  - 使用 `authClient.useSession()` 获取当前登录状态
- **要求**：
  - 未登录：显示"登录 / 注册"按钮
  - 已登录：显示用户名称和"退出登录"按钮
  - 点击退出调用 `authClient.signOut()`，成功后刷新页面或跳首页
- **验证**：登录后能看到自己的名字，点击退出后状态变回未登录
- **记录文件**：`docs/user-management-system/day3/phase-3-4.md`

> 💡 **为后续对话隔离做准备**：Day 3 完成后，前端已具备完整的登录/登出/Session 能力。better-auth 的 session cookie 会在后续所有同域请求中自动携带，这是 Day 4 后端识别用户身份的基础。

#### Day 3 补充改进 — 登录页增加注册跳转链接
- **发现问题**：登录界面没有注册入口，新用户无法从登录页跳转到注册页
- **解决**：在 `frontend/src/app/login/page.tsx` 登录按钮下方增加"还没有账号？立即注册"跳转链接
- **涉及文件**：
  - `frontend/src/app/login/page.tsx`
- **验证**：访问 `/login` 页面能看到注册跳转链接，点击后正常跳转到 `/register`

---

### 📅 Day 4：后端 API 认证保护 + 对话隔离（核心日）
> **今日目标**：
> 1. 后端能认出"这是谁发来的请求"，未登录不能访问敏感接口
> 2. **新增**：实现用户对话层面的数据隔离——用户只能看到和操作自己的对话

**对话隔离方案总览（必读）**

为了不破坏前端现有调用方式（`useStream`、`apiClient.threads.search` 等），我们采用 **Gateway 代理模式**：

| 改造点 | 说明 |
|--------|------|
| 流量切换 | 通过修改 `.env` 中的 `LANGGRAPH_UPSTREAM` 和 `LANGGRAPH_REWRITE`，让 nginx 把 `/api/langgraph/*` 全部转发到 FastAPI gateway，而不是独立的 LangGraph Server。这样前端 `LangGraphClient` 的调用自动经过 gateway，**无需改一行前端代码**。 |
| 身份传递 | 前端请求携带 better-auth 的 session cookie（同域默认自动携带），gateway 读取 Cookie 验证用户身份。 |
| 数据关联 | 利用 LangGraph checkpointer 和 store 的 **metadata** 字段存储 `user_id`，**不修改任何数据库表结构**。 |
| 兼容老数据 | 已存在的对话（没有 `user_id`）允许所有人访问，确保升级后历史数据不丢失。 |

> ⚠️ **架构演进注意**：DeerFlow upstream（`release/2.0-rc`）正在推进统一的认证架构（RFC #2470 / #2429），包括 `AuthProvider` 请求级钩子、`app/plugins/auth` 插件体系和 `actor_context` 请求级用户上下文。本方案使用自定义 better-auth + 手动 session 验证是**当前代码基线（main 分支）下的过渡性实现**。当 upstream 正式发布官方认证插件后，用户模型、登录注册端点和鉴权方式可能需要迁移，但**对话隔离的核心逻辑**（metadata 存 `user_id` + 搜索过滤 + 权限检查）可以保留，只需将 `user_id` 的获取方式从"手动解析 cookie"改为"从 `actor_context` 读取"。建议将 `get_current_user` 依赖封装成可替换的接口，方便未来迁移。

---

#### Phase 4.1 — 后端安装必要依赖（Docker 环境下）
- **做什么**：FastAPI 需要解析 Cookie 并查询 SQLite
- **命令**：
  ```bash
  cd backend
  uv add pyjwt  # 用于后续可能的手动 token 验证
  # Python 自带 sqlite3，不需要额外安装
  ```
- **注意**：
  - Python 自带 `sqlite3` 库，**不需要额外安装**
  - 如果是在 Docker 容器内开发，依赖安装后要**重启 gateway 容器**才能生效：
    ```powershell
    $env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml restart gateway
    ```
- **记录文件**：`docs/user-management-system/day4/phase-4-1.md`

#### Phase 4.2 — 创建后端 Session 验证工具
- **做什么**：写一个 Python 工具函数，根据请求中的 Cookie 查询 better-auth 的 session 表
- **涉及文件**：
  - `backend/app/gateway/deps.py`（或新建 `backend/app/gateway/auth_deps.py`）
- **核心逻辑**：
  1. 从请求的 Cookie 中读取 `better-auth.session_token`
  2. 用 Python 的 `sqlite3` 连接 `/app/data/auth.db`（Docker 容器内共享路径）
  3. 查询 `session` 表，看 token 是否有效（未过期）
  4. 如果有效，查出对应的 `user` 信息返回
- **注意**：
  - 数据库路径是 **容器内路径** `/app/data/auth.db`，不是宿主机路径
  - 如果后端想在宿主机直接运行（非 Docker），可以从环境变量读取路径，如 `os.getenv("AUTH_DB_PATH", "./data/auth.db")`
- **记录文件**：`docs/user-management-system/day4/phase-4-2.md`

#### Phase 4.3 — 创建 FastAPI `get_current_user` 依赖
- **做什么**：封装成一个 FastAPI Dependency，方便其他路由直接注入使用
- **涉及文件**：
  - `backend/app/gateway/deps.py`
- **预期用法**：
  ```python
  from fastapi import Depends
  from .deps import get_current_user

  @router.get("/protected")
  def protected_route(user=Depends(get_current_user)):
      return {"message": f"Hello {user.email}"}
  ```
- **要求**：未登录时返回 `401 Unauthorized`
- **记录文件**：`docs/user-management-system/day4/phase-4-3.md`

#### Phase 4.4 — 切换 nginx 到 Gateway 模式（对话隔离前置）
- **做什么**：修改环境变量，让前端 `LangGraphClient` 的所有请求都经过 FastAPI gateway，而不是直接访问 LangGraph Server。这样 gateway 才能对所有对话 API 做用户鉴权。
- **涉及文件**：
  - 项目根目录 `.env`
- **修改内容**：
  ```env
  LANGGRAPH_UPSTREAM=gateway:8001
  LANGGRAPH_REWRITE=/api/
  ```
- **原理**：
  - `nginx.conf` 中 `/api/langgraph/` Location 会把请求 rewrite 后转发到 `langgraph` upstream。
  - 默认 `LANGGRAPH_UPSTREAM=langgraph:2024`（标准模式），请求直达 LangGraph Server。
  - 改为 `gateway:8001` 且 `LANGGRAPH_REWRITE=/api/` 后：
    - `/api/langgraph/threads/search` → rewrite 为 `/api/threads/search` → gateway
    - `/api/langgraph/threads/{id}/runs/stream` → rewrite 为 `/api/threads/{id}/runs/stream` → gateway
    - `/api/langgraph/assistants/search` → rewrite 为 `/api/assistants/search` → gateway
  - 前端代码**完全不需要修改**，`useStream`、对话列表、assistant 初始化等继续正常工作。
- **验证**：
  1. 修改 `.env` 后重启容器：`$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d`
  2. 登录后打开 `/workspace`，能正常发送消息、看到对话列表
  3. 浏览器 DevTools 中确认 `/api/langgraph/threads/search` 的响应来自 gateway（可观察返回数据结构或 gateway 日志）
- **⚠️ 已知问题提醒**：
  1. Gateway 模式目前标记为 **experimental**。社区 issues #1513（dev watcher 因 sandbox 文件变化无限重启）、#1516/#1837（nginx DNS 缓存策略调整）都与 gateway 模式相关。切换后如遇 502，优先检查 nginx 日志确认 upstream IP 是否正确。
  2. 如果切换到 gateway mode 后发现某些 LangGraph Platform 特有端点返回 404，说明 gateway 尚未实现该 stub，请在对应 router 中补充最小实现，或临时切回标准模式排查。
- **记录文件**：`docs/user-management-system/day4/phase-4-4.md`

#### Phase 4.5 — 创建对话时自动关联当前用户
- **做什么**：在用户创建新对话（无论是通过 `POST /threads` 还是通过 `start_run` 自动创建）时，将当前用户的 `user_id` 写入对话的 metadata 中。
- **涉及文件**：
  - `backend/app/gateway/routers/threads.py` —— `create_thread` 端点
  - `backend/app/gateway/services.py` —— `_upsert_thread_in_store` 函数
- **核心修改**：
  1. `create_thread` 中，在写入 Store 和 Checkpointer 的 metadata 时，加入 `user_id: current_user.id`
  2. `_upsert_thread_in_store` 中，同样在 metadata 中加入 `user_id`
- **注意**：
  - `thread_runs.py` 和 `runs.py` 在启动 run 时也会调用 `_upsert_thread_in_store`，因此这些路径会自动带上 `user_id`。
  - **不要将 `user_id` 放在 `config.context` 中传递**。upstream P1 issue #2509 已确认 `config.context` 当前被 lead agent factory 忽略，metadata 是唯一可靠的存储位置。
  - **规避已知 bug #2594**：社区已确认 `threads.py` 中使用 `time.time()` 生成的时间戳返回 Unix 格式而非 ISO 格式。你在修改 `create_thread`、`patch_thread` 等端点时，建议直接使用 `datetime.now(UTC).isoformat()` 生成 `created_at`/`updated_at`，避免引入同样的 bug。
- **验证**：登录后发送一条新消息（创建新对话），然后在后端检查 Store / Checkpointer 中的该对话 metadata，确认包含 `user_id` 字段。
- **记录文件**：`docs/user-management-system/day4/phase-4-5.md`

#### Phase 4.6 — 对话搜索列表隔离
- **做什么**：修改 `/threads/search`，让已登录用户只能看到属于自己的对话；未登录返回 401。
- **涉及文件**：
  - `backend/app/gateway/routers/threads.py` —— `search_threads` 端点
- **核心逻辑**：
  1. 端点注入 `get_current_user`，未登录返回 401
  2. 从 Store 和 Checkpointer 查询到全部对话后，增加过滤：
     ```python
     # 只保留：属于当前用户 或 没有 user_id 的老数据
     if user:
         results = [r for r in results if r.metadata.get("user_id") in (user.id, None)]
     ```
  3. 返回过滤后的列表
- **兼容策略**：没有 `user_id` 的历史对话对所有人可见，避免升级后数据丢失。
- **验证**：
  1. 用户 A 创建几个对话
  2. 用户 B 登录后调用 `/threads/search`，**看不到** A 的对话
  3. 未登录调用 `/threads/search`，返回 401
- **记录文件**：`docs/user-management-system/day4/phase-4-6.md`

#### Phase 4.7 — 单对话操作权限检查
- **做什么**：对单个对话的读取、修改、删除、状态查询等操作增加所有权检查，防止用户 A 通过猜测 `thread_id` 访问用户 B 的对话。
- **涉及文件**：
  - `backend/app/gateway/routers/threads.py`
- **需要加锁的端点**：
  - `GET /threads/{thread_id}` —— 获取对话详情
  - `PATCH /threads/{thread_id}` —— 修改对话 metadata
  - `DELETE /threads/{thread_id}` —— 删除对话
  - `GET /threads/{thread_id}/state` —— 获取对话状态
  - `POST /threads/{thread_id}/state` —— 更新对话状态
  - `POST /threads/{thread_id}/history` —— 获取对话历史
- **权限检查逻辑**：
  1. 注入 `get_current_user`，未登录返回 401
  2. 读取目标对话的 `metadata.user_id`
  3. 如果 `user_id` 为空（老数据）或等于当前用户 id，允许操作
  4. 否则返回 `403 Forbidden`
- **注意**：修改 `patch_thread` 时如果涉及更新 `updated_at` 字段，同样使用 `datetime.now(UTC).isoformat()` 规避 #2594 时间戳 bug。
- **验证**：
  1. 用户 A 创建对话，记录 `thread_id`
  2. 用户 B 尝试 `GET /threads/{thread_id}`，返回 403
  3. 用户 A 自己访问，正常返回
- **记录文件**：`docs/user-management-system/day4/phase-4-7.md`

#### Phase 4.8 — Runs 端点也增加对话权限检查
- **做什么**：`thread_runs.py` 和 `runs.py` 中的 stream、wait、cancel 等端点在操作具体对话前，也要检查用户是否有权访问该对话，防止通过 runs API 绕过 threads 的权限控制。
- **涉及文件**：
  - `backend/app/gateway/routers/thread_runs.py`
  - `backend/app/gateway/routers/runs.py`
- **核心修改**：
  1. 在 `thread_runs.py` 的 `create_run`、`stream_run`、`wait_run` 等端点中，注入 `get_current_user` 并检查 `thread_id` 的访问权限。
  2. 在 `runs.py` 的 `stateless_stream`、`stateless_wait` 中，如果请求体带了 `config.configurable.thread_id`（复用已有对话），同样检查权限。
  3. 可以将权限检查逻辑抽取为公共函数 `_require_thread_access(thread_id, user)`，放在 `threads.py` 中供其他模块导入复用。
- **验证**：
  1. 用户 B 尝试向用户 A 的 `thread_id` 发送消息（`POST /threads/{id}/runs/stream`），返回 403
  2. 用户 A 自己发送，正常流式返回
- **记录文件**：`docs/user-management-system/day4/phase-4-8.md`

#### Phase 4.9 — 为测试 API 添加认证并验证
- **做什么**：选一个现有的测试接口（如 `/api/memory` 或自己新建 `/api/me`），加上认证保护，并验证对话隔离已生效
- **涉及文件**：
  - 选一个 `backend/app/gateway/routers/` 下的路由文件
- **验证清单**：
  1. 未登录时用浏览器/Postman 访问 `/api/threads/search`，返回 401
  2. 登录后携带 Cookie 访问 `/api/threads/search`，能正常返回当前用户的对话列表
  3. 用户 A 创建对话后，用户 B 无法通过 `/threads/{id}` 或 `/threads/{id}/runs/stream` 访问
  4. 老数据（Day2 之前创建的对话）仍然可以被已登录用户看到
- **记录文件**：`docs/user-management-system/day4/phase-4-9.md`

---

### 📅 Day 5：用户资料管理
> **今日目标**：用户能查看和修改自己的个人资料

#### Phase 5.1 — 扩展 better-auth 用户表字段
- **做什么**：在 better-auth 配置中给 `user` 表增加 `nickname` 和 `avatar` 字段
- **涉及文件**：
  - `frontend/src/server/better-auth/config.ts`
- **配置示例**：
  ```ts
  export const auth = betterAuth({
    // ... database 等配置
    user: {
      additionalFields: {
        nickname: { type: "string", required: false, defaultValue: "" },
        avatar: { type: "string", required: false, defaultValue: "" },
        role: { type: "string", required: false, defaultValue: "user", input: false },
      },
    },
  });
  ```
- **验证**：重新运行迁移命令（同样推荐在容器内执行），数据库 `user` 表出现新字段：
  ```bash
  docker exec -it deer-flow-frontend sh -c "cd /app/frontend && npx @better-auth/cli migrate --config src/server/better-auth/config.ts"
  ```
- **记录文件**：`docs/user-management-system/day5/phase-5-1.md`

#### Phase 5.2 — 创建个人资料页面 `/profile`
- **做什么**：新建页面，展示当前用户的邮箱、昵称、头像
- **涉及文件**：
  - `frontend/src/app/profile/page.tsx`
- **要求**：页面为服务端组件或客户端组件均可，获取当前 session 信息展示
- **验证**：访问 `/profile` 能看到自己的注册邮箱
- **记录文件**：`docs/user-management-system/day5/phase-5-2.md`

#### Phase 5.3 — 实现资料修改功能
- **做什么**：在资料页添加编辑表单，允许修改昵称（头像先用文字占位，不上传文件）
- **涉及文件**：
  - `frontend/src/app/profile/page.tsx`
- **要求**：调用 better-auth 的 `authClient.updateUser()` 更新信息
- **验证**：修改昵称后刷新页面，新昵称生效
- **记录文件**：`docs/user-management-system/day5/phase-5-3.md`

#### Phase 5.4 — 更新导航栏入口
- **做什么**：在 Day 3 做的用户状态区域，增加"个人资料"链接
- **涉及文件**：
  - 导航栏组件（同 Day 3）
- **要求**：点击头像/用户名下拉菜单中有"个人资料"选项，点击进入 `/profile`
- **记录文件**：`docs/user-management-system/day5/phase-5-4.md`

#### Phase 5.5 — 在资料页显示用户对话数（可选）
- **做什么**：在 `/profile` 页面增加当前用户拥有的对话数量展示，增强个人中心的信息丰富度
- **涉及文件**：
  - `frontend/src/app/profile/page.tsx`
  - `backend/app/gateway/routers/threads.py`（可在 `search_threads` 基础上新增 `/api/me/stats` 接口）
- **要求**：
  - 后端提供一个接口返回当前用户的对话统计（如对话总数）
  - 前端资料页调用该接口展示数字
- **注意**：此 Phase 为可选，如果时间紧张可以跳过，不影响核心功能。
- **记录文件**：`docs/user-management-system/day5/phase-5-5.md`

---

### 📅 Day 6：角色与权限（简化版）
> **今日目标**：区分管理员和普通用户，管理员能看到所有人

#### Phase 6.1 — 确认角色字段已添加
- **做什么**：检查 Day 5 是否已在 `additionalFields` 中加入 `role`，如果没有补上
- **涉及文件**：
  - `frontend/src/server/better-auth/config.ts`
- **要求**：`role` 默认值为 `"user"`，且 `input: false`（用户注册时不能自己选角色）
- **验证**：数据库中已有用户的 `role` 都是 `user`
- **记录文件**：`docs/user-management-system/day6/phase-6-1.md`

#### Phase 6.2 — 创建管理员鉴权依赖
- **做什么**：在后端新建一个 `require_admin` 依赖，只有 `role === "admin"` 才能通过
- **涉及文件**：
  - `backend/app/gateway/deps.py`
- **预期行为**：普通用户访问返回 `403 Forbidden`
- **记录文件**：`docs/user-management-system/day6/phase-6-2.md`

#### Phase 6.3 — 管理员可查看所有用户的对话
- **做什么**：在 Day4 做的对话隔离逻辑中，为管理员角色增加"特权"——管理员调用 `/threads/search` 或访问单个对话时，不受 `user_id` 过滤限制。
- **涉及文件**：
  - `backend/app/gateway/routers/threads.py`
  - `backend/app/gateway/routers/thread_runs.py`
- **核心修改**：
  1. 在 `search_threads` 的过滤逻辑中，判断当前用户 `role === "admin"` 时，跳过 `user_id` 过滤
  2. 在单对话权限检查函数中，同样对 admin 放行
  3. `thread_runs.py` 中 runs 的权限检查也对 admin 放行
- **验证**：
  1. 用普通账号访问 `/threads/search`，只能看到自己的对话
  2. 用 admin 账号访问 `/threads/search`，能看到系统中所有对话（包括其他用户的）
  3. admin 可以正常通过 `/threads/{id}/runs/stream` 与任意用户的对话交互
- **记录文件**：`docs/user-management-system/day6/phase-6-3.md`

#### Phase 6.4 — 创建用户管理页面 `/admin/users`
- **做什么**：只有管理员能访问的页面，列出所有注册用户
- **涉及文件**：
  - `frontend/src/app/admin/users/page.tsx`
- **要求**：
  - 页面加载时请求后端获取用户列表（需要一个后端接口 `/api/admin/users`）
  - 显示每个用户的邮箱、昵称、角色、注册时间
- **后端接口涉及文件**：
  - 新建或修改 `backend/app/gateway/routers/` 下的路由，使用 `require_admin` 保护
- **记录文件**：`docs/user-management-system/day6/phase-6-4.md`

#### Phase 6.5 — 前端路由守卫（可选但推荐）
- **做什么**：普通用户直接访问 `/admin/users` 时，前端也做一层拦截，重定向到首页
- **涉及文件**：
  - `frontend/src/app/admin/users/page.tsx`
- **要求**：判断当前用户 `role !== "admin"` 时，用 `router.push("/workspace")` 跳转
- **验证**：用普通账号访问 `/admin/users` 会被踢走
- **记录文件**：`docs/user-management-system/day6/phase-6-5.md`

---

### 📅 Day 7：测试、修复与总结
> **今日目标**：把所有功能串起来跑通，修 bug，写文档

#### Phase 7.1 — 全链路手动测试
- **做什么**：按下面清单逐一验证：
  1. 新用户注册 → 成功
  2. 注册后自动登录/手动登录 → 成功
  3. 登录后访问 `/profile` → 能看到资料
  4. 修改昵称 → 成功保存
  5. 访问后端受保护接口 → 未登录 401，已登录 200
  6. 登出 → 状态恢复未登录
  7. 管理员访问用户列表 → 正常；普通用户访问 → 被拦截
  8. **新增**：用户 A 创建对话 → 用户 B 搜索列表中看不到该对话 → 用户 B 直接访问 thread_id 返回 403
  9. **新增**：管理员能看到用户 A 的对话，并能正常发送消息
  10. **新增**：老数据（Day2 前创建的对话）在登录后仍然可见
  11. **新增**：metadata 字段完整性——创建对话后，确认 checkpointer 中的 metadata 除了 `user_id` 外，DeerFlow 原有的 metadata 字段（如 `assistant_id`、`created_at`、`updated_at` 等）没有被破坏或覆盖
- **记录文件**：`docs/user-management-system/day7/phase-7-1.md`（把测试结果写进去）

#### Phase 7.2 — 修复测试中发现的问题
- **做什么**：把 Phase 7.1 发现的 bug 逐个修复
- **要求**：每个 bug 的**现象、原因、修复方法**都记录到对应文件中
- **记录文件**：`docs/user-management-system/day7/phase-7-2.md`

#### Phase 7.3 — 编写对话隔离自动化测试
- **做什么**：为 Day4-Day6 的对话隔离逻辑编写后端单元测试，确保权限控制不会被后续代码改动意外破坏。
- **涉及文件**：
  - `backend/tests/test_thread_isolation.py`（新建）
- **测试用例建议**：
  1. `test_search_threads_isolated` —— 用户只能看到自己的对话
  2. `test_search_threads_shows_legacy` —— 无 `user_id` 的老数据对所有人可见
  3. `test_get_other_user_thread_forbidden` —— 访问他人对话返回 403
  4. `test_run_on_other_user_thread_forbidden` —— 向他人对话发送消息返回 403
  5. `test_admin_can_access_all_threads` —— admin 不受隔离限制
  6. `test_unauthenticated_search_returns_401` —— 未登录返回 401
- **记录文件**：`docs/user-management-system/day7/phase-7-3.md`

#### Phase 7.4 — 代码清理与格式化
- **做什么**：
  1. 删除开发过程中写的 `console.log`
  2. 运行 `pnpm lint`（前端）和 `ruff check`（后端）检查代码风格
  3. 确保没有引入未使用的 import
- **记录文件**：`docs/user-management-system/day7/phase-7-4.md`

#### Phase 7.5 — 编写最终总结文档
- **做什么**：写一份 `summary.md`，总结本次用户管理系统添加了哪些功能、涉及哪些文件、后续可扩展方向
- **后续可扩展方向建议**：
  1. **迁移到 upstream 官方认证**：DeerFlow `release/2.0-rc` 正在推进 `app/plugins/auth` 插件体系和 `actor_context` 请求级用户上下文。未来可将 better-auth 方案迁移到官方认证体系，届时 `get_current_user` 可以从 `actor_context` 直接读取，无需手动解析 cookie。
  2. **多副本部署支持**：配合 upstream RFC #2471（Multi-replica deployment），对话隔离的 metadata 方案天然支持多副本，因为 `user_id` 存储在共享的 checkpointer/store 中。
  3. **更细粒度的权限**：当前仅区分 `admin`/`user`，未来可扩展为基于 capabilities 的细粒度授权（与 upstream `authorization/` 模块对齐）。
- **记录文件**：`docs/user-management-system/day7/phase-7-5.md` 或 `docs/user-management-system/summary.md`

---

## 四、每日执行 checklist（每天开始前看一遍）

- [ ] 今天要做哪几个 Phase？先读一遍计划
- [ ] 当前代码是否已提交/保存？（避免丢失）
- [ ] 每个 Phase 做完后，在 `docs/user-management-system/dayX/phase-X-Y.md` 写记录
- [x] 当天的 Phase 全部完成后，在 `dayX/` 下打个勾 ✅

---

## 五、常见问题预判（FAQ）

**Q1：better-auth 迁移命令报错了怎么办？**  
A：先确认 `better-sqlite3` 是否安装成功（它依赖 C++ 编译，Windows 上可能需要 Visual Studio Build Tools）。如果装不上，可改用 `bun:sqlite` 或先跳过迁移，手动建表（详见 better-auth 官方文档"Core Schema"部分）。

**Q2：后端读前端的 SQLite 文件路径怎么写？**  
A：Docker 环境下统一使用容器内路径 `/app/data/auth.db`。因为 docker-compose 已经把宿主机的 `./data` 挂载到了两个容器的 `/app/data`。如果后端在宿主机直接运行，可以从环境变量读取，如 `./data/auth.db`。

**Q3：用户注册成功了但登录失败？**  
A：检查 `.env` 里的 `BETTER_AUTH_SECRET` 是否设置，且注册和登录用的是同一个 secret。如果改了 secret，旧 session 会失效。

**Q4：后端验证 Cookie 时找不到数据库？**  
A：
  - Docker 环境：确认两个 compose 文件都正确挂载了 `- ../data:/app/data`，且代码里写的是 `/app/data/auth.db`
  - 非 Docker 环境：确认 `./data/auth.db` 存在，且 FastAPI 进程有读取权限
  - 建议先用 `docker exec deer-flow-gateway ls -la /app/data/` 检查容器内是否能看到文件

**Q5（Docker 专有问题）：容器重启后用户数据还在吗？**  
A：在。因为 `data/auth.db` 是挂载在宿主机 `./data/` 目录下的，容器删除重建不会影响宿主机文件。只要不手动删除 `./data/` 文件夹，数据就一直在。

**Q6（Docker 专有问题）：前端修改了代码但页面没变化？**  
A：开发环境（docker-compose-dev.yaml）下，frontend 容器已挂载了 `../frontend/src:/app/frontend/src`，源码修改会自动热更新。如果修改了 better-auth 配置文件或其他未挂载的文件，需要重启容器：`$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml restart frontend`。

**Q7：upstream 官方认证架构会不会导致我们当前方案作废？**  
A：短期内（1-2 个月内）不会。`release/2.0-rc` 的 auth 插件尚未合并到 `main` 分支，当前代码基线中不存在 `app/plugins/auth` 目录和 `actor_context`。本方案是当前 main 分支唯一可行的实现。但当 upstream 正式发布后，建议评估迁移——核心对话隔离逻辑（metadata 过滤、权限检查）可以保留，只需替换用户身份获取方式。

---

## 六、文件总览（最终会产生/修改的文件清单）

### 新增文件
```
frontend/src/app/register/page.tsx
frontend/src/app/login/page.tsx
frontend/src/app/profile/page.tsx
frontend/src/app/admin/users/page.tsx
backend/app/gateway/auth_deps.py          # 如果决定新建而不是改 deps.py
backend/tests/test_thread_isolation.py    # 对话隔离自动化测试
data/auth.db                              # SQLite 数据库（自动生成，宿主机）
```

### 修改文件
```
frontend/src/server/better-auth/config.ts
frontend/.env
frontend/.env.example
backend/app/gateway/deps.py
backend/app/gateway/routers/threads.py    # 对话隔离过滤与权限检查
backend/app/gateway/routers/thread_runs.py # runs 端点权限检查
backend/app/gateway/routers/runs.py       # stateless runs 权限检查
backend/app/gateway/services.py           # _upsert_thread_in_store 写入 user_id
backend/app/gateway/routers/*.py          # 其他路由添加认证依赖
frontend/src/components/layout/xxx.tsx    # 导航栏（根据实际路径）
docker/docker-compose.yaml                # 新增 data volume 挂载
docker/docker-compose-dev.yaml            # 新增 data volume 挂载
```

---

**祝开发顺利！遇到问题随时在对应 Phase 的记录文件里写下现象，方便回头排查。**
