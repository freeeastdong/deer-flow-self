# Agent 状态栏（顶部 Hover 展开）

## 需求背景

在聊天页面顶部 header 的左侧区域增加一个可展开的状态栏，鼠标悬停时向下展开，展示所有可用 Agent 的卡片列表（类似微信聊天列表的样式），点击卡片即可快速切换到对应 Agent 的新对话。

## 新增文件

### `frontend/src/components/workspace/agent-status-bar.tsx`

状态栏组件本体，包含以下特性：

- **默认状态**：一个紧凑的触发条，显示当前 Agent 名称（或"智能体"/"Agents"）+ 向下箭头图标
- **Hover 展开**：鼠标移入后 200ms 内向下展开一个面板
  - 面板宽度自适应内容：`min-w-64`（最小 256px）/ `max-w-lg`（最大 512px），不设固定宽度，由内部最长的 Agent 卡片自然撑开
  - 背景带毛玻璃效果 `bg-background/95 backdrop-blur-md`
  - 圆角 + 阴影边框
  - 最大高度限制 `min(400px, 70vh)`，超出可滚动
- **Agent 列表**：垂直排列的 Agent 项，每项包含：
  - 左侧 Bot 图标（`bg-primary/10` 圆角底色）
  - Agent 名称（单行截断）
  - Agent 标签：取 `skills` + `tool_groups` 前 3 个，用 `Badge` 组件展示（`variant="secondary"`，`10px` 字号）
- **当前高亮**：当前正在对话的 Agent 会带有 `bg-accent/50` 高亮背景
- **通用智能体**：列表顶部固定显示一个"通用智能体"（Default Agent）项，使用对话图标（`MessageSquareIcon`），点击后跳转到默认对话页 `/workspace/chats/new`
- **分隔线**：通用智能体与自定义 Agent 列表之间有一条细分割线（`bg-border h-px`）
- **点击跳转**：点击自定义 Agent 项会导航到 `/workspace/agents/{name}/chats/new`
- **最近对话子列表**：每个自定义 Agent 项右侧有一个展开按钮（`ChevronRightIcon`），点击后在该 Agent 项下方展开最近 **5 次对话**列表
  - 对话卡片显示标题（`titleOfThread`）和相对时间（`formatTimeAgo`）
  - 点击对话卡片直接跳转到该对话（`/workspace/agents/{name}/chats/{thread_id}`）
  - 数据来源：`useThreads({ limit: 200 })`，按 `agent_name` 过滤分组，每个 Agent 最多显示 5 条
- **加载/空态**：支持加载中（`t.common.loading`）和空列表（`t.agents.emptyTitle`）状态

## 修改文件

### `frontend/src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx`

**改动点**：
- 移除 `BotIcon` 的 import（不再使用）
- 新增 `AgentStatusBar` 的 import
- 将 header 左侧原来的静态 Agent badge：
  ```tsx
  <div className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1">
    <BotIcon className="text-primary h-3.5 w-3.5" />
    <span className="text-xs font-medium">
      {agent?.name ?? agent_name}
    </span>
  </div>
  ```
  替换为：
  ```tsx
  <AgentStatusBar currentAgentName={agent?.name ?? agent_name} />
  ```

### `frontend/src/core/i18n/locales/zh-CN.ts` 与 `en-US.ts`

- 在 `agents` 对象中新增 `defaultAgent` 字段：
  - 中文：`"通用智能体"`
  - 英文：`"Default Agent"`

### `frontend/src/app/workspace/chats/[thread_id]/page.tsx`

**改动点**：
- 新增 `AgentStatusBar` 的 import
- 在 header 的 className 中增加 `gap-2`（与 Agent 聊天页保持一致）
- 在 header 左侧、`ThreadTitle` 之前插入：
  ```tsx
  <AgentStatusBar />
  ```
  普通聊天页没有当前 Agent 上下文，因此不传入 `currentAgentName`，组件会默认显示 `t.sidebar.agents`（即"智能体"/"Agents"）

## 交互效果

```
┌─────────────────────────────────────┐
│ [🤖 agent-name ▼]    Thread Title       │  ← 默认状态：紧凑触发条
├─────────────────────────────────────┤
│                                     │
│   🦌 你好，欢迎回来！                  │
│                                     │
└─────────────────────────────────────┘

Hover 后展开：

┌─────────────────────────────────────┐
│ [🤖 agent-name ▲]    Thread Title       │  ← 箭头旋转
├─────────────────────────────────────┤
│ ┌─────────────────────────────────┐ │
│ │ 💬 通用智能体               │     │  ← 固定项，跳转到默认对话
│ │ ─────────────────────────── │     │
│ │ 🤖 code-reviewer      ▶     │     │  ← 右侧展开按钮
│ │    [skill-1] [skill-2]      │     │  ← skills / tool_groups 标签（最多3个）
│ │    ├─ 南京今日天气          │     │
│ │    ├─ 代码审查报告          │     │  ← 点击 ▶ 展开最近 5 次对话
│ │    └─ API 设计讨论    2天前 │     │
│ │ ─────────────────────────── │     │
│ │ 🤖 data-analyst       ▶     │     │
│ │ ─────────────────────────── │     │
│ │ 🤖 copywriter   (高亮)      │     │  ← 当前 Agent 高亮
│ │    Write marketing copy     │     │
│ └─────────────────────────────┘     │
└─────────────────────────────────────┘
```

## 后续可扩展方向

1. **在线状态指示**：可在 Agent 图标旁增加小圆点表示"在线/离线"或"正在运行"状态
2. **拖拽排序**：支持用户拖拽调整 Agent 列表顺序
3. **搜索过滤**：Agent 数量较多时，在面板顶部增加搜索输入框
