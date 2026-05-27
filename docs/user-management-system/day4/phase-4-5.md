# Phase 4.5 — 创建对话时自动关联当前用户

## 目标

在用户创建新对话时（无论是通过 `POST /threads` 还是通过 `start_run` 自动创建），将当前用户的 `user_id` 写入对话的 Store 和 Checkpointer metadata 中。

## 涉及文件

- `backend/app/gateway/routers/threads.py`
- `backend/app/gateway/services.py`

## 实现内容

### 1. `threads.py` — `create_thread` 端点

**注入 `get_current_user` 依赖：**

```python
async def create_thread(
    body: ThreadCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ThreadResponse:
```

**在 metadata 中注入 `user_id`：**

```python
metadata = dict(body.metadata) if body.metadata else {}
metadata["user_id"] = current_user["id"]
```

- 使用 `dict(body.metadata)` 创建副本，避免修改传入的 Pydantic 模型
- `user_id` 使用 better-auth 用户表的 `id` 字段（UUID 字符串）

**Store 写入：**

```python
await _store_put(
    store,
    {
        "thread_id": thread_id,
        "status": "idle",
        "created_at": now,
        "updated_at": now,
        "metadata": metadata,  # ← 包含 user_id
    },
)
```

**Checkpointer 写入：**

```python
ckpt_metadata = {
    "step": -1,
    "source": "input",
    "writes": None,
    "parents": {},
    **metadata,  # ← user_id 通过 spread 进入 checkpointer metadata
    "created_at": now,
}
await checkpointer.aput(config, empty_checkpoint(), ckpt_metadata, {})
```

### 2. `threads.py` — `_store_upsert` 函数

扩展签名以支持 `user_id` 透传：

```python
async def _store_upsert(
    store,
    thread_id: str,
    *,
    metadata: dict | None = None,
    values: dict | None = None,
    user_id: str | None = None,
) -> None:
```

函数内部将 `user_id` 合并到 metadata（不修改调用方的 dict）：

```python
merged_metadata = dict(metadata) if metadata else {}
if user_id is not None:
    merged_metadata["user_id"] = user_id
```

**兼容性**：`user_id` 是 keyword-only 参数且默认 `None`，不影响现有调用（如 `search_threads` 中的 lazy migration）。

### 3. `services.py` — `_upsert_thread_in_store` 和 `start_run`

**`_upsert_thread_in_store`** 添加 `user_id` 参数并透传给 `_store_upsert`：

```python
async def _upsert_thread_in_store(
    store, thread_id: str, metadata: dict | None, *, user_id: str | None = None
) -> None:
    await _store_upsert(store, thread_id, metadata=metadata, user_id=user_id)
```

**`start_run`** 中从 request cookie 解析当前用户并传入：

```python
user = get_session_user(request)
user_id = user["id"] if user else None
await _upsert_thread_in_store(store, thread_id, body.metadata, user_id=user_id)
```

这样，通过 `POST /runs/stream` 或 `POST /threads/{id}/runs/stream` 隐式创建的对话也会自动带上 `user_id`。

### 4. 规避已知 bug #2594（时间戳格式）

本次修改将 `threads.py` 和 `services.py` 中所有 `time.time()` 替换为 `datetime.now(UTC).isoformat()`：

| 位置 | 修改前 | 修改后 |
|------|--------|--------|
| `_store_upsert` | `time.time()` | `datetime.now(UTC).isoformat()` |
| `create_thread` | `time.time()` | `datetime.now(UTC).isoformat()` |
| `patch_thread` | `time.time()` | `datetime.now(UTC).isoformat()` |
| `update_thread_state` | `time.time()` | `datetime.now(UTC).isoformat()` |
| `_sync_thread_title_after_run` | `time.time()` | `datetime.now(UTC).isoformat()` |

## 验证

### 验证 1：未登录时创建对话 → 401

