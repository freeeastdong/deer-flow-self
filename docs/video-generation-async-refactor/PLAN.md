# 视频生成异步化重构计划（子方案 B：提交+查询分离）

> **⚠️ 计划状态：已暂停（PAUSED）**
>
> 本计划目前**尚未开始执行**，处于封存状态。所有 Phase 和 Step 均未实施，代码库未做任何改动。
>
> - 封存日期：2026-05-10
> - 暂停原因：待后续评估后决定是否启动
> - 恢复执行前，请先确认是否继续沿用本方案，或需要根据当时情况调整设计
>
> 如需恢复执行，请从 **Phase 1** 开始，按步骤逐一实施，并在 `CHANGELOG.md` 中记录。

---

## 1. 项目概述

### 1.1 背景
当前视频生成通过 `generate.py` 在 AIO Sandbox 内同步阻塞执行，存在以下问题：
- `AioSandbox` 的 `no_change_timeout=600`（10 分钟）会在视频生成完成前强制终止任务
- Subagent 默认 15 分钟超时不足以覆盖 10 秒视频生成（通常需 30-60 分钟）
- Agent 被阻塞，用户体验差（长时间无响应）
- 无进度反馈，用户无法知道当前生成状态

### 1.2 目标
将视频生成从"同步阻塞执行"重构为"异步提交 + 后端轮询 + 前端进度展示"模式：
1. `generate.py` 只负责提交工作流到 ComfyUI，5 秒内返回 `prompt_id`
2. 后端启动后台线程轮询 ComfyUI 状态并下载结果
3. 前端实时显示生成进度（排队中 / 生成中 XX% / 下载中 / 完成）
4. 任务与 agent session 解耦，浏览器关闭后任务继续执行

### 1.3 范围
**涉及模块**：
- `skills/public/video-generation/scripts/generate.py`
- `backend/packages/harness/deerflow/`（新增服务层）
- `backend/app/gateway/routers/`（新增 REST API）
- `frontend/src/components/workspace/artifacts/`（前端进度展示）
- `frontend/src/core/`（新增 API 客户端）

**不涉及**：
- ComfyUI 本身的工作流定义（`.json` 文件不变）
- AIO Sandbox 的核心架构（只调整超时配置）
- 其他 skill 的生成逻辑

### 1.4 成功标准
- [ ] 10 秒视频生成不再触发 AIO Sandbox 超时
- [ ] 前端可以显示实时生成进度
- [ ] 浏览器刷新/关闭后，任务继续执行且可恢复跟踪
- [ ] 同时提交 3 个以上视频任务时，后端自动排队处理
- [ ] 原有 2 秒短视频功能不受影响（向后兼容）

---

## 2. 架构设计

### 2.1 数据流

```
┌─────────────┐
│   用户请求   │ "生成10秒视频"
└──────┬──────┘
       │
       ▼
┌─────────────┐     1. 提交工作流      ┌─────────────┐
│  Lead Agent  │ ────────────────────> │  AIO Sandbox │
│              │    (generate.py        │   容器       │
│              │     --submit-only)     │  (5秒内释放) │
└──────┬───────┘                       └──────┬───────┘
       │                                       │
       │ 2. 返回 prompt_id + task_id            │
       ▼                                       │
┌─────────────┐                               │
│   前端界面   │ ◄──── 4. 实时进度推送 ─────────┤
│  (进度条)    │      (SSE/轮询)                │
└─────────────┘                               │
                                              │
                       ┌──────────────────────┘
                       │ 3. 后端轮询 ComfyUI
                       ▼
              ┌─────────────────┐
              │ VideoGeneration │
              │  TaskManager    │
              │  (后台线程)      │
              └────────┬────────┘
                       │
                       ├── 轮询 /history/{prompt_id}
                       ├── 下载视频到 outputs/
                       └── 更新任务状态 → DB/State
```

### 2.2 新增组件

| 组件名 | 职责 | 位置（建议） |
|--------|------|-------------|
| `VideoGenerationTask` | 任务数据模型（dataclass） | `deerflow/tasks/video_generation.py` |
| `VideoGenerationTaskStore` | 任务持久化存储（SQLite/JSON） | `deerflow/tasks/video_generation_store.py` |
| `ComfyUIAsyncClient` | 封装 ComfyUI API（提交+轮询+下载） | `deerflow/tasks/comfyui_async_client.py` |
| `VideoGenerationWorker` | 后台轮询工作线程 | `deerflow/tasks/video_generation_worker.py` |
| `VideoGenerationRouter` | REST API（查询任务状态） | `app/gateway/routers/video_generation.py` |
| `useVideoTask` | 前端 Hook（轮询任务状态） | `frontend/src/core/tasks/hooks.ts` |

