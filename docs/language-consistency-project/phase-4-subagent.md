# Phase 4：子代理（Subagent）Prompt 改造

## 目标

子代理（Subagent）是实际执行复杂任务（代码生成、文件操作、Bash 命令等）的主体，其输出更容易出现英文。本 Phase 确保所有 Subagent 都能接收到 `locale` 并在 system prompt 和初始对话中注入强制性语言约束。

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/packages/harness/deerflow/subagents/executor.py` | 修改类定义 + 方法 | `SubagentExecutor` 新增 `locale` 参数；`_create_agent` 和 `_build_initial_state` 注入语言约束 |
| `backend/packages/harness/deerflow/tools/builtins/task_tool.py` | 修改调用处 | 从 runtime 读取 `locale` 并传给 `SubagentExecutor` |

## 设计决策

### 为什么采用"双保险"策略？

子代理的上下文隔离性更强，模型更容易"忘记"主对话的语言。因此采用：

1. **System Prompt 追加**：在 `SubagentExecutor._create_agent()` 中，将 `<LANGUAGE_CONSTRAINT>` 区块追加到原有 `system_prompt` 末尾。这是最强的约束层级。
2. **语言锚点 Message**：在 `SubagentExecutor._build_initial_state()` 中，在 `HumanMessage(task)` 之前插入一条 `SystemMessage` 作为对话中的动态提醒。这可以覆盖 system prompt 被模型忽略的情况。

### locale 的传递链路

```
frontend context.locale
    ↓
backend config.configurable.locale
    ↓
make_lead_agent() → agent runtime
    ↓
task_tool() 被调用时从 runtime.context/runtime.config 读取 locale
    ↓
SubagentExecutor(locale=...)
    ↓
_create_agent(): system_prompt += <LANGUAGE_CONSTRAINT>
_build_initial_state(): messages.insert(SystemMessage(language reminder))
```

## 代码变更记录

### 4.1 executor.py —— SubagentExecutor 构造函数

```python
# BEFORE
def __init__(
    self,
    config: SubagentConfig,
    tools: list[BaseTool],
    app_config: AppConfig | None = None,
    parent_model: str | None = None,
    sandbox_state: SandboxState | None = None,
    thread_data: ThreadDataState | None = None,
    thread_id: str | None = None,
    trace_id: str | None = None,
):
    self.config = config
    self.app_config = app_config
    # ...

# AFTER
def __init__(
    self,
    config: SubagentConfig,
    tools: list[BaseTool],
    app_config: AppConfig | None = None,
    parent_model: str | None = None,
    sandbox_state: SandboxState | None = None,
    thread_data: ThreadDataState | None = None,
    thread_id: str | None = None,
    trace_id: str | None = None,
    locale: str | None = None,  # ← 新增
):
    self.config = config
    self.app_config = app_config
    self.locale = locale  # ← 新增
    # ...
```

### 4.2 executor.py —— _create_agent 注入语言指令

```python
# BEFORE
def _create_agent(self):
    app_config = self.app_config or get_app_config()
    if self.model_name is None:
        self.model_name = resolve_subagent_model_name(self.config, self.parent_model, app_config=app_config)
    model = create_chat_model(name=self.model_name, thinking_enabled=False, app_config=app_config)

    from deerflow.agents.middlewares.tool_error_handling_middleware import build_subagent_runtime_middlewares
    middlewares = build_subagent_runtime_middlewares(app_config=app_config, model_name=self.model_name, lazy_init=True)

    return create_agent(
        model=model,
        tools=self.tools,
        middleware=middlewares,
        system_prompt=self.config.system_prompt,
        state_schema=ThreadState,
    )

