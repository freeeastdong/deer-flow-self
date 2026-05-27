# Phase 4.3 — 创建 FastAPI `get_current_user` 依赖

## 目标

将 Phase 4.2 的 Session 验证工具封装成 FastAPI Dependency，让任意路由只需一行 `Depends(get_current_user)` 即可获得当前登录用户，未登录时自动返回 401。

## 涉及文件

- `backend/app/gateway/deps.py`

## 实现内容

### 1. 导入 `get_session_user`

在 `deps.py` 顶部新增从 `auth_deps.py` 的导入：

```python
from fastapi import FastAPI, HTTPException, Request, status
from .auth_deps import get_session_user
```

### 2. 新增 `get_current_user` 依赖函数

```python
def get_current_user(request: Request) -> dict:
    """Validate the incoming request's session and return the authenticated user.

    This is the primary FastAPI dependency used by routers to enforce
    authentication.  It reads the ``better-auth.session_token`` cookie,
    looks up the shared SQLite database, and returns the user dict.

    If the session is missing, expired, or invalid a **401 Unauthorized**
    response is raised immediately.
    """
    user = get_session_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    # Compatibility: the ``role`` column is added later (Day 5) via
    # better-auth ``additionalFields``.  Default to "user" so that
    # Day 6 admin checks work even before the migration runs.
    user.setdefault("role", "user")
    return user
```

### 设计要点

| 要点 | 说明 |
|------|------|
| **复用已有逻辑** | 直接调用 Phase 4.2 的 `get_session_user(request)`，不重复写 cookie 解析和数据库查询 |
| **401 统一返回** | 未登录、cookie 缺失、session 过期都统一返回 `401 Unauthorized` |
| **role 兼容性** | 使用 `user.setdefault("role", "user")`——如果数据库已有 `role` 字段（Day 5 添加后）则保留原值，否则默认 `"user"`，确保 Day 6 的 admin 检查提前可用 |
| **可替换接口** | 函数签名和返回类型（`dict`）保持稳定。未来 upstream 发布 `actor_context` 后，只需替换此函数内部实现，所有路由的 `Depends(get_current_user)` 无需改动 |

### 使用示例

任意 router 中注入：

```python
from fastapi import Depends
from app.gateway.deps import get_current_user

@router.get("/protected")
def protected_route(user: dict = Depends(get_current_user)):
    return {"message": f"Hello {user['email']}"}
```

## 验证

1. 语法检查通过：
   ```bash
   cd backend && python -c "import py_compile; py_compile.compile('app/gateway/deps.py', doraise=True)"
   # 输出：Syntax OK
   ```

2. 后续 Phase 4.4–4.9 的实际路由集成将验证 `Depends(get_current_user)` 在真实请求中的行为。

## 遇到的问题

无。
