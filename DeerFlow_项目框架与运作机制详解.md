# DeerFlow 项目框架与运作机制详解

## Phase 0: 整体架构一览

DeerFlow 是一个**前后端分离**的 **LangGraph-based Super Agent Harness**。它的核心定位不是"一个 Agent"，而是**一个能编排多个 Sub-agent、管理记忆、在 Sandbox 中执行代码的 Agent 运行时框架**。

### 技术栈分层

| 层级 | 技术 | 职责 |
|------|------|------|
| **前端** | Next.js 14 (App Router) + TypeScript + React Query | 聊天界面、工作区、配置面板 |
| **Gateway** | FastAPI | 路由、鉴权、文件上传、线程管理 |
| **Agent 运行时** | LangGraph + LangChain | 图编排、工具调用、状态管理 |
| **核心包** | `deerflow-harness` | Agent 工厂、Sandbox、工具、Memory、Middleware |
| **Sandbox** | Local (subprocess) / AioSandbox (Docker) | 隔离执行 bash、文件操作 |
| **持久化** | LangGraph Checkpointer (SQLite/Postgres) | 线程状态、消息历史 |
| **部署** | Docker Compose / K8s Provisioner | 服务编排、沙箱容器 |

### 核心目录结构

```
deer-flow/
├── frontend/src/                    # Next.js 前端
│   ├── app/workspace/chats/         # 聊天页面
│   ├── core/threads/hooks.ts        # useThreadStream — 流式消息核心
│   └── components/workspace/        # 消息列表、输入框、Artifacts
├── backend/
│   ├── app/gateway/                 # FastAPI Gateway
│   │   ├── app.py                   # 应用入口、lifespan、路由挂载
│   │   └── routers/thread_runs.py   # /threads/{id}/runs/stream (SSE)
│   └── packages/harness/deerflow/   # 核心 Agent 框架
│       ├── agents/
│       │   ├── lead_agent/agent.py  # make_lead_agent — 主 Agent 工厂
│       │   ├── factory.py           # create_deerflow_agent — 通用 Agent 工厂
│       │   └── middlewares/         # 14 层中间件链
│       ├── sandbox/                 # 沙箱执行层
│       │   ├── tools.py             # bash/read_file/ls/grep 工具定义
│       │   └── local/local_sandbox.py  # LocalSandbox (subprocess)
│       ├── community/aio_sandbox/   # AioSandbox (Docker HTTP API)
│       ├── subagents/
│       │   ├── builtins/            # general-purpose, bash subagent
│       │   └── executor.py          # SubagentExecutor — 子代理执行引擎
│       └── tools/
│           ├── tools.py             # get_available_tools — 工具加载器
│           └── builtins/task_tool.py # task 工具 — 委派给 subagent
└── config.yaml                      # 全量配置：模型、工具、Sandbox、Memory
```

---

## Phase 1: 请求入口层 — 从用户点击发送到 Gateway

### 1.1 前端：聊天页面与流式 Hook

用户在前端输入消息并点击发送，入口在：

**`frontend/src/app/workspace/chats/[thread_id]/page.tsx`** (第 34-94 行)

```tsx
export default function ChatPage() {
  const { thread, sendMessage } = useThreadStream({
    threadId: isNewThread ? undefined : threadId,
    context: settings.context,
    // ...
  });

  const handleSubmit = useCallback((message: PromptInputMessage) => {
    void sendMessage(threadId, message);
  }, [sendMessage, threadId]);
}
```

`useThreadStream` 是前端最核心的 Hook，它底层调用 LangGraph SDK 的 `useStream`，通过 **SSE (Server-Sent Events)** 与后端建立长连接，实时接收 Agent 的流式输出。

### 1.2 前端 Hook 分层详解

前端不是单一 Hook 搞定一切，而是**四层 Hook 各司其职**：

```
┌─────────────────────────────────────────────────────────────┐
│  ChatPage (页面组件)                                          │
│  ├── useThreadChat()     → 管 threadId / URL / isNewThread   │
│  ├── useThreadStream()   → 管 SSE 流、发送消息、消息合并       │
│  │   ├── useStream()     → LangGraph SDK 底层 SSE 连接       │
│  │   └── useThreadHistory() → 管历史消息分页加载               │
│  └── useThreadSettings() → 管当前会话配置 (mode/context)       │
└─────────────────────────────────────────────────────────────┘
```

#### useThreadChat：URL 与 threadId 同步

**`frontend/src/components/workspace/chats/use-thread-chat.ts`**

```typescript
export function useThreadChat() {
  const { thread_id: threadIdFromPath } = useParams();
  const [threadId, setThreadId] = useState(() => {
    // URL 是 /chats/new 时，前端立刻生成 UUID，不等后端
    return threadIdFromPath === "new" ? uuid() : threadIdFromPath;
  });
```

关键点：
- `/chats/new` → 前端自动生成 UUID
- 发送第一条消息后，`history.replaceState` 改成 `/chats/{UUID}`
- 有 Guard 逻辑防止 Next.js router 返回 stale 的 `"new"` 值

#### useThreadStream：前端的心脏

**`frontend/src/core/threads/hooks.ts`**（第 101-527 行）

核心职责：建立 SSE 长连接、发送消息、合并三层消息、处理各种事件。

##### 底层 useStream（LangGraph SDK）

```typescript
const thread = useStream<AgentThreadState>({
  client: getAPIClient(isMock),
  assistantId: "lead_agent",      // 对应 langgraph.json 的图名
  threadId: onStreamThreadId,
  reconnectOnMount: true,         // 组件挂载自动重连
  fetchStateHistory: { limit: 1 },// 重连只拉最新状态

  onCreated(meta) {
    handleStreamStart(meta.thread_id, meta.run_id);
  },
  onLangChainEvent(event) {
    if (event.event === "on_tool_end") {
      listeners.current.onToolEnd?.({ name: event.name, data: event.data });
    }
  },
  onCustomEvent(event) {
    if (event.type === "task_running") {
      updateSubtask({ id: event.task_id, latestMessage: event.message });
    }
  },
  onUpdateEvent(data) {
    if (data["SummarizationMiddleware.before_model"]) {
      appendMessages(_movedMessages); // 被摘要的旧消息移到历史区
    }
  },
  onFinish(state) {
    listeners.current.onFinish?.(state.values);
    queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
  },
  onError(error) {
    setOptimisticMessages([]);
    toast.error(getStreamErrorMessage(error));
  },
});
```

##### 三层消息合并

```typescript
const mergedMessages = mergeMessages(
  history,            // ← useThreadHistory，旧 run 的消息
  thread.messages,    // ← useStream，当前 run 实时消息
  optimisticMessages, // ← 本地乐观更新
);
```

`mergeMessages` 去重逻辑（第 41-76 行）：

```typescript
function mergeMessages(historyMessages, threadMessages, optimisticMessages) {
  const threadMessageIds = new Set(
    threadMessages.map((m) => m.id || m.tool_call_id).filter(Boolean)
  );

  // 从 history 末尾往前扫描，去掉和 threadMessages 重叠的部分
  let cutoff = historyMessages.length;
  for (let i = historyMessages.length - 1; i >= 0; i--) {
    if (threadMessageIds.has(historyMessages[i].id)) {
      cutoff = i;
    } else {
      break;
    }
  }

  return [
    ...historyMessages.slice(0, cutoff),  // 不重叠的旧历史
    ...threadMessages,                     // 当前实时流
    ...optimisticMessages,                 // 乐观消息
  ];
}
```

##### 乐观更新（Optimistic UI）

用户点击发送后，网络还没到后端，前端已显示消息：

```typescript
const newOptimistic: Message[] = [];
newOptimistic.push({
  type: "human",
  id: `opt-human-${Date.now()}`,  // 临时 ID
  content: text ? [{ type: "text", text }] : "",
});

// 如果有文件，显示"正在上传..."占位
if (optimisticFiles.length > 0) {
  newOptimistic.push({
    type: "ai",
    id: `opt-ai-${Date.now()}`,
    content: "正在上传文件...",
  });
}
setOptimisticMessages(newOptimistic);
```

等后端 SSE 返回真实消息后，`thread.messages.length` 增加，触发 effect 清空乐观消息。

##### sendMessage 完整流程

```typescript
const sendMessage = useCallback(async (threadId, message) => {
  // 1. 防重入
  if (sendInFlightRef.current) return;
  sendInFlightRef.current = true;

  // 2. 显示乐观消息
  setOptimisticMessages([...]);

  // 3. 上传文件（独立 HTTP POST）
  if (message.files?.length > 0) {
    const uploadResponse = await uploadFiles(threadId, files);
    uploadedFileInfo = uploadResponse.files;
    // 乐观消息状态从 "uploading" → "uploaded"
  }

  // 4. 调用 thread.submit() 发送到 LangGraph Server
  await thread.submit(
    {
      messages: [{
        type: "human",
        content: [{ type: "text", text }],
        additional_kwargs: { files: filesForSubmit },
      }],
    },
    {
      threadId,
      streamSubgraphs: true,    // Subagent 事件也流过来
      streamResumable: true,    // 支持断线重连
      config: { recursion_limit: 1000 },
      context: {
        thinking_enabled: context.mode !== "flash",
        is_plan_mode: context.mode === "pro" || context.mode === "ultra",
        subagent_enabled: context.mode === "ultra",
        reasoning_effort: /* 根据 mode 映射 */,
        thread_id: threadId,
        locale,
      },
    },
  );
}, [...]);
```

**mode → 能力映射：**

| mode | thinking | plan_mode (todo) | subagent | reasoning_effort |
|------|----------|------------------|----------|------------------|
| flash | ❌ | ❌ | ❌ | 无 |
| pro | ✅ | ✅ | ❌ | medium |
| ultra | ✅ | ✅ | ✅ | high |

##### SSE 事件分类处理

**LangGraph 标准事件**（`onLangChainEvent`）：
- `on_chat_model_stream` → 模型正在输出 token（逐字显示的来源）
- `on_tool_start/end` → 工具调用开始/结束
- `on_chain_start/end` → Subagent 子图开始/结束

**后端自定义事件**（`onCustomEvent`）：

| 事件类型 | 来源 | 前端表现 |
|---------|------|---------|
| `task_started` | task_tool.py | 显示子任务卡片 |
| `task_running` | task_tool.py | 更新卡片进度日志 |
| `task_completed/failed` | task_tool.py | 卡片标记完成/失败 |
| `llm_retry` | LLM 出错重试 | toast 提示 |

**状态更新事件**（`onUpdateEvent`）：
- `SummarizationMiddleware.before_model` → 把被摘要的旧消息追加到历史区
- `title` 生成 → 更新左侧线程列表的标题

#### useThreadHistory：历史消息分页

```typescript
export function useThreadHistory(threadId: string) {
  const runs = useThreadRuns(threadId);  // 查询该 thread 的所有 run

  const loadMessages = useCallback(async () => {
    const run = runsRef.current[indexRef.current];  // 从最老的 run 开始
    const result = await fetch(
      `/api/threads/${threadId}/runs/${run.run_id}/messages`
    ).then((res) => res.json());

    const _messages = result.data
      .filter((m) => !m.metadata.caller?.startsWith("middleware:"))  // 过滤中间件内部消息
      .map((m) => m.content);

    setMessages((prev) => [..._messages, ...prev]);  // prepend
    indexRef.current -= 1;
  }, []);

  return { messages, hasMore, loadMore: loadMessages, appendMessages };
}
```

关键点：
- 一个 Thread 有多个 Run（用户每次发送消息是一个新 Run）
- 按 **Run 维度分页**，从老到新加载
- 过滤 `caller.startsWith("middleware:")`，不暴露 SummarizationMiddleware 内部调用