### 2.3 任务状态机

```
PENDING ──► QUEUED ──► GENERATING ──► DOWNLOADING ──► COMPLETED
   │           │            │                │
   └───────────┴────────────┴────────────────┘──► FAILED
   │           │            │
   └───────────┴────────────┘──► CANCELLED
```

| 状态 | 含义 | 前端展示 |
|------|------|---------|
| `PENDING` | 已提交，等待后端处理 | "准备中..." |
| `QUEUED` | 后端已接收，ComfyUI 排队中 | "排队中 (#{queue_position})" |
| `GENERATING` | ComfyUI 正在生成 | "生成中 ({progress}%)" |
| `DOWNLOADING` | 生成完成，正在下载文件 | "下载中..." |
| `COMPLETED` | 文件已保存到 outputs/ | 显示下载按钮 |
| `FAILED` | 生成或下载失败 | "生成失败：{error_msg}" |
| `CANCELLED` | 用户取消 | "已取消" |

---

## 3. 详细实施步骤

> **执行原则**：每个 Phase 可以独立作为一个 AI 会话完成。Phase 内部步骤按依赖顺序执行，不可跳过。
> 
> **回退原则**：每个步骤执行前，相关文件必须先通过 `git checkout -b` 创建 feature 分支，或通过 `cp` 备份。详见第 5 节。

---

### Phase 1：基础数据层（无侵入性）
**目标**：创建任务模型和存储层，不影响现有任何功能。
**预计耗时**：1 个 AI 会话
**风险等级**：低

#### Step 1.1：创建目录结构
```
backend/packages/harness/deerflow/tasks/
├── __init__.py
├── video_generation.py          # 数据模型 + 状态机
├── video_generation_store.py     # 持久化存储
├── comfyui_async_client.py       # ComfyUI API 客户端
└── video_generation_worker.py    # 后台工作线程
```

#### Step 1.2：定义 `VideoGenerationTask` 数据模型
**文件**：`backend/packages/harness/deerflow/tasks/video_generation.py`

> **架构决策**：复用 DeerFlow 现有的 SQLAlchemy ORM 和 `deerflow.db`，不创建独立数据库文件。详见第 2.3 节架构决策说明。

**SQLAlchemy ORM 模型**：
```python
from sqlalchemy import Column, String, Float, DateTime, Integer, Enum as SQLEnum
from sqlalchemy.orm import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    GENERATING = "generating"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class VideoGenerationTask(Base):
    __tablename__ = "video_generation_tasks"
    
    task_id = Column(String, primary_key=True)              # UUID
    thread_id = Column(String, nullable=False, index=True)  # 关联 thread
    user_id = Column(String, nullable=True)
    prompt_id = Column(String, nullable=True)               # ComfyUI prompt_id
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    
    # 输入参数（JSON 序列化存储，保持灵活性）
    prompt_file = Column(String)
    output_file = Column(String)
    aspect_ratio = Column(String)
    duration = Column(Float)
    
    # 进度信息
    progress = Column(Float, default=0.0)
    queue_position = Column(Integer, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # 错误信息
    error_message = Column(String, nullable=True)
```

**设计要点**：
- 使用 `declarative_base()` 与现有 ORM 体系保持一致
- `task_id` 使用 UUID 字符串主键，与现有 `runs`/`threads` 表风格一致
- `thread_id` 加索引，支持按 thread 快速查询
- 时间戳统一使用 `datetime.utcnow()`，与现有表一致

#### Step 1.3：实现 `VideoGenerationTaskStore`
**文件**：`backend/packages/harness/deerflow/tasks/video_generation_store.py`

**需求**：
- **复用 DeerFlow 现有数据库连接**（`deerflow.db`），不创建独立数据库文件
- 复用 `deerflow.persistence.engine.get_session_factory()` 获取的 `async_sessionmaker`
- 支持 CRUD + 按 thread_id 查询 + 按状态查询 + 按 task_id 查询
- 支持自动清理 7 天前的已完成任务

