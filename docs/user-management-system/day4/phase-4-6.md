# Phase 4.6 — 对话搜索列表隔离

## 目标

修改 `/threads/search` 端点，让已登录用户只能看到属于自己的对话；未登录用户返回 401。

同时保持**向后兼容**：没有 `user_id` 的历史对话（Day 4 之前创建的对话）对所有人可见，避免升级后数据丢失。

## 涉及文件

- `backend/app/gateway/routers/threads.py`

## 实现内容

### 1. 注入 `get_current_user` 依赖

在 `search_threads` 函数签名中添加 `current_user` 依赖：

```python
@router.post("/search", response_model=list[ThreadResponse])
async def search_threads(
    body: ThreadSearchRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> list[ThreadResponse]:
```

未登录时 `get_current_user` 会自动抛出 `401 Unauthorized`（已在 Phase 4.3 中实现）。

### 2. 在搜索结果中过滤对话

在 Phase 3（Filter → sort → paginate）中加入 `user_id` 隔离过滤：

```python
    # -----------------------------------------------------------------------
    # Phase 3: Filter → sort → paginate
    # -----------------------------------------------------------------------
    results = list(merged.values())

    # 对话隔离：只保留属于当前用户或没有 user_id 的老数据
    results = [r for r in results if r.metadata.get("user_id") in (current_user["id"], None)]

    if body.metadata:
        results = [r for r in results if all(r.metadata.get(k) == v for k, v in body.metadata.items())]

    if body.status:
        results = [r for r in results if r.status == body.status]

    results.sort(key=lambda r: r.updated_at, reverse=True)
    return results[body.offset : body.offset + body.limit]
```

**过滤逻辑说明**：

- `r.metadata.get("user_id")` 获取对话的归属用户 ID
- `current_user["id"]` 是当前登录用户的 better-auth UUID
- `None` 表示老数据（Day 4 之前创建的对话没有 `user_id`）
- 使用 `in (current_user["id"], None)` 同时满足：**属于当前用户** 或 **没有 user_id 的老数据**

### 3. 兼容策略

| 对话类型 | 可见性 |
|----------|--------|
| Day 4 之后创建、带有 `user_id` 的对话 | 仅对对应的 `user_id` 可见 |
| Day 4 之前创建、没有 `user_id` 的老数据 | 对所有已登录用户可见 |
| Checkpointer lazy migration 写入 Store 的对话 | 如果原始 checkpoint metadata 中有 `user_id`，则保留该限制；如果没有，则对所有人可见 |

## 验证

### 验证 1：未登录调用 /threads/search → 401

```bash
curl -X POST http://localhost:2026/api/langgraph/threads/search \
  -H "Content-Type: application/json" \
  -d '{"metadata":{},"limit":100}'
```

**预期结果**：`401 Unauthorized`，响应体 `{"detail":"请先登录后再进行操作"}`

### 验证 2：用户 A 创建对话 → 用户 B 搜索列表中看不到

**步骤 1**：用户 A 登录后创建对话
```bash
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<用户A的token>" \
  -d '{"metadata":{}}'
```

**步骤 2**：用户 B 登录后搜索对话
```bash
curl -X POST http://localhost:2026/api/langgraph/threads/search \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<用户B的token>" \
  -d '{"metadata":{},"limit":100}'
```

**预期结果**：用户 B 的搜索结果中**不包含**用户 A 创建的对话。

### 验证 3：老数据（无 user_id）仍然可见

对于 Day 4 之前创建的对话（metadata 中没有 `user_id`），任何已登录用户调用 `/threads/search` 都应该能看到。

## 遇到的问题

无。
