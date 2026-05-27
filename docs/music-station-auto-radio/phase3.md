# Phase 3：智能决策层（Agent Routing）

> 状态: ⏳ 待实施
> 目标: Agent 意图理解 + L1/L2/L3 路由 + 24小时模式智能调度

## 任务清单

- [ ] `backend/app/services/intent_parser.py` - 新增意图理解模块
- [ ] `backend/app/services/routing_engine.py` - 新增路由决策模块
- [ ] `backend/app/services/recommender.py` - 重构为 L1/L2/L3 三层调用
- [ ] `backend/app/services/agent_core.py` - 24小时模式智能调度
- [ ] `backend/app/services/agent_core.py` - 集成意图解析到 chat/segment 流程
- [ ] 前端适配（如有需要）
- [ ] 端到端测试

## 三层路由逻辑

```
用户请求到达
    │
    ├── 明确歌名/艺人？
    │     └── → L1 精确匹配（用户收藏/历史）
    │
    ├── 模糊描述（"深夜emo钢琴"）？
    │     ├── Step 1: 解析为结构化查询
    │     │            {mood: melancholic, instrument: piano, tempo: slow}
    │     ├── Step 2: 先查 L2 本地库存
    │     │            ├── 匹配 ≥3 首 → 返回 + 可选补充 L3
    │     │            └── 匹配 <3 首 → 触发 L3 实时搜索
    │     └── Step 3: L3 结果自动写入 L2（缓存）
    │
    └── 24小时模式自动播放？
          ├── 开场 → L1/L2（建立舒适感）
          ├── 中段 → L2（稳定供应）
          └── 穿插 → L3（新鲜感，每 N 首触发一次）
```

## 验收标准

- [ ] Agent 能解析"深夜 emo 钢琴"为结构化查询条件
- [ ] 本地库存 ≥3 首匹配时，不触发实时搜索（响应 < 200ms）
- [ ] 本地库存 <3 首时，自动触发实时搜索补充
- [ ] 24小时模式下，每 N 首自动插入"新鲜感发现"（L3）

## 实施记录

<!-- 实施过程中在这里记录关键决策、遇到的问题、解决方案 -->

