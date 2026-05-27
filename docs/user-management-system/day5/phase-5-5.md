# Phase 5.5 — 在资料页显示用户对话数

## 目标

在 `/profile` 页面增加当前用户拥有的对话数量展示。

## 涉及文件

- `backend/app/gateway/routers/threads.py`
- `frontend/src/app/profile/page.tsx`

## 实现内容

### 1. 后端：新增 `GET /api/threads/stats`

在 `threads.py` 中新增一个统计端点，直接复用 `search_threads` 的过滤逻辑，只返回数量：

```python
@router.get("/stats", response_model=dict)
async def get_thread_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Return the total number of conversations owned by the current user."""
    body = ThreadSearchRequest(limit=10_000)
    threads = await search_threads(body, request, current_user)
    return {"thread_count": len(threads)}
```

**设计要点**：
- 复用 `search_threads`，自动继承所有过滤逻辑（Store + Checkpointer + user_id 隔离）
- 老数据（无 user_id）也会被计入
- 返回简单 JSON，前端易于消费

### 2. 前端：资料页展示对话数量

在 `profile/page.tsx` 中：

1. 新增状态 `threadCount`
2. 用 `useEffect` 调用 `/api/threads/stats`
3. 在信息列表中新增"对话数量"卡片（使用 `MessageSquare` 图标）

```tsx
const [threadCount, setThreadCount] = useState<number | null>(null);

useEffect(() => {
  if (!user) return;
  fetch("/api/threads/stats", { credentials: "include" })
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((data) => setThreadCount(data.thread_count))
    .catch(() => setThreadCount(0));
}, [user]);
```

UI 展示：

```
┌─────────────────────────────┐
│ 💬 对话数量                   │
│ 12                          │
└─────────────────────────────┘
```

---

## 验证

### 验证 1：资料页显示正确的对话数量

1. 登录 DeerFlow
2. 访问 `/profile`
3. **预期结果**："对话数量"字段显示当前用户的对话总数（与侧边栏最近对话的数量一致）

### 验证 2：未登录时返回 401

```bash
curl -X GET http://localhost:2026/api/threads/stats
```

**预期结果**：`401 Unauthorized`

### 验证 3：创建新对话后数量增加

1. 在 `/profile` 页面记录当前对话数量
2. 在 workspace 中新建一个对话
3. 刷新 `/profile` 页面
4. **预期结果**：对话数量 +1

## 遇到的问题

无。
