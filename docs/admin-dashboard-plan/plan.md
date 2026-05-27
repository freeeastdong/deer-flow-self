# DeerFlow 管理员后台完善计划

## 1. 项目概述

**目标**：将 DeerFlow 当前简陋的"用户列表查看器"升级为具备完整 CRUD、权限控制、注册管理和统计看板的管理员后台。

**范围**：P0（禁用/启用 + 重置密码）→ P1（创建/编辑用户）→ P2（删除用户 + 级联清理）→ P3（注册开关 + 邀请码）→ P4（Dashboard 统计看板）

**当前状态**：
- 后端 `admin.py` 只有 `GET /api/admin/users` 一个只读接口
- `UserRow` 没有 `is_active` 字段，无法禁用用户
- 没有 `delete_user` 方法（Repository / Provider / Router 三层均缺失）
- 注册完全开放，无任何控制
- 前端 `/admin/users` 只有只读表格，使用 raw `fetch`（缺失 CSRF 保护）
- 数据库无外键约束，级联删除需在应用层实现
- Alembic 版本目录为空，schema 由 `Base.metadata.create_all()` 自动创建

---

## 2. 当前架构速查

### 2.1 后端关键文件

| 层级 | 文件 | 职责 |
|------|------|------|
| Router | `backend/app/gateway/routers/admin.py` | 管理 API（仅 list_users） |
| Router | `backend/app/gateway/routers/auth.py` | 登录/注册/初始化（注册无限制） |
| Provider | `backend/app/gateway/auth/local_provider.py` | 用户 CRUD（无 delete） |
| Repository | `backend/app/gateway/auth/repositories/sqlite.py` | SQLite CRUD（无 delete） |
| Interface | `backend/app/gateway/auth/repositories/base.py` | UserRepository 抽象类 |
| Model | `backend/packages/harness/deerflow/persistence/user/model.py` | UserRow ORM |
| Auth | `backend/app/gateway/auth_middleware.py` | 全局认证中间件（不检查 active 状态） |
| Deps | `backend/app/gateway/deps.py` | `get_current_user_from_request`（不检查 active） |
| Config | `backend/app/gateway/auth/config.py` | AuthConfig（无注册控制字段） |

### 2.2 前端关键文件

| 文件 | 职责 |
|------|------|
| `frontend/src/app/admin/layout.tsx` | SSR 权限守卫 |
| `frontend/src/app/admin/users/page.tsx` | 用户列表（raw fetch，无 CSRF） |
| `frontend/src/components/workspace/workspace-nav-menu.tsx` | 设置菜单中的"用户管理"入口 |
| `frontend/src/core/api/fetcher.ts` | CSRF-aware fetch 封装（admin 页面未使用） |
| `frontend/src/core/auth/AuthProvider.tsx` | 全局 auth context |

### 2.3 数据库表引用关系

```
users (id PK)
  └── threads_meta (user_id, nullable, 无 FK)
  └── runs (user_id, nullable, 无 FK)
  └── run_events (user_id, nullable, 无 FK)
  └── feedback (user_id, nullable, 无 FK)
```

> **注意**：所有 `user_id` 均为 nullable 且无外键约束。级联清理必须在应用层通过 SQLAlchemy `delete()` 执行。

---

## 3. P0 — 用户禁用/启用 + 重置密码

### 3.1 目标
- 管理员可以禁用/启用普通用户账号
- 管理员可以重置用户密码（生成随机密码并返回）
- 被禁用的用户无法登录（JWT 校验阶段拦截）

### 3.2 后端变更

#### 3.2.1 数据库 Schema — 新增 `is_active` 字段

**修改文件**：`backend/packages/harness/deerflow/persistence/user/model.py`