### 1.3 Gateway 层详解：从 HTTP 请求到 LangGraph 运行时的完整链路

Gateway 层的设计哲学是**"薄路由 + 厚运行时"**。FastAPI 路由只负责 HTTP 协议解析和参数校验，所有业务逻辑都委托给 `services.py` 和 `deerflow.runtime` 包。

#### 1.3.1 系统启动与依赖注入

**`backend/app/gateway/deps.py`** 是整个 Gateway 的依赖管理中枢。

```python
@asynccontextmanager
async def langgraph_runtime(app: FastAPI):
    async with AsyncExitStack() as stack:
        # 1. StreamBridge — 内存事件总线
        app.state.stream_bridge = await stack.enter_async_context(make_stream_bridge(config))

        # 2. 数据库引擎（SQLite/Postgres）
        await init_engine_from_config(config.database)

        # 3. Checkpointer — LangGraph 状态持久化
        app.state.checkpointer = await stack.enter_async_context(make_checkpointer(config))

        # 4. Store — LangGraph 键值存储
        app.state.store = await stack.enter_async_context(make_store(config))

        # 5. 持久化仓库
        app.state.run_store = RunRepository(sf)
        app.state.feedback_repo = FeedbackRepository(sf)
        app.state.thread_store = make_thread_store(sf, app.state.store)

        # 6. Run 事件存储（用于审计和消息查询）
        app.state.run_event_store = make_run_event_store(run_events_config)

        # 7. RunManager — Run 生命周期管理
        app.state.run_manager = RunManager(store=app.state.run_store)

        yield
```

所有核心组件都是**单例**，挂在 `app.state` 上。Router 通过 `_require("attr")` 工厂函数创建依赖注入器，请求来时从 `app.state` 取出对应实例。

#### 1.3.2 HTTP 路由端点

**`backend/app/gateway/routers/thread_runs.py`** 实现了 LangGraph Platform 兼容的 Runs API：

| 端点 | 方法 | 作用 |
|------|------|------|
| `/{thread_id}/runs` | POST | 创建后台 Run，立即返回 |
| `/{thread_id}/runs/stream` | POST | 创建 Run 并通过 SSE 流式推送事件 |
| `/{thread_id}/runs/wait` | POST | 创建 Run 并阻塞到完成，返回最终状态 |
| `/{thread_id}/runs/{run_id}/cancel` | POST | 取消运行（interrupt 或 rollback） |
| `/{thread_id}/runs/{run_id}/join` | GET | 加入一个已有 Run 的 SSE 流 |
| `/{thread_id}/runs/{run_id}/messages` | GET | 查询某个 Run 的消息记录 |
| `/{thread_id}/messages` | GET | 查询整个 Thread 的消息（跨 Run） |

最核心的是 **`stream_run`**：

```python
@router.post("/{thread_id}/runs/stream")
async def stream_run(thread_id: str, body: RunCreateRequest, request: Request):
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    record = await start_run(body, thread_id, request)

    return StreamingResponse(
        sse_consumer(bridge, record, request, run_mgr),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Location": f"/api/threads/{thread_id}/runs/{record.run_id}",
        },
    )
```

这里做了三件事：
1. **`start_run()`** — 创建 `RunRecord`，启动后台 Agent 任务
2. **`StreamBridge`** — 内存事件总线，解耦 Agent Worker（生产者）和 SSE Endpoint（消费者）
3. **`sse_consumer()`** — 异步生成器，持续从 Bridge 消费事件并格式化为 SSE 帧

#### 1.3.3 start_run：Run 的创建与启动

**`backend/app/gateway/services.py`** 第 230-316 行：

```python
async def start_run(body, thread_id, request) -> RunRecord:
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    run_ctx = get_run_context(request)

    # 1. 并发控制：检查是否有正在运行的 Run
    record = await run_mgr.create_or_reject(
        thread_id,
        body.assistant_id,
        on_disconnect=DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_,
        multitask_strategy=body.multitask_strategy,  # reject / interrupt / rollback
    )

    # 2. 确保 Thread 元数据存在（用于 /threads/search 显示）
    existing = await run_ctx.thread_store.get(thread_id)
    if existing is None:
        await run_ctx.thread_store.create(thread_id, assistant_id=body.assistant_id)
    else:
        await run_ctx.thread_store.update_status(thread_id, "running")

    # 3. 解析 Agent 工厂（始终指向 make_lead_agent）
    agent_factory = resolve_agent_factory(body.assistant_id)

    # 4. 标准化输入（把前端 JSON 转为 LangChain Message 对象）
    graph_input = normalize_input(body.input)

    # 5. 构建 RunnableConfig
    config = build_run_config(thread_id, body.config, body.metadata, assistant_id=body.assistant_id)
    merge_run_context_overrides(config, getattr(body, "context", None))  # 合并 mode/thinking 等

    stream_modes = normalize_stream_modes(body.stream_mode)

    # 6. 创建后台 asyncio.Task 执行 Agent
    task = asyncio.create_task(
        run_agent(
            bridge, run_mgr, record,
            ctx=run_ctx,
            agent_factory=agent_factory,
            graph_input=graph_input,
            config=config,
            stream_modes=stream_modes,
            stream_subgraphs=body.stream_subgraphs,
        )
    )
    record.task = task

    return record
```

##### 并发控制：RunManager.create_or_reject

**`backend/packages/harness/deerflow/runtime/runs/manager.py`** 第 168-232 行：

```python
async def create_or_reject(self, thread_id, assistant_id, *, multitask_strategy="reject"):
    async with self._lock:
        inflight = [r for r in self._runs.values()
                    if r.thread_id == thread_id and r.status in (pending, running)]

        if multitask_strategy == "reject" and inflight:
            raise ConflictError(f"Thread {thread_id} already has an active run")

        if multitask_strategy in ("interrupt", "rollback") and inflight:
            for r in inflight:
                r.abort_event.set()      # 设置取消信号
                r.task.cancel()           # 取消 asyncio Task
                r.status = interrupted

        record = RunRecord(
            run_id=str(uuid.uuid4()),
            thread_id=thread_id,
            status=RunStatus.pending,
            ...
        )
        self._runs[run_id] = record
    return record
```

三种并发策略：

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| **reject** | 如果该 Thread 已有运行中的 Run，直接返回 409 Conflict | 默认策略，防止重复提交 |
| **interrupt** | 取消正在运行的 Run，保留当前 checkpoint，新建 Run | 用户发新消息打断当前思考 |
| **rollback** | 取消正在运行的 Run，回滚到 Run 开始前的 checkpoint | 用户彻底放弃当前操作 |

##### 配置构建：build_run_config

**`backend/app/gateway/services.py`** 第 154-222 行：

```python
def build_run_config(thread_id, request_config, metadata, assistant_id=None):
    config = {"recursion_limit": 100}

    if request_config:
        # LangGraph >= 0.6 用 context 传参， Legacy 用 configurable
        if "context" in request_config:
            config["context"] = dict(request_config["context"])
        else:
            config["configurable"] = {"thread_id": thread_id}
            config["configurable"].update(request_config.get("configurable", {}))

    # 自定义 Agent 名称映射
    if assistant_id and assistant_id != "lead_agent":
        target = config.get("configurable") or config.get("context")
        target["agent_name"] = assistant_id

    if metadata:
        config.setdefault("metadata", {}).update(metadata)
    return config
```

这里处理了 LangGraph 的**配置兼容性**问题：
- LangGraph >= 0.6 推荐使用 `config["context"]` 传递运行时数据
- 但旧代码和某些工具通过 `config["configurable"]` 读取
- DeerFlow 的策略是**两边都写**，确保向后兼容

#### 1.3.4 StreamBridge：内存事件总线

**`backend/packages/harness/deerflow/runtime/stream_bridge/memory.py`**：

```python
class MemoryStreamBridge(StreamBridge):
    def __init__(self, *, queue_maxsize: int = 256):
        self._streams: dict[str, _RunStream] = {}  # run_id → 事件日志
        self._counters: dict[str, int] = {}

    async def publish(self, run_id: str, event: str, data: Any):
        stream = self._get_or_create_stream(run_id)
        entry = StreamEvent(id=self._next_id(run_id), event=event, data=data)
        async with stream.condition:
            stream.events.append(entry)
            if len(stream.events) > self._maxsize:
                overflow = len(stream.events) - self._maxsize
                del stream.events[:overflow]        # 超限时丢弃最旧事件
                stream.start_offset += overflow
            stream.condition.notify_all()

    async def subscribe(self, run_id: str, *, last_event_id: str | None = None):
        stream = self._get_or_create_stream(run_id)
        next_offset = self._resolve_start_offset(stream, last_event_id)

        while True:
            async with stream.condition:
                local_index = next_offset - stream.start_offset
                if 0 <= local_index < len(stream.events):
                    entry = stream.events[local_index]
                    next_offset += 1
                elif stream.ended:
                    entry = END_SENTINEL
                else:
                    await asyncio.wait_for(stream.condition.wait(), timeout=15.0)
                    continue  # 被唤醒后重新检查

            if entry is END_SENTINEL:
                yield END_SENTINEL
                return
            yield entry
```

**StreamBridge 的核心设计：**

| 特性 | 实现 |
|------|------|
| **生产者-消费者解耦** | Agent Worker 调用 `publish()`，SSE Consumer 调用 `subscribe()`，互不阻塞 |
| **事件回放** | 每个 Run 保留最近 256 个事件，支持 `Last-Event-ID` 断线重连 |
| **心跳机制** | Consumer 15 秒没收到事件，自动发送 `: heartbeat` 保持连接 |
| **内存上限** | 超限时丢弃最旧事件，防止内存泄漏 |

#### 1.3.5 sse_consumer：SSE 帧生成

**`backend/app/gateway/services.py`** 第 319-349 行：

```python
async def sse_consumer(bridge, record, request, run_mgr):
    last_event_id = request.headers.get("Last-Event-ID")
    try:
        async for entry in bridge.subscribe(record.run_id, last_event_id=last_event_id):
            if await request.is_disconnected():
                break

            if entry is HEARTBEAT_SENTINEL:
                yield ": heartbeat\n\n"
                continue

            if entry is END_SENTINEL:
                yield format_sse("end", None, event_id=entry.id)
                return

            yield format_sse(entry.event, entry.data, event_id=entry.id)

    finally:
        # on_disconnect 语义
        if record.status in (pending, running):
            if record.on_disconnect == DisconnectMode.cancel:
                await run_mgr.cancel(record.run_id)
```

SSE 帧格式（兼容 LangGraph Platform）：

```
event: metadata
data: {"run_id": "abc", "thread_id": "xyz"}

event: values
data: {"messages": [{"type": "ai", "content": "Hello"}]}

event: messages
data: [{"type": "ai", "content": "Hello"}, {"lc": 1, ...}]

: heartbeat

event: end
data: null

```

#### 1.3.6 run_agent：后台 Worker 执行 LangGraph 图

**`backend/packages/harness/deerflow/runtime/runs/worker.py`** 第 120-393 行。

这是 Gateway 层最复杂的函数，它真正驱动 LangGraph 图执行：

