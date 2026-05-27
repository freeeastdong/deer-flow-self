# 方案一：全链路语言传递 + Prompt 强制约束 — 实施计划

## 背景与问题诊断

当前项目存在**前后端语言链路断裂**：

- 前端有完整的 `en-US`/`zh-CN` i18n 体系，但 `locale` 仅用于 UI 渲染，未传递到后端
- 后端 Gateway 未读取 `Accept-Language` 或 `locale` cookie
- LLM 回复语言完全依赖 system prompt 中的软性指令：`"Keep using the same language as user's"`
- 子代理（subagent）的 system prompt 中**没有任何语言相关指令**

导致用户用中文提问后，模型可能因工具输出含英文、训练数据偏向等原因切换回英文回答。

## 实施目标

1. 建立从前端到后端的完整 `locale` 传递链路
2. 将软性语言提示替换为**结构化、强制性**的语言约束
3. 覆盖主 Agent（Lead Agent）和所有子代理（Subagent）
4. 保证中文用户始终收到中文回复，英文用户始终收到英文回复

---

## Phase 1：前端传递语言标识

### 1.1 修改类型定义
**文件**: `frontend/src/core/threads/types.ts`

在 `AgentThreadContext` 接口中添加 `locale` 字段：
```typescript
export interface AgentThreadContext extends Record<string, unknown> {
  thread_id: string;
  model_name: string | undefined;
  thinking_enabled: boolean;
  is_plan_mode: boolean;
  subagent_enabled: boolean;
  reasoning_effort?: "minimal" | "low" | "medium" | "high";
  agent_name?: string;
  locale?: string;  // ← 新增
}
```

### 1.2 在消息提交时注入 locale
**文件**: `frontend/src/core/threads/hooks.ts`

`useThreadStream` 中已调用 `useI18n()` 获取翻译，现扩展为同时获取 `locale`：
```typescript
const { t, locale } = useI18n();
```

在 `sendMessage` 调用 `thread.submit()` 的 `context` 参数中注入 `locale`：
```typescript
context: {
  ...extraContext,
  ...context,
  thinking_enabled: context.mode !== "flash",
  // ... 其他字段
  locale,  // ← 新增
}
```

> **设计决策**: 选择通过 `thread.submit()` 的 `context` 传递而非 HTTP Header，因为本项目使用 LangGraph SDK 的流式接口（`useStream` + `runs.stream`），`context` 会被原样发送到后端并进入 `_CONTEXT_CONFIGURABLE_KEYS` 处理链路，比修改 `fetcher.ts` 更直接可靠。

---

## Phase 2：后端接收并转发 locale

### 2.1 扩展 Context 白名单
**文件**: `backend/app/gateway/services.py`

将 `"locale"` 加入 `_CONTEXT_CONFIGURABLE_KEYS` frozenset：
```python
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

**效果**: `merge_run_context_overrides()` 会自动将前端传来的 `locale` 同时写入 `config["configurable"]["locale"]` 和 `config["context"]["locale"]`，确保 LangGraph 新旧版本的 context 消费者都能读取。

---

## Phase 3：主 Agent（Lead Agent）Prompt 改造

### 3.1 修改 Prompt 模板函数
**文件**: `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

#### 3.1.1 修改 `apply_prompt_template` 签名
```python
def apply_prompt_template(
    subagent_enabled: bool = False,
    max_concurrent_subagents: int = 3,
    *,
    agent_name: str | None = None,
    available_skills: set[str] | None = None,
    app_config: AppConfig | None = None,
    locale: str | None = None,  # ← 新增
) -> str:
```

#### 3.1.2 改造 `SYSTEM_PROMPT_TEMPLATE` 中的语言指令
定位到 `<critical_reminders>` 区块第 527 行附近：

将原软性提示：
```
- Language Consistency: Keep using the same language as user's
```

替换为结构化强制指令：
```
- Language Constraint: The user is communicating in {user_locale}. 
  YOU MUST respond ONLY in {user_locale} under ALL circumstances.
  Do NOT switch languages even if tool outputs, code, or external sources are in other languages.
  This is a hard requirement, not a suggestion.
```

并在 `apply_prompt_template` 函数体内注入 `user_locale`：
```python
user_locale = locale or "the same language as the user's"
# 在格式化模板时传入
system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
    # ... 其他已有参数
    user_locale=user_locale,
)
```

### 3.2 修改主 Agent 创建逻辑
**文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`

在 `make_lead_agent` 中从 `config` 读取 `locale` 并传给 `apply_prompt_template`：
```python
# 从 config 中提取 locale（兼容 configurable 和 context 两种容器）
cfg = config.get("configurable", {}) or config.get("context", {})
locale = cfg.get("locale") if isinstance(cfg, dict) else None

# 在 apply_prompt_template 调用中传入
system_prompt=apply_prompt_template(
    subagent_enabled=subagent_enabled,
    max_concurrent_subagents=max_concurrent_subagents,
    agent_name=agent_name,
    available_skills=...,
    app_config=resolved_app_config,
    locale=locale,  # ← 新增
)
```

### 3.3 修改 Client SDK 入口
**文件**: `backend/packages/harness/deerflow/client.py`

在 `_ensure_agent` 中同样读取 `locale` 并传入：
```python
cfg = config.get("configurable", {}) or config.get("context", {})
locale = cfg.get("locale") if isinstance(cfg, dict) else None

