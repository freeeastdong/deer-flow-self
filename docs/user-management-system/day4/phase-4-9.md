# Phase 4.9 — 为 Memory API 添加认证并验证对话隔离

## 目标

1. 给 `/api/memory` 接口加上认证保护，演示如何为新接口添加 `Depends(get_current_user)`。
2. 用手动测试验证前面 4.6~4.8 的对话隔离是否真正生效。

## 涉及文件

- `backend/app/gateway/routers/memory.py`

## 实现内容

### 给所有 Memory 端点注入 `get_current_user`

`memory.py` 原有 10 个端点，全部加上 `current_user: dict = Depends(get_current_user)`：

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/memory` | `get_memory` | 获取记忆数据 |
| `POST /api/memory/reload` | `reload_memory` | 重新加载记忆 |
| `DELETE /api/memory` | `clear_memory` | 清空记忆 |
| `POST /api/memory/facts` | `create_memory_fact_endpoint` | 创建记忆事实 |
| `DELETE /api/memory/facts/{fact_id}` | `delete_memory_fact_endpoint` | 删除记忆事实 |
| `PATCH /api/memory/facts/{fact_id}` | `update_memory_fact_endpoint` | 更新记忆事实 |
| `GET /api/memory/export` | `export_memory` | 导出记忆 |
| `POST /api/memory/import` | `import_memory` | 导入记忆 |
| `GET /api/memory/config` | `get_memory_config_endpoint` | 记忆配置 |
| `GET /api/memory/status` | `get_memory_status` | 记忆状态 |

**新增导入**：

```python
from fastapi import Depends  # 已有 APIRouter, HTTPException
from app.gateway.deps import get_current_user  # 新增
```

**修改示例**（以 `get_memory` 为例）：

```python
@router.get("/memory", ...)
async def get_memory(current_user: dict = Depends(get_current_user)) -> MemoryResponse:
    memory_data = get_memory_data()
    return MemoryResponse(**memory_data)
```

> **注意**：Memory 数据当前仍是全局共享的（不区分用户），本次修改仅增加了"必须登录才能访问"的门槛。如果要实现用户级别的记忆隔离，需要后续改造存储层。

---

## 验证

### 验证 1：未登录访问 Memory API → 401

```bash
curl -X GET http://localhost:2026/api/memory
```

**预期结果**：`401 Unauthorized`

### 验证 2：登录后访问 Memory API → 正常

```bash
curl -X GET http://localhost:2026/api/memory \
  -H "Cookie: better-auth.session_token=<你的token>"
```

**预期结果**：正常返回记忆数据 JSON

### 验证 3：未登录访问对话列表 → 401

```bash
curl -X POST http://localhost:2026/api/langgraph/threads/search \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}'
```

**预期结果**：`401 Unauthorized`

### 验证 4：登录后访问对话列表 → 只看到当前用户的对话

```bash
curl -X POST http://localhost:2026/api/langgraph/threads/search \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<你的token>" \
  -d '{"limit": 10}'
```

**预期结果**：返回当前用户的对话列表，不包含其他用户的对话。

### 验证 5：用户 B 访问用户 A 的对话 → 403

先用用户 A 创建对话并记录 `thread_id`，然后用用户 B 的 Cookie 访问：

```bash
# 查看对话详情
curl -X GET http://localhost:2026/api/langgraph/threads/{用户A的thread_id} \
  -H "Cookie: better-auth.session_token=<用户B的token>"

# 尝试流式运行
curl -X POST http://localhost:2026/api/langgraph/threads/{用户A的thread_id}/runs/stream \
  -H "Content-Type: application/json" \
  -H "Cookie: better-auth.session_token=<用户B的token>" \
  -d '{"assistant_id":"lead_agent","input":{"messages":[]}}'
```

**预期结果**：两条请求都返回 `403 Forbidden`，响应体 `{"detail":"您没有权限访问该对话"}`

### 验证 6：老数据（无 user_id）→ 已登录用户可见

对于 Day 4 之前创建的对话（metadata 中没有 `user_id`），用任意已登录用户访问：

```bash
curl -X GET http://localhost:2026/api/langgraph/threads/{老对话的thread_id} \
  -H "Cookie: better-auth.session_token=<任意用户的token>"
```

**预期结果**：正常返回对话详情（老数据兼容，不返回 403）。

## 遇到的问题

无。
