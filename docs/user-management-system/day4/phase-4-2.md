# Phase 4.2 — 创建后端 Session 验证工具

## 目标

编写独立的 Python 工具模块，用于从 FastAPI 请求中读取 better-auth session cookie，验证其有效性，并返回对应的用户信息。

## 涉及文件

- `backend/app/gateway/auth_deps.py`（新建）

## 实现内容

### 模块职责

`auth_deps.py` 是认证层的**纯工具模块**，不依赖 FastAPI 的 `Depends` 机制，只提供底层的 session 查询和验证能力。

### 核心函数

#### `get_auth_db_path() -> str`

返回 SQLite 数据库路径。优先从环境变量 `AUTH_DB_PATH` 读取，默认为 `/app/data/auth.db`（Docker 容器内共享路径）。

#### `verify_session_token(token: str) -> dict | None`

验证 session token 的核心函数：

1. **数据库查询**：JOIN `session` 和 `user` 表，通过 `s.token = ?` 匹配
2. **过期校验**：better-auth 存储 `expiresAt` 为 ISO-8601 格式（如 `"2026-05-04T11:43:53.083Z"`），用 `datetime.fromisoformat()` 解析并对比 UTC 当前时间
3. **返回用户信息**：`{id, name, email, image}` 或 `None`
4. **异常安全**：所有数据库/解析异常都被捕获，返回 `None` 而非抛错，避免认证层崩溃导致服务不可用

SQL 查询：
```sql
SELECT
    s.expiresAt AS session_expires,
    u.id        AS user_id,
    u.name      AS user_name,
    u.email     AS user_email,
    u.image     AS user_image
FROM session s
JOIN user u ON s.userId = u.id
WHERE s.token = ?
```

#### `get_session_user(request: Request) -> dict | None`

FastAPI 请求级别的便捷包装：

1. 从 `request.cookies` 读取 `better-auth.session_token`
2. 调用 `verify_session_token()` 验证
3. 返回用户信息或 `None`

### 关键设计决策

| 决策 | 说明 |
|------|------|
| **不直接返回 401** | 本层只负责"验证并返回结果"，不抛 HTTP 异常。401 统一由上层的 `get_current_user`（Phase 4.3）抛出 |
| **异常吞掉返回 None** | 数据库文件暂时不可读、格式异常等情况都返回 `None`，让上层决定如何响应（如 401 或降级处理） |
| **环境变量覆盖路径** | 支持非 Docker 开发环境（宿主机直接运行）通过 `AUTH_DB_PATH` 指定本地路径 |

## 验证

1. 文件存在且路径正确：`backend/app/gateway/auth_deps.py` ✅
2. Python 语法检查通过 ✅
3. 数据库查询逻辑在后续 Phase 4.3–4.9 的实际请求中验证

## 遇到的问题

无。