**实现**：
```python
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from deerflow.persistence.engine import get_session_factory
from deerflow.tasks.video_generation import VideoGenerationTask, TaskStatus

class VideoGenerationTaskStore:
    def __init__(self):
        self._session_factory = get_session_factory()
    
    async def create(self, task: VideoGenerationTask) -> None:
        async with self._session_factory() as session:
            session.add(task)
            await session.commit()
    
    async def get(self, task_id: str) -> VideoGenerationTask | None:
        async with self._session_factory() as session:
            return await session.get(VideoGenerationTask, task_id)
    
    async def get_by_thread(self, thread_id: str) -> list[VideoGenerationTask]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(VideoGenerationTask)
                .where(VideoGenerationTask.thread_id == thread_id)
                .order_by(VideoGenerationTask.created_at.desc())
            )
            return result.scalars().all()
    
    async def get_pending_tasks(self) -> list[VideoGenerationTask]:
        """获取所有待处理的任务，用于 Worker 重启后恢复"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(VideoGenerationTask)
                .where(VideoGenerationTask.status.in_([
                    TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.GENERATING, TaskStatus.DOWNLOADING
                ]))
                .order_by(VideoGenerationTask.created_at.asc())
            )
            return result.scalars().all()
    
    async def update_status(self, task_id: str, **kwargs) -> None:
        async with self._session_factory() as session:
            task = await session.get(VideoGenerationTask, task_id)
            if task:
                for key, value in kwargs.items():
                    setattr(task, key, value)
                await session.commit()
    
    async def cleanup_old_tasks(self, days: int = 7) -> int:
        """清理 N 天前的已完成任务，返回删除数量"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        async with self._session_factory() as session:
            result = await session.execute(
                delete(VideoGenerationTask)
                .where(VideoGenerationTask.status.in_([
                    TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED
                ]))
                .where(VideoGenerationTask.completed_at < cutoff)
            )
            await session.commit()
            return result.rowcount
```

**回退方式**：
- 数据库表由 `Base.metadata.create_all()` 自动创建
- 回退时删除 `video_generation_tasks` 表即可：
  ```sql
  DROP TABLE video_generation_tasks;
  ```
- 或通过 Alembic 降级 migration（如果后续引入 migration）

#### Step 1.4：实现 `ComfyUIAsyncClient`
**文件**：`backend/packages/harness/deerflow/tasks/comfyui_async_client.py`

**接口设计**：
```python
class ComfyUIAsyncClient:
    def __init__(self, base_url: str = "http://host.docker.internal:8188"): ...
    
    def submit_workflow(self, workflow: dict, client_id: str) -> str:
        """提交工作流，返回 prompt_id"""
        
    def get_status(self, prompt_id: str) -> dict:
        """查询任务状态，返回 {status, progress, outputs, ...}"""
        
    def download_output(self, file_info: dict, output_path: Path) -> None:
        """从 ComfyUI 下载视频文件"""
```

**注意**：此客户端**仅在后端进程内**使用，不在 sandbox 容器内使用。

#### Step 1.5 验证
- [ ] 单元测试：`VideoGenerationTaskStore` 的 CRUD 操作
- [ ] 单元测试：`ComfyUIAsyncClient.submit_workflow` 可以成功提交（需要 ComfyUI 运行）

---

### Phase 2：后台工作线程
**目标**：实现轮询 ComfyUI 并管理任务生命周期的后台线程。
**预计耗时**：1-2 个 AI 会话
**风险等级**：中
**前置依赖**：Phase 1 完成

#### Step 2.1：实现 `VideoGenerationWorker`
**文件**：`backend/packages/harness/deerflow/tasks/video_generation_worker.py`

**设计要点**：
- 使用 `threading.Thread` + `queue.Queue` 实现任务队列
- 单消费者线程（简化并发控制），串行处理视频生成任务
- 每 2 秒轮询一次 ComfyUI 状态
- 支持优雅关闭（`atexit` 注册 + `shutdown()` 方法）
- 从 `deerflow.db` 的 `video_generation_tasks` 表恢复未完成的任务（进程重启后）

**核心逻辑**：
```python
class VideoGenerationWorker(threading.Thread):
    def run(self):
        while not self._stop_event.is_set():
            task = self._get_next_pending_task()
            if task:
                self._process_task(task)
            else:
                time.sleep(2)
    
    def _process_task(self, task: VideoGenerationTask):
        # 1. 读取 prompt JSON
        # 2. 调用 ComfyUIAsyncClient.submit_workflow()
        # 3. 轮询状态直到完成/失败
        # 4. 下载视频到实际 outputs 目录
        # 5. 更新 task status = COMPLETED
```