```python
async def run_agent(bridge, run_manager, record, *, ctx, agent_factory, graph_input, config, ...):
    run_id = record.run_id
    thread_id = record.thread_id

    # 1. 标记运行中
    await run_manager.set_status(run_id, RunStatus.running)

    # 2. 捕获 Run 开始前的 checkpoint（用于 rollback）
    ckpt_tuple = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    pre_run_snapshot = copy.deepcopy(ckpt_tuple.checkpoint)

    # 3. 推送 metadata 事件（前端 useStream 需要）
    await bridge.publish(run_id, "metadata", {"run_id": run_id, "thread_id": thread_id})

    # 4. 构建 Agent
    runtime_ctx = _build_runtime_context(thread_id, run_id, config.get("context"), ctx.app_config)
    _install_runtime_context(config, runtime_ctx)

    runnable_config = RunnableConfig(**config)
    agent = agent_factory(config=runnable_config, app_config=ctx.app_config)

    # 5. 附加 checkpointer 和 store
    agent.checkpointer = checkpointer
    agent.store = store

    # 6. 流式执行
    async for chunk in agent.astream(graph_input, config=runnable_config, stream_mode="values"):
        if record.abort_event.is_set():   # 检查取消信号
            break
        await bridge.publish(run_id, "values", serialize(chunk))

    # 7. 最终状态处理
    if record.abort_event.is_set():
        if record.abort_action == "rollback":
            await _rollback_to_pre_run_checkpoint(...)  # 回滚到 pre_run_snapshot
        else:
            await run_manager.set_status(run_id, RunStatus.interrupted)
    else:
        await run_manager.set_status(run_id, RunStatus.success)

    # 8. 收尾工作
    await bridge.publish_end(run_id)          # 通知 StreamBridge 结束
    asyncio.create_task(bridge.cleanup(run_id, delay=60))  # 60秒后清理内存
```

**关键执行步骤解析：**

| 步骤 | 代码 | 作用 |
|------|------|------|
| 捕获快照 | `checkpointer.aget_tuple()` | 保存 Run 开始前的完整状态，支持 rollback |
| 注入 Runtime | `_install_runtime_context()` | 把 `thread_id`, `run_id`, `app_config` 注入 `ToolRuntime.context`，让工具能访问 |
| 回调注入 | `config["callbacks"].append(journal)` | `RunJournal` 监听 LLM 调用，记录 token 使用 |
| 取消检查 | `record.abort_event.is_set()` | 每个 chunk 之间检查，合作式取消 |
| Rollback | `_rollback_to_pre_run_checkpoint()` | 用 `checkpointer.aput()` 把旧 checkpoint 写回去 |
| 标题同步 | `thread_store.update_display_name()` | 从 checkpoint 读取 `title`，同步到线程列表 |

#### 1.3.7 总结：Gateway 层的请求生命周期

现在把 Phase 1.3 的完整链路串联起来：

```
用户点击发送
  ↓
前端 POST /api/threads/{thread_id}/runs/stream
  ↓
FastAPI Router (thread_runs.py::stream_run)
  ├── start_run()
  │   ├── RunManager.create_or_reject()    ← 并发控制
  │   ├── resolve_agent_factory()          ← 定位 make_lead_agent
  │   ├── normalize_input()                ← JSON → LangChain Message
  │   ├── build_run_config()               ← 组装 RunnableConfig
  │   └── asyncio.create_task(run_agent()) ← 启动后台 Worker
  │
  └── StreamingResponse(sse_consumer())
      └── bridge.subscribe(run_id)         ← 订阅内存事件总线
              ↑
run_agent() Worker (后台 asyncio.Task)
  ├── checkpointer.aget_tuple()            ← 捕获 pre-run 快照
  ├── bridge.publish(metadata)             ← 推送 run_id/thread_id
  ├── agent_factory()                      ← 调用 make_lead_agent
  ├── agent.astream()                      ← LangGraph 图执行
  │   └── 每个 chunk → bridge.publish(values, data)
  ├── bridge.publish_end()                 ← 推送结束信号
  └── bridge.cleanup(delay=60)             ← 60秒后释放内存
```

Gateway 层的核心设计要点：

| 设计点 | 源码体现 | 价值 |
|--------|---------|------|
| **薄路由** | `thread_runs.py` 只有 377 行 | HTTP 层只做协议转换，不碰业务逻辑 |
| **单例依赖注入** | `deps.py` 的 `langgraph_runtime()` | 所有组件统一初始化、统一销毁 |
| **内存事件总线** | `MemoryStreamBridge` | 零外部依赖，支持断线重连和事件回放 |
| **Run 状态机** | `RunManager` + `RunRecord` | 精确跟踪每个 Run 的生命周期 |
| **并发策略** | `create_or_reject()` | reject/interrupt/rollback 三种模式 |
| **配置双写** | `build_run_config()` + `merge_run_context_overrides()` | 同时兼容 Legacy `configurable` 和新 `context` |
| **取消与回滚** | `abort_event` + `_rollback_to_pre_run_checkpoint()` | 用户可以随时打断，甚至恢复到之前状态 |

---

## Phase 2: Agent 编排核心 — LangGraph 图与 Lead Agent

### 2.1 LangGraph 配置入口

DeerFlow 使用 LangGraph Platform 的规范配置，在 **`backend/langgraph.json`** 中：

```json
{
  "graphs": {
    "lead_agent": "deerflow.agents:make_lead_agent"
  },
  "checkpointer": {
    "path": "./packages/harness/deerflow/runtime/checkpointer/async_provider.py:make_checkpointer"
  }
}
```

所有用户对话都进入 `lead_agent` 这个图，工厂函数是 **`deerflow.agents.lead_agent.agent:make_lead_agent`**。

### 2.2 Lead Agent 工厂

**`backend/packages/harness/deerflow/agents/lead_agent/agent.py`** (第 318-411 行)

```python
def _make_lead_agent(config: RunnableConfig, *, app_config: AppConfig):
    # 1. 从 runtime config 解析参数
    requested_model_name = cfg.get("model_name") or cfg.get("model")
    is_plan_mode = cfg.get("is_plan_mode", False)
    subagent_enabled = cfg.get("subagent_enabled", False)
    agent_name = validate_agent_name(cfg.get("agent_name"))

    # 2. 加载模型
    model = create_chat_model(name=model_name, thinking_enabled=thinking_enabled, ...)

    # 3. 构建工具列表
    tools = get_available_tools(
        model_name=model_name,
        groups=agent_config.tool_groups if agent_config else None,
        subagent_enabled=subagent_enabled,
    )

    # 4. 构建 Middleware 链
    middleware = _build_middlewares(config, model_name=model_name, agent_name=agent_name)

    # 5. 组装 Prompt
    system_prompt = apply_prompt_template(
        subagent_enabled=subagent_enabled,
        available_skills=...,
        app_config=app_config,
    )

    # 6. 创建 LangGraph Agent
    return create_agent(
        model=model,
        tools=tools,
        middleware=middleware,
        system_prompt=system_prompt,
        state_schema=ThreadState,
    )
```

这是 DeerFlow 的心脏。它用 `langchain.agents.create_agent` 创建了一个**带 Middleware 链的 ReAct 风格 Agent**，状态类型是 `ThreadState`。

### 2.3 Agent 状态定义 ThreadState

**`backend/packages/harness/deerflow/agents/thread_state.py`**：

```python
class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]      # 当前沙箱实例
    thread_data: NotRequired[ThreadDataState | None]  # 工作区路径映射
    title: NotRequired[str | None]                 # 对话标题
    artifacts: Annotated[list[str], merge_artifacts]  # 生成的文件
    todos: NotRequired[list | None]                # 待办列表
    uploaded_files: NotRequired[list[dict] | None] # 用户上传文件
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
```

`ThreadState` 继承自 LangGraph 的 `AgentState`（包含 `messages` 列表），并扩展了 DeerFlow 特有的状态字段。这些字段会在整个对话生命周期中被各种 Middleware 读写。

---

## Phase 3: 工具系统与 Sandbox 执行层

### 3.1 工具加载器

**`backend/packages/harness/deerflow/tools/tools.py`**：

```python
def get_available_tools(groups=None, subagent_enabled=False, ...):
    # 1. 从 config.yaml 加载用户配置的工具
    tool_configs = [tool for tool in config.tools if groups is None or tool.group in groups]
    loaded_tools = [resolve_variable(cfg.use, BaseTool) for cfg in tool_configs]

    # 2. 内置工具
    builtin_tools = [present_file_tool, ask_clarification_tool]
    if subagent_enabled:
        builtin_tools.append(task_tool)      # 子代理委派
    if model_config.supports_vision:
        builtin_tools.append(view_image_tool)

    # 3. MCP 工具（外部 MCP Server）
    mcp_tools = get_cached_mcp_tools()

    # 4. ACP 工具（兼容 ACP 协议的 Agent）
    acp_tools = build_invoke_acp_agent_tool(acp_agents)

    # 5. 去重合并
    all_tools = loaded_tools + builtin_tools + mcp_tools + acp_tools
    return unique_tools
```

工具分四层来源，优先级：**配置工具 > 内置工具 > MCP 工具 > ACP 工具**。

### 3.2 Sandbox 工具

核心工具定义在 **`backend/packages/harness/deerflow/sandbox/tools.py`**：

```python
@tool("bash", parse_docstring=True)
def bash_tool(runtime, description: str, command: str) -> str:
    sandbox = ensure_sandbox_initialized(runtime)
    if is_local_sandbox(runtime):
        # 安全校验：禁止路径穿越
        validate_local_bash_command_paths(command, thread_data)
        # 虚拟路径 → 宿主机真实路径
        command = replace_virtual_paths_in_command(command, thread_data)
        # 自动 cd 到 workspace
        command = _apply_cwd_prefix(command, thread_data)
        # 执行
        output = sandbox.execute_command(command)
        # 输出截断 + 路径脱敏
        return _truncate_bash_output(mask_local_paths_in_output(output, thread_data), max_chars)

@tool("read_file", parse_docstring=True)
def read_file_tool(runtime, file_path: str) -> str:
    content = sandbox.read_file(resolved_path)
    return _truncate_read_file_output(content, max_chars)

@tool("ls", parse_docstring=True)
def ls_tool(runtime, path: str, max_depth: int = 2) -> str:
    entries = sandbox.list_dir(resolved_path, max_depth)
    return _truncate_ls_output(formatted, max_chars)
```

### 3.3 Sandbox 执行模式

DeerFlow 支持两种 Sandbox 执行后端：

| 模式 | 类 | 执行方式 | 适用场景 |
|------|-----|---------|---------|
| **LocalSandbox** | `deerflow.sandbox.local:LocalSandboxProvider` | `subprocess.run([shell, "-c", command])` | 本地开发，直接执行在宿主机 |
| **AioSandbox** | `deerflow.community.aio_sandbox:AioSandboxProvider` | HTTP API → Docker 容器 | 生产环境，真正的进程隔离 |

**LocalSandbox 执行代码** (`local/local_sandbox.py` 第 300-337 行)：

```python
def execute_command(self, command: str) -> str:
    resolved_command = self._resolve_paths_in_command(command)
    shell = self._get_shell()  # /bin/zsh → /bin/bash → /bin/sh

    result = subprocess.run(
        [shell, "-c", resolved_command],
        shell=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    output = result.stdout
    if result.stderr:
        output += f"\nStd Error:\n{result.stderr}"
    return self._reverse_resolve_paths_in_output(output)
```

**AioSandbox 执行代码** (`community/aio_sandbox/aio_sandbox.py` 第 57-87 行)：

```python
def execute_command(self, command: str) -> str:
    with self._lock:  # 串行执行，防止 shell session  corruption
        result = self._client.shell.exec_command(
            command=command,
            no_change_timeout=600
        )
        output = result.data.output if result.data else ""
        return output
```

AioSandbox 通过锁实现了**单 session 串行执行**，避免并发命令污染同一个 shell 环境。

---

## Phase 4: Subagent 委派与并发执行

当 Lead Agent 遇到复杂任务时，会调用 **`task` 工具** 委派给 Subagent。这是 DeerFlow "Super Agent Harness" 定位的核心体现。