# AFTER
def _create_agent(self):
    app_config = self.app_config or get_app_config()
    if self.model_name is None:
        self.model_name = resolve_subagent_model_name(self.config, self.parent_model, app_config=app_config)
    model = create_chat_model(name=self.model_name, thinking_enabled=False, app_config=app_config)

    from deerflow.agents.middlewares.tool_error_handling_middleware import build_subagent_runtime_middlewares
    middlewares = build_subagent_runtime_middlewares(app_config=app_config, model_name=self.model_name, lazy_init=True)

    # 动态注入语言约束到 system_prompt
    system_prompt = self.config.system_prompt or ""
    if self.locale:
        language_instruction = (
            f"\n\n<LANGUAGE_CONSTRAINT>\n"
            f"CRITICAL: The parent conversation is in {self.locale}. "
            f"YOU MUST respond ONLY in {self.locale}. "
            f"Do NOT switch languages even if technical outputs are in other languages.\n"
            f"</LANGUAGE_CONSTRAINT>"
        )
        system_prompt = system_prompt + language_instruction

    return create_agent(
        model=model,
        tools=self.tools,
        middleware=middlewares,
        system_prompt=system_prompt,
        state_schema=ThreadState,
    )
```

### 4.3 executor.py —— _build_initial_state 添加语言锚点

```python
# BEFORE
async def _build_initial_state(self, task: str) -> dict[str, Any]:
    skill_messages = await self._load_skill_messages()
    messages: list = []
    messages.extend(skill_messages)
    messages.append(HumanMessage(content=task))

    state: dict[str, Any] = {
        "messages": messages,
    }
    if self.sandbox_state is not None:
        state["sandbox"] = self.sandbox_state
    if self.thread_data is not None:
        state["thread_data"] = self.thread_data
    return state

# AFTER
async def _build_initial_state(self, task: str) -> dict[str, Any]:
    skill_messages = await self._load_skill_messages()
    messages: list = []
    messages.extend(skill_messages)
    
    # 语言锚点：在 task 前插入语言提醒
    if self.locale:
        messages.append(SystemMessage(
            content=f"Reminder: The user is speaking in {self.locale}. Your response must be in {self.locale}."
        ))
    
    messages.append(HumanMessage(content=task))

    state: dict[str, Any] = {
        "messages": messages,
    }
    if self.sandbox_state is not None:
        state["sandbox"] = self.sandbox_state
    if self.thread_data is not None:
        state["thread_data"] = self.thread_data
    return state
```

### 4.4 task_tool.py —— 从 runtime 读取 locale 并传递

在 `task` 函数中创建 `executor_kwargs` 之前添加 locale 读取逻辑：

```python
# 新增：从 runtime 读取 locale
locale = None
if hasattr(runtime, "context") and isinstance(runtime.context, dict):
    locale = runtime.context.get("locale")
if locale is None and hasattr(runtime, "config"):
    locale = runtime.config.get("configurable", {}).get("locale")

# 在 executor_kwargs 中注入 locale
executor_kwargs = {
    "config": config,
    "tools": tools,
    "parent_model": parent_model,
    "sandbox_state": sandbox_state,
    "thread_data": thread_data,
    "thread_id": thread_id,
    "trace_id": trace_id,
    "locale": locale,  # ← 新增
}
```

## 对现有测试的影响

`backend/tests/test_subagent_executor.py` 中存在大量 `SubagentExecutor(...)` 构造调用。由于新增 `locale` 参数有默认值 `None`，现有测试代码无需修改即可继续运行。

但建议后续在测试文件中补充以下测试用例：
1. 传入 `locale="zh-CN"` 时，`_create_agent()` 生成的 system prompt 包含 `<LANGUAGE_CONSTRAINT>`
2. 传入 `locale="zh-CN"` 时，`_build_initial_state()` 的 messages 列表在 HumanMessage 之前包含语言提醒 SystemMessage

## 验证方式

1. **单元测试**: Mock `SubagentExecutor` 创建过程，验证 `_create_agent()` 返回的 agent 的 system prompt 包含语言约束
2. **集成测试**: 触发一个会调用子代理的复杂中文任务，验证子代理的输出为中文
3. **日志验证**: 在 `task_tool.py` 中添加日志，确认 `locale` 正确从 runtime 读取

## 状态

- [x] 修改 `executor.py` 构造函数
- [x] 修改 `executor.py` `_create_agent`
- [x] 修改 `executor.py` `_build_initial_state`
- [x] 修改 `task_tool.py` 传递 locale
- [x] 验证子代理输出语言