#### Step 2.2：Worker 生命周期管理
**文件**：`backend/packages/harness/deerflow/tasks/__init__.py` + `app/gateway/app.py`

**需求**：
- 在 Gateway 启动时自动启动 `VideoGenerationWorker`
- 在 Gateway 关闭时（SIGTERM/SIGINT）优雅停止 Worker
- 提供全局单例 `get_video_generation_worker()`

#### Step 2.3 验证
- [ ] 手动提交一个测试任务到 Store，观察 Worker 是否正确轮询 ComfyUI
- [ ] 验证进程重启后，未完成的任务被自动恢复

---

### Phase 3：REST API 层
**目标**：为前端提供任务状态查询接口。
**预计耗时**：1 个 AI 会话
**风险等级**：低
**前置依赖**：Phase 1-2 完成

#### Step 3.1：新增 `VideoGenerationRouter`
**文件**：`backend/app/gateway/routers/video_generation.py`

**接口设计**：
```python
@router.get("/threads/{thread_id}/video-tasks")
async def list_video_tasks(thread_id: str) -> list[VideoTaskResponse]:
    """获取指定 thread 的所有视频生成任务"""

@router.get("/threads/{thread_id}/video-tasks/{task_id}")
async def get_video_task(thread_id: str, task_id: str) -> VideoTaskResponse:
    """获取单个任务详情"""

@router.post("/threads/{thread_id}/video-tasks/{task_id}/cancel")
async def cancel_video_task(thread_id: str, task_id: str) -> dict:
    """取消正在执行的任务"""

@router.get("/threads/{thread_id}/video-tasks/stream")
async def stream_video_task_updates(thread_id: str) -> EventSourceResponse:
    """SSE 实时推送任务状态变更（可选，Phase 5 再实现）"""
```

#### Step 3.2：注册路由到 Gateway
**文件**：`backend/app/gateway/app.py`

在 FastAPI app 创建时注册新路由，URL 前缀保持与现有 artifacts API 一致。

#### Step 3.3 验证
- [ ] 使用 `curl` 测试 API 可以正确返回任务列表
- [ ] 测试 404/403 边界条件

---

### Phase 4：`generate.py` 重构
**目标**：将脚本拆分为"提交模式"，并与后端 Worker 对接。
**预计耗时**：1 个 AI 会话
**风险等级**：中
**前置依赖**：Phase 1-3 完成

#### Step 4.1：重构 `generate.py`
**文件**：`skills/public/video-generation/scripts/generate.py`

**修改内容**：
1. 新增 `--submit-only` 参数：
   ```python
   parser.add_argument("--submit-only", action="store_true", 
                       help="仅提交工作流到 ComfyUI，不等待完成")
   ```
2. 当 `--submit-only` 时：
   - 读取 prompt JSON
   - 调用 `queue_prompt()`
   - 打印 `{"prompt_id": "xxx", "status": "submitted"}` 后退出
3. 保留原有完整逻辑作为默认行为（向后兼容）

#### Step 4.2：修改 `generate_video()` 函数
```python
def generate_video(..., submit_only: bool = False) -> str:
    # ... 原有 prompt 读取和 workflow 准备逻辑 ...
    
    if submit_only:
        prompt_id = queue_prompt(base_url, wf, client_id)
        return json.dumps({"prompt_id": prompt_id, "status": "submitted"})
    
    # ... 原有轮询和下载逻辑（不变）...
```

#### Step 4.3 验证
- [ ] `python generate.py --submit-only ...` 5 秒内返回 prompt_id
- [ ] 不带 `--submit-only` 时原有功能完全不变

---

### Phase 5：Agent 集成（Skill 层）
**目标**：修改 Skill 和 Agent Prompt，让 agent 使用新的异步流程。
**预计耗时**：1 个 AI 会话
**风险等级**：中
**前置依赖**：Phase 1-4 完成

#### Step 5.1：修改 `video-generation` Skill
**文件**：`skills/public/video-generation/SKILL.md`

**修改要点**：
1. 新增"异步生成流程"说明：
   - Step 1：创建 JSON prompt（不变）
   - Step 2：调用 `generate.py --submit-only` 获取 `prompt_id`
   - Step 3：使用 `register_video_task` 工具（新增）将任务注册到后端
   - Step 4：告知用户"视频正在后台生成，预计需要 XX 分钟"
   - Step 5：**不要**调用 `present_files`，前端会自动显示进度