### 4.1 Task 工具

**`backend/packages/harness/deerflow/tools/builtins/task_tool.py`** (第 51-95 行)：

```python
@tool("task", parse_docstring=True)
async def task_tool(runtime, description: str, prompt: str, subagent_type: str, ...):
    # 1. 获取 subagent 配置
    config = get_subagent_config(subagent_type)

    # 2. 准备工具（继承父 agent 的 tool_groups，但禁用 subagent 防止嵌套）
    tools = get_available_tools(
        model_name=effective_model,
        groups=parent_tool_groups,
        subagent_enabled=False,  # 禁止递归
    )

    # 3. 创建执行器
    executor = SubagentExecutor(
        config=config,
        tools=tools,
        sandbox_state=sandbox_state,   # 继承父 sandbox
        thread_data=thread_data,       # 继承父 thread_data
        thread_id=thread_id,
        trace_id=trace_id,
    )

    # 4. 异步执行 + 轮询
    task_id = executor.execute_async(prompt, task_id=tool_call_id)

    # 5. 每 5 秒轮询，实时推送 task_running 事件到前端
    while True:
        result = get_background_task_result(task_id)
        if result.status == SubagentStatus.COMPLETED:
            return f"Task Succeeded. Result: {result.result}"
        elif result.status == SubagentStatus.FAILED:
            return f"Task failed. Error: {result.error}"
        await asyncio.sleep(5)
```

### 4.2 Subagent 执行引擎

**`backend/packages/harness/deerflow/subagents/executor.py`**：

`SubagentExecutor` 在一个**独立的持久 Event Loop + ThreadPool** 中运行，避免阻塞父 Agent 的事件循环。

```python
class SubagentExecutor:
    def _create_agent(self):
        model = create_chat_model(name=self.model_name, ...)
        middlewares = build_subagent_runtime_middlewares(...)
        return create_agent(model=model, tools=self.tools, middleware=middlewares, ...)

    async def _aexecute(self, task: str, result_holder: SubagentResult):
        agent = self._create_agent()
        state = await self._build_initial_state(task)  # 加载 skill + task

        async for chunk in agent.astream(state, config=..., stream_mode="values"):
            # 合作式取消检查
            if result_holder.cancel_event.is_set():
                result_holder.status = SubagentStatus.CANCELLED
                return

            # 收集 AI 消息用于前端实时展示
            messages = chunk.get("messages", [])
            if messages and isinstance(messages[-1], AIMessage):
                result_holder.ai_messages.append(messages[-1].model_dump())

        # 提取最终结果
        result_holder.result = extract_final_message(...)
        result_holder.status = SubagentStatus.COMPLETED
```

Subagent 与 Lead Agent 共享：
- **Sandbox 状态**（同一工作区）
- **ThreadData**（同一文件系统挂载）
- **工具集**（但禁用了 task 工具防止无限递归）
- **Trace ID**（分布式追踪）

---

## Phase 5: Middleware 链 — 上下文工程的核心

DeerFlow 最强大的设计之一是它的 **AgentMiddleware 链**。这不是简单的装饰器，而是**在 LangGraph 的每次迭代前后介入**，对状态、消息、工具调用进行深加工。

### 5.1 Middleware 架构总览

DeerFlow 的中间件系统基于 LangChain 的 `AgentMiddleware` 抽象基类。每个中间件通过重写特定的 **hook 方法** 来介入 Agent 执行的生命周期。

#### AgentMiddleware 提供的 Hook 点

| Hook 方法 | 触发时机 | 典型用途 |
|-----------|---------|---------|
| `before_agent(state, runtime)` | **Agent 执行开始前**（每个 Run 一次） | 初始化目录、获取沙箱、设置状态 |
| `after_agent(state, runtime)` | **Agent 执行结束后**（每个 Run 一次） | 释放资源、队列记忆更新 |
| `before_model(state, runtime)` | **每次调用 LLM 之前** | 注入上下文、摘要压缩、注入提醒 |
| `after_model(state, runtime)` | **每次调用 LLM 之后** | 生成标题、限制工具调用、检测循环 |
| `wrap_model_call(request, handler)` | **包装 LLM 调用本身** | 重试逻辑、熔断器、过滤工具 schema |
| `wrap_tool_call(request, handler)` | **包装单个工具调用** | 安全审计、护栏、错误处理、拦截澄清 |

#### 在一个 ReAct 循环中的插入位置

```
┌─────────────────────────────────────────────────────────────────────┐
│  Agent 一次迭代（Turn）                                               │
│                                                                     │
│  before_agent ──► [仅首次迭代触发]                                    │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │ before_model│ ◄── 各中间件依次介入：注入记忆、todo提醒、图片等      │
│  └─────────────┘                                                    │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │wrap_model   │ ◄── LLMErrorHandling：重试+熔断                     │
│  │_call        │     DanglingToolCall：修复历史                       │
│  └─────────────┘     DeferredToolFilter：过滤延迟工具 schema          │
│       │                                                             │
│       ▼                                                             │
│    LLM 推理 → 输出 AIMessage（可能含 tool_calls）                     │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │ after_model │ ◄── SubagentLimit：截断超额 task 调用               │
│  └─────────────┘     LoopDetection：检测循环                         │
│       │              Title：生成标题                                 │
│       ▼              Todo：防止未完成时退出                           │
│  是否有 tool_calls？                                                 │
│       │                                                             │
│   是 ─┴─► 遍历每个 tool_call                                         │
│              │                                                      │
│              ▼                                                      │
│         ┌─────────────┐                                             │
│         │wrap_tool_   │ ◄── Guardrail：内容安全策略                 │
│         │call         │     SandboxAudit：bash 命令审计               │
│         └─────────────┘     ToolErrorHandling：异常转错误消息         │
│              │           Clarification：拦截澄清请求                  │
│              ▼                                                      │
│         执行工具（bash/read_file/task 等）                            │
│              │                                                      │
│              ▼                                                      │
│         生成 ToolMessage                                            │
│              │                                                      │
│              └───────► 进入下一次迭代（before_model → ...）          │
│                                                                     │
│  after_agent ──► [Run 结束时触发]                                    │
└─────────────────────────────────────────────────────────────────────┘
```

#### 中间件链的组装机制

中间件链由两个工厂函数组装：

