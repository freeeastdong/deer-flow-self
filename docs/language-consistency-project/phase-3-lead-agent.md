# Phase 3：主 Agent（Lead Agent）Prompt 改造

## 目标

将 Lead Agent system prompt 中的软性语言提示（`"Keep using the same language as user's"`）替换为**结构化、强制性的语言约束**，并确保 `locale` 参数从运行时配置正确传入 Prompt 模板。

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` | 修改模板 + 函数签名 | `SYSTEM_PROMPT_TEMPLATE` 语言指令改造；`apply_prompt_template` 新增 `locale` 参数 |
| `backend/packages/harness/deerflow/agents/lead_agent/agent.py` | 修改调用处 | `make_lead_agent` 读取 `config` 中的 `locale` 并传给 `apply_prompt_template` |
| `backend/packages/harness/deerflow/client.py` | 修改调用处 | `_ensure_agent` 读取 `config` 中的 `locale` 并传给 `apply_prompt_template` |

## 设计决策

### 为什么同时修改 `agent.py` 和 `client.py`？

项目中存在两个创建 Lead Agent 的入口：
- `agent.py:make_lead_agent()` —— Gateway HTTP API 调用时使用
- `client.py:_ensure_agent()` —— 嵌入式 Python SDK（直接 import 使用）时使用

两者都需要注入 `locale`，因此都要修改。

### 如何从 config 中读取 locale？

LangGraph 在不同版本中可能将用户 context 放在 `config["configurable"]` 或 `config["context"]` 中。为了兼容：

```python
cfg = config.get("configurable", {}) or config.get("context", {})
locale = cfg.get("locale") if isinstance(cfg, dict) else None
```

### Prompt 改造策略

原软性提示：
```
- Language Consistency: Keep using the same language as user's
```

问题：
1. "Consistency" 是建议性词汇，模型可能不严格遵守
2. 没有明确指出具体语言，模型需要自行推断
3. 没有处理"工具输出是英文"的边界情况

新结构化指令：
```
- Language Constraint: The user is communicating in {user_locale}. 
  YOU MUST respond ONLY in {user_locale} under ALL circumstances.
  Do NOT switch languages even if tool outputs, code, or external sources are in other languages.
  This is a hard requirement, not a suggestion.
```

改进点：
1. 使用 `Constraint` 替代 `Consistency`，强调强制性
2. 使用 `YOU MUST` 和 `ONLY` 等强约束词汇
3. 明确声明 `{user_locale}`，模型无需推断
4. 预先声明"即使工具输出是其他语言也不要切换"
5. 使用 `hard requirement` 明确这不是建议

## 代码变更记录

### 3.1 prompt.py —— 函数签名扩展

```python
# BEFORE
def apply_prompt_template(
    subagent_enabled: bool = False,
    max_concurrent_subagents: int = 3,
    *,
    agent_name: str | None = None,
    available_skills: set[str] | None = None,
    app_config: AppConfig | None = None,
) -> str:

# AFTER
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

### 3.2 prompt.py —— SYSTEM_PROMPT_TEMPLATE 语言指令改造

定位到 `<critical_reminders>` 区块中第 527 行附近：

```
# BEFORE
- Language Consistency: Keep using the same language as user's

# AFTER
- Language Constraint: The user is communicating in {user_locale}. 
  YOU MUST respond ONLY in {user_locale} under ALL circumstances.
  Do NOT switch languages even if tool outputs, code, or external sources are in other languages.
  This is a hard requirement, not a suggestion.
```

### 3.3 prompt.py —— apply_prompt_template 函数体注入 locale

在函数末尾、格式化模板前添加：

```python
# 新增：确定用户语言
user_locale = locale or "the same language as the user's"

# 在格式化时传入 user_locale
# 需要确认 SYSTEM_PROMPT_TEMPLATE 中其他已有占位符，确保 format 调用完整
system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
    agent_name=agent_name or "Lead Agent",
    soul=soul,
    memory_context=memory_context,
    skills_section=skills_section,
    subagent_section=subagent_section,
    deferred_tools_section=deferred_tools_section,
    subagent_reminder=subagent_reminder,
    subagent_thinking=subagent_thinking,
    current_date=current_date,
    user_locale=user_locale,  # ← 新增
)
```

> **注意**: 需要检查 `SYSTEM_PROMPT_TEMPLATE` 中实际使用的 `{...}` 占位符列表，确保 `format()` 调用提供所有必要参数。

### 3.4 agent.py —— make_lead_agent 读取 locale

在 `make_lead_agent` 函数开头（获取其他 config 字段附近）添加：

```python
# 从 config 中提取 locale（兼容 configurable 和 context 两种容器）
cfg = config.get("configurable", {}) or config.get("context", {})
locale = cfg.get("locale") if isinstance(cfg, dict) else None
```

在两个 `apply_prompt_template()` 调用处（bootstrap agent 和 default lead agent）都传入 `locale`：

```python
# BEFORE
system_prompt=apply_prompt_template(
    subagent_enabled=subagent_enabled,
    max_concurrent_subagents=max_concurrent_subagents,
    agent_name=agent_name,
    available_skills=...,
    app_config=resolved_app_config,
),

# AFTER
system_prompt=apply_prompt_template(
    subagent_enabled=subagent_enabled,
    max_concurrent_subagents=max_concurrent_subagents,
    agent_name=agent_name,
    available_skills=...,
    app_config=resolved_app_config,
    locale=locale,  # ← 新增
),
```

### 3.5 client.py —— _ensure_agent 读取 locale

在 `_ensure_agent` 方法中类似处理：

```python
# 在方法开头添加
cfg = config.get("configurable", {}) or config.get("context", {})
locale = cfg.get("locale") if isinstance(cfg, dict) else None

# 在 apply_prompt_template 调用中传入 locale
system_prompt=apply_prompt_template(
    subagent_enabled=subagent_enabled,
    max_concurrent_subagents=max_concurrent_subagents,
    agent_name=self._agent_name,
    available_skills=self._available_skills,
    locale=locale,  # ← 新增
),
```

## 验证方式

1. **单元测试**: 调用 `apply_prompt_template(locale="zh-CN")`，检查返回的 system prompt 是否包含强制中文指令
2. **日志验证**: 在 `make_lead_agent` 中添加临时日志，确认 `locale` 正确读取
3. **实际对话**: 中文提问后检查 AI 回复的 system prompt 中是否包含语言约束

## 状态

- [x] 修改 `prompt.py` 函数签名
- [x] 改造 `SYSTEM_PROMPT_TEMPLATE` 语言指令
- [x] 修改 `apply_prompt_template` 函数体注入 `user_locale`
- [x] 修改 `agent.py` 传递 `locale`
- [x] 修改 `client.py` 传递 `locale`
- [x] 验证 prompt 输出
