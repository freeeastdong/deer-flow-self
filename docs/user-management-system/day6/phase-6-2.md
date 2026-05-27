# Phase 6.2 — 创建管理员鉴权依赖

## 目标

在后端新建一个 `require_admin` 依赖，只有 `role === "admin"` 才能通过。

## 涉及文件

- `backend/app/gateway/auth_deps.py`
- `backend/app/gateway/deps.py`

## 实现内容

### 1. 修复 `auth_deps.py` — Session 查询未返回 `role`

**发现的问题**：`verify_session_token` 函数的 SQL 只查询了 `u.id, u.name, u.email, u.image`，**没有查 `u.role`**。这意味着即使数据库里有 `role` 字段，`get_session_user()` 返回的 user dict 中也没有 `role`，`get_current_user` 里的 `user.setdefault("role", "user")` 会永远设置默认 `"user"`，管理员永远过不了检查。

**修复**：在 SQL SELECT 中加入 `u.role`，并在返回 dict 中加入 `"role"`。

```python
cursor.execute(
    """
    SELECT
        s.expiresAt AS session_expires,
        u.id        AS user_id,
        u.name      AS user_name,
        u.email     AS user_email,
        u.image     AS user_image,
        u.role      AS user_role        -- 新增
    FROM session s
    JOIN user u ON s.userId = u.id
    WHERE s.token = ?
    """,
    (token,),
)

# ...

return {
    "id": row["user_id"],
    "name": row["user_name"],
    "email": row["user_email"],
    "image": row["user_image"],
    "role": row["user_role"],        # 新增
}
```

### 2. 新增 `require_admin` 依赖

在 `deps.py` 中新增 `require_admin` 函数（放在 `get_current_user` 上方）：

```python
def require_admin(request: Request) -> dict:
    """Validate the request is from an admin user."""
    user = get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有管理员权限",
        )
    return user
```

**设计要点**：
- 先复用 `get_current_user` 做认证（未登录 → 401）
- 再检查 `role`（非 admin → 403）
- 返回 user dict，方便后续路由使用

---

## 验证

### 验证 1：普通用户访问受保护的端点 → 403

用一个没有 `admin` 角色的用户 Cookie 测试：

```bash
curl -X GET http://localhost:2026/api/some-admin-endpoint \
  -H "Cookie: better-auth.session_token=<普通用户的token>"
```

**预期结果**：`403 Forbidden`，响应体 `{"detail":"您没有管理员权限"}`

### 验证 2：未登录访问 → 401

不带 Cookie 访问：

```bash
curl -X GET http://localhost:2026/api/some-admin-endpoint
```

**预期结果**：`401 Unauthorized`

### 验证 3：数据库中手动设置一个 admin，验证能通过

在数据库中把某个用户的 `role` 改成 `"admin"`：

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/auth.db')
conn.execute(\"UPDATE user SET role = 'admin' WHERE email = '你的邮箱'\")
conn.commit()
conn.close()
"
```

然后用该用户的 Cookie 访问受保护端点，预期 `200 OK`。

---

## 遇到的问题

`verify_session_token` 原来没有查询 `role` 字段，导致 `get_current_user` 永远 fallback 到 `"user"`。这个 bug 如果不修复，即使数据库里 `role = 'admin'`，后端也识别不出来。
