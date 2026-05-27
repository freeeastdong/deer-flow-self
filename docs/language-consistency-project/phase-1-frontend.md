# Phase 1：前端传递语言标识

## 目标

让前端将用户当前选择的 `locale`（`en-US` 或 `zh-CN`）传递到后端，使后端 LLM 知道应该以何种语言回复。

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `frontend/src/core/threads/types.ts` | 新增字段 | `AgentThreadContext` 接口增加 `locale?: string` |
| `frontend/src/core/threads/hooks.ts` | 修改逻辑 | `sendMessage` 中把 `locale` 注入到 `thread.submit()` 的 `context` |

## 设计决策

### 为什么选择通过 `thread.submit()` 的 `context` 传递？

本项目前端使用 LangGraph SDK 的 `useStream` Hook，消息流通过 `thread.submit()` 发送。该方法的 `context` 参数会被 SDK 序列化后发送到后端 `/runs/stream` 接口。

后端 `services.py` 中的 `merge_run_context_overrides()` 函数会读取 `body.context`，并将其中的白名单字段同时写入 `config["configurable"]` 和 `config["context"]`，供 Agent 运行时使用。

相比修改 `fetcher.ts` 注入 HTTP Header，此方式：
- 更直接：无需修改 SDK 底层请求逻辑
- 更可靠：`context` 是 LangGraph Platform 的标准机制
- 向后兼容：未升级的前端客户端不会传递 `locale`，后端逻辑有默认值保护

## 代码变更记录

### 1.1 types.ts

```typescript
// BEFORE
export interface AgentThreadContext extends Record<string, unknown> {
  thread_id: string;
  model_name: string | undefined;
  thinking_enabled: boolean;
  is_plan_mode: boolean;
  subagent_enabled: boolean;
  reasoning_effort?: "minimal" | "low" | "medium" | "high";
  agent_name?: string;
}

// AFTER
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

### 1.2 hooks.ts

```typescript
// BEFORE
export function useThreadStream({
  threadId,
  context,
  isMock,
  onSend,
  onStart,
  onFinish,
  onToolEnd,
}: ThreadStreamOptions) {
  const { t } = useI18n();
  // ...
}

// AFTER
export function useThreadStream({
  threadId,
  context,
  isMock,
  onSend,
  onStart,
  onFinish,
  onToolEnd,
}: ThreadStreamOptions) {
  const { t, locale } = useI18n();  // ← 新增解构 locale
  // ...
}
```

在 `sendMessage` 的 `thread.submit()` 调用中：

```typescript
// BEFORE
context: {
  ...extraContext,
  ...context,
  thinking_enabled: context.mode !== "flash",
  is_plan_mode: context.mode === "pro" || context.mode === "ultra",
  subagent_enabled: context.mode === "ultra",
  reasoning_effort: ...,
  thread_id: threadId,
}

// AFTER
context: {
  ...extraContext,
  ...context,
  thinking_enabled: context.mode !== "flash",
  is_plan_mode: context.mode === "pro" || context.mode === "ultra",
  subagent_enabled: context.mode === "ultra",
  reasoning_effort: ...,
  thread_id: threadId,
  locale,  // ← 新增
}
```

## 验证方式

1. 在前端浏览器 DevTools 的 Network 面板中，找到 `runs/stream` 的 WebSocket 或 SSE 请求
2. 检查 payload 中 `context` 字段是否包含 `"locale": "zh-CN"`（或 `"en-US"`）
3. 切换前端语言设置后再次发送消息，确认 `locale` 值随之变化

## 状态

- [x] 修改 `types.ts`
- [x] 修改 `hooks.ts`
- [x] 验证 context 中携带 locale
