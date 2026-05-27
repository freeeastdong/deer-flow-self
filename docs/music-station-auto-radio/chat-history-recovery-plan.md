# 音乐电台聊天记录恢复方案

## 背景

当前 `useAgentStore` 使用 `zustand/persist` 将 `messages`、`sessionId`、`currentRecommendations` 持久化到 localStorage。由于 music-station 以 iframe 形式嵌入 DeerFlow，与 DeerFlow 共享 localStorage，导致：

1. **新用户登录后，打开音乐电台会看到上一个用户的聊天记录**（严重隐私问题）
2. **同一用户刷新页面后，聊天记录丢失**（体验问题）

之前的"完全移除持久化"修复虽然解决了问题1，但连带导致了问题2恶化。

## 目标

1. **不同用户登录** → 打开音乐电台时看到干净界面，绝对看不到其他用户的聊天记录
2. **同一用户刷新/重进** → 自动恢复自己最近的聊天记录和推荐列表
3. **不依赖 localStorage 共享** → 聊天记录的隔离和恢复由后端 API 驱动

## 架构设计

```
┌─────────────────┐     1. GET /chat/sessions          ┌─────────────────┐
│  VoiceAssistant  │ ─────────────────────────────────→ │  后端 API       │
│  组件挂载时      │                                    │  (按 user_id)   │
│                 │     2. GET /chat/history           │                 │
│                 │ ←───────────────────────────────── │  Conversation表 │
└─────────────────┘                                    └─────────────────┘
```

**核心原则**：
- localStorage 不再保存 `messages`、`sessionId`、`currentRecommendations`
- 聊天记录的持久化由后端数据库负责（天然按 `user_id` 隔离）
- 前端仅在组件挂载时从后端拉取历史，恢复到内存中的 store

## Phase 1: 后端 API 增强

### 1.1 新增 `GET /agent/chat/sessions`

返回当前用户最近活跃的会话列表，用于前端找到"最近一次聊天"的 `session_id`。

```python
GET /agent/chat/sessions?limit=5

Response:
{
  "sessions": [
    {
      "session_id": "abc123",
      "last_message_at": "2026-05-06T10:00:00Z",
      "message_count": 12,
      "last_message_preview": "好的，马上为你播放..."
    }
  ]
}
```

### 1.2 扩展 `GET /agent/chat/history`

已支持按 `session_id` 查询，无需修改。但需确认返回字段是否包含 `created_at`（前端需要按时间排序展示）。

### 涉及文件

- `music-station/backend/app/api/agent.py` — 新增路由
- `music-station/backend/app/models/conversation.py` — 确认模型字段

## Phase 2: 前端状态管理重构

### 2.1 修改 `useAgentStore`

- 移除 `messages`、`sessionId`、`currentRecommendations` 的持久化（已做，保持不变）
- 移除 `hasAutoGreeted` 的持久化（每次打开页面都应该可以重新问候，或由后端历史判断）
- 新增 `loadHistory` action：将后端拉取的消息写入 store
- 新增 `initFromBackend` action：封装"找最近 session → 拉历史 → 写入 store"的完整流程

### 涉及文件

- `music-station/frontend/src/stores/useAgentStore.ts`

## Phase 3: 前端组件集成

### 3.1 `VoiceAssistant.tsx` 挂载时加载历史

在组件 `useEffect`（挂载时）中：

1. 调用 `GET /agent/chat/sessions` 获取最近 session
2. 如果有 session：
   - 调用 `GET /agent/chat/history?session_id=xxx&limit=50` 拉取完整历史
   - 将历史消息写入 store（`messages`）
   - 设置 `sessionId`
   - **推荐列表恢复**：如果最后一条 assistant 消息触发了工具调用（如 `search_songs_by_description`），需要恢复 `currentRecommendations`。但这需要后端在历史记录中保存 recommendations（见 Phase 3.2）
