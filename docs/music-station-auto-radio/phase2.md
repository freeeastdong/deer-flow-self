# Phase 2：本地库存扩充 + 标签增强

> 状态: ⏳ 待实施
> 目标: 按流派批量导入 5000+ 首 Jamendo 歌曲，songs 表增加标签字段

## 任务清单

- [ ] `backend/app/models/song.py` - songs 表增加 mood/scene/instrument/source/source_id 字段
- [ ] `backend/alembic/versions/` - 创建 Alembic 迁移脚本
- [ ] `backend/scripts/sync_royalty_free.py` - 支持按流派批量导入
- [ ] `backend/scripts/sync_royalty_free.py` - 支持增量同步
- [ ] 批量导入 8 大流派 × 500 首 = 4000 首
- [ ] 数据库索引优化
- [ ] 性能测试

## 批量导入策略

| 批次 | 流派 | 关键词 | 数量 |
|------|------|--------|------|
| 1 | Ambient / New Age | ambient,meditation,nature | 500 |
| 2 | Lo-Fi | lofi,chill,beats | 500 |
| 3 | Classical | classical,piano,violin | 500 |
| 4 | Jazz | jazz,smooth,swing | 500 |
| 5 | Electronic | electronic,synth,chillout | 500 |
| 6 | Acoustic | acoustic,guitar,fingerstyle | 500 |
| 7 | Cinematic | cinematic,epic,orchestral | 500 |
| 8 | Pop / Indie | pop,indie,upbeat | 500 |

## 验收标准

- [ ] `songs` 表字段扩展完成，包含 mood/scene/instrument/source/source_id
- [ ] 本地库存 ≥ 5000 首，覆盖 8 大流派
- [ ] 增量同步机制可用，重复导入不重复入库
- [ ] 查询性能：按流派筛选 < 100ms

## 实施记录

<!-- 实施过程中在这里记录关键决策、遇到的问题、解决方案 -->

