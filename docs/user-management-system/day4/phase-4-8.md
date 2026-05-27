# Phase 4.8 — Runs 端点增加对话权限检查

## 目标

`thread_runs.py` 和 `runs.py` 中的 stream、wait、cancel 等端点在操作具体对话前，也要检查用户是否有权访问该对话，防止通过 Runs API 绕过 threads 的权限控制。

## 涉及文件

- `backend/app/gateway/routers/thread_runs.py`
- `backend/app/gateway/routers/runs.py`

## 实现内容

### 1. 复用 Phase 4.7 的 `_require_thread_access`

Phase 4.7 已经把权限检查逻辑抽取为 `_require_thread_access(thread_id, user, request)`，放在 `threads.py` 中。Phase 4.8 直接跨模块导入复用，避免重复代码。

### 2. `thread_runs.py` — 为所有涉及 `thread_id` 的端点加锁

新增导入：

```python
from fastapi import Depends  # 新增
from app.gateway.deps import get_current_user  # 新增
from app.gateway.routers.threads import _require_thread_access  # 新增
```

为以下 **8 个端点**注入 `get_current_user` 并在开头调用 `_require_thread_access`：

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /threads/{id}/runs` | `create_run` | 创建后台运行 |
| `POST /threads/{id}/runs/stream` | `stream_run` | 创建并流式运行 |
| `POST /threads/{id}/runs/wait` | `wait_run` | 创建并阻塞等待 |
| `GET /threads/{id}/runs` | `list_runs` | 列出运行历史 |
| `GET /threads/{id}/runs/{run_id}` | `get_run` | 查看运行详情 |
| `POST /threads/{id}/runs/{run_id}/cancel` | `cancel_run` | 取消运行 |
| `GET /threads/{id}/runs/{run_id}/join` | `join_run` | 加入已有 SSE 流 |
| `GET/POST /threads/{id}/runs/{run_id}/stream` | `stream_existing_run` | 加入/取消再流 |

**修改示例**（以 `stream_run` 为例）：

```python
@router.post("/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    body: RunCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),  # 新增
) -> StreamingResponse:
    await _require_thread_access(thread_id, current_user, request)  # 新增
    bridge = get_stream_bridge(request)
    ...
```

### 3. `runs.py` — 无状态 runs 复用已有对话时加锁

新增导入：

```python
from fastapi import Depends  # 新增
from app.gateway.deps import get_current_user  # 新增
from app.gateway.routers.threads import _require_thread_access  # 新增
```

`stateless_stream` 和 `stateless_wait` 的修改逻辑：

- 如果请求体带了 `config.configurable.thread_id`（说明客户端在复用已有对话），则调用 `_require_thread_access` 检查权限。
- 如果没有带 `thread_id`（创建临时新对话），则跳过检查。

```python
@router.post("/stream")
async def stateless_stream(
    body: RunCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),  # 新增
) -> StreamingResponse:
    thread_id = _resolve_thread_id(body)
    # 如果客户端在复用已有对话，检查权限
    if body.config and body.config.get("configurable", {}).get("thread_id"):
        await _require_thread_access(thread_id, current_user, request)
    ...
```

## 验证

### 验证 1：用户 B 向用户 A 的对话发送消息 → 403

```bash
curl -X POST http://localhost:2026/api/langgraph/threads/{用户A的thread_id}/runs/stream \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<用户B的token>" \
  -d '{"assistant_id":"lead_agent","input":{"messages":[]}}'
```

**预期结果**：`403 Forbidden`，响应体 `{"detail":"您没有权限访问该对话"}`

### 验证 2：用户 B 通过无状态接口复用用户 A 的对话 → 403

```bash
curl -X POST http://localhost:2026/api/langgraph/runs/stream \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<用户B的token>" \
  -d '{
    "assistant_id": "lead_agent",
    "input": {"messages": []},
    "config": {"configurable": {"thread_id": "用户A的thread_id"}}
  }'
```

**预期结果**：`403 Forbidden`

### 验证 3：用户 A 自己操作 → 正常

使用用户 A 的 Cookie 访问上述接口，预期正常返回 SSE 流或运行记录。

### 验证 4：无状态接口创建新对话 → 正常

不带 `config.configurable.thread_id` 调用 `/runs/stream`：

```bash
curl -X POST http://localhost:2026/api/langgraph/runs/stream \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<任意用户token>" \
  -d '{"assistant_id":"lead_agent","input":{"messages":[]}}'
```

**预期结果**：正常创建临时对话并返回 SSE 流。

### 验证 5：未登录 → 401

不带 Cookie 访问任意 Runs 端点，预期返回 `401 Unauthorized`。

## 遇到的问题

无。