system_prompt=apply_prompt_template(
    subagent_enabled=subagent_enabled,
    max_concurrent_subagents=max_concurrent_subagents,
    agent_name=self._agent_name,
    available_skills=self._available_skills,
    locale=locale,  # ← 新增
)
```

---

## Phase 4：子代理（Subagent）Prompt 改造

### 4.1 修改 SubagentExecutor 接收 locale
**文件**: `backend/packages/harness/deerflow/subagents/executor.py`

#### 4.1.1 构造函数扩展
```python
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
    # ...
    self.locale = locale
```

#### 4.1.2 `_create_agent` 中注入语言指令
在创建 agent 前，动态修改 system_prompt：
```python
def _create_agent(self):
    # ... 原有逻辑 ...
    
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

#### 4.1.3 `_build_initial_state` 中添加语言锚点
在 task 前插入一条 SystemMessage 作为额外提醒：
```python
async def _build_initial_state(self, task: str) -> dict[str, Any]:
    skill_messages = await self._load_skill_messages()
    messages: list = []
    messages.extend(skill_messages)
    
    # 语言锚点：在 task 前提醒模型保持语言一致
    if self.locale:
        messages.append(SystemMessage(
            content=f"Reminder: The user is speaking in {self.locale}. Your response must be in {self.locale}."
        ))
    
    messages.append(HumanMessage(content=task))
    # ... 其余逻辑不变
```

### 4.2 修改 task_tool 传递 locale
**文件**: `backend/packages/harness/deerflow/tools/builtins/task_tool.py`

在创建 `SubagentExecutor` 的 `executor_kwargs` 中注入 `locale`：
```python
# 从 runtime context 读取 locale
locale = None
if hasattr(runtime, "context") and isinstance(runtime.context, dict):
    locale = runtime.context.get("locale")
if locale is None and hasattr(runtime, "config"):
    locale = runtime.config.get("configurable", {}).get("locale")

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

---

## Phase 5：文档与目录结构

在 `docs/` 下创建本次改造的专属目录：

```
docs/
└── language-consistency-project/
    ├── README.md                 # 项目背景、目标、整体架构图
    ├── plan.md                   # 本计划文件（复制/链接）
    ├── phase-1-frontend.md       # Phase 1 修改记录
    ├── phase-2-gateway.md        # Phase 2 修改记录
    ├── phase-3-lead-agent.md     # Phase 3 修改记录
    ├── phase-4-subagent.md       # Phase 4 修改记录
    └── phase-5-verification.md   # Phase 5 测试验证记录
```

每个 phase 记录文件应包含：
- 修改的文件清单
- 关键代码 diff（或前后对比）
- 设计决策说明
- 遇到的问题及解决方案
- 验证结果

---

## Phase 6：测试验证

### 6.1 单元测试
- 验证 `apply_prompt_template` 在传入 `locale="zh-CN"` 时正确生成含强制中文指令的 prompt
- 验证 `SubagentExecutor` 在传入 `locale` 后 system_prompt 和初始 messages 均包含语言约束

### 6.2 集成测试
- 前端切换语言为中文 → 发送消息 → 抓包确认 context 中包含 `"locale": "zh-CN"`
- 后端确认 `config["configurable"]["locale"]` 正确接收
- 实际对话测试：中文提问复杂任务（触发子代理），确认主 Agent 和子代理均用中文回复

### 6.3 回归测试
- 验证未传 `locale` 时行为不变（向后兼容）
- 验证英文用户对话不受影响

---

## 关键文件清单

| 文件路径 | Phase | 作用 |
|---------|-------|------|
| `frontend/src/core/threads/types.ts` | 1 | 扩展 `AgentThreadContext` 接口 |
| `frontend/src/core/threads/hooks.ts` | 1 | `sendMessage` 注入 `locale` 到 context |
| `backend/app/gateway/services.py` | 2 | `_CONTEXT_CONFIGURABLE_KEYS` 添加 `locale` |
| `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` | 3 | 改造 `SYSTEM_PROMPT_TEMPLATE` 和 `apply_prompt_template` |
| `backend/packages/harness/deerflow/agents/lead_agent/agent.py` | 3 | `make_lead_agent` 读取并传递 `locale` |
| `backend/packages/harness/deerflow/client.py` | 3 | `_ensure_agent` 读取并传递 `locale` |
| `backend/packages/harness/deerflow/subagents/executor.py` | 4 | `SubagentExecutor` 接收并注入语言约束 |
| `backend/packages/harness/deerflow/tools/builtins/task_tool.py` | 4 | 从 runtime 读取 `locale` 并传给 SubagentExecutor |

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 新 `locale` 字段未向后兼容 | 低 | `locale` 为 Optional，所有注入逻辑均有 `if locale:` 保护 |
| Prompt 过长导致 token 增加 | 低 | 语言指令仅增加约 50 tokens，影响可忽略 |
| 子代理测试用例需同步更新 | 中 | 测试文件中大量 `SubagentExecutor(...)` 构造调用，需确认新增参数不影响现有测试（因 `locale` 有默认值） |
| 模型仍不遵守硬性指令 | 中 | 采用 XML 标签包裹 + "CRITICAL" + "YOU MUST" 多层强化，若仍不遵守需考虑在模型层（factory）传入特定参数 |