在 `UserRow` 中新增：
```python
is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

**Schema 迁移策略**（Alembic 为空，采用启动时自动检测）：
- 修改文件：`backend/packages/harness/deerflow/persistence/engine.py`
- 在 `Base.metadata.create_all()` 之后，检测 `users` 表是否存在 `is_active` 列
- 若不存在，执行 `ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1`
- 实现为 `_migrate_users_is_active()` 辅助函数

#### 3.2.2 Auth 中间件 — 拦截禁用用户

**修改文件**：`backend/app/gateway/deps.py`

在 `get_current_user_from_request` 中，JWT 校验通过后、返回 user 前，增加：
```python
if not user.is_active:
    raise HTTPException(status_code=403, detail="Account disabled")
```

**修改文件**：`backend/app/gateway/auth_middleware.py`

在 middleware 中同样检查 `user.is_active`，若被禁用返回 403。

#### 3.2.3 User Model — 新增 `is_active` 字段

**修改文件**：`backend/app/gateway/auth/models.py`

在 `User` Pydantic model 和 `UserResponse` 中新增 `is_active: bool = True`。

#### 3.2.4 Repository — 更新与查询支持

**修改文件**：`backend/app/gateway/auth/repositories/sqlite.py`

- `update_user`：映射 `is_active` 字段
- `list_all_users`：保持返回全部用户（admin 需要看到禁用状态）
- （可选）新增 `get_active_user_by_email` 用于非 admin 场景

**修改文件**：`backend/app/gateway/auth/repositories/base.py`

抽象接口同步更新。

#### 3.2.5 Admin Router — 新增两个接口

**修改文件**：`backend/app/gateway/routers/admin.py`

```python
@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    request: Request,
    body: dict,  # {"is_active": false}
    _: None = Depends(require_admin),
) -> dict

@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    request: Request,
    _: None = Depends(require_admin),
) -> dict  # {"password": "随机明文密码"}
```

- `reset-password`：调用 `LocalAuthProvider.get_user()` → 生成随机密码（`secrets.token_urlsafe(12)`）→ `hash_password()` → `update_user()` → `token_version += 1` → 返回明文密码
- 重置成功后，该用户所有现有 JWT 立即失效（因为 token_version 已变）

### 3.3 前端变更

**修改文件**：`frontend/src/app/admin/users/page.tsx`

- 将 raw `fetch` 替换为 `@/core/api/fetcher`（解决 CSRF 缺失问题）
- 表格增加"状态"列：显示"正常"/"已禁用" Badge
- 每行增加操作按钮组：
  - 「禁用/启用」Switch 切换按钮 → `PATCH /api/admin/users/{id}/status`
  - 「重置密码」按钮 → 弹窗显示新密码（一次性展示，要求复制）
- 重置密码弹窗：显示生成的随机密码，带复制按钮，5 秒后自动关闭

### 3.4 涉及文件清单

| 文件 | 变更类型 |
|------|---------|
| `backend/packages/harness/deerflow/persistence/user/model.py` | 新增 `is_active` 列 |
| `backend/packages/harness/deerflow/persistence/engine.py` | 启动时 schema 自动迁移 |
| `backend/app/gateway/auth/models.py` | 新增 `is_active` 字段 |
| `backend/app/gateway/auth_middleware.py` | 拦截禁用用户 |
| `backend/app/gateway/deps.py` | 拦截禁用用户 |
| `backend/app/gateway/auth/repositories/base.py` | 接口同步 |
| `backend/app/gateway/auth/repositories/sqlite.py` | 映射 `is_active` |
| `backend/app/gateway/routers/admin.py` | 新增 status + reset-password 接口 |
| `frontend/src/app/admin/users/page.tsx` | 操作按钮 + CSRF fetch |

---

## 4. P1 — 创建用户 + 修改角色

### 4.1 目标
- 管理员可以创建新用户（指定邮箱、密码、角色）
- 管理员可以修改现有用户的角色（普通用户 ↔ 管理员）
- 前端表单校验（邮箱格式、密码强度）

### 4.2 后端变更

**修改文件**：`backend/app/gateway/routers/admin.py`

```python
@router.post("/users")
async def create_user(
    request: Request,
    body: CreateUserBody,  # {email, password, system_role}
    _: None = Depends(require_admin),
) -> dict

