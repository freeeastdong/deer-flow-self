# Phase 2：后端接收并转发 locale

## 目标

让后端 Gateway 能够识别前端传来的 `locale` 字段，并将其注入到 Agent 的运行时配置中，供 Lead Agent 和 Subagent 读取。

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/gateway/services.py` | 修改常量 | `_CONTEXT_CONFIGURABLE_KEYS` frozenset 新增 `"locale"` |

## 背景知识

后端 Gateway 使用 `_CONTEXT_CONFIGURABLE_KEYS` 白名单机制来决定哪些 `body.context` 字段需要被转发到 Agent 的 `RunnableConfig`。

`merge_run_context_overrides(config, context)` 函数会遍历白名单中的每个 key：
1. 如果该 key 存在于 `body.context` 中
2. 则将其写入 `config["configurable"][key]`（兼容旧版 LangGraph）
3. 同时写入 `config["context"][key]`（兼容新版 LangGraph >= 0.6）

这意味着只要将 `"locale"` 加入白名单，前端传来的 `locale` 就会自动出现在 Agent 运行时可以读取的配置中。

## 代码变更记录

### 2.1 services.py

```python
# BEFORE
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset(
    {
        "model_name",
        "mode",
        "thinking_enabled",
        "reasoning_effort",
        "is_plan_mode",
        "subagent_enabled",
        "max_concurrent_subagents",
        "agent_name",
        "is_bootstrap",
    }
)

# AFTER
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset(
    {
        "model_name",
        "mode",
        "thinking_enabled",
        "reasoning_effort",
        "is_plan_mode",
        "subagent_enabled",
        "max_concurrent_subagents",
        "agent_name",
        "is_bootstrap",
        "locale",  # ← 新增
    }
)
```

## 效果说明

修改后，当前端发送如下请求体时：

```json
{
  "input": { "messages": [...] },
  "config": { "recursion_limit": 1000 },
  "context": {
    "locale": "zh-CN",
    "model_name": "gpt-4",
    "thinking_enabled": true
  }
}
```

`merge_run_context_overrides()` 会生成如下 `config`：

```python
{
  "recursion_limit": 1000,
  "configurable": {
    "locale": "zh-CN",
    "model_name": "gpt-4",
    "thinking_enabled": True,
    "thread_id": "..."
  },
  "context": {
    "locale": "zh-CN",
    "model_name": "gpt-4",
    "thinking_enabled": True
  }
}
```

Lead Agent 的 `make_lead_agent(config, ...)` 和 Subagent 的 `task_tool` 都可以从 `config` 中读取 `locale`。

## 验证方式

1. 在 `merge_run_context_overrides()` 或 `start_run()` 中添加临时日志：
   ```python
   logger.info("Merged config locale: %s", config.get("configurable", {}).get("locale"))
   ```
2. 发送一条消息，检查后端日志是否输出 `zh-CN`

## 状态

- [x] 修改 `services.py`
- [x] 验证 config 中携带 locale