2. 新增工具说明（如果实现为独立工具）：
   ```
   register_video_task(
       prompt_id="...",
       output_file="/mnt/user-data/outputs/xxx.mp4",
       aspect_ratio="16:9",
       duration=10.0
   )
   ```

#### Step 5.2：（可选）新增 `register_video_task` 工具
**文件**：`backend/packages/harness/deerflow/tools/builtins/` 或作为 `bash_tool` 的扩展

**方案 A（推荐）**：不新增独立工具，而是通过 `bash_tool` 执行 `generate.py --submit-only` 后，agent 的回复中自然包含 `prompt_id`。后端通过解析 bash 输出来自动注册任务。

**方案 B**：新增 `register_video_task` 工具，agent 显式调用。

**推荐方案 A**，对 agent 的侵入性更小。

#### Step 5.3 验证
- [ ] 在 Plan Mode 下测试 agent 是否能正确执行新流程
- [ ] 验证 agent 不再长时间阻塞

---

### Phase 6：前端进度展示
**目标**：前端实时显示视频生成进度，任务完成后自动出现下载按钮。
**预计耗时**：2 个 AI 会话
**风险等级**：中
**前置依赖**：Phase 1-5 完成

#### Step 6.1：新增视频任务 API 客户端
**文件**：`frontend/src/core/tasks/api.ts`

```typescript
export async function listVideoTasks(threadId: string): Promise<VideoTask[]> { ... }
export async function getVideoTask(threadId: string, taskId: string): Promise<VideoTask> { ... }
export async function cancelVideoTask(threadId: string, taskId: string): Promise<void> { ... }
```

#### Step 6.2：新增 `useVideoTasks` Hook
**文件**：`frontend/src/core/tasks/hooks.ts`

**设计**：
- 每 3 秒轮询一次 `listVideoTasks`
- 当任务状态变为 `COMPLETED` 时，自动将 output_file 加入 artifacts 列表
- 当任务状态为 `GENERATING` 时，显示进度条

```typescript
export function useVideoTasks(threadId: string) {
    const [tasks, setTasks] = useState<VideoTask[]>([]);
    
    useEffect(() => {
        const interval = setInterval(() => {
            listVideoTasks(threadId).then(setTasks);
        }, 3000);
        return () => clearInterval(interval);
    }, [threadId]);
    
    // 当任务完成时，自动同步到 artifacts
    useEffect(() => {
        const completed = tasks.filter(t => t.status === 'COMPLETED');
        completed.forEach(task => {
            addArtifact(task.output_file);  // 伪代码
        });
    }, [tasks]);
    
    return { tasks, isLoading };
}
```

#### Step 6.3：新增 `VideoTaskProgress` 组件
**文件**：`frontend/src/components/workspace/artifacts/video-task-progress.tsx`

**UI 设计**：
- 卡片式布局，显示文件名、状态、进度条
- `GENERATING`：蓝色进度条 + 百分比
- `QUEUED`：灰色 + 排队位置
- `FAILED`：红色 + 错误信息 + 重试按钮
- `COMPLETED`：自动消失，转为普通 artifact 下载卡片

#### Step 6.4：集成到聊天界面
**文件**：`frontend/src/components/workspace/chats/chat-box.tsx`

在消息列表下方（或 Artifacts 面板内）显示正在进行的视频任务列表。

#### Step 6.5 验证
- [ ] 提交视频任务后，前端 3 秒内出现进度卡片
- [ ] 进度条随 ComfyUI 进度实时更新
- [ ] 任务完成后，自动出现 MP4 下载按钮
- [ ] 浏览器刷新后，仍能恢复显示进行中的任务

---

### Phase 7：端到端测试 & 调优
**目标**：全链路验证，修复边界问题。
**预计耗时**：1 个 AI 会话
**风险等级**：中
**前置依赖**：Phase 1-6 完成

#### Step 7.1：测试用例清单
| 场景 | 预期结果 |
|------|---------|
| 提交 10 秒视频任务 | 5 秒内返回，前端显示"排队中" |
| ComfyUI 生成中 | 前端显示"生成中 X%"，Agent 不被阻塞 |
| 生成完成 | 自动出现下载卡片，文件可正常下载 |
| ComfyUI 服务不可用 | 任务状态变为 FAILED，前端显示错误信息 |
| 同时提交 3 个视频 | 后端自动排队，依次执行 |
| 浏览器刷新 | 任务继续执行，恢复进度显示 |
| 原有 2 秒视频（不带 --submit-only）| 功能完全不变 |