@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: Request,
    body: dict,  # {"system_role": "admin" | "user"}
    _: None = Depends(require_admin),
) -> dict
```

- `create_user`：复用 `LocalAuthProvider.create_user()`，校验邮箱唯一性，密码最小 8 位
- `update_user_role`：至少保留一个 admin。若把最后一个 admin 降级为 user，返回 400 错误
- `update_user_role` 同步更新 `token_version`（可选，角色变更后强制重新登录）

### 4.3 前端变更

**修改文件**：`frontend/src/app/admin/users/page.tsx`

- 页面顶部增加「创建用户」按钮 → 打开 Dialog 弹窗
- Dialog 表单字段：邮箱（input）、密码（input，可生成随机密码）、角色（Select: admin/user）
- 表格"角色"列改为可编辑：点击后显示 Select 下拉，选择后自动保存（`PATCH /api/admin/users/{id}/role`）
- 操作列增加「编辑」按钮（可选，与行内编辑二选一）

### 4.4 涉及文件清单

| 文件 | 变更类型 |
|------|---------|
| `backend/app/gateway/routers/admin.py` | 新增 create_user + update_role |
| `frontend/src/app/admin/users/page.tsx` | 创建弹窗 + 角色编辑 |

---

## 5. P2 — 删除用户（级联清理）

### 5.1 目标
- 管理员可以删除用户账号
- 删除时级联清理该用户的所有数据（线程、运行、事件、反馈）
- 至少保留一个管理员，防止误删最后一个 admin
- 用户不能删除自己

### 5.2 后端变更

#### 5.2.1 Repository — 新增 delete_user

**修改文件**：`backend/app/gateway/auth/repositories/base.py`

抽象接口新增：
```python
async def delete_user(self, user_id: str) -> bool:
    """Delete user by ID. Return True if deleted, False if not found."""
```

**修改文件**：`backend/app/gateway/auth/repositories/sqlite.py`

实现 `delete_user`：
```python
async def delete_user(self, user_id: str) -> bool:
    async with self._sf() as session:
        row = await session.get(UserRow, user_id)
        if not row:
            return False
        await session.delete(row)
        await session.commit()
        return True
```

#### 5.2.2 Provider — 新增 delete_user（级联清理）

**修改文件**：`backend/app/gateway/auth/local_provider.py`

```python
async def delete_user(self, user_id: str) -> bool:
    # 1. 级联删除 threads_meta
    # 2. 级联删除 runs
    # 3. 级联删除 run_events
    # 4. 级联删除 feedback
    # 5. 删除 users 表记录
    # 6. 删除用户目录 backend/.deer-flow/users/{user_id}/
