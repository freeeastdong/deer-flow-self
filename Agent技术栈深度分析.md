# DeerFlow 项目 Agent 技术栈深度分析

> 本文档基于 DeerFlow 2.0 代码库（commit 前后版本）深入分析，覆盖 Prompt Engineering、RAG、Agent 架构、LangChain/LangGraph、Tool Use、工作流编排、记忆机制 7 大技术栈的实际实现与原理。

---

## 目录

1. [概述](#1-概述)
2. [Prompt Engineering（提示工程）](#2-prompt-engineering提示工程)
3. [RAG 技术（检索增强生成）](#3-rag-技术检索增强生成)
4. [Agent 基本架构（ReAct / Plan / Execute / Multi-Agent）](#4-agent-基本架构)
5. [LangChain / LangGraph 框架](#5-langchain--langgraph-框架)
6. [Tool Use（工具使用）](#6-tool-use工具使用)
7. [工作流编排（Workflow Orchestration）](#7-工作流编排)
8. [记忆机制（Memory Mechanism）](#8-记忆机制)
9. [技术栈对比总表](#9-技术栈对比总表)

---

## 1. 概述

DeerFlow（**D**eep **E**xploration and **E**fficient **R**esearch **F**low）是字节跳动开源的 **Super Agent Harness**，其核心定位不是"一个 Agent"，而是**一个能编排多个 Sub-agent、管理记忆、在 Sandbox 中执行代码的 Agent 运行时框架**。

### 1.1 技术栈分层

| 层级 | 技术 | 职责 |
|------|------|------|
| **前端** | Next.js 14 + TypeScript + React Query | 聊天界面、工作区、配置面板 |
| **Gateway** | FastAPI | 路由、鉴权、文件上传、线程管理 |
| **Agent 运行时** | **LangGraph + LangChain** | 图编排、工具调用、状态管理 |
| **核心包** | `deerflow-harness` | Agent 工厂、Sandbox、工具、Memory、Middleware |
| **Sandbox** | Local (subprocess) / AioSandbox (Docker) | 隔离执行 bash、文件操作 |
| **持久化** | LangGraph Checkpointer (SQLite/Postgres) | 线程状态、消息历史 |

### 1.2 核心设计哲学

DeerFlow 2.0 是一个**从零重写**的版本，其设计哲学可以概括为：

- **高度封装而非低层拼装**：把 LangGraph 的节点/边细节交给 `create_agent`，自身聚焦于通过 **Middleware 管道**和**配置驱动工厂**构建企业级 Agent 功能
- **Web-first 信息源**：核心信息来源是互联网实时搜索，而非私有知识库
- **Lead Agent 决策 + Sub-agent 并行执行**：主 Agent 负责任务分解与综合，子 Agent 负责并行执行
- **上下文激进管理**：通过 SummarizationMiddleware 自动压缩历史，通过技能渐进式加载保持上下文窗口精简

---

## 2. Prompt Engineering（提示工程）

**结论：本项目大量且深度地使用了 Prompt Engineering，是 DeerFlow 最核心的设计维度之一。**

### 2.1 系统提示词的模块化动态组装

DeerFlow 最核心的提示词工程文件是：

> **`backend/packages/harness/deerflow/agents/lead_agent/prompt.py`**

该文件定义了主 Agent 的 `SYSTEM_PROMPT_TEMPLATE`，采用 **Python `str.format()`** 动态格式化，而非 Jinja2。模板结构如下：

```python
SYSTEM_PROMPT_TEMPLATE = """
<role>
You are {agent_name}, an open-source super agent.
</role>

{soul}
{memory_context}

<thinking_style>
- Think concisely and strategically about the user's request BEFORE taking action
- Break down the task: What is clear? What is ambiguous? What is missing?
- **PRIORITY CHECK: If anything is unclear...you MUST ask for clarification FIRST**
- **DECOMPOSITION CHECK: Can this task be broken into 2+ parallel sub-tasks?**
- Never write down your full final answer in thinking process, but only outline
- CRITICAL: After thinking, you MUST provide your actual response to the user
</thinking_style>

<clarification_system>
**WORKFLOW PRIORITY: CLARIFY → PLAN → ACT**
...
</clarification_system>

{skills_section}
{deferred_tools_section}
{subagent_section}

<working_directory existed="true">
...
</working_directory>

<response_style>
...
</response_style>

<citations>
...
</citations>

<critical_reminders>
...
</critical_reminders>
"""
```

**关键设计特点：**

| 设计元素 | 说明 |
|---------|------|
| **XML 标签结构** | 使用 `<role>`、`<thinking_style>`、`<clarification_system>` 等 XML 标签组织提示词，帮助模型理解结构化指令 |
| **动态占位符** | `{agent_name}`、`{soul}`、`{memory_context}`、`{skills_section}`、`{subagent_section}` 等运行时动态注入 |
| **思维链引导** | 在 `<thinking_style>` 中明确要求模型先思考再行动，内置 DECOMPOSITION CHECK 促使任务分解 |
| **工作流优先级** | `CLARIFY → PLAN → ACT` 的强制工作流 |

系统提示词的构建入口 `apply_prompt_template()`（第 727-784 行）将所有动态组件组装成最终提示词：

```python
def apply_prompt_template(
    subagent_enabled: bool = False,
    max_concurrent_subagents: int = 3,
    *,
    agent_name: str | None = None,
    available_skills: set[str] | None = None,
    app_config: AppConfig | None = None,
) -> str:
    # 1. 获取记忆上下文
    memory_context = _get_memory_context(agent_name, app_config=app_config)
    # 2. 构建子 Agent 段落
    subagent_section = _build_subagent_section(...) if subagent_enabled else ""
    # 3. 获取技能段落
    skills_section = get_skills_prompt_section(available_skills, app_config=app_config)
    # 4. 获取延迟工具段落
    deferred_tools_section = get_deferred_tools_prompt_section(app_config=app_config)
    # 5. 格式化最终提示词 + 追加当前日期
    prompt = SYSTEM_PROMPT_TEMPLATE.format(...)
    return prompt + f"\n<current_date>{datetime.now().strftime('%Y-%m-%d, %A')}</current_date>"
```

### 2.2 提示词优化技术

#### A. Chain-of-Thought（思维链）引导

系统提示词中包含明确的 CoT 引导，要求模型：
- 先战略性思考，再行动
- 分解任务：什么是清晰的？什么是模糊的？缺失了什么？
- 识别是否需要澄清或分解为并行子任务

#### B. Few-Shot 示例

在子 Agent 系统提示中嵌入了 **隐式的 Few-Shot 示例**：

```markdown
**Example 1: "Why is Tencent's stock price declining?" (3 sub-tasks → 1 batch)**
→ Turn 1: Launch 3 subagents in parallel...
→ Turn 2: Synthesize results

**Example 2: "Compare 5 cloud providers" (5 sub-tasks → multi-batch)**
...
```

#### C. 结构化输出约束

记忆更新提示中要求严格的 JSON Schema 输出：

```python
Output Format (JSON):
{
  "user": {
    "workContext": { "summary": "...", "shouldUpdate": true/false },
    ...
  },
  "history": { ... },
  "newFacts": [
    { "content": "...", "category": "preference|knowledge|...", "confidence": 0.0-1.0 }
  ],
  "factsToRemove": ["fact_id_1"]
}
```

#### D. Prompt Caching（提示词缓存）优化

针对 Claude 模型实现了 Prompt Caching：

> **`backend/packages/harness/deerflow/models/claude_provider.py`**（第 192-244 行）

```python
def _apply_prompt_caching(self, payload: dict) -> None:
    MAX_CACHE_BREAKPOINTS = 4
    # 收集候选块：系统文本块、最近消息内容块、最后一个工具定义
    candidates = []
    # 仅在最后 MAX_CACHE_BREAKPOINTS 个候选上应用 cache_control
    for block in candidates[-MAX_CACHE_BREAKPOINTS:]:
        block["cache_control"] = {"type": "ephemeral"}
```

#### E. Thinking Budget 自动分配

```python
def _apply_thinking_budget(self, payload: dict) -> None:
    max_tokens = payload.get("max_tokens", 8192)
    thinking["budget_tokens"] = int(max_tokens * THINKING_BUDGET_RATIO)  # 80%
```

### 2.3 动态提示词构建

#### A. 技能系统的渐进式加载

技能提示段落采用 **LRU 缓存** 机制，结合动态过滤：

```python
@lru_cache(maxsize=32)
def _get_cached_skills_prompt_section(...):
    # 只加载技能的元数据（name + description），不加载完整内容
    # Agent 需要时通过 read_file 工具按需读取 SKILL.md
```

**渐进式披露设计（三级加载）：**
1. **Metadata**（name + description）- 始终在上下文中（~100 词）
2. **SKILL.md body** - 技能触发时在上下文中（<500 行理想）
3. **Bundled resources** - 按需加载（无限制，脚本可直接执行）

#### B. 记忆上下文的动态注入

```python
def _get_memory_context(agent_name: str | None = None) -> str:
    memory_data = get_memory_data(agent_name, user_id=get_effective_user_id())
    memory_content = format_memory_for_injection(memory_data, max_tokens=config.max_injection_tokens)
    return f"""<memory>\n{memory_content}\n</memory>\n"""
```

实现了**基于 Token 预算的智能截断**，按置信度排序 facts，在预算内保留高置信度事实。

#### C. 循环检测与干预

当检测到重复工具调用时，系统注入干预消息：

```python
_WARNING_MSG = "[LOOP DETECTED] You are repeating the same tool calls. Stop calling tools and produce your final answer now."
_HARD_STOP_MSG = "[FORCED STOP] Repeated tool calls exceeded the safety limit. Producing final answer with results collected so far."
```

### 2.4 技能系统作为 Prompt Engineering 的延伸

`skills/public/` 下包含 21 个内置技能，每个 `SKILL.md` 都是精心设计的提示词工程产物。例如 `deep-research` Skill 定义了四阶段研究方法论：

```markdown
## Research Methodology
### Phase 1: Broad Exploration
### Phase 2: Deep Dive
### Phase 3: Diversity & Validation
### Phase 4: Synthesis Check
**If any answer is NO, continue researching before generating content.**
```

Skill Creator 技能甚至包含**元提示词工程**——自动评估和优化技能描述，通过 20 个评估查询测试技能触发准确率。

### 2.5 小结

DeerFlow 的 Prompt Engineering 体系展现了以下核心设计理念：

1. **模块化动态组装**：系统提示词由多个独立段落动态组合
2. **上下文感知注入**：记忆、技能、工具根据运行时状态动态注入，且受 Token 预算约束
3. **渐进式披露**：技能采用三级加载策略，保持上下文窗口精简
4. **安全与效率并重**：Prompt Caching、循环检测、工具频率限制、摘要压缩
5. **元提示词工程**：通过 Skill Creator 实现提示词的自动评估和优化

---

## 3. RAG 技术（检索增强生成）

**结论：本项目未使用传统 RAG 技术，而是采用了 Web Search + 长上下文窗口 + SummarizationMiddleware 的替代方案。**

### 3.1 未使用的 RAG 组件

| RAG 组件 | 项目中的情况 |
|---------|------------|
| **向量数据库** | ❌ 无 Chroma、FAISS、Pinecone、Qdrant、Milvus、Weaviate 的代码集成 |
| **Embedding 模型** | ❌ 无 `embed_documents`、`embed_query` 调用，无 `OpenAIEmbeddings` 等类导入 |
| **文档检索/相似度搜索** | ❌ 无基于向量相似度的检索逻辑 |
| **文档分块/索引构建** | ❌ 无 chunking、indexing 逻辑 |
| **知识库查询** | ❌ 无知识库相关 Skill 或工具 |

**全局验证：**

```bash
# 全局搜索 VectorStore / Retriever / Embeddings
grep -rn "VectorStore\|Retriever\|BaseRetriever\|Embeddings\|OpenAIEmbeddings" backend/ --include="*.py"
# → 无任何结果
```

`config.example.yaml` 中也**没有任何**向量存储或 Embedding 相关的配置项。

### 3.2 替代技术架构

DeerFlow 不使用传统 RAG，而是采用以下替代技术组合：

#### A. Web Search + Web Fetch（实时信息获取）

DeerFlow 的核心信息来源是**互联网实时搜索**，通过多 Provider 获取最新信息：

| 工具/模块 | 类型 | 路径 |
|----------|------|------|
| DuckDuckGo 搜索 | Web Search | `backend/packages/harness/deerflow/community/ddg_search/tools.py` |
| Tavily 搜索 | Web Search | `backend/packages/harness/deerflow/community/tavily/tools.py` |
| Exa 搜索 | Web Search | `backend/packages/harness/deerflow/community/exa/tools.py` |
| Firecrawl 搜索/抓取 | Web Search + Fetch | `backend/packages/harness/deerflow/community/firecrawl/tools.py` |
| Jina AI Reader | Web Fetch | `backend/packages/harness/deerflow/community/jina_ai/tools.py` |
| InfoQuest（字节自研）| Web Search + Fetch | `backend/packages/harness/deerflow/community/infoquest/tools.py` |

```python
# Tavily Web Search 示例
@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    client = _get_tavily_client()
    res = client.search(query, max_results=max_results)
    return json.dumps(normalized_results, indent=2, ensure_ascii=False)
```

#### B. 长上下文窗口 + SummarizationMiddleware（长文本处理）

DeerFlow 通过 **SummarizationMiddleware** 解决上下文长度问题：

> **`backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py`**

```yaml
# config.example.yaml
summarization:
  enabled: true
  trigger:
    - token_count: 80000
      min_messages: 2
  keep:
    token_count: 40000
    min_messages: 1
```

**原理**：当对话 token 数达到阈值（如 80k）时，由 LLM 对旧消息进行总结压缩，保留最近的消息窗口。特别地，它会 **"抢救"（rescue）最近加载的技能文件内容**，避免技能上下文在摘要后丢失。

#### C. 结构化 Memory 系统（用户画像记忆）

DeerFlow 的 Memory 不是向量记忆，而是**基于 JSON 文件的结构化记忆**（详见第 8 章）。

#### D. 文件系统 + Sandbox（文档处理）

用户上传的文档通过 `read_file` 工具在 sandbox 中直接读取，依赖 LLM 的上下文能力处理，不做向量索引。支持 PDF/PPT/Excel/Word 转换为 Markdown，但有 50,000 字符上限截断。

### 3.3 为什么 DeerFlow 不需要传统 RAG？

| DeerFlow 的定位 | 传统 RAG 的适用场景 |
|----------------|-------------------|
| **Deep Research（深度研究）**：面向开放域的实时信息获取 | 面向**私有文档知识库**的问答 |
| **多 Agent 编排框架**：强调 Tool Use、Sub-agent 协作 | 强调**文档检索 + 生成** |
| **Web-first 信息源**：搜索互联网最新信息 | 检索本地预构建索引 |

DeerFlow 的架构设计明确选择了 **"Web Search + 长上下文 + Summarization"** 的路径，这与它的产品定位（Deep Research Agent）高度一致。对于需要处理私有知识库的场景，项目目前**没有内置支持**。

---

## 4. Agent 基本架构

**结论：本项目深度使用了 ReAct、Plan、Execute、Multi-Agent 架构，是 DeerFlow 作为 "Super Agent Harness" 的核心体现。**

### 4.1 ReAct 模式：思考-行动-观察循环

DeerFlow 的 ReAct 模式构建在 **LangGraph `create_agent`** 之上，天然实现了标准的 ReAct 状态机循环：

> **模型推理（Thought）→ 工具调用决策（Action）→ 工具执行（Tool Node）→ 结果观察（Observation）→ 回到模型**

**状态定义**（`backend/packages/harness/deerflow/agents/thread_state.py`）：

```python
class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: NotRequired[list | None]          # Plan 模式使用
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
```

`messages` 字段（继承自 `AgentState`）是 ReAct 循环的核心载体，按顺序保存 `HumanMessage`、`AIMessage`、`ToolMessage`。

**Lead Agent 创建入口**（`backend/packages/harness/deerflow/agents/lead_agent/agent.py`）：

```python
def _make_lead_agent(config: RunnableConfig, *, app_config: AppConfig):
    # ...
    return create_agent(
        model=create_chat_model(...),
        tools=get_available_tools(...),
        middleware=_build_middlewares(...),   # 14 层 Middleware 链
        system_prompt=apply_prompt_template(...),
        state_schema=ThreadState,
    )
```

### 4.2 Plan 模式：任务规划与 Todo List

Plan 模式通过运行时参数 `is_plan_mode` 控制。当启用时，系统会：

1. **注入 Todo List 系统提示**：教导 Agent 仅在复杂任务（≥3 步）时使用 `write_todos` 工具，实时更新 todo 状态
2. **TodoMiddleware 上下文丢失检测**：当历史消息被 SummarizationMiddleware 截断后，若 `write_todos` 调用不在上下文窗口中，自动注入提醒消息
3. **防止提前退出**：当 Agent 还有未完成的 todo 却想直接输出最终答案时，Middleware 强制跳回模型节点

```python
# TodoMiddleware.after_model
def after_model(self, state: PlanningState, runtime: Runtime) -> dict[str, Any] | None:
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if not last_ai or last_ai.tool_calls:
        return None
    todos = state.get("todos") or []
    if not todos or all(t.get("status") == "completed" for t in todos):
        return None
    # 防循环：最多提醒 2 次
    if _completion_reminder_count(messages) >= self._MAX_COMPLETION_REMINDERS:
        return None
    # 注入提醒并强制跳转回 model 节点
    return {"jump_to": "model", "messages": [reminder]}
```

### 4.3 Execute 模式：任务执行引擎

**SubagentExecutor**（`backend/packages/harness/deerflow/subagents/executor.py`）是任务执行的核心：

```python
class SubagentExecutor:
    def _create_agent(self):
        model = create_chat_model(name=self.model_name, thinking_enabled=False)
        middlewares = build_subagent_runtime_middlewares(...)
        return create_agent(model=model, tools=self.tools, middleware=middlewares, ...)

    async def _aexecute(self, task: str, result_holder: SubagentResult):
        agent = self._create_agent()
        state = await self._build_initial_state(task)  # 加载 skill + task
        async for chunk in agent.astream(state, config=..., stream_mode="values"):
            if result.cancel_event.is_set():
                result.status = SubagentStatus.CANCELLED
                return
            # 实时捕获 AI 消息供前端展示
            messages = chunk.get("messages", [])
            if messages and isinstance(messages[-1], AIMessage):
                result.ai_messages.append(messages[-1].model_dump())
        result.result = extract_final_message(...)
        result.status = SubagentStatus.COMPLETED
```

执行特点：
- **状态继承**：子 Agent 继承父 Agent 的 `sandbox` 和 `thread_data`
- **协程级取消**：支持 `cancel_event` 合作式取消
- **三种执行模式**：同步阻塞、后台线程池、异步流式

### 4.4 Multi-Agent 架构

#### 整体架构

```
┌─────────────────────────────────────────┐
│           User Request                  │
└─────────────┬───────────────────────────┘
              ▼
┌─────────────────────────────────────────┐
│         Lead Agent (主代理)              │
│  - 思考、规划、决策                       │
│  - 直接调用工具 或 委派 Sub-agent         │
│  - 汇总 Sub-agent 结果                   │
└─────────────┬───────────────────────────┘
              │ task_tool (并行，max 3-4个)
              ▼
┌─────────────────────────────────────────┐
│      Sub-agent Executor (执行引擎)       │
│  - 创建隔离的 Agent 实例                  │
│  - 流式执行 + 实时消息收集                │
│  - 继承父级 sandbox/thread 状态           │
└─────────────┬───────────────────────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐
│Sub-A  │ │Sub-B  │ │Sub-C  │  (并行执行)
└───┬───┘ └───┬───┘ └───┬───┘
    └─────────┴─────────┘
              ▼
┌─────────────────────────────────────────┐
│         结果返回 Lead Agent              │
│         (Synthesize 综合回答)            │
└─────────────────────────────────────────┘
```

#### Lead Agent 与 Sub-agent 的关系

| 特性 | Lead Agent | Sub-agent |
|------|-----------|-----------|
| 角色 | 用户直接交互入口 | 被委派的执行者 |
| 工具权限 | 完整（含 `task` 工具）| **禁止 `task` 工具**，防止无限递归 |
| Middleware | 14 层完整链 | 简化版链 |
| 澄清能力 | 可以调用 `ask_clarification` | 禁止调用 `ask_clarification` 和 `present_files` |
| 并发限制 | 无（但受模型输出限制）| 受 `SubagentLimitMiddleware` 限制 |

#### Task Tool：Multi-Agent 的调用入口

> **`backend/packages/harness/deerflow/tools/builtins/task_tool.py`**

```python
@tool("task", parse_docstring=True)
async def task_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    description: str,
    prompt: str,
    subagent_type: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_turns: int | None = None,
) -> str:
    # 1. 获取 subagent 配置
    config = get_subagent_config(subagent_type)
    # 2. 过滤工具：禁用 subagent 防止嵌套
    tools = get_available_tools(subagent_enabled=False)
    # 3. 创建 Executor，继承父 sandbox/thread_data
    executor = SubagentExecutor(config=config, tools=tools, sandbox_state=sandbox_state, ...)
    # 4. 后台执行
    task_id = executor.execute_async(prompt, task_id=tool_call_id)
    # 5. 每 5 秒轮询，实时推送 task_running 事件
    while True:
        result = get_background_task_result(task_id)
        if result.status == SubagentStatus.COMPLETED:
            return f"Task Succeeded. Result: {result.result}"
        elif result.status == SubagentStatus.FAILED:
            return f"Task failed. Error: {result.error}"
        await asyncio.sleep(5)
```

#### 并发限制与结果汇聚

`SubagentLimitMiddleware` 在模型输出后、工具执行前硬性截断超过限制的 `task` 调用：

```python
def _truncate_task_calls(self, state: AgentState) -> dict | None:
    task_indices = [i for i, tc in enumerate(tool_calls) if tc.get("name") == "task"]
    if len(task_indices) <= self.max_concurrent:
        return None
    # 仅保留前 max_concurrent 个 task 调用，其余丢弃
    indices_to_drop = set(task_indices[self.max_concurrent:])
    truncated_tool_calls = [tc for i, tc in enumerate(tool_calls) if i not in indices_to_drop]
    return {"messages": [last_msg.model_copy(update={"tool_calls": truncated_tool_calls})]}
```

- 默认最大并发：`MAX_CONCURRENT_SUBAGENTS = 3`
- 允许范围：`[2, 4]`

#### Agent 间通信机制

DeerFlow 的 Multi-Agent 通信是 **"委派-轮询"模式**：

1. **状态传递**：通过 `sandbox_state`、`thread_data`、`thread_id` 共享文件系统和线程上下文
2. **任务传递**：`task_tool` 的 `prompt` 参数是唯一的输入载体
3. **结果回传**：子 Agent 的最终 `AIMessage.content` 作为字符串返回
4. **实时流**：通过 `stream_writer` 发送 `task_running` 事件，前端可实时看到子 Agent 的中间思考

---

## 5. LangChain / LangGraph 框架

**结论：本项目以 LangChain 和 LangGraph 为绝对核心基础设施，几乎所有 Agent 相关功能都建立在二者之上。**

### 5.1 LangGraph 图的定义和构建

DeerFlow **没有直接使用** `StateGraph.add_node()` / `add_edge()` 手工拼图（`external/ai-hedge-fund` 子项目除外）。相反，它完全基于 **LangChain 预构建的 `create_agent`**：

> **`backend/packages/harness/deerflow/agents/factory.py`**

```python
from langchain.agents import create_agent          # LangChain 预构建 agent
from langgraph.graph.state import CompiledStateGraph # 返回类型

def create_deerflow_agent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    middleware: list[AgentMiddleware] | None = None,
    system_prompt: str | None = None,
    state_schema: type[AgentState] = ThreadState,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    return create_agent(
        model=model,
        tools=effective_tools or None,
        middleware=effective_middleware,
        system_prompt=system_prompt,
        state_schema=effective_state,
        checkpointer=checkpointer,
        name=name,
    )
```

**LangGraph Server 配置**（`backend/langgraph.json`）：

```json
{
  "$schema": "https://langgra.ph/schema.json",
  "python_version": "3.12",
  "graphs": {
    "lead_agent": "deerflow.agents:make_lead_agent"
  },
  "auth": {
    "path": "./app/gateway/langgraph_auth.py:auth"
  },
  "checkpointer": {
    "path": "./packages/harness/deerflow/runtime/checkpointer/async_provider.py:make_checkpointer"
  }
}
```

### 5.2 扩展机制：AgentMiddleware 链

由于不直接操作节点和边，DeerFlow 通过 **14 层 AgentMiddleware** 在 `create_agent` 的预定义生命周期钩子中注入行为：

| 顺序 | Middleware | 职责 |
|------|-----------|------|
| 0 | `ThreadDataMiddleware` | 线程数据初始化 |
| 1 | `UploadsMiddleware` | 用户上传文件处理 |
| 2 | `SandboxMiddleware` | 沙箱环境注入 |
| 3 | `DanglingToolCallMiddleware` | 补全缺失的 ToolMessage |
| 4 | `GuardrailMiddleware` | 内容安全护栏 |
| 5 | `ToolErrorHandlingMiddleware` | 工具异常捕获并转为 ToolMessage |
| 6 | `SummarizationMiddleware` | 长上下文自动摘要 |
| 7 | `TodoMiddleware` | 计划模式任务列表 |
| 8 | `TitleMiddleware` | 自动生成对话标题 |
| 9 | `MemoryMiddleware` | 对话记忆更新队列 |
| 10 | `ViewImageMiddleware` | 多模态图像注入 |
| 11 | `SubagentLimitMiddleware` | 并行子 agent 限制 |
| 12 | `LoopDetectionMiddleware` | 循环工具调用检测 |
| 13 | `ClarificationMiddleware` | 澄清请求拦截（总是最后） |

每个 Middleware 可在以下钩子中介入：
- `before_model`：在模型推理前修改状态
- `after_model`：在模型输出后、工具执行前拦截
- `wrap_tool_call`：包裹工具调用
- `after_agent`：整个 Agent 轮次结束后

### 5.3 LangChain 组件的使用

#### ChatModel（大模型封装）

- **基类**：`langchain_core.language_models.BaseChatModel`
- **工厂**：`backend/packages/harness/deerflow/models/factory.py` 的 `create_chat_model()`
- **支持的 Provider**：`ChatOpenAI`（含兼容网关）、`ClaudeChatModel`、`CodexChatModel`、`MindIEChatModel`、`vLLM` 等
- **关键特性**：自动开启 `stream_usage`、thinking 模式切换、reasoning_effort 映射、tracing callbacks 注入

```python
def create_chat_model(name=None, thinking_enabled=False, **kwargs) -> BaseChatModel:
    model_class = resolve_class(model_config.use, BaseChatModel)
    model_instance = model_class(**kwargs, **model_settings_from_config)
    callbacks = build_tracing_callbacks()
    model_instance.callbacks = [*existing_callbacks, *callbacks]
    return model_instance
```

#### Tools（工具系统）

- **基类**：`langchain.tools.BaseTool`
- **装饰器**：大量工具使用 `@tool("name", parse_docstring=True)` 定义

#### Messages（消息类型）

广泛使用 LangChain 标准消息类型进行序列化和流式处理：

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
```

#### RunnableConfig

作为 LangGraph 运行时配置载体，贯穿 agent 创建、流式调用和中间件上下文。

### 5.4 状态管理（State、Checkpointer、Store）

#### State 定义

`ThreadState` 继承自 `langchain.agents.AgentState`，使用 `Annotated` + reducer 函数实现状态合并：

```python
from langchain.agents import AgentState
from typing import Annotated, NotRequired, TypedDict

def merge_artifacts(existing, new):
    return list(dict.fromkeys((existing or []) + (new or [])))

class ThreadState(AgentState):
    artifacts: Annotated[list[str], merge_artifacts]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
```

#### Checkpointer（检查点持久化）

支持 **memory / sqlite / postgres** 三种后端：

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
```

#### Store（跨线程 KV 存储）

Store 与 Checkpointer **共享同一后端配置**：

```python
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite.aio import AsyncSqliteStore
from langgraph.store.postgres.aio import AsyncPostgresStore
```

### 5.5 LangGraph 的流式执行

#### 服务端异步流式（Gateway）

> **`backend/packages/harness/deerflow/runtime/runs/worker.py`**

```python
async def run_agent(...):
    agent = agent_factory(config=runnable_config)
    agent.checkpointer = checkpointer
    agent.store = store

    async for chunk in agent.astream(graph_input, config=runnable_config, stream_mode="values"):
        if record.abort_event.is_set():
            break
        await bridge.publish(run_id, "values", serialize(chunk))
```

支持多 mode 组合和 subgraph 展开：
- `stream_mode="values"` / `"updates"` / `"messages"` / `"custom"`
- `subgraphs=True` 时前端可观察子图内部状态

#### 客户端同步流式（Embedded SDK）

> **`backend/packages/harness/deerflow/client.py`**

```python
for item in self._agent.stream(state, config=config, stream_mode=["values", "messages", "custom"]):
    if mode == "messages":
        msg_chunk, _metadata = chunk
        if isinstance(msg_chunk, AIMessage):
            yield StreamEvent(type="messages-tuple", data={"type": "ai", "content": text})
```

### 5.6 与 LangSmith / Langfuse 的集成

> **`backend/packages/harness/deerflow/tracing/factory.py`**

通过 **LangChain Callback Handler** 机制集成：

```python
from langchain_core.tracers.langchain import LangChainTracer
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

def build_tracing_callbacks() -> list[Any]:
    for provider in enabled_providers:
        if provider == "langsmith":
            callbacks.append(_create_langsmith_tracer(...))
        elif provider == "langfuse":
            callbacks.append(_create_langfuse_handler(...))
    return callbacks
```

**自动注入到模型**：`create_chat_model()` 会在模型实例化后自动附加 tracing callbacks。

### 5.7 设计哲学

DeerFlow 选择**高度封装**而非**低层拼装**——把 LangGraph 的节点/边细节交给 `create_agent`，自身聚焦于通过 **Middleware 管道**和**配置驱动工厂**来构建企业级 agent 功能（护栏、记忆、沙箱、子 agent、标题生成、Token 审计等）。这使得代码更紧凑，但也意味着图的拓扑结构受限于 `create_agent` 的内部实现。

---

## 6. Tool Use（工具使用）

**结论：本项目深度且广泛地使用了 Tool Use，构建了四层工具体系（内置工具 + 配置工具 + MCP 工具 + ACP 工具），并围绕工具调用实现了完整的安全控制机制。**

### 6.1 工具定义和注册机制

#### @tool 装饰器

DeerFlow 基于 LangChain 的工具生态，所有工具均使用 `@tool` 装饰器定义：

```python
from langchain.tools import ToolRuntime, tool

@tool("bash", parse_docstring=True)
def bash_tool(runtime: ToolRuntime[ContextT, ThreadState], description: str, command: str) -> str:
    """Execute a bash command in a Linux environment.
    Args:
        description: Explain why you are running this command...
        command: The bash command to execute...
    """
```

- `parse_docstring=True`：自动从 docstring 提取参数描述生成 JSON Schema
- `return_direct=True`（如 `ask_clarification_tool`）：工具结果直接返回，不经过 Agent 再处理

#### 动态解析与注册

```python
# reflection/resolvers.py
def resolve_variable[T](variable_path: str, expected_type: type[T] | None = None) -> T:
    module_path, variable_name = variable_path.rsplit(":", 1)
    module = import_module(module_path)
    variable = getattr(module, variable_name)
    return variable
```

`config.yaml` 中工具的声明格式：

```yaml
tools:
  - name: bash
    group: bash
    use: deerflow.sandbox.tools:bash_tool
  - name: web_search
    group: search
    use: deerflow.community.ddg_search.tools:web_search_tool
```

#### 工具聚合入口

> **`backend/packages/harness/deerflow/tools/tools.py`**（`get_available_tools`）

```python
def get_available_tools(...) -> list[BaseTool]:
    # 1. 从 config.yaml 加载配置化工具
    loaded_tools = [resolve_variable(cfg.use, BaseTool) for cfg in config.tools]
    # 2. 添加内置工具
    builtin_tools = [present_file_tool, ask_clarification_tool]
    if subagent_enabled:
        builtin_tools.append(task_tool)
    # 3. 添加 MCP 工具
    mcp_tools = get_cached_mcp_tools()
    # 4. 添加 ACP 工具
    acp_tools = build_invoke_acp_agent_tool(acp_agents)
    # 5. 按名称去重合并
    return unique_tools
```

### 6.2 内置工具列表

#### 沙箱/文件操作工具

> **`backend/packages/harness/deerflow/sandbox/tools.py`**

| 工具名 | 功能 |
|--------|------|
| `bash` | 在 Linux 环境中执行 bash 命令 |
| `ls` | 列出目录内容（树形格式，最多2层） |
| `glob` | 根据 glob 模式查找文件 |
| `grep` | 在文本文件中搜索匹配行 |
| `read_file` | 读取文本文件内容（支持行范围） |
| `write_file` | 写入文本内容到文件 |
| `str_replace` | 替换文件中的子字符串 |

#### Agent/交互工具

> **`backend/packages/harness/deerflow/tools/builtins/*.py`**

| 工具名 | 功能 |
|--------|------|
| `ask_clarification` | 向用户请求澄清/确认（会被 ClarificationMiddleware 拦截） |
| `present_files` | 将 `/mnt/user-data/outputs` 下的文件呈现给用户 |
| `view_image` | 读取图片文件并更新 `viewed_images` 状态 |
| `task` | 委派任务给子 Agent（Multi-Agent 核心） |
| `setup_agent` | 创建自定义 Agent |
| `skill_manage` | 创建/编辑/删除自定义 Skill |

#### 社区/第三方搜索工具

| 工具名 | 来源 |
|--------|------|
| `web_search` | DuckDuckGo、Tavily、Exa、InfoQuest |
| `web_fetch` | Tavily、Firecrawl、Jina AI |
| `image_search` | 图片搜索 |
| `music` | Last.fm 音乐搜索 |

### 6.3 MCP（Model Context Protocol）工具的集成

MCP 集成采用 **langchain-mcp-adapters** 库，支持三种传输类型：`stdio`、`sse`、`http`。

> **`backend/packages/harness/deerflow/mcp/tools.py`**

```python
async def get_mcp_tools() -> list[BaseTool]:
    from langchain_mcp_adapters.client import MultiServerMCPClient
    extensions_config = ExtensionsConfig.from_file()
    servers_config = build_servers_config(extensions_config)
    initial_oauth_headers = await get_initial_oauth_headers(extensions_config)
    tool_interceptors = [build_oauth_tool_interceptor(extensions_config)]
    client = MultiServerMCPClient(servers_config, tool_interceptors=tool_interceptors, tool_name_prefix=True)
    tools = await client.get_tools()
    # 同步包装：异步 coroutine 包装为 sync func
    for tool in tools:
        if getattr(tool, "func", None) is None and getattr(tool, "coroutine", None) is not None:
            tool.func = _make_sync_tool_wrapper(tool.coroutine, tool.name)
    return tools
```

**缓存与热更新**：通过监控 `extensions_config.json` 的 `mtime` 实现热更新。

**延迟加载（Tool Search）**：当 MCP 工具很多时，DeerFlow 支持延迟加载以节省上下文 token。Agent 需先调用 `tool_search(query)` 获取完整 schema。

### 6.4 ACP（Agent Communication Protocol）工具的集成

ACP 允许 DeerFlow **调用外部 ACP 兼容的 Agent**（如 Codex ACP adapter）：

> **`backend/packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py`**

```python
def build_invoke_acp_agent_tool(agents: dict) -> BaseTool:
    async def _invoke(agent: str, prompt: str, config: Annotated[RunnableConfig, InjectedToolArg] = None) -> str:
        async with spawn_agent_process(...) as (conn, proc):
            await conn.initialize(...)
            session = await conn.new_session(...)
            await conn.prompt(session_id=session.id, prompt=[text_block(prompt)])
        return client.collected_text
    return StructuredTool.from_function(name="invoke_acp_agent", ...)
```

### 6.5 工具调用流程

高层架构：

```
User Message → LLM (bind_tools) → AIMessage with tool_calls
                                    ↓
                              ToolNode 执行工具
                                    ↓
                              ToolMessage 返回结果
                                    ↓
                              LLM 继续推理 → Final Answer
```

中间件处理链：

| 中间件 | 作用 |
|--------|------|
| `ThreadDataMiddleware` | 创建线程数据目录 |
| `SandboxMiddleware` | 获取/释放沙箱环境 |
| `ToolErrorHandlingMiddleware` | 将工具异常转为 ToolMessage |
| `DeferredToolFilterMiddleware` | 过滤延迟工具 schema |
| `DanglingToolCallMiddleware` | 修复中断导致的缺失 ToolMessage |
| `ClarificationMiddleware` | 拦截澄清请求并中断执行 |

### 6.6 工具运行时上下文（ToolRuntime）

`ToolRuntime` 包含三个核心字段：

```python
runtime.state      # AgentState：包含 thread_data, sandbox, viewed_images 等
runtime.context    # dict：运行时上下文，如 thread_id, run_id, locale, sandbox_id
runtime.config     # RunnableConfig：包含 configurable, metadata, callbacks
```

沙箱懒加载示例：

```python
def ensure_sandbox_initialized(runtime: ToolRuntime) -> Sandbox:
    sandbox_state = runtime.state.get("sandbox")
    if sandbox_state:
        return provider.get(sandbox_state["sandbox_id"])
    thread_id = runtime.context.get("thread_id") or runtime.config.get("configurable", {}).get("thread_id")
    sandbox_id = provider.acquire(thread_id)
    runtime.state["sandbox"] = {"sandbox_id": sandbox_id}
    return provider.get(sandbox_id)
```

### 6.7 工具权限和安全控制

#### 主机 Bash 安全控制

```python
def is_host_bash_allowed(config=None) -> bool:
    if not uses_local_sandbox_provider(config):
        return True  # AioSandboxProvider 默认允许（容器隔离）
    return bool(getattr(sandbox_cfg, "allow_host_bash", False))
```

当使用 `LocalSandboxProvider` 时，主机 bash 默认被禁用。

#### 虚拟路径验证

```python
def validate_local_tool_path(path: str, thread_data: ThreadDataState | None, *, read_only: bool = False) -> None:
    _reject_path_traversal(path)
    if _is_skills_path(path):
        if not read_only:
            raise PermissionError(f"Write access to skills path is not allowed: {path}")
    if path.startswith(f"{VIRTUAL_PATH_PREFIX}/"):
        return  # /mnt/user-data/* 始终允许
```

#### 路径隐私保护

```python
def mask_local_paths_in_output(output: str, thread_data: ThreadDataState | None) -> str:
    # 用虚拟路径替换主机绝对路径，防止泄露主机目录结构
    # 替换 skills 主机路径 → /mnt/skills
    # 替换 ACP workspace 主机路径 → /mnt/acp-workspace
    # 替换 user-data 主机路径 → /mnt/user-data
```

---

## 7. 工作流编排

**结论：本项目使用了基于 LangGraph ReAct 循环的隐式工作流编排，配合 14 层 Middleware 链和技能系统实现能力扩展，没有采用显式的 DAG 节点编排。**

### 7.1 技能系统（Skills）

#### Skill 的定义

技能在 DeerFlow 中是一种**声明式的、基于 Markdown 的轻量级扩展单元**。

> **`backend/packages/harness/deerflow/skills/types.py`**

```python
@dataclass
class Skill:
    name: str
    description: str
    license: str | None
    skill_dir: Path
    skill_file: Path          # 指向 SKILL.md
    relative_path: Path
    category: SkillCategory   # 'public' 或 'custom'
    enabled: bool = False
```

每个技能目录包含一个 `SKILL.md` 文件，头部采用 **YAML front-matter** 声明元数据：

```yaml
---
name: bootstrap
description: Generate a personalized SOUL.md through...
---
```

#### Skill 的执行机制

技能**不是以独立进程或 DAG 节点方式执行**，而是在 Agent 运行时被**读取并注入为对话上下文**（SystemMessage）：

> **`backend/packages/harness/deerflow/subagents/executor.py`**

```python
async def _load_skill_messages(self) -> list[SystemMessage]:
    all_skills = await asyncio.to_thread(storage.load_skills, enabled_only=True)
    messages = []
    for skill in skills:
        content = await asyncio.to_thread(skill.skill_file.read_text, encoding="utf-8")
        messages.append(SystemMessage(content=f'<skill name="{skill.name}">\n{content}\n</skill>'))
    return messages
```

#### 技能安装与安全扫描

`installer.py` 提供 ZIP 归档安装：
- 防目录遍历攻击、ZIP Bomb 防御（最大 512MB）
- **AI 安全扫描**：对 SKILL.md、references、scripts 等执行内容审查，决定 `allow/warn/block`

### 7.2 Middleware 链

#### 构建工厂

> **`backend/packages/harness/deerflow/agents/factory.py`**

```python
def create_deerflow_agent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    middleware: list[AgentMiddleware] | None = None,
    features: RuntimeFeatures | None = None,
    extra_middleware: list[AgentMiddleware] | None = None,
    ...
) -> CompiledStateGraph:
```

#### 动态插入机制：`@Next` / `@Prev`

```python
@dataclass
class RuntimeFeatures:
    sandbox: bool | AgentMiddleware = True
    memory: bool | AgentMiddleware = False
    summarization: Literal[False] | AgentMiddleware = False
    subagent: bool | AgentMiddleware = False
    ...

def Next(anchor: type[AgentMiddleware]):
    cls._next_anchor = anchor

def Prev(anchor: type[AgentMiddleware]):
    cls._prev_anchor = anchor
```

工厂中通过 `_insert_extra()` 算法解析锚点并插入，支持冲突检测和循环依赖检测。

### 7.3 工作流定义：LangGraph StateGraph

DeerFlow 没有采用显式手写 DAG 节点编排的方式。工作流图是固定的 ReAct 循环：

- **节点**：模型推理节点、工具执行节点（由 LangGraph 预构建）
- **边**：模型输出 tool_calls → 工具节点 → 模型节点；无 tool_calls → `__end__`

用户通过 **Skills** 和 **Tools** 扩展能力，而非通过拖拽节点定义 DAG。

### 7.4 任务分解和并行执行

#### Task Tool

主代理通过调用 `task` 工具将复杂任务委托给子代理（详见第 4.4 节）。

#### 并行执行与限制

- **并行限制**：`SubagentLimitMiddleware` 截断单条 AI 消息中超过 `max_concurrent`（默认 3）的 `task` 工具调用
- **后台异步执行**：`task_tool` 调用 `execute_async()`，提交到全局 `ThreadPoolExecutor`（max_workers=3），通过**独立的持久 Event Loop** 运行

#### 轮询与流式状态推送

`task_tool` 对后台任务进行**后端轮询**（每 5 秒），并通过 `get_stream_writer()` 将子代理状态实时推送到主事件流：

```python
writer({"type": "task_started", "task_id": task_id, "description": description})
writer({"type": "task_running", "task_id": task_id, "message": message})
writer({"type": "task_completed", "task_id": task_id, "result": result.result})
```

### 7.5 子图（Subgraph）的使用

#### LangGraph 原生 Subgraph

在 `worker.py` 中支持 `stream_subgraphs` 参数：

```python
async for item in agent.astream(
    graph_input, config=runnable_config, stream_mode=lg_modes, subgraphs=stream_subgraphs
):
    mode, chunk = _unpack_stream_item(item, lg_modes, stream_subgraphs)
```

当 `stream_subgraphs=True` 时，LangGraph 输出三元组 `(namespace, mode, chunk)`，允许前端观察子图内部状态。

#### 子代理作为逻辑子图

每个子代理都是一个**独立编译的 `CompiledStateGraph`**，相对于主 Lead Agent 而言就是一个 Subgraph：
- 拥有独立的 `ThreadState` 实例和中间件链
- 通过 `recursion_limit` 限制最大轮数（默认 50-100）
- 禁止嵌套子代理

### 7.6 事件系统和流式推送

DeerFlow 拥有**三层事件体系**：

#### 运行级事件存储：RunEventStore

> **`backend/packages/harness/deerflow/runtime/events/store/base.py`**

```python
class RunEventStore(abc.ABC):
    async def put(self, *, thread_id, run_id, event_type, category, content, metadata, ...)
    async def list_messages(self, thread_id, limit=50, ...)
    async def list_events(self, thread_id, run_id, ...)
```

#### LangChain 回调采集：RunJournal

> **`backend/packages/harness/deerflow/runtime/journal.py`**

`RunJournal` 是 `BaseCallbackHandler` 子类，挂接到 LangGraph 执行过程中：

```python
class RunJournal(BaseCallbackHandler):
    def on_chat_model_start(self, serialized, messages, ...):
        # 记录 llm.human.input
    def on_llm_end(self, response, ...):
        # 记录 llm.ai.response，累加 token usage
    def on_tool_end(self, output, ...):
        # 记录 llm.tool.result
```

#### 流式桥接：StreamBridge → SSE

> **`backend/packages/harness/deerflow/runtime/stream_bridge/memory.py`**

```python
class MemoryStreamBridge(StreamBridge):
    async def publish(self, run_id: str, event: str, data: Any):
        # 基于 asyncio.Condition 实现发布-订阅
        # 每个 run 保留最近 256 条事件（支持断线重连回放）
        # 心跳机制：15 秒无事件下发 __heartbeat__
```

---

## 8. 记忆机制

**结论：本项目构建了非常完整且精细的多层记忆体系，涵盖短期记忆（ThreadState + Checkpointer）、长期记忆（结构化 JSON 文件）、记忆摘要（SummarizationMiddleware）和记忆更新（LLM 驱动 + 防抖队列）。**

### 8.1 短期记忆（Short-term Memory）

短期记忆体现为 **LangGraph 的 ThreadState**，核心是对话消息列表 `messages`。

```python
class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
```

`ThreadDataMiddleware` 在每个 agent 执行前运行，为当前线程创建/获取数据目录。

### 8.2 长期记忆（Long-term Memory）

#### 记忆数据结构

> **`backend/packages/harness/deerflow/agents/memory/storage.py`**

```python
def create_empty_memory() -> dict[str, Any]:
    return {
        "version": "1.0",
        "lastUpdated": utc_now_iso_z(),
        "user": {
            "workContext": {"summary": "", "updatedAt": ""},
            "personalContext": {"summary": "", "updatedAt": ""},
            "topOfMind": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentMonths": {"summary": "", "updatedAt": ""},
            "earlierContext": {"summary": "", "updatedAt": ""},
            "longTermBackground": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }
```

- **user**：职业角色、沟通偏好、当前优先事项
- **history**：近 1-3 个月、3-12 个月、长期背景
- **facts**：结构化事实列表，包含 `id`, `content`, `category`, `confidence`, `createdAt`, `source`

#### 文件存储实现

`FileMemoryStorage` 特点：
- **缓存机制**：按 `(user_id, agent_name)` 缓存，通过文件 `mtime` 判断缓存有效性
- **原子写入**：使用临时文件 + `replace` 保证写入原子性
- **多租户支持**：支持 `user_id` 和 `agent_name` 隔离
  - 全局记忆：`memory.json`
  - 按 Agent：`agents/{agent_name}/memory.json`
  - 按用户：`users/{user_id}/memory.json`

#### 记忆注入系统提示词

```python
def _get_memory_context(agent_name: str | None = None) -> str:
    memory_data = get_memory_data(agent_name, user_id=get_effective_user_id())
    memory_content = format_memory_for_injection(memory_data, max_tokens=config.max_injection_tokens)
    return f"""<memory>\n{memory_content}\n</memory>\n"""
```

`format_memory_for_injection()` 按 token 预算裁剪事实列表：按置信度降序排列，逐行计算 token，超出预算时截断。对 correction 类型的事实特殊标注 `avoid: {source_error}`。

### 8.3 Checkpointer 机制：状态持久化

支持三种后端：

| 类型 | 特点 |
|------|------|
| **memory** | `InMemorySaver`，进程内，重启丢失 |
| **sqlite** | `AsyncSqliteSaver`，本地文件持久化 |
| **postgres** | `AsyncPostgresSaver`，数据库存储 |

使用场景：
- **对话恢复**：用户重新打开线程时，LangGraph 从 checkpointer 加载历史状态
- **断点续传**：Agent 执行中断后，从最后一个 checkpoint 恢复
- **回滚**：取消 Run 后恢复到 Run 开始前的 checkpoint

### 8.4 Store 机制：LangGraph 键值存储

Store 与 Checkpointer **共享同一配置**，用于保存线程元数据、运行事件等非图状态数据。

#### RunEventStore

统一存储运行事件流：
- `put()`：写入事件，自动分配递增 `seq`
- `list_messages()`：查询某线程的展示消息
- 支持双向游标分页（`before_seq` / `after_seq`）

#### ThreadMetaStore

抽象接口定义线程 CRUD 操作：
- `MemoryThreadMetaStore`：包装 LangGraph `BaseStore`
- `ThreadMetaRepository`：SQLAlchemy + 异步会话

### 8.5 记忆摘要（Summarization）：上下文压缩

> **`backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py`**

```python
class DeerFlowSummarizationMiddleware(SummarizationMiddleware):
    def __init__(self, ..., preserve_recent_skill_count: int = 5,
                 preserve_recent_skill_tokens: int = 25_000, ...):
```

工作流程：
1. `before_model()` 在模型调用前触发
2. 计算消息总 token，判断是否需要摘要
3. 确定 `cutoff_index`，将消息分为待摘要和保留两部分
4. **Skill Rescue**：识别并保留最近加载的 skill 文件内容（避免摘要后丢失 skill 上下文）
5. 调用 LLM 生成摘要
6. 用 `RemoveMessage(id=REMOVE_ALL_MESSAGES)` 清除旧消息，替换为摘要消息 + 保留消息

### 8.6 记忆的更新和去重机制

#### 更新触发流程

> **`backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py`**

`MemoryMiddleware` 在每次 Agent 执行后（`after_agent`）触发：
1. 从 state 提取 `messages`
2. 调用 `filter_messages_for_memory()` 过滤：只保留 `human` 和最终 `ai` 消息
3. 检测修正信号（`detect_correction`）和强化信号（`detect_reinforcement`）
4. 将过滤后的对话加入 `MemoryUpdateQueue`

#### Debounce 队列

> **`backend/packages/harness/deerflow/agents/memory/queue.py`**

```python
class MemoryUpdateQueue:
    def add(self, thread_id, messages, ...):
        # 同一线程的多次更新会合并
        self._enqueue_locked(...)
        self._reset_timer()  # 重置 debounce 计时器（默认 30 秒）

    def _schedule_timer(self, delay_seconds: float):
        self._timer = threading.Timer(delay_seconds, self._process_queue)
        self._timer.start()
```

- **去重合并**：同一 `thread_id` 的新消息会替换队列中旧记录
- **防抖处理**：默认延迟 30 秒，避免频繁调用 LLM

#### LLM 驱动的记忆更新

> **`backend/packages/harness/deerflow/agents/memory/updater.py`**

```python
def _do_update_memory_sync(self, messages, thread_id, agent_name, ...):
    current_memory, prompt = self._prepare_update_prompt(...)
    model = self._get_model()
    response = model.invoke(prompt, config={"run_name": "memory_agent"})
    return self._finalize_update(current_memory, response.content, thread_id, agent_name)
```

关键细节：
- **同步线程池**：使用 `ThreadPoolExecutor`（`max_workers=4`）执行同步 `model.invoke()`，避免与主事件循环的 async httpx client 冲突
- **上传过滤**：`_strip_upload_mentions_from_memory()` 使用正则移除文件上传相关句子

#### 去重与限制机制

```python
def _apply_updates(self, current_memory, update_data, thread_id):
    # 1. 移除 facts
    facts_to_remove = set(update_data.get("factsToRemove", []))
    current_memory["facts"] = [f for f in current_memory["facts"] if f["id"] not in facts_to_remove]
    # 2. 添加新 facts（内容去重）
    existing_fact_keys = {_fact_content_key(fact.get("content")) for fact in current_memory["facts"]}
    for fact in new_facts:
        if confidence >= config.fact_confidence_threshold:  # 默认 0.7
            fact_key = _fact_content_key(normalized_content)
            if fact_key in existing_fact_keys:
                continue  # 跳过重复
            current_memory["facts"].append(fact_entry)
    # 3. 数量限制（默认 100）
    if len(current_memory["facts"]) > config.max_facts:
        current_memory["facts"] = sorted(..., key=lambda f: f.get("confidence", 0), reverse=True)[:config.max_facts]
```

去重策略：
- **内容去重**：基于 `_fact_content_key()`（`casefold()` 后的 stripped content）
- **置信度过滤**：低于 0.7 的事实丢弃
- **数量上限**：超出 100 时按置信度排序保留高分事实

#### 信号检测

> **`backend/packages/harness/deerflow/agents/memory/message_processing.py`**

```python
_CORRECTION_PATTERNS = (
    re.compile(r"\bthat(?:'s| is) (?:wrong|incorrect)\b", re.IGNORECASE),
    re.compile(r"不对"), re.compile(r"你理解错了"), ...
)

_REINFORCEMENT_PATTERNS = (
    re.compile(r"\bperfect(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"完全正确(?:[。！？!?.]|$)"),
    ...
)
```

- **Correction**：检测用户纠正，生成高置信度（≥0.95）的 `correction` 类型 fact
- **Reinforcement**：检测用户肯定，生成高置信度（≥0.9）的 `preference`/`behavior` 类型 fact

#### 摘要触发时的记忆 Flush

> **`backend/packages/harness/deerflow/agents/memory/summarization_hook.py`**

```python
def memory_flush_hook(event: SummarizationEvent) -> None:
    filtered_messages = filter_messages_for_memory(list(event.messages_to_summarize))
    queue = get_memory_queue()
    queue.add_nowait(thread_id=event.thread_id, messages=filtered_messages, ...)
```

在 `DeerFlowSummarizationMiddleware` 执行摘要前，通过 `before_summarization` hook 将被摘要的消息立即 flush 到记忆队列，确保摘要前的完整对话被保存到长期记忆。

### 8.7 Memory API 路由

> **`backend/app/gateway/routers/memory.py`**

提供 RESTful API 供外部管理记忆：

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/memory` | 获取记忆数据 |
| POST | `/api/memory/reload` | 强制从文件重新加载 |
| DELETE | `/api/memory` | 清空所有记忆 |
| POST | `/api/memory/facts` | 手动创建 fact |
| DELETE | `/api/memory/facts/{fact_id}` | 删除 fact |
| PATCH | `/api/memory/facts/{fact_id}` | 部分更新 fact |
| GET | `/api/memory/export` | 导出记忆 |
| POST | `/api/memory/import` | 导入记忆 |

---

## 9. 技术栈对比总表

| # | 技术栈 | 是否使用 | 实现深度 | 核心文件/模块 | 说明 |
|---|--------|---------|---------|-------------|------|
| 1 | **Prompt Engineering** | ✅ 大量使用 | 极深 | `agents/lead_agent/prompt.py`, `agents/memory/prompt.py`, `skills/public/*` | 模块化动态组装、渐进式披露、Prompt Caching、元提示词工程 |
| 2 | **RAG 技术** | ❌ 未使用 | — | — | 采用 Web Search + 长上下文 + Summarization 替代传统 RAG |
| 3 | **ReAct 模式** | ✅ 大量使用 | 极深 | `agents/lead_agent/agent.py`, `agents/factory.py` | 基于 LangGraph `create_agent` 的 ReAct 循环 + 14 层 Middleware 扩展 |
| 3 | **Plan 模式** | ✅ 使用 | 深 | `agents/middlewares/todo_middleware.py` | TodoMiddleware + write_todos 工具实现任务规划 |
| 3 | **Execute 模式** | ✅ 大量使用 | 极深 | `subagents/executor.py`, `tools/builtins/task_tool.py` | SubagentExecutor 异步流式执行引擎 |
| 3 | **Multi-Agent** | ✅ 大量使用 | 极深 | `subagents/executor.py`, `tools/builtins/task_tool.py`, `agents/middlewares/subagent_limit_middleware.py` | Lead Agent + Sub-agent 委派-轮询模式，最大并发 3 |
| 4 | **LangChain/LangGraph** | ✅ 大量使用 | 极深 | 整个 `agents/`、`runtime/`、`models/` 目录 | 核心基础设施，`create_agent` 预构建 + Middleware 扩展 |
| 5 | **Tool Use** | ✅ 大量使用 | 极深 | `tools/tools.py`, `sandbox/tools.py`, `mcp/tools.py`, `tools/builtins/*.py` | 四层工具体系 + 完整安全控制 + MCP/ACP 扩展 |
| 6 | **工作流编排** | ✅ 使用 | 深 | `agents/middlewares/`, `skills/`, `runtime/stream_bridge/` | 隐式 ReAct 循环 + Middleware 链 + 技能系统，无显式 DAG |
| 7 | **记忆机制** | ✅ 大量使用 | 极深 | `agents/memory/`, `agents/middlewares/summarization_middleware.py`, `runtime/checkpointer/` | 短期记忆(ThreadState) + 长期记忆(JSON) + Checkpointer + Summarization + 防抖队列 |

---

## 附录：核心文件索引

### Agent 核心

| 文件 | 路径 |
|------|------|
| Lead Agent 工厂 | `backend/packages/harness/deerflow/agents/lead_agent/agent.py` |
| 通用 Agent 工厂 | `backend/packages/harness/deerflow/agents/factory.py` |
| 状态定义 | `backend/packages/harness/deerflow/agents/thread_state.py` |
| 系统提示词模板 | `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` |
| 运行时特性 | `backend/packages/harness/deerflow/agents/features.py` |

### Middleware

| 文件 | 路径 |
|------|------|
| SummarizationMiddleware | `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py` |
| TodoMiddleware | `backend/packages/harness/deerflow/agents/middlewares/todo_middleware.py` |
| LoopDetectionMiddleware | `backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py` |
| ClarificationMiddleware | `backend/packages/harness/deerflow/agents/middlewares/clarification_middleware.py` |
| MemoryMiddleware | `backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py` |
| SubagentLimitMiddleware | `backend/packages/harness/deerflow/agents/middlewares/subagent_limit_middleware.py` |
| ToolErrorHandlingMiddleware | `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py` |

### Sub-agent

| 文件 | 路径 |
|------|------|
| SubagentExecutor | `backend/packages/harness/deerflow/subagents/executor.py` |
| Subagent Registry | `backend/packages/harness/deerflow/subagents/registry.py` |
| 通用子 Agent | `backend/packages/harness/deerflow/subagents/builtins/general_purpose.py` |
| Bash 子 Agent | `backend/packages/harness/deerflow/subagents/builtins/bash_agent.py` |

### 工具

| 文件 | 路径 |
|------|------|
| 工具聚合入口 | `backend/packages/harness/deerflow/tools/tools.py` |
| Task Tool | `backend/packages/harness/deerflow/tools/builtins/task_tool.py` |
| 沙箱工具 | `backend/packages/harness/deerflow/sandbox/tools.py` |
| MCP 工具 | `backend/packages/harness/deerflow/mcp/tools.py` |
| ACP 工具 | `backend/packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py` |

### 记忆

| 文件 | 路径 |
|------|------|
| 记忆存储 | `backend/packages/harness/deerflow/agents/memory/storage.py` |
| 记忆更新器 | `backend/packages/harness/deerflow/agents/memory/updater.py` |
| 记忆队列 | `backend/packages/harness/deerflow/agents/memory/queue.py` |
| 记忆提示 | `backend/packages/harness/deerflow/agents/memory/prompt.py` |
| 消息处理 | `backend/packages/harness/deerflow/agents/memory/message_processing.py` |

### 运行时

| 文件 | 路径 |
|------|------|
| Run Worker | `backend/packages/harness/deerflow/runtime/runs/worker.py` |
| Run Manager | `backend/packages/harness/deerflow/runtime/runs/manager.py` |
| StreamBridge | `backend/packages/harness/deerflow/runtime/stream_bridge/memory.py` |
| Checkpointer 工厂 | `backend/packages/harness/deerflow/runtime/checkpointer/async_provider.py` |
| Store 工厂 | `backend/packages/harness/deerflow/runtime/store/async_provider.py` |
| RunJournal | `backend/packages/harness/deerflow/runtime/journal.py` |

### Gateway

| 文件 | 路径 |
|------|------|
| Gateway 主应用 | `backend/app/gateway/app.py` |
| Thread Runs 路由 | `backend/app/gateway/routers/thread_runs.py` |
| 服务层 | `backend/app/gateway/services.py` |
| Memory API | `backend/app/gateway/routers/memory.py` |

### 配置

| 文件 | 路径 |
|------|------|
| LangGraph 配置 | `backend/langgraph.json` |
| Agent 配置 | `backend/packages/harness/deerflow/config/agents_config.py` |
| 子 Agent 配置 | `backend/packages/harness/deerflow/config/subagents_config.py` |
| 记忆配置 | `backend/packages/harness/deerflow/config/memory_config.py` |
| 摘要配置 | `backend/packages/harness/deerflow/config/summarization_config.py` |
| Tracing 配置 | `backend/packages/harness/deerflow/config/tracing_config.py` |

### 技能

| 目录 | 路径 |
|------|------|
| 内置技能 | `skills/public/` |
| 技能类型定义 | `backend/packages/harness/deerflow/skills/types.py` |
| 技能解析器 | `backend/packages/harness/deerflow/skills/parser.py` |
| 技能安装器 | `backend/packages/harness/deerflow/skills/installer.py` |

---

> 文档生成时间：2026-05-22
> 基于 DeerFlow 2.0 代码库分析
