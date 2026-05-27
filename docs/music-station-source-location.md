# Music Station 源码位置记录

> 此文件用于记录 Music Station（音乐电台）独立项目的源码位置，防止后续开发时找不到源代码。

## 源码路径

**绝对路径**: `F:\字节跳动开源项目\music-station`

## 项目结构

```
music-station/
├── backend/                    # 后端服务 (FastAPI)
│   ├── app/
│   │   ├── api/                # API 路由
│   │   │   ├── agent.py        # Agent 聊天接口
│   │   │   ├── songs.py        # 歌曲管理接口
│   │   │   ├── voice.py        # 语音/TTS 接口
│   │   │   ├── recommend.py    # 推荐接口
│   │   │   ├── users.py        # 用户接口
│   │   │   └── feedback.py     # 反馈接口
│   │   ├── services/           # 核心服务逻辑
│   │   │   ├── agent_core.py   # LLM 对话 + 工具调度 (关键文件)
│   │   │   ├── semantic_search.py  # 语义搜索 (关键文件)
│   │   │   ├── music_search.py
│   │   │   ├── recommender.py
│   │   │   ├── tts_service.py
│   │   │   └── ...
│   │   ├── core/               # 核心配置
│   │   ├── models/             # 数据模型
│   │   └── schemas/            # Pydantic 模型
│   └── scripts/                # 数据导入脚本
├── frontend/                   # 前端源码 (React + Vite)
│   ├── src/
│   │   └── components/         # 前端组件 (VoiceAssistant.tsx 等)
│   └── dist/                   # 构建产物
└── demo/                       # 演示/素材
```

## 与 DeerFlow 的关系

- Music Station 是一个**独立的项目/仓库**，拥有自己的前后端
- 构建后的前端产物 (`frontend/dist/`) 会被复制到 `deer-flow-0502/frontend/public/applications/music-station/`
- DeerFlow 通过 iframe 嵌入 Music Station 前端页面
- Music Station 后端作为独立容器运行 (`music_station_backend`)

## 部署路径

- **前端部署**: `deer-flow-0502/frontend/public/applications/music-station/`
- **后端容器**: `music_station_backend` (Docker)

## 常用文件速查

| 用途 | 文件路径 |
|------|----------|
| Agent 核心逻辑 | `backend/app/services/agent_core.py` |
| 语义搜索 | `backend/app/services/semantic_search.py` |
| 前端播放组件 | `frontend/src/components/VoiceAssistant.tsx` |
| API 路由 | `backend/app/api/agent.py` |
| TTS 服务 | `backend/app/services/tts_service.py` |

---

*记录时间: 2026-05-06*
