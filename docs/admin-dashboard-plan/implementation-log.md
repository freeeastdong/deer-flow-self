# DeerFlow 管理员后台完善 — 实施记录

## 1. 实施概览

| 项目 | 内容 |
|------|------|
| **目标** | 将 DeerFlow 的只读用户列表升级为完整的管理员后台 |
| **范围** | P0-P4 全部功能 |
| **总修改文件数** | 18 个后端文件 + 4 个前端文件 = 22 个 |
| **实施日期** | 2026-05-06 |

---

## 2. 后端修改清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/packages/harness/deerflow/persistence/user/model.py` | 修改 | UserRow 新增 is_active 字段 |
| `backend/packages/harness/deerflow/persistence/engine.py` | 修改 | 启动时自动检测并 ALTER TABLE 添加缺失列 |
| `backend/packages/harness/deerflow/persistence/models/__init__.py` | 修改 | 导入 InviteCodeRow |
| `backend/packages/harness/deerflow/persistence/invite_code/model.py` | 新建 | InviteCodeRow ORM 模型 |
| `backend/app/gateway/auth/models.py` | 修改 | User / UserResponse 新增 is_active |
| `backend/app/gateway/auth/errors.py` | 修改 | 新增 FORBIDDEN 错误码 |
| `backend/app/gateway/auth/repositories/base.py` | 修改 | 新增 delete_user 抽象方法 |
| `backend/app/gateway/auth/repositories/sqlite.py` | 修改 | 映射 is_active，实现 delete_user |
| `backend/app/gateway/auth/local_provider.py` | 修改 | 新增 delete_user（级联删除 DB + 文件系统） |
| `backend/app/gateway/auth/config.py` | 修改 | 新增 allow_public_registration 配置 |
| `backend/app/gateway/auth_middleware.py` | 修改 | 拦截禁用用户（返回 403） |
| `backend/app/gateway/deps.py` | 修改 | get_current_user_from_request 拦截禁用用户；get_local_provider 传 session_factory |
| `backend/app/gateway/routers/admin.py` | 重写 | 从 1 个接口扩展到 10 个接口 |
| `backend/app/gateway/routers/auth.py` | 修改 | register 接口增加邀请码校验和注册开关控制 |

---

## 3. 前端修改清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `frontend/src/app/admin/users/page.tsx` | 重写 | 从只读表格升级为完整 CRUD |
| `frontend/src/app/admin/settings/page.tsx` | 新建 | 注册开关 + 邀请码管理 |
| `frontend/src/app/admin/dashboard/page.tsx` | 新建 | 统计卡片 + 30 天注册趋势条形图 |
| `frontend/src/components/workspace/workspace-nav-menu.tsx` | 修改 | 管理员入口拆分为 Dashboard / 用户管理 / 系统设置 |

---

## 4. 遇到的问题及解决方案

### 4.1 SQLite 数据库被 DataGrip 锁定

**现象**：重启容器后 gateway 无法启动，nginx 返回 504。日志显示 `sqlite3.OperationalError: disk I/O error`。

**根因**：DataGrip 直接打开了 deerflow.db，SQLite WAL 文件锁与 Docker 容器冲突。

**解决**：断开 DataGrip 连接后恢复正常。

---

### 4.2 gateway 日志输出到文件而非 stdout

**现象**：`docker logs` 为空，无法排查问题。

**根因**：容器启动命令将输出重定向到 `/app/logs/gateway.log`。

**解决**：直接读取日志文件。

---

### 4.3 前端缺少 Label 组件

**现象**：编译时找不到 `@/components/ui/label`。

**解决**：移除 Label 导入，改用原生 label 标签。

---

### 4.4 PowerShell 命令兼容性问题

**现象**：curl、|| 管道、dir 路径等命令在 PowerShell 5.1 下频繁失败。

**解决**：改用 Invoke-WebRequest 和分步执行。

---

### 4.5 Next.js Turbopack 文件变更检测延迟

**现象**：修改 page.tsx 后前端没有自动重新编译。

**解决**：touch 文件手动触发，或直接重启容器。

---

### 4.6 级联删除需要跨表操作

**现象**：LocalAuthProvider 只有 UserRepository，无法删除其他表的数据。

**解决**：修改构造函数接收可选的 session_factory，在 delete_user 中执行级联删除。

---

### 4.7 AuthErrorCode 缺少 FORBIDDEN

**现象**：middleware 中引用了不存在的错误码。

**解决**：在 errors.py 中新增 FORBIDDEN。

---

### 4.8 auth.py 缺少 datetime 导入

**现象**：register 函数使用了 datetime.now(UTC) 但未导入。

**解决**：添加 from datetime import UTC, datetime。

---

## 5. 关键架构决策

- **Schema 迁移**：不使用 Alembic，采用启动时自动检测 + ALTER TABLE
- **级联删除**：应用层逐表删除（feedback -> run_events -> runs -> threads_meta -> users -> 文件系统）
- **图表实现**：纯 CSS 条形图，不引入 recharts
- **重置密码**：返回明文（本地环境），生产环境务必启用 HTTPS

---

## 6. 测试验证结果

| 测试项 | 结果 |
|--------|------|
| Gateway 启动 | 通过 |
| Frontend 启动 | 通过 |
| /api/v1/auth/setup-status | 200 正常 |
| /api/admin/stats（无认证） | 401 正常 |
| /api/admin/users（无认证） | 401 正常 |
| 所有前端页面编译 | 无错误 |