```bash
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -d '{"metadata":{}}'
```

结果：`401 Unauthorized` ✅

### 验证 2：登录后创建对话 → metadata 包含 user_id

```bash
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<token>" \
  -d '{"metadata":{}}'
```

结果：
```json
{
  "thread_id": "6eb167ea-85a7-4b97-8510-33f95b6e32fc",
  "status": "idle",
  "created_at": "2026-04-28T12:02:54.409177+00:00",
  "updated_at": "2026-04-28T12:02:54.409177+00:00",
  "metadata": {
    "user_id": "SBLDKRchsSVmGJDHfdt59TZCyGK1UhBq"
  }
}
```

✅ `metadata` 中正确包含 `user_id`  
✅ `created_at` / `updated_at` 为 ISO 格式（非 Unix 时间戳）

### 验证 3：隐式创建路径（runs）兼容

`start_run` → `_upsert_thread_in_store` → `_store_upsert(..., user_id=...)` 的调用链已打通，后续 Phase 4.8 的 runs 权限测试将最终验证。

## 方案 A 补充修改（友好未认证提示）

Phase 4.5 原始实现中，`create_thread` 直接依赖 `get_current_user`，未登录时后端返回 `401 Unauthorized`，前端会显示生硬的报错 toast。为了提升用户体验，执行了以下补充修改：

### 后端 — 友好的 401 提示

**文件**：`backend/app/gateway/deps.py`

将 `get_current_user` 的异常提示从英文 `"Unauthorized"` 改为中文：

```python
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="请先登录后再进行操作",
)
```

这样所有注入 `Depends(get_current_user)` 的接口在未登录时都会返回统一的中文友好提示。

### 前端 — "新建对话"入口预检拦截

**文件 1**：`frontend/src/components/workspace/workspace-header.tsx`

侧边栏"新建对话"按钮添加 `onClick` 预检：未登录时阻止默认导航，自动跳转到 `/login`：

```tsx
const { data: sessionData } = authClient.useSession();
const isLoggedIn = !!sessionData?.user;

const handleNewChat = (e: React.MouseEvent<HTMLAnchorElement>) => {
  if (!isLoggedIn) {
    e.preventDefault();
    router.push("/login");
  }
};

<Link href="/workspace/chats/new" onClick={handleNewChat}>
```

**文件 2**：`frontend/src/components/workspace/command-palette.tsx`

Command Palette 的 `⌘+⇧+N` / `Ctrl+Shift+N` 快捷键和菜单项同样添加预检：

```tsx
const handleNewChat = useCallback(() => {
  if (!isLoggedIn) {
    router.push("/login");
  } else {
    router.push("/workspace/chats/new");
  }
  setOpen(false);
}, [router, isLoggedIn]);
```

**文件 3**：`frontend/src/app/workspace/chats/[thread_id]/page.tsx`

聊天输入框的 `handleSubmit` 添加兜底预检：即使用户通过 URL 直接访问 `/workspace/chats/new`，未登录时点击发送也会跳转登录页，而不是等到 API 返回 401：

```tsx
const handleSubmit = useCallback(
  (message: PromptInputMessage) => {
    if (!isLoggedIn) {
      router.push("/login");
      return;
    }
    void sendMessage(threadId, message);
  },
  [sendMessage, threadId, isLoggedIn, router],
);
```

### 效果

| 场景 | 之前 | 之后 |
|------|------|------|
| 未登录点击侧边栏"新建对话" | 跳转 `/workspace/chats/new` → 发送消息 → API 401 → toast 报错 | 直接跳转 `/login` |
| 未登录使用快捷键 `⌘+⇧+N` | 同上 | 直接跳转 `/login` |
| 未登录在聊天页发送消息 | API 401 → toast 报错 | 直接跳转 `/login` |
| 后端所有需认证接口 | `"Unauthorized"` | `"请先登录后再进行操作"` |

## 遇到的问题

无。