1. **`_build_runtime_middlewares()`** (`tool_error_handling_middleware.py` 第 70-126 行)：构建**所有 Agent 共享的基础中间件**（Lead Agent 和 Subagent 都用）
2. **`_build_middlewares()`** (`lead_agent/agent.py` 第 238-308 行）：在基础链之上追加 **Lead Agent 特有的中间件**

两者组合后的完整顺序如下：

```
[0]   ThreadDataMiddleware          ─ 基础链
[1]   UploadsMiddleware               ─ 基础链（仅 Lead Agent）
[2]   SandboxMiddleware               ─ 基础链
[3]   DanglingToolCallMiddleware      ─ 基础链
[4]   LLMErrorHandlingMiddleware      ─ 基础链
[5]   GuardrailMiddleware             ─ 基础链（可选，配置启用）
[6]   SandboxAuditMiddleware          ─ 基础链
[7]   ToolErrorHandlingMiddleware     ─ 基础链
[8]   SummarizationMiddleware         ─ Lead 追加（可选）
[9]   TokenUsageMiddleware            ─ Lead 追加（可选）
[10]  TodoMiddleware                  ─ Lead 追加（plan_mode 时）
[11]  TitleMiddleware                 ─ Lead 追加
[12]  MemoryMiddleware                ─ Lead 追加
[13]  ViewImageMiddleware             ─ Lead 追加（vision 时）
[14]  DeferredToolFilterMiddleware    ─ Lead 追加（tool_search 时）
[15]  SubagentLimitMiddleware         ─ Lead 追加（subagent 时）
[16]  LoopDetectionMiddleware         ─ Lead 追加
[17]  ClarificationMiddleware         ─ Lead 追加（ always last）
```

---

### 5.2 逐个 Middleware 深度解析

以下按照实际组装顺序，逐一讲解每个中间件的**插入位置**、**实现的 hook**、**核心原理**和**源码细节**。

---

#### [0] ThreadDataMiddleware — 线程目录初始化

**源码位置**：`agents/middlewares/thread_data_middleware.py`

**实现 Hook**：`before_agent`

**插入位置**：链的最前端。必须在 SandboxMiddleware 之前执行，因为后续中间件需要 `thread_id` 来定位目录。

**核心原理**：

```python
def before_agent(self, state, runtime):
    thread_id = runtime.context.get("thread_id")
    user_id = get_effective_user_id()

    if self._lazy_init:
        # 懒加载：只计算路径，不创建目录（等真正需要时再创建）
        paths = self._get_thread_paths(thread_id, user_id)
    else:
        # 立即创建：workspace / uploads / outputs
        paths = self._create_thread_directories(thread_id, user_id)

    # 同时给最后一条 HumanMessage 打上 run_id + 时间戳
    messages = list(state.get("messages", []))
    if last_message and isinstance(last_message, HumanMessage):
        messages[-1] = HumanMessage(
            content=last_message.content,
            additional_kwargs={
                **last_message.additional_kwargs,
                "run_id": runtime.context.get("run_id"),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    return {
        "thread_data": {**paths},
        "messages": messages,
    }
```

**创建的目录结构**：
```
{base_dir}/threads/{thread_id}/user-data/workspace   ← 工作区
{base_dir}/threads/{thread_id}/user-data/uploads     ← 用户上传文件
{base_dir}/threads/{thread_id}/user-data/outputs     ← Agent 输出文件
```

**关键点**：
- `lazy_init=True`（默认）：首次调用时只计算虚拟路径，目录在第一次真正被访问时才创建，避免空 run 的磁盘 IO。
- 给 `HumanMessage` 附加 `run_id` 和 `timestamp`，方便后续审计和前端展示。

---

#### [1] UploadsMiddleware — 上传文件上下文注入

**源码位置**：`agents/middlewares/uploads_middleware.py`

**实现 Hook**：`before_agent`

**插入位置**：ThreadDataMiddleware 之后、SandboxMiddleware 之前。需要 thread_id 来定位 uploads 目录。

**核心原理**：

读取当前消息中的上传文件元数据（`additional_kwargs.files`），并扫描历史 uploads 目录，将所有文件信息格式化为 `<uploaded_files>` 块，**prepend 到最后一条 HumanMessage 的内容中**。

```python
def before_agent(self, state, runtime):
    last_message = messages[-1]
    # 1. 从当前消息的 additional_kwargs.files 提取新上传文件
    new_files = self._files_from_kwargs(last_message, uploads_dir)

    # 2. 扫描 uploads 目录，收集历史文件（排除当前新文件）
    historical_files = []
    for file_path in sorted(uploads_dir.iterdir()):
        if file_path.name not in new_filenames:
            outline, preview = _extract_outline_for_file(file_path)
            historical_files.append({...})

    # 3. 构建 <uploaded_files> 消息块
    files_message = self._create_files_message(new_files, historical_files)

    # 4. prepend 到最后一条 HumanMessage
    updated_content = f"{files_message}\n\n{original_content}"
    messages[-1] = HumanMessage(content=updated_content, ...)

    return {"uploaded_files": new_files, "messages": messages}
```

**文件大纲提取**：如果上传的是文档（如 PDF、Word），上传管道会将其转换为同名的 `.md` 文件。UploadsMiddleware 会读取该 `.md` 文件：
- 如果有标题结构，提取 `outline`（`[{title, line}, ...]`）
- 如果没有标题，提取前 5 行作为 `preview`

这样模型就知道文件里有什么，应该用 `read_file` 读哪一部分。

---

#### [2] SandboxMiddleware — 沙箱生命周期管理

**源码位置**：`sandbox/middleware.py`

**实现 Hook**：`before_agent`（eager 模式）、`after_agent`

**插入位置**：UploadsMiddleware 之后。确保 thread_data 目录已就绪，再获取沙箱。

**核心原理**：

```python
def before_agent(self, state, runtime):
    if self._lazy_init:
        return  # 懒加载：等第一次工具调用时再获取

    if "sandbox" not in state or state["sandbox"] is None:
        thread_id = runtime.context.get("thread_id")
        sandbox_id = self._acquire_sandbox(thread_id)
        return {"sandbox": {"sandbox_id": sandbox_id}}

def after_agent(self, state, runtime):
    sandbox = state.get("sandbox")
    if sandbox is not None:
        sandbox_id = sandbox["sandbox_id"]
        get_sandbox_provider().release(sandbox_id)
```

**关键点**：
- `lazy_init=True`（默认）：沙箱不在 `before_agent` 中创建，而是延迟到**第一次 bash/read_file 等工具调用**时才获取。这避免了无工具调用的纯对话 Run 浪费沙箱资源。
- 同一个 Thread 的多次迭代**复用同一个沙箱实例**（通过 `sandbox_id` 关联），保证文件系统状态连续性。
- Run 结束时在 `after_agent` 中释放沙箱。

---

#### [3] DanglingToolCallMiddleware — 修复畸形历史

**源码位置**：`agents/middlewares/dangling_tool_call_middleware.py`

**实现 Hook**：`wrap_model_call` / `awrap_model_call`

**插入位置**：LLM 调用之前。

**为什么要用 `wrap_model_call` 而不是 `before_model`**：

如果用 `before_model` 返回 `{messages: [...]}`，LangGraph 的 `add_messages` reducer 会把新消息**追加到列表末尾**。但我们需要把 `ToolMessage` **插入到对应的 `AIMessage` 之后**（即历史中间），追加到末尾会破坏消息顺序。

`wrap_model_call` 直接修改 `ModelRequest.messages` 数组，可以精确控制插入位置。

**核心原理**：

```python
def wrap_model_call(self, request, handler):
    patched = self._build_patched_messages(request.messages)
    if patched is not None:
        request = request.override(messages=patched)
    return handler(request)

def _build_patched_messages(self, messages):
    # 收集所有已有 ToolMessage 的 tool_call_id
    existing_tool_msg_ids = {msg.tool_call_id for msg in messages if isinstance(msg, ToolMessage)}

    # 扫描每个 AIMessage，检查其 tool_calls 是否都有对应的 ToolMessage
    for msg in messages:
        if msg.type != "ai":
            continue
        for tc in msg.tool_calls:
            if tc["id"] not in existing_tool_msg_ids:
                # 在 AIMessage 之后插入伪造的 ToolMessage
                patched.insert_after(msg, ToolMessage(
                    content="[Tool call was interrupted and did not return a result.]",
                    tool_call_id=tc["id"],
                    status="error",
                ))
```

**触发场景**：
- 用户在中途取消 Run（前端断开 SSE）
- 工具执行时进程崩溃
- 网络超时导致 ToolMessage 丢失

没有 DanglingToolCallMiddleware，LLM 会收到 "tool_calls 缺少对应 ToolMessage" 的报错，整个 Run 失败。

---

#### [4] LLMErrorHandlingMiddleware — LLM 错误重试与熔断

**源码位置**：`agents/middlewares/llm_error_handling_middleware.py`

**实现 Hook**：`wrap_model_call` / `awrap_model_call`

**插入位置**：包装每次 LLM 调用。

**核心原理**：这是一个**带熔断器（Circuit Breaker）的指数退避重试器**。

```python
def wrap_model_call(self, request, handler):
    # 1. 检查熔断器状态
    if self._check_circuit():
        return AIMessage(content=" Circuit breaker is engaged...")

    attempt = 1
    while True:
        try:
            response = handler(request)
            self._record_success()  # 重置熔断器
            return response
        except Exception as exc:
            retriable, reason = self._classify_error(exc)
            if retriable and attempt < self.retry_max_attempts:
                # 2. 指数退避等待
                wait_ms = self._build_retry_delay_ms(attempt, exc)
                self._emit_retry_event(attempt, wait_ms, reason)  # 推送 llm_retry 事件到前端
                time.sleep(wait_ms / 1000)
                attempt += 1
                continue

            # 3. 不可恢复错误，记录熔断器并返回友好错误消息
            if retriable:
                self._record_failure()
            return AIMessage(content=self._build_user_message(exc, reason))
```

**错误分类逻辑**：

| 错误类型 | 判断依据 | 是否重试 |
|---------|---------|---------|
| **瞬态错误** | `APITimeoutError`, `APIConnectionError`, status 429/502/503, 包含 "server busy" / "服务繁忙" | ✅ 是 |
| **配额耗尽** | 包含 "quota", "billing", "余额不足" | ❌ 否 |
| **认证失败** | 包含 "unauthorized", "invalid api key", "未授权" | ❌ 否 |
| **其他** | 其他异常 | ❌ 否 |

**熔断器状态机**：

```
Closed（正常） ──► 连续失败达到 threshold ──► Open（熔断，快速失败）
  ▲                                              │
  │                                              │
  └── 恢复超时后 probing 成功 ─────────────────┘
```

- `failure_threshold`（默认 5 次）：连续失败多少次后熔断
- `recovery_timeout_sec`（默认 60 秒）：熔断后多久允许一次探测请求

**前端事件**：每次重试时通过 `get_stream_writer()` 推送 `{"type": "llm_retry", "attempt": 1, ...}`，前端显示 toast 提示。

---

#### [5] GuardrailMiddleware — 内容安全护栏

**源码位置**：`guardrails/middleware.py`

**实现 Hook**：`wrap_tool_call` / `awrap_tool_call`

**插入位置**：每个工具调用执行前。

**核心原理**：

```python
def wrap_tool_call(self, request, handler):
    # 构建 Guardrail 请求
    gr = GuardrailRequest(
        tool_name=request.tool_call["name"],
        tool_input=request.tool_call["args"],
        agent_id=self.passport,
    )

    try:
        decision = self.provider.evaluate(gr)
    except Exception:
        if self.fail_closed:
            decision = Deny  # _PROVIDER 异常时默认拒绝_
        else:
            return handler(request)

    if not decision.allow:
        return ToolMessage(content="Guardrail denied: ...", status="error")

    return handler(request)
```

**设计要点**：
- `fail_closed=True`（默认）：Provider 异常时**默认拒绝**，宁可误杀也不放行。
- Provider 是可插拔的（通过 `config.yaml` 配置），内置有基于 allowlist 的简单实现。
- 只拦截**工具调用**，不审查 LLM 的文本输出（那是 GuardrailMiddleware 上层或模型层面的事）。

---

#### [6] SandboxAuditMiddleware — Bash 命令安全审计

**源码位置**：`agents/middlewares/sandbox_audit_middleware.py`

**实现 Hook**：`wrap_tool_call` / `awrap_tool_call`

**插入位置**：GuardrailMiddleware 之后、ToolErrorHandlingMiddleware 之前。

**核心原理**：这是一个**专门针对 `bash` 工具**的安全审计中间件。它不拦截其他工具。

```python
def wrap_tool_call(self, request, handler):
    if request.tool_call.get("name") != "bash":
        return handler(request)  # 只审计 bash

    command, thread_id, verdict, reject_reason = self._pre_process(request)

    if verdict == "block":
        return ToolMessage(content="Command blocked: ...", status="error")

    result = handler(request)  # 执行命令

    if verdict == "warn":
        result = self._append_warn_to_result(result, command)

    return result
```

**两层分类策略**：

1. **输入消毒**（`_validate_input`）：
   - 空命令、超过 10,000 字符、包含 `\x00` null 字节 → 直接 block

2. **命令分类**（`_classify_command`）：
   - **整命令扫描**：先对整条命令（不拆分）匹配高危模式，防止 `while true; do bash & done` 这类跨语句攻击被拆分后漏检。
   - **子命令拆分**：按 `;` / `&&` / `||` 拆分复合命令（**引号感知**，防止 `";rm -rf /"` 被误拆），逐条匹配。

**高风险（block）规则示例**：

| 模式 | 说明 |
|------|------|
| `rm -rf /` | 递归删除根目录 |
| `\| (ba)?sh\b` | 管道到 shell（curl \| sh） |
| `$\(?\s*(curl\|wget\|bash)` | 命令替换执行远程代码 |
| `base64 .* -d .* \|` | base64 解码后执行 |
| `>+\s*/etc/` | 覆盖系统配置文件 |
| `/dev/tcp/` | bash 内置网络（绕过工具白名单） |
| `fork bomb` | `:(){ :\|:& };:` 等 |

**中风险（warn）规则示例**：`pip install`、`apt install`、`chmod 777`、`sudo`

中风险命令**允许执行**，但在返回结果中追加警告文本，让模型意识到自己在修改环境。

**审计日志**：每条 bash 命令都会以结构化 JSON 形式写入日志：
```json
{"timestamp": "2026-05-19T13:14:09Z", "thread_id": "abc", "command": "ls -la", "verdict": "pass"}
```

---

#### [7] ToolErrorHandlingMiddleware — 工具异常兜底

**源码位置**：`agents/middlewares/tool_error_handling_middleware.py`

**实现 Hook**：`wrap_tool_call` / `awrap_tool_call`

**插入位置**：SandboxAuditMiddleware 之后。这是工具调用异常前的**最后一道防线**。

**核心原理**：

```python
def wrap_tool_call(self, request, handler):
    try:
        return handler(request)
    except GraphBubbleUp:
        raise  # LangGraph 控制流信号（interrupt/pause/resume）必须透传
    except Exception as exc:
        logger.exception("Tool execution failed")
        return self._build_error_message(request, exc)

def _build_error_message(self, request, exc):
    detail = str(exc).strip()[:500]
    return ToolMessage(
        content=f"Error: Tool '{tool_name}' failed with {exc.__class__.__name__}: {detail}. Continue with available context...",
        tool_call_id=tool_call_id,
        status="error",
    )
```

**为什么需要它**：如果 `bash` 命令抛出异常（如文件不存在、权限不足），没有 ToolErrorHandlingMiddleware，整个 LangGraph Run 会崩溃。有了它，异常被捕获并转换为一条 `status="error"` 的 `ToolMessage`，模型可以看到错误信息并决定下一步怎么做（比如换个路径重试）。

**注意**：`GraphBubbleUp` 必须 `re-raise`，否则 LangGraph 的 interrupt/ resume 机制会失效。

---

#### [8] SummarizationMiddleware — 超长上下文摘要压缩

**源码位置**：`agents/middlewares/summarization_middleware.py`

**实现 Hook**：`before_model` / `abefore_model`

**插入位置**：基础链之后、Lead Agent 特有中间件之前。尽早压缩，让后续中间件和模型都受益。

**核心原理**：继承自 LangChain 的 `SummarizationMiddleware`，DeerFlow 扩展为 `DeerFlowSummarizationMiddleware`。

```python
def before_model(self, state, runtime):
    messages = state["messages"]
    total_tokens = self.token_counter(messages)

    if not self._should_summarize(messages, total_tokens):
        return None  # 未触发阈值，不压缩

    cutoff_index = self._determine_cutoff_index(messages)
    messages_to_summarize, preserved = self._partition_with_skill_rescue(messages, cutoff_index)

    # 摘要前执行 hook（如把记忆刷盘）
    self._fire_hooks(messages_to_summarize, preserved, runtime)

    # 用轻量模型生成摘要
    summary = self._create_summary(messages_to_summarize)

    # 清空旧消息，插入摘要 + 保留消息
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),  # 标记删除所有旧消息
            *new_messages,  # 摘要消息（HumanMessage，name="summary"）
            *preserved,     # 保留的近期消息
        ]
    }
```

**Skill Rescue 机制**：

这是一个 DeerFlow 特有的优化。模型经常通过 `read_file` 读取技能文件（如 `/mnt/skills/python.md`），如果摘要时把这些技能读取记录也压缩掉了，模型就忘记自己读过什么技能。

Skill Rescue 的逻辑：
1. 在 `to_summarize` 的消息中，找出最近通过 `read_file` 读取 `/mnt/skills/` 下文件的 AIMessage + ToolMessage 组合（称为 Skill Bundle）
2. 如果该 bundle 的 token 数不超过预算，把它**从 to_summarize 移到 preserved**
3. 这样模型始终记得自己加载过哪些技能

**摘要消息的特殊处理**：
```python
def _build_new_messages(self, summary):
    return [HumanMessage(
        content=f"Here is a summary of the conversation to date:\n\n{summary}",
        name="summary",  # 前端会忽略 name="summary" 的消息，不展示给用户
    )]
```

**触发条件**（来自 `config.yaml`）：
- `trigger`：token 数或消息数达到阈值
- `keep`：保留最近 N 条消息 + 所有系统消息
- `trim_tokens_to_summarize`：摘要前截断超长单条消息

---

#### [9] TokenUsageMiddleware — Token 使用记录

**源码位置**：`agents/middlewares/token_usage_middleware.py`

**实现 Hook**：`after_model` / `aafter_model`

**插入位置**：SummarizationMiddleware 之后。

**核心原理**：

```python
def after_model(self, state, runtime):
    last = messages[-1]  # 刚产生的 AIMessage
    usage = getattr(last, "usage_metadata", None)
    if usage:
        logger.info("LLM token usage: input=%s output=%s total=%s",
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("total_tokens"),
        )
```

非常简单：每次 LLM 调用后，从 `AIMessage.usage_metadata` 中读取 token 使用量并记录到日志。用于成本审计和性能监控。

---

#### [10] TodoMiddleware — 待办列表管理

**源码位置**：`agents/middlewares/todo_middleware.py`

**实现 Hook**：`before_model` / `after_model`

**插入位置**：TitleMiddleware 之前（因为 Todo 的约束应该在标题生成之前介入）。

**核心原理**：继承自 LangChain 的 `TodoListMiddleware`，扩展了两个关键能力：

**能力一：上下文丢失检测（`before_model`）**

当 `SummarizationMiddleware` 压缩历史后，原来的 `write_todos` 工具调用可能被 scroll out。此时模型不知道还有 todo 没完成。TodoMiddleware 检测这种情况并注入提醒：

```python
def before_model(self, state, runtime):
    todos = state.get("todos", [])
    if not todos:
        return None

    # 检查消息历史中是否还有 write_todos 的踪迹
    if _todos_in_messages(messages):
        return None  # 还在上下文中，无需提醒

    if _reminder_in_messages(messages):
        return None  # 已经注入过提醒，还没被压缩掉

    # 注入 todo_reminder HumanMessage
    return {"messages": [HumanMessage(
        name="todo_reminder",
        content="<system_reminder>Your todo list from earlier is no longer visible... {formatted_todos}</system_reminder>",
    )]}
```

**能力二：防止提前退出（`after_model`）**

当模型产生没有 `tool_calls` 的 AIMessage（意味着它想结束回答），但 `todos` 中还有未完成的条目时，TodoMiddleware 会：

```python
def after_model(self, state, runtime):
    # 1. 调用父类逻辑（检测并行 write_todos）
    base_result = super().after_model(state, runtime)
    if base_result is not None:
        return base_result

    # 2. 模型想退出（无 tool_calls）？
    last_ai = ...
    if not last_ai or last_ai.tool_calls:
        return None  # 还有工具要调，不管

    # 3. 还有未完成的 todo？
    todos = state.get("todos", [])
    if not todos or all_completed:
        return None

    # 4. 已达提醒上限？防止无限循环
    if _completion_reminder_count(messages) >= self._MAX_COMPLETION_REMINDERS:
        return None  # 允许退出，不再强制

    # 5. 强制跳回 model 节点，并注入提醒
    return {
        "jump_to": "model",
        "messages": [HumanMessage(
            name="todo_completion_reminder",
            content="<system_reminder>You have incomplete todo items... Please continue working.</system_reminder>",
        )]
    }
```

`jump_to: "model"` 是 LangGraph 的 **Command** 机制，直接让图跳回 model 节点重新调用 LLM，不经过工具执行。

---

#### [11] TitleMiddleware — 自动生成对话标题

**源码位置**：`agents/middlewares/title_middleware.py`

**实现 Hook**：`after_model` / `aafter_model`

**插入位置**：MemoryMiddleware 之前。先生成标题，再更新线程元数据。

**核心原理**：

```python
def after_model(self, state, runtime):
    if not self._should_generate_title(state):
        return None

    # 同步路径：直接返回 fallback 标题（用户消息截断）
    return self._generate_title_result(state)

async def aafter_model(self, state, runtime):
    if not self._should_generate_title(state):
        return None

    # 异步路径：调用轻量模型生成标题
    try:
        model = create_chat_model(name=config.model_name or default, thinking_enabled=False)
        model = model.with_config(tags=["middleware:title"])  # 标记为中间件调用
        response = await model.ainvoke(prompt, config=self._get_runnable_config())
        title = self._parse_title(response.content)
        if title:
            return {"title": title}
    except Exception:
        pass

    # 失败 fallback：用用户消息前 50 字符
    return {"title": self._fallback_title(user_msg)}
```

**触发条件**：
- `config.enabled` 为 True
- `state.title` 尚为空
- 消息历史中至少有 1 条 human + 1 条 assistant（即第一次完整交互后）

**为什么用 `after_model`**：标题需要基于用户消息和模型的第一次回复来生成，所以在模型输出之后判断最合适。

**RunJournal 标记**：通过 `tags=["middleware:title"]` 让 RunJournal 把这些 LLM 调用识别为中间件行为，不计入 `lead_agent` 的 token 消耗统计。

---

#### [12] MemoryMiddleware — 长期记忆队列

**源码位置**：`agents/middlewares/memory_middleware.py`

**实现 Hook**：`after_agent`

**插入位置**：TitleMiddleware 之后。

**核心原理**：MemoryMiddleware **不在每次迭代中直接注入记忆**，而是在整个 Run 结束后把对话加入**异步队列**，由后台进程批量处理。

```python
def after_agent(self, state, runtime):
    # 1. 过滤消息：只保留 human 和 ai，去掉 tool_calls
    filtered_messages = filter_messages_for_memory(messages)

    # 2. 检测用户是否在进行"纠正"或"强化"
    correction_detected = detect_correction(filtered_messages)
    reinforcement_detected = detect_reinforcement(filtered_messages)

    # 3. 加入记忆队列（带 debounce）
    queue = get_memory_queue()
    queue.add(
        thread_id=thread_id,
        messages=filtered_messages,
        agent_name=self._agent_name,
        user_id=user_id,
        correction_detected=correction_detected,
        reinforcement_detected=reinforcement_detected,
    )
```

**为什么用 `after_agent` 而不是 `after_model`**：
- 记忆更新不需要实时，而且涉及 LLM 总结（消耗 token），放在每次迭代太浪费。
- 等整个 Run 结束后一次性处理更合理。

**记忆队列的 debounce 机制**：队列使用 `threading.Timer`，如果同一个 thread 在 N 秒内多次被加入，会合并为一次处理，避免高频写入。

**纠正/强化检测**：如果用户说 "不对，应该是 XXX"，系统会标记 `correction_detected=True`，记忆更新时会优先覆盖旧记忆；如果是 "你说得对"，则标记 `reinforcement_detected=True`，强化已有记忆。

---

#### [13] ViewImageMiddleware — Vision 图片注入

**源码位置**：`agents/middlewares/view_image_middleware.py`

**实现 Hook**：`before_model` / `abefore_model`

**插入位置**：LLM 调用之前。需要在模型看到图片内容之前注入。

**核心原理**：

当模型调用 `view_image` 工具读取图片后，ViewImageMiddleware 在下一次 `before_model` 时检查：

```python
def before_model(self, state, runtime):
    # 1. 最后一条 AIMessage 是否包含 view_image tool_calls？
    last_ai = self._get_last_assistant_message(messages)
    if not self._has_view_image_tool(last_ai):
        return None

    # 2. 所有 view_image 调用是否都已完成（有 ToolMessage）？
    if not self._all_tools_completed(messages, last_ai):
        return None  # 还有图片没加载完，等下次

    # 3. 是否已经注入过图片详情消息？
    if already_injected:
        return None

    # 4. 构建多模态消息（text + image_url）
    content_blocks = [
        {"type": "text", "text": "Here are the images you've viewed:"},
        {"type": "text", "text": "\n- **image.png** (image/png)"},
        {"type": "image_url", "image_url": {"url": "https://.../api/threads/{thread_id}/files/image/..."}},
    ]

    return {"messages": [HumanMessage(content=content_blocks)]}
```

**关键点**：
- 不直接内联 base64（省 token），而是构造 HTTP URL 让模型通过 `image_url` 方式访问。
- 使用 `APP_BASE_URL` 环境变量构建图片访问 URL。
- 只注入一次：检测消息历史中是否已有 `"Here are the images you've viewed"` 开头的 HumanMessage。

---

#### [14] DeferredToolFilterMiddleware — 延迟工具过滤

**源码位置**：`agents/middlewares/deferred_tool_filter_middleware.py`

**实现 Hook**：`wrap_model_call` + `wrap_tool_call`

**插入位置**：模型绑定工具和工具执行两层。

**核心原理**：

当 `tool_search` 功能启用时，MCP 工具会被注册为**延迟工具**（deferred tools）。这些工具的 schema **不发给 LLM**（节省上下文 token），但 `ToolNode` 仍然持有它们用于执行。

```python
# 在 wrap_model_call 中：过滤掉延迟工具的 schema
def wrap_model_call(self, request, handler):
    registry = get_deferred_registry()
    deferred_names = registry.deferred_names
    active_tools = [t for t in request.tools if t.name not in deferred_names]
    return handler(request.override(tools=active_tools))

# 在 wrap_tool_call 中：拦截对未暴露延迟工具的直接调用
def wrap_tool_call(self, request, handler):
    if registry.contains(request.tool_call["name"]):
        return ToolMessage(content="Error: Tool is deferred... Call tool_search first")
    return handler(request)
```

**使用流程**：
1. LLM 只能看到 `tool_search` 工具
2. LLM 调用 `tool_search(query="...")` 发现需要的工具
3. `tool_search` 将该工具从 deferred 提升为 active
4. 后续 LLM 调用就能看到并使用该工具了

---

#### [15] SubagentLimitMiddleware — 并发 Subagent 限制

**源码位置**：`agents/middlewares/subagent_limit_middleware.py`

**实现 Hook**：`after_model` / `aafter_model`

**插入位置**：模型输出之后、LoopDetectionMiddleware 之前。

**核心原理**：

模型有时会在一次响应中并行发起多个 `task` 工具调用（比如 "同时分析3个文件"）。SubagentLimitMiddleware 截断超额的调用：

```python
def after_model(self, state, runtime):
    last_msg = messages[-1]
    if last_msg.type != "ai":
        return None

    tool_calls = last_msg.tool_calls
    task_indices = [i for i, tc in enumerate(tool_calls) if tc.get("name") == "task"]

    if len(task_indices) <= self.max_concurrent:
        return None  # 未超限

    # 只保留前 max_concurrent 个 task 调用，其余丢弃
    indices_to_drop = set(task_indices[self.max_concurrent:])
    truncated = [tc for i, tc in enumerate(tool_calls) if i not in indices_to_drop]

    updated_msg = last_msg.model_copy(update={"tool_calls": truncated})
    return {"messages": [updated_msg]}
```

- `max_concurrent` 默认 3，范围被 clamp 到 `[2, 4]`
- 丢弃的 task 调用**不会通知模型**，模型不知道自己的某些调用被静默丢弃了。这是为了简化逻辑——模型下次迭代会看到执行结果并继续。

---

#### [16] LoopDetectionMiddleware — 死循环检测与打破

**源码位置**：`agents/middlewares/loop_detection_middleware.py`

**实现 Hook**：`after_model` / `aafter_model`

**插入位置**：ClarificationMiddleware 之前。

**核心原理**：这是 P0 安全中间件，采用**两层检测策略**。

**第一层：Hash-based 检测（相同调用集合）**

```python
def _hash_tool_calls(tool_calls):
    # 对每个 tool call 提取 (name, stable_key)
    # stable_key 对 read_file 做了行号分桶（200行为一桶），防止 L1-L100 和 L101-L200 被视为不同调用
    normalized = [f"{name}:{key}" for ...]
    normalized.sort()  # 顺序无关
    return md5(json.dumps(normalized)).hexdigest()[:12]
```

- 相同 hash 出现 **3 次**：注入警告 HumanMessage（`[LOOP DETECTED] You are repeating...`）
- 相同 hash 出现 **5 次**：**强制停止**——清空 `tool_calls`，把 AIMessage 改成纯文本回答

**第二层：Frequency-based 检测（同工具类型高频）**

某些场景下模型不是在重复完全相同的调用，而是在疯狂调用同一个工具的不同参数（如连续 `read_file` 50个不同文件）。hash 检测会漏掉这种情况。

- 同一个工具调用 **30 次**：注入频率警告
- 同一个工具调用 **50 次**：强制停止

**为什么用 HumanMessage 注入警告而不是 SystemMessage**：

Anthropic 模型要求 SystemMessage 只能在对话开头出现。如果在中间插入 SystemMessage，`langchain_anthropic` 会崩溃。所以 LoopDetectionMiddleware 使用 `name="loop_warning"` 的 HumanMessage。

**强制停止的实现**：

```python
def _build_hard_stop_update(last_msg, content):
    return {
        "tool_calls": [],
        "content": content,
        "additional_kwargs": {pop "tool_calls", "function_call"},
        "response_metadata": {"finish_reason": "stop"},  # 覆盖 tool_calls → stop
    }
```

清空 `tool_calls` 后，LangGraph 认为模型没有工具要调，直接进入输出阶段。

**Per-thread 状态隔离**：使用 `thread_id` 作为 key，每个 thread 有自己的滑动窗口历史（LRU 淘汰，最多跟踪 100 个 thread）。

---

#### [17] ClarificationMiddleware — 澄清请求拦截

**源码位置**：`agents/middlewares/clarification_middleware.py`

**实现 Hook**：`wrap_tool_call` / `awrap_tool_call`

**插入位置**：链的**最末尾**。必须最后，确保它之前所有的错误处理和安全审计都已执行。

**核心原理**：拦截 `ask_clarification` 工具调用，将其转换为**用户可读的澄清消息**，并通过 `Command(goto=END)` **中断 Agent 执行**。

```python
def wrap_tool_call(self, request, handler):
    if request.tool_call.get("name") != "ask_clarification":
        return handler(request)  # 不是澄清，正常执行

    return self._handle_clarification(request)

def _handle_clarification(self, request):
    args = request.tool_call["args"]
    formatted = self._format_clarification_message(args)
    # e.g. "❓ 你需要我分析哪个时间范围的数据？\n  1. 最近7天\n  2. 最近30天"

    tool_message = ToolMessage(
        id=self._stable_message_id(tool_call_id, formatted),
        content=formatted,
        tool_call_id=tool_call_id,
        name="ask_clarification",
    )

    return Command(
        update={"messages": [tool_message]},
        goto=END,  # 跳转到图的结束节点
    )
```

**为什么用 `Command(goto=END)` 而不是直接返回 AIMessage**：

如果直接返回一条消息，LangGraph 的 ReAct 循环会继续——模型收到 ToolMessage 后会再次调用 LLM，可能又会生成新的 tool_calls。用 `Command(goto=END)` 可以**强制结束当前 Run**，把控制权交还给用户。

**前端如何展示**：前端检测到 `ask_clarification` 的 ToolMessage，直接渲染为澄清卡片（带选项按钮），用户点击后发送新消息，触发新 Run。

**`_stable_message_id`**：使用 `sha256` 生成确定性 ID，防止 ClarificationMiddleware 在重试时被重复执行导致消息重复追加。

---

### 5.4 中间件执行时序全景图

下面用伪代码展示一个**完整的 ReAct 迭代**中，各中间件的 hook 触发顺序：

```python
# ========== 第 1 次迭代（首次执行）==========
# before_agent hooks（仅首次）
for mw in middlewares:
    updates = mw.before_agent(state, runtime)
    state.update(updates)

# before_model hooks
for mw in middlewares:
    updates = mw.before_model(state, runtime)
    state.update(updates)

# LLM 调用（被 wrap_model_call 层层包装）
response = middlewares[-1].wrap_model_call(
    request,
    lambda req: middlewares[-2].wrap_model_call(
        req,
        lambda req: ... handler(req) ...  # 最终到达 LLM
    )
)
# 实际包装顺序（从内到外）：
#   DanglingToolCallMiddleware 修复历史
#   LLMErrorHandlingMiddleware 重试+熔断
#   DeferredToolFilterMiddleware 过滤延迟工具

# after_model hooks
for mw in middlewares:
    updates = mw.after_model(state, runtime)
    state.update(updates)
# 此时可能触发：
#   SubagentLimitMiddleware → 截断超额 task
#   LoopDetectionMiddleware → 检测到循环，注入警告
#   TodoMiddleware → jump_to="model"，跳过工具执行
#   TitleMiddleware → 生成 title

# 假设模型有 tool_calls，进入工具执行阶段
for tc in last_ai.tool_calls:
    # 每个 tool_call 被 wrap_tool_call 层层包装
    result = middlewares[-1].wrap_tool_call(
        ToolCallRequest(tool_call=tc),
        lambda req: middlewares[-2].wrap_tool_call(
            req,
            lambda req: ... execute_tool(req) ...
        )
    )
    # 实际包装顺序（从内到外）：
    #   ToolErrorHandlingMiddleware 兜底异常
    #   SandboxAuditMiddleware 审计 bash
    #   GuardrailMiddleware 内容安全
    #   ClarificationMiddleware 拦截澄清

    state.messages.append(result)  # 加入 ToolMessage

# ========== 第 2 次迭代 ==========
# before_model hooks 再次触发
#   SummarizationMiddleware → 如果 token 超限，压缩历史
#   ViewImageMiddleware → 如果 view_image 完成，注入图片消息
#   TodoMiddleware → 如果 todo 被 scroll out，注入提醒
# ...

# ========== Run 结束时 ==========
for mw in middlewares:
    updates = mw.after_agent(state, runtime)
    state.update(updates)
# 此时触发：
#   SandboxMiddleware → 释放沙箱
#   MemoryMiddleware → 队列记忆更新
```

---

### 5.5 设计哲学总结

| 设计原则 | 体现 |
|---------|------|
| **关注点分离** | 每个中间件只做一件事：安全、审计、错误、摘要、记忆、循环检测各司其职 |
| **可组合性** | 通过 `@Next`/`@Prev` 锚点，第三方中间件可以精确插入到内置链的任意位置 |
| **fail-safe** | 多个中间件都有 fallback：Title 生成失败用截断文本、LLM 错误返回友好消息、Tool 异常转成 error ToolMessage |
| **性能意识** | lazy_init（ThreadData、Sandbox）、debounce（Memory）、延迟工具（DeferredToolFilter）都为了减少不必要的开销 |
| **安全性分层** | Guardrail（策略层）→ SandboxAudit（命令层）→ ToolErrorHandling（异常层），三层防护 |

---

## Phase 6: 一个完整请求的全生命周期串联

现在把以上所有 Phase 串联起来，看看用户发送一条消息时，系统内部发生了什么：

### Step 0: 系统启动

1. `uvicorn app.gateway.app:app` 启动 FastAPI
2. `lifespan()` 加载 `config.yaml`，初始化 LangGraph Runtime（checkpointer、store）
3. `langgraph.json` 注册 `lead_agent = deerflow.agents:make_lead_agent`

### Step 1: 用户发送消息

```
用户在前端输入: "帮我分析一下 workspace/data.csv 的数据分布"

frontend/src/app/workspace/chats/[thread_id]/page.tsx
  → useThreadStream.sendMessage(threadId, message)
  → POST /api/threads/{thread_id}/runs/stream
```

### Step 2: Gateway 创建 Run

```
backend/app/gateway/routers/thread_runs.py::stream_run()
  → start_run(body, thread_id)
  → LangGraph runtime 开始执行 lead_agent 图
  → SSE 流建立，前端开始接收事件
```

### Step 3: LangGraph 执行 Lead Agent

```
deerflow.agents.lead_agent.agent::_make_lead_agent()
  → create_agent(
        model=gpt-4o (或配置的模型),
        tools=[bash, read_file, ls, grep, task, present_file, ...],
        middleware=[ThreadData, Uploads, Sandbox, ..., Clarification],
        system_prompt="...",
        state_schema=ThreadState,
    )
```

LangGraph 进入 ReAct 循环：
1. **调用 LLM** — 传入当前 `ThreadState.messages` + system_prompt + tools schema
2. **模型决定** — 返回 `AIMessage` 可能包含 `tool_calls=[...]`
3. **执行工具** — 比如 `read_file(file_path="/mnt/user-data/workspace/data.csv")`

### Step 4: Middleware 介入

在每次迭代前后，Middleware 链依次执行：

```
Before LLM:
  ThreadDataMiddleware   → 确保 workspace_path 存在
  MemoryMiddleware       → 把相关记忆注入 system prompt

After LLM (有 tool_calls):
  SandboxMiddleware      → 确保 sandbox 已初始化
  ToolErrorHandling      → 捕获工具异常

After Tool Execution:
  DanglingToolCall       → 确保 ToolMessage 完整
  SummarizationMiddleware → 如果消息太多，触发摘要
```

### Step 5: 工具执行（以 read_file 为例）

```
sandbox/tools.py::read_file_tool()
  → sandbox.read_file("/mnt/user-data/workspace/data.csv")
  → LocalSandbox: subprocess.run(["/bin/sh", "-c", "cat /real/path/to/data.csv"])
  → 或 AioSandbox: HTTP POST container:8080/shell/exec {command: "cat ..."}
  → _truncate_read_file_output(content, max_chars=50000)
  → mask_local_paths_in_output()  # 把真实路径脱敏为虚拟路径
  → 返回给模型
```

### Step 6: 可能触发 Subagent

如果模型判断需要复杂分析，会调用 `task` 工具：

```
task_tool()
  → SubagentExecutor(config="general-purpose")
    → 在独立 ThreadPool + EventLoop 中运行
    → 创建新的 Agent 实例（继承父工具集，但禁用 task 防递归）
    → astream() 实时执行
    → 每产生一条 AIMessage，推送到前端 (task_running 事件)
  → 轮询等待完成
  → 返回 "Task Succeeded. Result: ..."
```

前端 SSE 会收到：
```json
{"type": "task_started", "task_id": "abc123", "description": "分析数据分布"}
{"type": "task_running", "task_id": "abc123", "message": "...", "message_index": 1}
{"type": "task_completed", "task_id": "abc123", "result": "..."}
```

### Step 7: 结果汇总与返回

Subagent 结果返回给 Lead Agent，Lead Agent 继续迭代，最终生成回复。LangGraph 的 `StreamBridge` 把事件转换为 SSE：

```json
{"event": "on_chat_model_stream", "data": {"chunk": {"content": "根据"}}}
{"event": "on_chat_model_stream", "data": {"chunk": {"content": "分析"}}}
...
{"event": "on_chain_end", "data": {"output": {"messages": [...]}}}
```

### Step 8: 前端渲染

前端 `useThreadStream` 消费 SSE，逐字渲染到 MessageList。如果 Agent 产生了文件（Artifact），前端通过 `ArtifactTrigger` 展示下载链接。

---

---

## 附录：核心对象结构速查

> 阅读源码时，经常遇到 `request.headers.get("Last-Event-ID")` 这类写法却不清楚变量全貌。本附录列出 Gateway 层高频出现的核心对象及其字段，方便速查。

### 1. `request.headers` — 前端实际传过来的 HTTP Header 一览

阅读 Gateway 代码时，`request.headers.get("xxx")` 中的字符串就是**前端（或反向代理）在 HTTP 请求头中携带的字段**。下面列出 DeerFlow 中实际会被读取的 Header，以及它们是谁带过来的、起什么作用。

#### 1.1 本项目业务自定义 Header

| Header 键名 | 代码中出现的位置 | 谁传的 | 作用 |
|-------------|----------------|--------|------|
| **`Last-Event-ID`** | `services.py:331` | 前端（浏览器 SSE 客户端） | **SSE 断线重连标识**。前端网络断开后自动重连时，会把上次收到的最后一个事件的 ID 带回来，后端据此从 `MemoryStreamBridge` 的缓冲区中间恢复推送，实现无缝续传。 |
| **`X-CSRF-Token`** | `csrf_middleware.py:75`<br>`langgraph_auth.py:38` | 前端 JS | **CSRF 双提交 Cookie 校验**。后端生成 `csrf_token` Cookie 后，前端发 POST/PUT/DELETE/PATCH 请求时必须把这个值原样带回 Header，后端比对 Cookie 和 Header 是否一致，防止跨站攻击。 |
| **`X-Internal-Auth`** | `auth_middleware.py:80` | 内部服务 / 代理 | **内部服务间调用认证**。当 Gateway 和 LangGraph Server 分离部署，或内部脚本直接调用 API 时，用此 Header 携带内部密钥，绕过常规的 Cookie-JWT 鉴权。 |

#### 1.2 反向代理常见 Header

| Header 键名 | 代码中出现的位置 | 谁传的 | 作用 |
|-------------|----------------|--------|------|
| **`X-Forwarded-Proto`** | `csrf_middleware.py:22` | Nginx / Traefik / 负载均衡 | 告知后端**原始请求的协议**。当后端前面有 HTTPS 终结代理时，`request.url.scheme` 会变成 `http`，通过此 Header 可判断客户端实际是用 `https` 访问的，用于决定是否设置 `secure` Cookie。 |
| **`X-Real-IP`** | `auth.py:217` | Nginx / 代理 | 携带**客户端真实 IP**。代理把原始请求的 IP 写进此 Header，后端用于记录登录日志、IP 限制、审计等。 |

#### 1.3 浏览器自动携带的标准 Header（代码中未显式读取，但贯穿整个请求）

| Header 键名 | 说明 |
|-------------|------|
| **`Cookie`** | 浏览器自动带上当前域名下的所有 Cookie。DeerFlow 中主要包含两个：`access_token`（JWT 登录态）和 `csrf_token`（CSRF 校验值）。后端通过 `request.cookies.get(...)` 读取，而不是走 headers。 |
| **`Content-Type`** | 前端发 POST/PUT 时标记请求体格式，如 `application/json`（JSON 请求体）或 `multipart/form-data`（文件上传）。 |
| **`Accept`** | 前端声明可接受的响应格式，如 `application/json`、`text/event-stream`（SSE）。 |
| **`Accept-Language`** | 浏览器语言偏好，后端可据此做国际化。 |
| **`User-Agent`** | 浏览器/客户端标识。 |

#### 1.4 小结：一条典型请求的 Header 全貌

以前端发送 SSE 流式请求为例，浏览器实际发出去的 HTTP 请求头大概长这样：

```http
POST /api/threads/{thread_id}/runs/stream HTTP/1.1
Host: localhost:3000
Content-Type: application/json
Accept: text/event-stream
Cookie: access_token=eyJhbG...; csrf_token=abc123...
X-CSRF-Token: abc123...          ← 前端从 Cookie 中读出，再塞回 Header
Last-Event-ID: 42                ← 只有断线重连时才有；首次请求没有

{ "assistant_id": "lead_agent", "input": {...} }
```

> **记忆诀窍**：`request.headers` 里放的**全是字符串键值对**，键名大小写不敏感（HTTP 规范），但代码里通常按首字母大写的驼峰写法读取。

---

### 1.5 `request` 对象的其他常用属性

类型来源：`fastapi.Request`（继承自 `starlette.requests.Request`）

| 属性/方法 | 类型 | 本文中出现的用法 |
|-----------|------|----------------|
| `request.cookies` | `dict[str, str]` | `request.cookies.get("access_token")` — 读取登录 Token |
| `request.app` | `FastAPI` | `request.app.state.stream_bridge` — 访问全局单例 |
| `request.app.state` | `State` | 存储所有运行时单例（见下表） |
| `request.is_disconnected()` | `async -> bool` | SSE 消费循环中检测客户端是否断开 |
| `request.query_params` | `QueryParams` | 获取 URL `?key=value` 参数 |
| `request.path_params` | `dict` | 获取路由路径参数 `{thread_id}` |
| `request.method` | `str` | HTTP 方法名（GET / POST / …） |
| `request.url` | `URL` | 完整请求 URL |

**`request.app.state` 上挂载的单例**（由 `deps.py` / `langgraph_runtime()` 初始化）：

| 单例名 | 类型 | 获取方式 |
|--------|------|---------|
| `stream_bridge` | `MemoryStreamBridge` | `get_stream_bridge(request)` |
| `run_manager` | `RunManager` | `get_run_manager(request)` |
| `checkpointer` | `Checkpointer` | `get_checkpointer(request)` |
| `store` | `BaseStore | None` | `get_store(request)` |
| `run_store` | `RunRepository` | `get_run_store(request)` |
| `feedback_repo` | `FeedbackRepository` | `get_feedback_repo(request)` |
| `run_event_store` | `RunEventStore` | `get_run_event_store(request)` |
| `thread_store` | `ThreadMetaStore` | `get_thread_store(request)` |
| `config` | `AppConfig` | `get_config(request)` |

### 2. `body: RunCreateRequest` — 创建 Run 的请求体

类型来源：`backend/app/gateway/routers/thread_runs.py`

```python
class RunCreateRequest(BaseModel):
    assistant_id: str | None        # Agent 名称，如 "lead_agent"
    input: dict[str, Any] | None    # 图输入，如 {"messages": [...]}
    command: dict[str, Any] | None  # LangGraph Command
    metadata: dict[str, Any] | None # Run 元数据
    config: dict[str, Any] | None   # RunnableConfig 覆盖项
    context: dict[str, Any] | None  # DeerFlow 上下文（model_name / thinking_enabled 等）
    webhook: str | None             # 完成回调 URL
    checkpoint_id: str | None       # 从 checkpoint 恢复
    checkpoint: dict[str, Any] | None
    interrupt_before: list[str] | Literal["*"] | None
    interrupt_after: list[str] | Literal["*"] | None
    stream_mode: list[str] | str | None
    stream_subgraphs: bool = False  # 是否流式推送子图事件
    stream_resumable: bool | None   # SSE 是否支持断线重连
    on_disconnect: Literal["cancel", "continue"] = "cancel"
    on_completion: Literal["delete", "keep"] = "keep"
    multitask_strategy: Literal["reject", "rollback", "interrupt", "enqueue"] = "reject"
    after_seconds: float | None     # 延迟执行
    if_not_exists: Literal["reject", "create"] = "create"
    feedback_keys: list[str] | None
```

### 3. `record: RunRecord` — Run 运行时记录

类型来源：`backend/packages/harness/deerflow/runtime/runs/manager.py`

```python
@dataclass
class RunRecord:
    run_id: str
    thread_id: str
    assistant_id: str | None
    status: RunStatus                 # pending / running / success / interrupted / error
    on_disconnect: DisconnectMode     # cancel / continue_
    multitask_strategy: str = "reject"
    metadata: dict = field(default_factory=dict)
    kwargs: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    task: asyncio.Task | None = None       # 后台 Agent 执行 Task
    abort_event: asyncio.Event = field(...) # 取消信号
    abort_action: str = "interrupt"         # "interrupt" 或 "rollback"
    error: str | None = None
```

### 4. `bridge: MemoryStreamBridge` — 内存事件总线

类型来源：`backend/packages/harness/deerflow/runtime/stream_bridge/memory.py`

```python
class MemoryStreamBridge:
    async def publish(self, run_id: str, event: str, data: Any) -> None
    async def subscribe(self, run_id: str, *, last_event_id: str | None = None) -> AsyncGenerator[StreamEvent, None]
```

`StreamEvent` 结构：

```python
class StreamEvent:
    id: str      # 事件序号（用于 Last-Event-ID）
    event: str   # 事件类型（metadata / values / messages / end）
    data: Any    # 事件载荷
```

### 5. `ctx: RunContext` — Run 运行时上下文

类型来源：`backend/app/gateway/deps.py::get_run_context()`

```python
class RunContext:
    checkpointer: Checkpointer      # LangGraph 状态持久化
    store: BaseStore | None         # LangGraph 键值存储
    event_store: RunEventStore      # Run 事件存储
    run_events_config: Any | None   # 事件存储配置
    thread_store: ThreadMetaStore   # Thread 元数据存储
    app_config: AppConfig           # 全局应用配置
```

---

## 总结：DeerFlow 的设计亮点

| 设计点 | 源码体现 | 价值 |
|--------|---------|------|
| **Middleware 链** | `agents/factory.py` 14 层中间件 | 像洋葱一样包裹 Agent 执行，每个关注点解耦 |
| **状态扩展** | `ThreadState` 继承 `AgentState` | 在标准 ReAct 状态上叠加 Sandbox、Memory、Artifacts |
| **双模式 Sandbox** | `local/local_sandbox.py` + `aio_sandbox/` | 开发用 Local（快），生产用 Docker（安全） |
| **Subagent 隔离** | `subagents/executor.py` 独立 EventLoop | 复杂任务不阻塞主对话，支持实时流 |
| **工具分层加载** | `tools/tools.py` config + builtin + MCP + ACP | 灵活扩展，兼容外部生态 |
| **输出硬截断** | `_truncate_bash_output()` 等 | 最后一道防线，防止超长输出打爆上下文 |
| **Summarization** | `SummarizationMiddleware` | 让长对话可持续，而不是无限增长 |

DeerFlow 的本质是**在 LangGraph 之上搭建了一个完整的 Agent 操作系统**：它处理了状态管理、工具发现、沙箱执行、子代理编排、记忆注入、上下文压缩、异常恢复等所有生产级 Agent 需要面对的问题。理解它的框架后，你可以根据需要调整 `config.yaml`、自定义 Subagent、添加 MCP Server，或修改 Middleware 链来适配自己的业务场景。