3. 如果没有 session：
   - 保持干净界面
   - 可选：自动调用 `getRadioGreeting()` 生成开场白（根据产品决策）

### 3.2 推荐列表持久化（可选，视体验要求）

当前 `Conversation` 表只保存了文本内容，没有保存 recommendations。这导致恢复历史后，上方的推荐歌曲卡片会消失。

**方案 A（简单）**：接受刷新后推荐卡片消失，用户可以通过文本上下文理解之前的推荐。

**方案 B（完整）**：在 `Conversation` 表中增加 `recommendations` JSON 字段，保存每次 assistant 回复时的推荐列表。需要数据库 migration。

本计划先实施方案 A，如果体验不佳再追加方案 B。

### 涉及文件

- `music-station/frontend/src/components/VoiceAssistant.tsx`
- `music-station/frontend/src/api/agent.ts` — 新增 `getChatSessions` API

## Phase 4: 边界情况与体验优化

### 4.1 开场白判断逻辑

当前 `hasAutoGreeted` 被持久化，但已被移除。需要根据后端历史判断是否需要问候：

- 如果加载到了历史记录（有 messages）→ **不自动问候**（用户正在继续之前的对话）
- 如果没有历史记录 → **可以自动问候**（新用户或全新会话）

### 4.2 加载状态

历史记录加载是异步的，需要避免与用户的首次输入冲突：

- 加载历史期间，输入框应显示"恢复对话中..."或禁用状态
- 加载完成后，才允许用户输入

### 4.3 降级处理

- 后端 API 失败时（如 401、500）→ 静默失败，显示干净界面，不阻塞用户
- 网络超时 → 同上

### 4.4 "开始新对话"功能

如果用户想主动清空当前对话重新开始：

- `clearMessages()` 行为保持不变：清空前端 store 的 `messages`、`sessionId`、`currentRecommendations`
- 生成新的 `sessionId`（调用 `POST /chat/new-session` 或前端生成 UUID）
- **不删除后端历史**（后端历史是永久记录，前端只是切换到一个新 session）

## Phase 5: 构建、部署与验证

### 5.1 构建前端

```bash
cd music-station/frontend
npm run build
```

### 5.2 复制产物到 DeerFlow

```bash
cp -r music-station/frontend/dist/* deer-flow-0502/frontend/public/applications/music-station/
```

### 5.3 重启后端服务

```bash
docker restart music_station_backend
```

### 5.4 验证清单

| # | 场景 | 期望结果 |
|---|------|----------|
| 1 | 新用户 A 打开音乐电台 | 干净界面，无历史消息 |
| 2 | 用户 A 与 Agent 聊天后刷新页面 | 自动恢复刚才的聊天记录 |
| 3 | 用户 A 切到 DeerFlow 其他页面再回来 | 自动恢复聊天记录 |
| 4 | 退出用户 A，新用户 B 登录打开音乐电台 | 干净界面，看不到用户 A 的任何记录 |
| 5 | 用户 B 聊天后，用户 A 重新登录 | 恢复用户 A 自己的历史记录，看不到 B 的 |
| 6 | 网络异常时打开音乐电台 | 显示干净界面，不报错，可正常开始新对话 |

## 相关文件汇总

| Phase | 文件路径 | 操作 |
|-------|----------|------|
| 1 | `music-station/backend/app/api/agent.py` | 新增 `GET /chat/sessions` |
| 1 | `music-station/backend/app/models/conversation.py` | 确认/扩展字段 |
| 2 | `music-station/frontend/src/stores/useAgentStore.ts` | 重构持久化逻辑，新增 actions |
| 3 | `music-station/frontend/src/api/agent.ts` | 新增 `getChatSessions` API |
| 3 | `music-station/frontend/src/components/VoiceAssistant.tsx` | 挂载时加载历史 |
| 5 | `deer-flow-0502/frontend/public/applications/music-station/` | 部署构建产物 |

---

*计划制定时间: 2026-05-06*
