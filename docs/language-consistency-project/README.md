# Language Consistency Project（语言一致性改造）

## 项目背景

当前 Deer-Flow 项目存在**前后端语言链路断裂**问题：

- 前端拥有完善的 `en-US` / `zh-CN` i18n 双语言体系，但 `locale` 仅用于前端 UI 渲染
- 后端 Gateway 未读取任何语言标识（无 `Accept-Language` Header、无 `locale` Cookie 读取）
- LLM 回复语言完全依赖 system prompt 中的软性指令：`"Keep using the same language as user's"`
- 子代理（subagent）的 system prompt 中**没有任何语言相关指令**

这导致用户用中文提问后，模型仍可能因工具输出含英文、训练数据偏向等原因切换回英文回答。

## 项目目标

1. ✅ 建立从前端到后端的完整 `locale` 传递链路
2. ✅ 将软性语言提示替换为**结构化、强制性**的语言约束
3. ✅ 覆盖主 Agent（Lead Agent）和所有子代理（Subagent）
4. ✅ 保证中文用户始终收到中文回复，英文用户始终收到英文回复

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                          前端 (Frontend)                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ 用户选择语言  │───→│ locale cookie │───→│ UI 文本渲染 (已有)   │  │
│  │ (en-US/zh-CN)│    │             │    └─────────────────────┘  │
│  └─────────────┘    └──────┬──────┘                             │
│                            │                                    │
│                            ↓ 新增                                │
│                     thread.submit(context)                       │
│                     注入 { locale: "zh-CN" }                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      后端 Gateway                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ _CONTEXT_CONFIGURABLE_KEYS 白名单新增 "locale"            │    │
│  │ merge_run_context_overrides() 自动转发到 config           │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Lead Agent (主代理)                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ apply_prompt_template(locale=...)                       │    │
│  │ SYSTEM_PROMPT_TEMPLATE 中 <critical_reminders> 改造      │    │
│  │ 软性提示 → 结构化强制指令:                                │    │
│  │ "YOU MUST respond ONLY in {user_locale}"                │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Subagent (子代理)                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ SubagentExecutor 接收 locale 参数                        │    │
│  │ _create_agent(): system_prompt 追加 <LANGUAGE_CONSTRAINT>│   │
│  │ _build_initial_state(): 插入语言锚点 SystemMessage       │   │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 文档索引

| 文件 | 内容 |
|------|------|
| [plan.md](./plan.md) | 完整实施计划 |
| [phase-1-frontend.md](./phase-1-frontend.md) | Phase 1：前端传递 `locale` 标识 |
| [phase-2-gateway.md](./phase-2-gateway.md) | Phase 2：后端接收并转发 `locale` |
| [phase-3-lead-agent.md](./phase-3-lead-agent.md) | Phase 3：主 Agent Prompt 改造 |
| [phase-4-subagent.md](./phase-4-subagent.md) | Phase 4：子代理 Prompt 改造 |
| [phase-5-verification.md](./phase-5-verification.md) | Phase 5：测试验证记录 |

## 关键修改文件清单

| 文件路径 | 负责 Phase | 作用 |
|---------|-----------|------|
| `frontend/src/core/threads/types.ts` | 1 | 扩展 `AgentThreadContext` 接口 |
| `frontend/src/core/threads/hooks.ts` | 1 | `sendMessage` 注入 `locale` |
| `backend/app/gateway/services.py` | 2 | `_CONTEXT_CONFIGURABLE_KEYS` 添加 `locale` |
| `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` | 3 | 改造 `SYSTEM_PROMPT_TEMPLATE` |
| `backend/packages/harness/deerflow/agents/lead_agent/agent.py` | 3 | `make_lead_agent` 传递 `locale` |
| `backend/packages/harness/deerflow/client.py` | 3 | `_ensure_agent` 传递 `locale` |
| `backend/packages/harness/deerflow/subagents/executor.py` | 4 | `SubagentExecutor` 注入语言约束 |
| `backend/packages/harness/deerflow/tools/builtins/task_tool.py` | 4 | 从 runtime 读取 `locale` |

## 状态跟踪

- [x] Phase 1: 前端传递语言标识
- [x] Phase 2: 后端接收并转发 locale
- [x] Phase 3: 主 Agent Prompt 改造
- [x] Phase 4: 子代理 Prompt 改造
- [x] Phase 5: 测试验证