#### Step 7.2：性能调优
- [ ] Worker 轮询间隔从 2 秒调整为 5 秒（减少 ComfyUI API 压力）
- [ ] SQLite 连接池配置（如果使用 ORM）
- [ ] 前端轮询间隔根据状态动态调整（COMPLETED/FAILED 后停止轮询）

#### Step 7.3：文档更新
- [ ] 更新 `SKILL.md` 中的使用说明
- [ ] 更新 `docs/ARCHITECTURE.md` 中的视频生成架构图
- [ ] 在 `config.example.yaml` 中新增视频生成配置示例

---

## 4. 修改清单（执行时逐条勾选）

### 4.1 新增文件清单

| # | 文件路径 | 所属 Phase | 是否必须 |
|---|---------|-----------|---------|
| 1 | `backend/packages/harness/deerflow/tasks/__init__.py` | Phase 1 | ✅ |
| 2 | `backend/packages/harness/deerflow/tasks/video_generation.py` | Phase 1 | ✅ |
| 3 | `backend/packages/harness/deerflow/tasks/video_generation_store.py` | Phase 1 | ✅ |
| 4 | `backend/packages/harness/deerflow/tasks/comfyui_async_client.py` | Phase 1 | ✅ |
| 5 | `backend/packages/harness/deerflow/tasks/video_generation_worker.py` | Phase 2 | ✅ |
| 6 | `backend/app/gateway/routers/video_generation.py` | Phase 3 | ✅ |
| 7 | `frontend/src/core/tasks/api.ts` | Phase 6 | ✅ |
| 8 | `frontend/src/core/tasks/hooks.ts` | Phase 6 | ✅ |
| 9 | `frontend/src/core/tasks/types.ts` | Phase 6 | ✅ |
| 10 | `frontend/src/components/workspace/artifacts/video-task-progress.tsx` | Phase 6 | ✅ |

### 4.2 修改文件清单

| # | 文件路径 | 修改内容 | 所属 Phase | 回退方式 |
|---|---------|---------|-----------|---------|
| 1 | `skills/public/video-generation/scripts/generate.py` | 添加 `--submit-only` 参数 | Phase 4 | git diff |
| 2 | `skills/public/video-generation/SKILL.md` | 更新使用流程说明 | Phase 5 | git diff |
| 3 | `backend/app/gateway/app.py` | 注册 VideoGenerationRouter | Phase 3 | git diff |
| 4 | `backend/app/gateway/routers/__init__.py` | 导出 VideoGenerationRouter | Phase 3 | git diff |
| 5 | `frontend/src/components/workspace/chats/chat-box.tsx` | 集成 VideoTaskProgress | Phase 6 | git diff |
| 6 | `frontend/src/components/workspace/artifacts/artifact-file-list.tsx` | 支持"生成中"状态 | Phase 6 | git diff |
| 7 | `config.example.yaml` | 新增视频生成配置示例 | Phase 7 | git diff |

### 4.3 删除文件清单

无。

---

## 5. 回退策略（Rollback Plan）

### 5.1 分支策略

```bash
# 开始实施前
 git checkout -b feature/video-generation-async
```

所有 Phase 的修改均在此分支上进行。完成并测试通过后，再合并到 `main`。

### 5.2 文件级备份

每个 Phase 开始前，执行以下备份脚本（已提供在 `scripts/backup-phase.sh` 中）：

```bash
#!/bin/bash
PHASE=$1
BACKUP_DIR=".backups/video-generation-async/${PHASE}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${BACKUP_DIR}"

cp skills/public/video-generation/scripts/generate.py "${BACKUP_DIR}/"
cp skills/public/video-generation/SKILL.md "${BACKUP_DIR}/"
cp backend/app/gateway/app.py "${BACKUP_DIR}/"
# ... 其他即将修改的文件

echo "Backup completed at ${BACKUP_DIR}"
```

### 5.3 数据库回退

`video_generation_tasks` 表创建在已有的 `deerflow.db` 中：

- 回退时删除表即可：
  ```sql
  DROP TABLE IF EXISTS video_generation_tasks;
  ```
