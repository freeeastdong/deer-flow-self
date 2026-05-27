# Phase 1：实时搜索层（Search-on-Demand）

> 状态: 🚧 待实施
> 目标: Agent 能调用外部 API 搜索歌曲，结果自动缓存入库

## 任务清单

- [ ] `backend/app/services/agent_core.py` - 新增 `_tool_search_songs_online()` 方法
- [ ] `backend/app/services/agent_core.py` - TOOLS_SCHEMA 注册新工具
- [ ] `backend/app/api/agent.py` - 新增 `/agent/radio/search` 路由
- [ ] `backend/app/models/song.py` - 入库缓存逻辑（判重 + INSERT/UPDATE）
- [ ] `frontend/src/api/agent.ts` - 新增 `searchSongsOnline()` API 调用
- [ ] `frontend/src/components/VoiceAssistant.tsx` - 24小时模式集成实时搜索
- [ ] 端到端测试

## 设计文档

### Jamendo 搜索参数映射

| Agent 标签 | Jamendo API 参数 |
|-----------|-----------------|
| mood=relaxing | tags=relaxing,ambient |
| genre=lofi | tags=lofi |
| instrument=piano | tags=piano |
| tempo=slow | speed=slow |
| 自然语言描述 | search=描述文本 |

### 入库缓存逻辑

1. 搜索返回的歌曲，先检查 `songs` 表是否已存在（按 `source_id` + `source` 判重）
2. 不存在则 INSERT，存在则 UPDATE `audio_url`（防止外链失效）
3. 返回前 N 首给 Agent

## 验收标准

- [ ] Jamendo API 实时搜索能返回带 `audio_url` 的歌曲列表
- [ ] 搜索结果自动写入 `songs` 表，重复搜索不重复入库
- [ ] 前端 24小时模式下，当本地库存不足时自动触发实时搜索
- [ ] 从搜索到播放的端到端延迟 < 5 秒

## 实施记录

<!-- 实施过程中在这里记录关键决策、遇到的问题、解决方案 -->

