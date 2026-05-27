# Phase 4：多源聚合

> 状态: ❌ 已取消
> 原因: Pixabay 官方 API 仅支持图片/视频搜索，不支持音乐/音频搜索。多源聚合方案改为未来评估 Musopen / Free Music Archive 等替代方案。
> 原计划目标: Pixabay API 接入 + 结果去重融合

## 任务清单

- [ ] `backend/app/services/music_search.py` - 新增统一音乐搜索服务
- [ ] `backend/app/services/music_search.py` - Pixabay API 接入
- [ ] `backend/app/services/music_search.py` - Jamendo + Pixabay 结果融合去重
- [ ] 容灾测试（单一数据源失效时自动 fallback）
- [ ] 前端适配（如有需要）

## 去重逻辑

- 按 `title + artist` 去重
- 按 `audio_url` 去重
- 优先保留 URL 可用的结果
- 优先保留高音质结果

## 验收标准

- [ ] Pixabay API 能返回带 `audio_url` 的歌曲
- [ ] Jamendo + Pixabay 并行搜索，结果去重后返回
- [ ] 单一数据源失效时，自动 fallback 到另一数据源

## 实施记录

<!-- 实施过程中在这里记录关键决策、遇到的问题、解决方案 -->