- 或在 Python 中执行：
  ```python
  from deerflow.tasks.video_generation import Base
  from deerflow.persistence.engine import _engine
  
  async def rollback():
      async with _engine.begin() as conn:
          await conn.run_sync(Base.metadata.drop_all)
  ```
- 删除表不影响 `deerflow.db` 中的其他表（checkpoints、users、threads 等）

### 5.4 功能开关（Feature Flag）

在 `config.yaml` 中增加功能开关：

```yaml
video_generation:
  async_mode: true   # 设为 false 可立即回退到同步模式
  worker_poll_interval: 5
  worker_max_concurrent: 1
```

**应急回退**：将 `async_mode: false`，Gateway 重启后立即恢复原有同步行为，无需回滚代码。

### 5.5 完整回退步骤

如果必须完全回退代码：

```bash
# 方式 1：Git 回退（推荐）
git checkout main
git branch -D feature/video-generation-async

# 方式 2：手动恢复（如果未用 git）
cp .backups/video-generation-async/phase7_*/generate.py skills/public/video-generation/scripts/
cp .backups/video-generation-async/phase7_*/SKILL.md skills/public/video-generation/
rm -rf backend/packages/harness/deerflow/tasks/
rm backend/app/gateway/routers/video_generation.py
rm -rf frontend/src/core/tasks/
rm frontend/src/components/workspace/artifacts/video-task-progress.tsx
# 数据库表通过 Base.metadata.drop_all() 清理，无需删除文件
```

---

## 6. 风险与应对

| 风险 | 可能性 | 影响 | 应对措施 |
|------|--------|------|---------|
| ComfyUI 重启导致 prompt_id 丢失 | 中 | 高 | Worker 轮询时捕获异常，标记为 FAILED，前端提示用户重试 |
| Worker 线程崩溃导致任务卡住 | 低 | 高 | Gateway 启动时自动恢复 PENDING/QUEUED 状态的任务 |
| SQLite 并发写入冲突 | 低 | 中 | 使用 `threading.Lock()` 保护数据库操作 |
| 前端轮询频率过高导致 API 压力 | 中 | 低 | 动态调整轮询间隔，COMPLETED/FAILED 后停止轮询 |
| Agent 不理解新 Skill 流程 | 中 | 中 | 在 SKILL.md 中用清晰的步骤说明，必要时增加示例 |
| 磁盘空间不足（视频文件大） | 低 | 中 | Worker 下载前检查磁盘空间，不足时标记 FAILED |

---

## 7. 修改记录模板

每次执行一个 Step 后，在 `docs/video-generation-async-refactor/CHANGELOG.md` 中记录：

```markdown
## [Phase X - Step Y.Z] YYYY-MM-DD HH:MM

### 修改内容
- 修改了 `文件路径`：具体修改描述
- 新增了 `文件路径`：功能说明

### 验证结果
- [ ] 单元测试通过
- [ ] 手动测试通过
- [ ] 未引入回归问题

### 回退方式
- Git commit hash: `abc1234`
- 备份路径: `.backups/video-generation-async/phaseX_stepY_20260510_121500/`

### 备注
- 遇到的问题 / 需要注意的点
```

---

## 8. 附录

### 8.1 相关代码引用

- `AioSandbox.execute_command`: `backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox.py:57`
- `bash_tool`: `backend/packages/harness/deerflow/sandbox/tools.py:1224`
- `SubagentExecutor.execute_async`: `backend/packages/harness/deerflow/subagents/executor.py:659`
- `present_files` tool: `backend/packages/harness/deerflow/tools/builtins/present_file_tool.py:84`
- `generate.py`: `skills/public/video-generation/scripts/generate.py`
- `artifacts.py` router: `backend/app/gateway/routers/artifacts.py`

### 8.2 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `COMFYUI_BASE_URL` | `http://host.docker.internal:8188` | ComfyUI API 地址 |
| `VIDEO_WORKER_POLL_INTERVAL` | `5` | Worker 轮询 ComfyUI 间隔（秒） |
| `VIDEO_WORKER_POLL_INTERVAL` | `5` | Worker 轮询间隔（秒） |
| `VIDEO_WORKER_MAX_CONCURRENT` | `1` | 最大并发生成数 |

---

**计划制定日期**：2026-05-10  
**计划版本**：v1.0  
**负责人**：AI Agent（分会话执行）  
**目标完成日期**：待定（按 Phase 逐个完成）
