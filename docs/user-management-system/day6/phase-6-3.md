# Phase 6.3 — 管理员可查看所有用户的对话

## 目标

为管理员角色增加"特权"——管理员调用 `/threads/search` 或访问单个对话时，不受 `user_id` 过滤限制。

## 涉及文件

- `backend/app/gateway/routers/threads.py`

## 实现内容

### 1. `_require_thread_access` 对 admin 放行

在权限检查的最后一步，如果用户是 `admin`，跳过 403 拦截：

```python
thread_user_id = record.get("metadata", {}).get("user_id")
if thread_user_id is not None and thread_user_id != user["id"]:
    # Admin bypass: administrators can access any thread
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限访问该对话",
        )
```

> 这个函数被 `threads.py` 和 `thread_runs.py` 共用，所以修改一处，Runs 端点也会自动对 admin 放行。

### 2. `search_threads` 对 admin 跳过 `user_id` 过滤

在结果过滤阶段，如果当前用户是 `admin`，不执行 `user_id` 筛选：

```python
# 对话隔离：只保留属于当前用户或没有 user_id 的老数据
# Admin bypass: administrators can see all threads
if current_user.get("role") != "admin":
    results = [r for r in results if r.metadata.get("user_id") in (current_user["id"], None)]
```

**影响范围**：
- `/threads/search` — 管理员能看到系统中所有对话
- `/threads/{id}` — 管理员能访问任意单个对话
- `/threads/{id}/state` — 管理员能查看任意对话状态
- `/threads/{id}/runs/*` — 管理员能向任意对话发送消息（通过 `_require_thread_access` 复用）
- `/threads/stats` — 管理员能看到所有对话的统计（复用 `search_threads`）

---

## 验证

### 验证 1：普通用户只能看到自己的对话

```bash
curl -X POST http://localhost:2026/api/langgraph/threads/search \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<普通用户token>" \
  -d '{"limit": 10}'
```

**预期结果**：只返回该用户自己创建的对话。

### 验证 2：管理员能看到所有对话

先把某个用户的 `role` 改成 `"admin"`（如果还没改）：

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/auth.db')
conn.execute(\"UPDATE user SET role = 'admin' WHERE email = '你的邮箱'\")
conn.commit()
conn.close()
"
```

然后用该用户的 Cookie 访问：

```bash
curl -X POST http://localhost:2026/api/langgraph/threads/search \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<admin用户token>" \
  -d '{"limit": 10}'
```

**预期结果**：返回系统中所有用户的对话（包括其他用户的）。

### 验证 3：管理员能访问其他用户的单个对话

```bash
curl -X GET http://localhost:2026/api/langgraph/threads/{其他用户的thread_id} \
  -H "Cookie: better-auth.session_token=<admin用户token>"
```

**预期结果**：`200 OK`，正常返回对话详情（普通用户会收到 403）。

### 验证 4：管理员能向其他用户的对话发送消息

```bash
curl -X POST http://localhost:2026/api/langgraph/threads/{其他用户的thread_id}/runs/stream \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<admin用户token>" \
  -d '{"assistant_id":"lead_agent","input":{"messages":[]}}'
```

**预期结果**：正常返回 SSE 流（普通用户会收到 403）。

## 遇到的问题

无。
