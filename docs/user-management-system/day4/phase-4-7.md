# Phase 4.7 — 单对话操作权限检查

## 目标

对单个对话的读取、修改、删除、状态查询等操作增加所有权检查，防止用户 A 通过猜测 `thread_id` 访问用户 B 的对话。

## 涉及文件

- `backend/app/gateway/routers/threads.py`

## 实现内容

### 1. 新增 `_require_thread_access` 权限检查函数

在 `threads.py` 的 Helper 区域新增一个可复用的异步权限检查函数，供本模块及未来其他模块（如 `thread_runs.py`）调用：

```python
async def _require_thread_access(thread_id: str, user: dict, request: Request) -> dict:
    """Verify the current user has access to the specified thread.

    Checks the Store first, then falls back to the checkpointer metadata.
    Legacy threads (without ``user_id`` in metadata) are accessible to all
    authenticated users.
    """
    store = get_store(request)
    record = None
    if store is not None:
        record = await _store_get(store, thread_id)

    if record is None:
        checkpointer = getattr(request.app.state, "checkpointer", None)
        if checkpointer is not None:
            try:
                config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
                checkpoint_tuple = await checkpointer.aget_tuple(config)
                if checkpoint_tuple is not None:
                    ckpt_meta = getattr(checkpoint_tuple, "metadata", {}) or {}
                    record = {
                        "thread_id": thread_id,
                        "status": "idle",
                        "created_at": ckpt_meta.get("created_at", ""),
                        "updated_at": ckpt_meta.get("updated_at", ckpt_meta.get("created_at", "")),
                        "metadata": {k: v for k, v in ckpt_meta.items() if k not in ("created_at", "updated_at", "step", "source", "writes", "parents")},
                    }
            except Exception:
                logger.exception("Failed to get checkpoint for thread %s", thread_id)

    if record is None:
        return {}

    thread_user_id = record.get("metadata", {}).get("user_id")
    if thread_user_id is not None and thread_user_id != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限访问该对话",
        )

    return record
```

**设计要点**：

- **双源回退**：优先查 Store（快），Store 没有则查 Checkpointer（兼容老数据）
- **老数据兼容**：`user_id` 为 `None` 时放行，不破坏历史对话
- **返回值**：返回对话 record（或空 dict），方便调用方复用查询结果，减少重复 IO
- **异常分离**：找不到对话返回 `{}`（由调用方决定 404），权限不足直接抛 403

### 2. 为 6 个端点添加权限检查

| 端点 | 方法 | 修改内容 |
|------|------|---------|
| `DELETE /threads/{thread_id}` | `delete_thread_data` | 注入 `get_current_user`，调用 `_require_thread_access` |
| `PATCH /threads/{thread_id}` | `patch_thread` | 同上 |
| `GET /threads/{thread_id}` | `get_thread` | 同上，复用返回的 record 减少一次 Store 查询 |
| `GET /threads/{thread_id}/state` | `get_thread_state` | 同上 |
| `POST /threads/{thread_id}/state` | `update_thread_state` | 同上 |
| `POST /threads/{thread_id}/history` | `get_thread_history` | 同上 |

**修改示例**（以 `get_thread` 为例）：

```python
@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ThreadResponse:
    record = await _require_thread_access(thread_id, current_user, request)
    # ... 后续逻辑复用 record，减少重复查询
```

### 3. `patch_thread` 中的时间戳处理

`patch_thread` 在更新 `updated_at` 时继续使用 `datetime.now(UTC).isoformat()`（已在 Phase 4.5 中修复），符合计划要求规避 #2594 时间戳 bug。

## 验证

### 验证 1：用户 B 访问用户 A 的对话 → 403

```bash
curl -X GET http://localhost:2026/api/langgraph/threads/{用户A的thread_id} \
  -H "Cookie: better-auth.session_token=<用户B的token>"
```

**预期结果**：`403 Forbidden`，响应体 `{"detail":"您没有权限访问该对话"}`

### 验证 2：用户 A 访问自己的对话 → 200

```bash
curl -X GET http://localhost:2026/api/langgraph/threads/{用户A的thread_id} \
  -H "Cookie: better-auth.session_token=<用户A的token>"
```

**预期结果**：正常返回对话详情

### 验证 3：老数据（无 user_id）→ 任何登录用户可访问

对于 Day 4 之前创建的对话，metadata 中没有 `user_id`，已登录用户 A 和用户 B 都应该能正常访问。

### 验证 4：未登录 → 401

不带 Cookie 访问任意单对话端点：

```bash
curl -X GET http://localhost:2026/api/langgraph/threads/{thread_id}
```

**预期结果**：`401 Unauthorized`

## 遇到的问题

无。