```

级联清理实现方式：
- 通过共享的 `AsyncSession` 执行多条 `delete()` 语句
- `ThreadMetaRow`、`RunRow`、`RunEventRow`、`FeedbackRow` 均有过滤 `user_id == target_id`
- 使用 SQLAlchemy 的 `session.execute(delete(Model).where(...))` 批量删除
- 最后调用 `shutil.rmtree()` 删除文件系统上的用户目录

#### 5.2.3 Admin Router — 新增删除接口

**修改文件**：`backend/app/gateway/routers/admin.py`

```python
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    _: None = Depends(require_admin),
) -> dict
```

校验逻辑：
1. `user_id == request.state.user.id` → 403（不能删除自己）
2. 目标用户是 admin，且 `count_admin_users() <= 1` → 400（不能删除最后一个 admin）
3. 调用 `LocalAuthProvider.delete_user(user_id)`
4. 返回 `{"deleted": true}`

### 5.3 前端变更

**修改文件**：`frontend/src/app/admin/users/page.tsx`

- 每行增加「删除」按钮（红色 Destructive variant）
- 点击后弹出确认 Dialog：
  - 标题："确认删除用户？"
  - 内容："此操作将永久删除用户 {email} 及其所有数据（对话线程、运行记录、文件）。无法撤销。"
  - 需要输入用户邮箱二次确认（防止误触）
- 删除成功后刷新列表

### 5.4 涉及文件清单

| 文件 | 变更类型 |
|------|---------|
| `backend/app/gateway/auth/repositories/base.py` | 新增 delete_user 抽象方法 |
| `backend/app/gateway/auth/repositories/sqlite.py` | 实现 delete_user |
| `backend/app/gateway/auth/local_provider.py` | 新增级联删除逻辑 |
| `backend/app/gateway/routers/admin.py` | 新增 DELETE 接口 |
| `frontend/src/app/admin/users/page.tsx` | 删除按钮 + 确认弹窗 |

---

## 6. P3 — 注册开关 + 邀请码

### 6.1 目标
- 管理员可以控制是否开放公开注册
- 关闭公开注册后，新用户只能通过邀请码注册
- 邀请码管理：生成、查看、删除

### 6.2 后端变更

#### 6.2.1 数据库 Schema — 新增 `invite_codes` 表

**修改文件**：`backend/packages/harness/deerflow/persistence/user/model.py`（或新建 `invite_code/model.py`）

新建 `InviteCodeRow`：
```python
class InviteCodeRow(Base):
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    max_uses: Mapped[int] = mapped_column(nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(nullable=False, default=0)
    used_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

#### 6.2.2 Auth Config — 新增注册控制字段

**修改文件**：`backend/app/gateway/auth/config.py`

```python
class AuthConfig(BaseModel):
    jwt_secret: str
    token_expiry_days: int = 7
    oauth_github_client_id: str | None = None
    oauth_github_client_secret: str | None = None
    # 新增
    allow_public_registration: bool = Field(default=True)
```

环境变量：`ALLOW_PUBLIC_REGISTRATION`（默认 true）

#### 6.2.3 注册接口 — 增加邀请码校验

**修改文件**：`backend/app/gateway/routers/auth.py`

修改 `POST /api/v1/auth/register`：
1. 读取 `AuthConfig.allow_public_registration`
2. 若关闭公开注册，请求体必须包含 `invite_code`
3. 校验邀请码：存在、is_active=True、used_count < max_uses
4. 注册成功后，更新 invite_codes 的 used_count、used_by、used_at
5. 若邀请码达到 max_uses，自动设置 is_active=False

#### 6.2.4 Admin Router — 系统设置 + 邀请码管理

**修改文件**：`backend/app/gateway/routers/admin.py`

新增接口：
```python
# 系统设置
@router.get("/settings")
async def get_settings(...) -> dict  # {allow_public_registration: bool}

@router.put("/settings")
async def update_settings(body: dict, ...) -> dict

# 邀请码
@router.get("/invite-codes")
async def list_invite_codes(...) -> list[dict]

@router.post("/invite-codes")
async def create_invite_code(body: dict, ...) -> dict  # 自动生成 code

@router.delete("/invite-codes/{code}")
async def delete_invite_code(code: str, ...) -> dict
```

### 6.3 前端变更

**新建文件**：`frontend/src/app/admin/settings/page.tsx`

- 系统设置 Tab：
  - 「允许公开注册」Switch 切换
  - 保存按钮
- 邀请码管理 Tab：
  - 表格：code、创建者、最大使用次数、已使用次数、状态
  - 「生成邀请码」按钮（弹窗选择 max_uses）
  - 「复制」按钮
  - 「删除」按钮

**修改文件**：`frontend/src/app/admin/layout.tsx`

在 admin layout 中增加侧边导航或 Tab 切换（用户管理 / 系统设置），或保持简单在页面内用 Tabs 组件。

**修改文件**：`frontend/src/components/workspace/workspace-nav-menu.tsx`

将"用户管理"改为"管理后台"，或增加"系统设置"入口。

### 6.4 涉及文件清单

| 文件 | 变更类型 |
|------|---------|
| `backend/packages/harness/deerflow/persistence/user/model.py` | 新增 InviteCodeRow（或新建文件） |
| `backend/app/gateway/auth/config.py` | 新增 `allow_public_registration` |
| `backend/app/gateway/routers/auth.py` | 注册接口增加邀请码校验 |
| `backend/app/gateway/routers/admin.py` | 新增 settings + invite-codes CRUD |
| `frontend/src/app/admin/settings/page.tsx` | 新建：系统设置 + 邀请码管理 |
| `frontend/src/app/admin/layout.tsx` | 增加导航/Tab |
| `frontend/src/components/workspace/workspace-nav-menu.tsx` | 调整入口文案 |

---

## 7. P4 — Dashboard 统计看板

### 7.1 目标
- 管理员首页展示系统概览数据
- 用户增长趋势折线图（近 7 天/30 天）
- 关键指标卡片：总用户数、今日新增、管理员数、总线程数、总运行次数

### 7.2 后端变更

**修改文件**：`backend/app/gateway/routers/admin.py`

新增接口：
```python
@router.get("/stats")
async def get_stats(request: Request, _: None = Depends(require_admin)) -> dict:
    # 返回：
    # {
    #   "total_users": int,
    #   "total_admins": int,
    #   "today_new_users": int,
    #   "total_threads": int,
    #   "total_runs": int,
    #   "daily_new_users": [{"date": "2026-05-01", "count": 3}, ...]  # 近 30 天
    # }
```

实现方式：
- `total_users` / `total_admins`：复用 `count_users()` / `count_admin_users()`
- `today_new_users`：`SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')`
- `total_threads` / `total_runs`：通过共享 session 查询 `ThreadMetaRow` / `RunRow`
- `daily_new_users`：按天聚合最近 30 天

### 7.3 前端变更

**新建文件**：`frontend/src/app/admin/dashboard/page.tsx`

页面结构：
- 顶部 4-5 个统计卡片（StatCard 组件）
- 中部折线图：近 30 天用户注册趋势
- 底部表格：最新注册用户（前 5 条）

UI 组件：
- 使用已有的 `Card`、`CardHeader`、`CardTitle`、`CardContent`
- 图表使用 recharts（若项目中未安装，可选轻量方案：纯 CSS 条形图或暂不安装 recharts）
- **推荐**：先不引入 recharts，用简单的 div 条形图（CSS flex + height percentage）实现趋势，保持依赖最小化

**修改文件**：`frontend/src/components/workspace/workspace-nav-menu.tsx`

- 管理员入口改为下拉分组：
  - 「Dashboard 概览」→ `/admin/dashboard`
  - 「用户管理」→ `/admin/users`
  - 「系统设置」→ `/admin/settings`

### 7.4 涉及文件清单

| 文件 | 变更类型 |
|------|---------|
| `backend/app/gateway/routers/admin.py` | 新增 `/stats` 接口 |
| `frontend/src/app/admin/dashboard/page.tsx` | 新建：统计看板 |
| `frontend/src/components/workspace/workspace-nav-menu.tsx` | 调整导航结构 |

---

## 8. 关键架构决策

### 8.1 Schema 迁移策略

**问题**：Alembic 版本目录为空，当前使用 `Base.metadata.create_all()` 自动建表。

**决策**：不引入 Alembic 迁移脚本，采用**启动时自动检测 + ALTER TABLE** 策略：
1. 在 `init_engine()` 中 `create_all()` 之后调用 `_run_schema_patches(conn)`
2. 使用 `inspector = inspect(engine)` 检查表列是否存在
3. 缺失列通过 `await conn.execute(text("ALTER TABLE ... ADD COLUMN ..."))` 补齐
4. 新建表由 `create_all()` 自动处理

**理由**：
- 项目当前处于开发阶段，生产部署少
- 避免引入 Alembic 运维复杂性
- 自动检测对已有数据零侵入

### 8.2 级联删除策略

**问题**：SQLite 无外键约束，用户数据分散在 4 张表 + 文件系统。

**决策**：应用层级联删除，顺序如下：
1. `DELETE FROM feedback WHERE user_id = ?`
2. `DELETE FROM run_events WHERE user_id = ?`
3. `DELETE FROM runs WHERE user_id = ?`
4. `DELETE FROM threads_meta WHERE user_id = ?`
5. `DELETE FROM users WHERE id = ?`
6. `shutil.rmtree(user_dir)` 删除 `backend/.deer-flow/users/{user_id}/`

**理由**：
- 数据库无外键，无法依赖 `ON DELETE CASCADE`
- 显式删除代码可读性高，调试方便
- 事务包裹全部操作，任一失败回滚

### 8.3 前端 API 调用统一

**问题**：当前 admin 页面使用 raw `fetch`，缺失 CSRF 保护。

**决策**：全部替换为 `@/core/api/fetcher` 中的 `fetch`：
- 自动注入 `X-CSRF-Token`
- 自动处理 401 跳转
- 统一错误处理

### 8.4 角色变更后的 JWT 处理

**问题**：管理员修改用户角色后，该用户当前登录态是否应失效？

**决策**：
- **修改角色**：不强制失效 JWT（用户体验好，风险可控）
- **重置密码**：必须 `token_version += 1`，强制所有现有 JWT 失效
- **禁用用户**：中间件拦截，JWT 本身不过期但请求被 403 拒绝

---

## 9. 前端路由结构

完成后 admin 区域的路由：

```
/admin/dashboard          # P4 统计看板（默认首页）
/admin/users              # P0+P1+P2 用户管理
/admin/settings           # P3 系统设置 + 邀请码
```

导航入口（workspace-nav-menu.tsx 下拉菜单）：
```
管理员
├── 📊 Dashboard 概览
├── 👥 用户管理
└── ⚙️ 系统设置
```

---

## 10. 实施顺序建议

| 阶段 | 任务 | 预估工时 | 前置依赖 |
|------|------|---------|---------|
| **Phase 1** | P0 Schema 变更（is_active + 启动时迁移） | 2h | 无 |
| **Phase 1** | P0 Auth 中间件拦截禁用用户 | 1h | Schema |
| **Phase 1** | P0 后端 status + reset-password 接口 | 2h | Schema |
| **Phase 1** | P0 前端禁用/启用 + 重置密码按钮 | 3h | 后端接口 |
| **Phase 2** | P1 后端 create_user + update_role | 2h | 无 |
| **Phase 2** | P1 前端创建弹窗 + 角色编辑 | 3h | 后端接口 |
| **Phase 3** | P2 后端 delete_user（级联清理） | 3h | 无 |
| **Phase 3** | P2 前端删除确认弹窗 | 2h | 后端接口 |
| **Phase 4** | P3 后端 invite_codes 表 + 注册控制 | 4h | 无 |
| **Phase 4** | P3 后端 settings + invite-codes CRUD | 3h | 表创建 |
| **Phase 4** | P3 前端系统设置 + 邀请码管理页 | 4h | 后端接口 |
| **Phase 5** | P4 后端 /stats 接口 | 2h | 无 |
| **Phase 5** | P4 前端 Dashboard 看板 | 4h | 后端接口 |

**总预估：约 35 小时（5 个工作日）**

---

## 11. 风险与注意事项

1. **数据安全**：`reset-password` 返回明文密码，必须确保通过 HTTPS 传输。本地开发环境使用 HTTP，生产环境务必启用 TLS。
2. **误删保护**：删除用户前要求输入邮箱二次确认，且禁止删除自己、禁止删除最后一个 admin。
3. **SQLite WAL 兼容性**：Windows Docker bind mount 下 WAL 模式可能不稳定（已出现过 DataGrip 锁定导致 gateway 崩溃的情况）。建议在开发时避免同时用外部工具打开 `.deer-flow/data/deerflow.db`。
4. **CSRF 一致性**：所有 admin 相关的 state-changing 请求必须使用 `@/core/api/fetcher`，否则会被后端 CSRFMiddleware 拒绝。
5. **并发安全**：`token_version` 递增和邀请码 used_count 递增均存在竞态条件。SQLite 的写锁会自动序列化，但代码中应避免 `read-modify-write` 模式，尽量使用数据库原子操作。
