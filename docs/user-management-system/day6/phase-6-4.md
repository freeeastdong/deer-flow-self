# Phase 6.4 — 创建用户管理页面 `/admin/users`

## 目标

只有管理员能访问的页面，列出所有注册用户。

## 涉及文件

- `backend/app/gateway/routers/admin.py`（新建）
- `backend/app/gateway/app.py`
- `frontend/src/app/admin/users/page.tsx`（新建）

## 实现内容

### 1. 后端：新建 `GET /api/admin/users`

新建 `backend/app/gateway/routers/admin.py`：

- 前缀 `/api/admin`
- 端点 `GET /users`，使用 `require_admin` 保护
- 直接查询 SQLite `auth.db` 的 `user` 表
- 返回字段：`id`, `name`, `email`, `nickname`, `role`, `createdAt`

```python
@router.get("/users")
async def list_users(
    request: Request,
    current_user: dict = Depends(require_admin),
) -> list[dict]:
    ...
```

在 `app.py` 中注册路由：

```python
from app.gateway.routers import admin
# ...
app.include_router(admin.router)
```

### 2. 前端：新建 `/admin/users` 页面

新建 `frontend/src/app/admin/users/page.tsx`：

- **客户端组件**
- **路由守卫**（提前实现 Phase 6.5）：非 admin 自动跳转到 `/workspace`
- 调用 `/api/admin/users` 获取用户列表
- 展示表格：用户（头像+名称）、邮箱、昵称、角色（徽章）、注册时间

角色展示：
- `admin` → 蓝色徽章 "管理员" + Shield 图标
- `user` → 灰色徽章 "普通用户" + User 图标

---

## 验证

### 验证 1：管理员能访问用户管理页

1. 确保当前用户 `role = "admin"`
2. 访问 `http://localhost:2026/admin/users`
3. **预期结果**：页面显示所有注册用户的列表表格

### 验证 2：普通用户被重定向

1. 用普通用户账号登录
2. 直接访问 `http://localhost:2026/admin/users`
3. **预期结果**：自动跳转到 `/workspace`

### 验证 3：后端接口受保护

```bash
# 普通用户访问
curl -X GET http://localhost:2026/api/admin/users \
  -H "Cookie: better-auth.session_token=<普通用户token>"
```

**预期结果**：`403 Forbidden`

```bash
# 管理员访问
curl -X GET http://localhost:2026/api/admin/users \
  -H "Cookie: better-auth.session_token=<admin用户token>"
```

**预期结果**：`200 OK`，返回用户列表 JSON

## 遇到的问题

无。
