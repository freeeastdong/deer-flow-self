# Music Station 24小时自动电台 — 混合架构升级计划

> **目标**：构建一个真正能"24小时不间断运行"的 AI 自动电台，突破本地库存天花板，实现按需搜索+智能决策+本地缓存的混合架构。
>
> **当前状态**：数据库 8 首歌曲（示例 JSON 导入），Agent 推荐空间极其有限。
> **目标状态**：Agent 能根据用户心情/场景/喜好，实时从外部免版权音乐库搜索匹配歌曲，同时本地缓存热门歌曲保证响应速度。

---

## 一、架构设计

### 1.1 三层混合架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户交互层                            │
│         （24小时模式 / 手动对话 / 语音输入 / 收藏）            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent 决策引擎                          │
│                                                              │
│   Step 1: 意图理解 → 提取 心情、场景、风格、乐器 标签        │
│   Step 2: 策略路由 → 决定调用 L1 / L2 / L3                   │
│   Step 3: 结果融合 → 去重、排序、生成推荐理由                 │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │   L1 热缓存层    │ │   L2 本地库存层  │ │   L3 实时搜索层  │
    │                  │ │                  │ │                  │
    │ 用户收藏         │ │ 预导入免版权库   │ │ Jamendo API      │
    │ 最近播放         │ │ (按流派缓存)     │ │ Pixabay API      │
    │ 高频推荐         │ │                  │ │ 其他免版权源     │
    │                  │ │ 目标: 5000首     │ │                  │
    │ 数量: 几十首     │ │                  │ │ 数量: 无限       │
    │ 响应: <50ms      │ │ 响应: <100ms     │ │ 响应: 1-3s       │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 1.2 Agent 路由决策逻辑

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

### 1.3 数据流

```
[24小时模式启动]
    │
    ▼
[getRadioSegment('auto')]
    │
    ├── L2 本地推荐 ──────────────────────────────┐
    │   │                                          │
    │   ├── recommender.recommend()                │
    │   │       └── SELECT FROM songs              │
    │   └── 返回 3 首 + DJ 讲解                     │
    │                                              │
    ├── L3 实时搜索 ────────────────────────────┐  │
    │   │                                        │  │
    │   ├── search_songs_online()                │  │
    │   │       └── Jamendo API /tracks?tags=... │  │
    │   └── 返回 5 首 + 入库缓存                  │  │
    │                                             │  │
    └── 融合层 ───────────────────────────────────┘  │
        │                                             │
        ├── 去重（URL + title + artist）              │
        ├── 排序（L1优先 > L2 > L3）                  │
        └── 取前 3 首                                 │
                                                      │
        ▼                                             │
    [返回前端]                                         │
        │                                             │
        ├── 有 audio_url → Player 播放                │
        ├── 无 audio_url → 显示"暂无音频"跳过          │
        └── 播放结束 → scheduleNextProgram() ─────────┘
```

---

## 二、Phase 划分总览

| Phase | 主题 | 目标 | 预估工作量 |
|-------|------|------|-----------|
| **Phase 1** | 实时搜索层 | Agent 能调用外部 API 搜索歌曲，结果自动缓存入库 | 中 |
| **Phase 2** | 本地库存扩充 | 按流派批量导入 5000+ 首 Jamendo 歌曲，songs 表增加标签字段 | 中 |
| **Phase 3** | 智能决策层 | Agent 意图理解 + L1/L2/L3 路由 + 24小时模式智能调度 | 大 |
| **Phase 4** | 多源聚合 | Pixabay API 接入 + 结果去重融合 | 小 |

---

## 三、Phase 1：实时搜索层（Search-on-Demand）

### 3.1 目标

让 Agent 拥有"实时搜索外部音乐库"的能力。当本地库存不足时，自动调用 Jamendo API 搜索匹配歌曲，搜索结果自动写入 `songs` 表缓存。

### 3.2 核心任务

#### 3.2.1 后端：新增 `search_songs_online` 工具

**文件**: `backend/app/services/agent_core.py`

**实现**: 新增 `_tool_search_songs_online()` 方法

```python
async def _tool_search_songs_online(
    self,
    query: str = "",
    mood: str = "",
    genre: str = "",
    tags: List[str] = None,
    instrument: str = "",
    tempo: str = "",  # slow/medium/fast
    limit: int = 10
) -> Dict:
    """
    实时搜索外部免版权音乐库。
    优先调用 Jamendo API，支持多维度筛选。
    搜索结果自动写入 songs 表缓存。
    """
```

**Jamendo 搜索参数映射**:

| Agent 标签 | Jamendo API 参数 |
|-----------|-----------------|
| mood=relaxing | tags=relaxing,ambient |
| genre=lofi | tags=lofi |
| instrument=piano | tags=piano |
| tempo=slow | speed=slow |
| 自然语言描述 | search=描述文本 |

**入库缓存逻辑**:
- 搜索返回的歌曲，先检查 `songs` 表是否已存在（按 `source_id` + `source` 判重）
- 不存在则 INSERT，存在则 UPDATE `audio_url`（防止外链失效）
- 返回前 N 首给 Agent

#### 3.2.2 后端：Agent 工具注册

**文件**: `backend/app/services/agent_core.py`

将 `search_songs_online` 注册到 `TOOLS_SCHEMA` 列表中，让 LLM 能调用。

#### 3.2.3 后端：API 路由扩展

**文件**: `backend/app/api/agent.py`

新增独立搜索接口（供前端直接调用，绕过 LLM 延迟）:

```python
@router.post("/radio/search")
async def radio_search_online(
    req: RadioSearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """实时搜索外部音乐库，前端 24小时模式直接调用"""
```

#### 3.2.4 前端：新增实时搜索 API 调用

**文件**: `frontend/src/api/agent.ts`

```typescript
export interface RadioSearchRequest {
  query?: string
  mood?: string
  genre?: string
  tags?: string[]
  instrument?: string
  tempo?: 'slow' | 'medium' | 'fast'
  limit?: number
}

export const searchSongsOnline = async (params: RadioSearchRequest) => {
  const res = await apiClient.post('/agent/radio/search', params)
  return res.data
}
```

#### 3.2.5 前端：24小时模式集成实时搜索

**文件**: `frontend/src/components/VoiceAssistant.tsx`

修改 `playNextProgram()`:
- 当 `getRadioSegment('auto')` 返回的歌曲数量 < 3 时
- 自动调用 `searchSongsOnline()` 补充歌曲
- 合并结果后播放

### 3.3 验收标准

- [ ] Jamendo API 实时搜索能返回带 `audio_url` 的歌曲列表
- [ ] 搜索结果自动写入 `songs` 表，重复搜索不重复入库
- [ ] 前端 24小时模式下，当本地库存不足时自动触发实时搜索
- [ ] 从搜索到播放的端到端延迟 < 5 秒

---

## 四、Phase 2：本地库存扩充 + 标签增强

### 4.1 目标

将本地库存从 8 首扩展到 5000+ 首，让 L2 层能覆盖大多数常见场景，减少 L3 实时搜索的调用频率。

### 4.2 核心任务

#### 4.2.1 数据库：songs 表增加标签字段

**文件**: `backend/app/models/song.py`

```python
class Song(Base):
    ...
    # 新增字段
    mood = Column(String(50), nullable=True, index=True)       # relaxing, upbeat, melancholic...
    scene = Column(String(50), nullable=True, index=True)      # study, sleep, workout, driving...
    instrument = Column(String(50), nullable=True)             # piano, guitar, electronic...
    source = Column(String(20), nullable=False, default="unknown")  # jamendo, pixabay, local
    source_id = Column(String(50), nullable=True, index=True)  # 外部平台原始ID
```

#### 4.2.2 数据库：Alembic 迁移脚本

创建迁移脚本添加新字段。

#### 4.2.3 后端：同步脚本增强

**文件**: `backend/scripts/sync_royalty_free.py`

- 支持按流派批量导入：`--genre ambient,lofi,classical,jazz`
- 支持增量同步：记录上次同步时间，只同步新歌
- Jamendo API 返回的 `musicinfo` 解析为 `mood`/`instrument`/`tempo`

#### 4.2.4 批量导入策略

按流派分批导入（每批 500-1000 首）:

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

总目标：**4000-5000 首**，覆盖 8 大流派。

### 4.3 验收标准

- [ ] `songs` 表字段扩展完成，包含 mood/scene/instrument/source/source_id
- [ ] 本地库存 ≥ 5000 首，覆盖 8 大流派
- [ ] 增量同步机制可用，重复导入不重复入库
- [ ] 查询性能：按流派筛选 < 100ms

---

## 五、Phase 3：智能决策层（Agent Routing）

### 5.1 目标

让 Agent 能真正"理解"用户意图，并智能决定何时用本地库存、何时实时搜索。

### 5.2 核心任务

#### 5.2.1 后端：意图理解模块

**文件**: `backend/app/services/intent_parser.py`（新增）

```python
class IntentParser:
    """将用户自然语言转换为结构化音乐查询条件"""
    
    def parse(self, user_input: str) -> MusicIntent:
        """
        输入: "深夜一个人，有点emo，想听安静的钢琴"
        输出: {
            mood: "melancholic",
            scene: "night",
            instrument: "piano",
            tempo: "slow",
            genre: "classical",
            tags: ["piano", "night", "melancholic"],
            explicit_songs: [],
            explicit_artists: []
        }
        """
```

**实现方式**:
- **有 LLM**: 直接让 LLM 解析（prompt 工程）
- **Mock 模式**: 关键词映射表（正则匹配）

#### 5.2.2 后端：路由决策模块

**文件**: `backend/app/services/routing_engine.py`（新增）

```python
class RoutingEngine:
    """决定使用 L1/L2/L3 哪一层数据"""
    
    def decide(self, intent: MusicIntent, local_count: int) -> DataSource:
        """
        决策逻辑:
        - local_count >= 3 → L2 本地库存
        - local_count < 3 且 意图明确 → L3 实时搜索
        - 24小时模式且播放了 N 首 → L3 补充新鲜感
        - 用户明确要"新"的 → L3
        """
```

#### 5.2.3 后端：推荐服务重构

**文件**: `backend/app/services/recommender.py`

将现有 `recommend()` 重构为三层调用:

```python
async def recommend(self, user_id: int, intent: MusicIntent, limit: int = 3) -> List[Dict]:
    # 1. 查 L1 热缓存
    l1_results = await self._query_l1(user_id, intent, limit)
    if len(l1_results) >= limit:
        return l1_results
    
    # 2. 查 L2 本地库存
    remaining = limit - len(l1_results)
    l2_results = await self._query_l2(intent, remaining)
    combined = self._merge_and_deduplicate(l1_results, l2_results)
    if len(combined) >= limit:
        return combined[:limit]
    
    # 3. 触发 L3 实时搜索
    remaining = limit - len(combined)
    l3_results = await self._query_l3(intent, remaining)
    return self._merge_and_deduplicate(combined, l3_results)[:limit]
```

#### 5.2.4 后端：24小时模式智能调度

**文件**: `backend/app/services/agent_core.py`

增强 `generate_radio_segment('auto')`:

```python
async def generate_radio_segment(self, segment_type='auto', context=''):
    # 解析当前播放状态
    play_count = self._get_recent_play_count()
    
    # 每 5 首触发一次 L3 实时发现
    if play_count % 5 == 0:
        return await self._generate_discovery_segment()  # L3
    
    # 正常推荐（L1/L2）
    return await self._generate_recommend_segment()
```

### 5.3 验收标准

- [ ] Agent 能解析"深夜 emo 钢琴"为结构化查询条件
- [ ] 本地库存 ≥3 首匹配时，不触发实时搜索（响应 < 200ms）
- [ ] 本地库存 <3 首时，自动触发实时搜索补充
- [ ] 24小时模式下，每 N 首自动插入"新鲜感发现"（L3）

---

## 六、Phase 4：多源聚合

### 6.1 目标

引入第二个外部数据源（Pixabay API），与 Jamendo 形成互补，提高搜索覆盖率和 URL 可用性。

### 6.2 核心任务

#### 6.2.1 后端：Pixabay API 接入

**文件**: `backend/app/services/music_search.py`（新增）

```python
class MusicSearchService:
    """统一音乐搜索服务，聚合多个数据源"""
    
    async def search(self, intent: MusicIntent, limit: int = 10) -> List[SongResult]:
        # 并行查询多个源
        tasks = [
            self._search_jamendo(intent, limit),
            self._search_pixabay(intent, limit),
        ]
        results = await asyncio.gather(*tasks)
        
        # 融合去重
        return self._merge_and_deduplicate(results[0], results[1])[:limit]
```

#### 6.2.2 后端：结果去重逻辑

按 `title + artist` 或 `audio_url` 去重，优先保留 URL 可用的结果。

### 6.3 验收标准

- [ ] Pixabay API 能返回带 `audio_url` 的歌曲
- [ ] Jamendo + Pixabay 并行搜索，结果去重后返回
- [ ] 单一数据源失效时，自动 fallback 到另一数据源

---

## 七、实施路线图

```
Week 1-2    [Phase 1] 实时搜索层
            ├── search_songs_online 工具开发
            ├── API 路由扩展
            ├── 前端集成
            └── 验收测试

Week 3-4    [Phase 2] 本地库存扩充
            ├── songs 表字段扩展
            ├── 批量导入脚本增强
            ├── 按流派导入 5000 首
            └── 索引优化

Week 5-6    [Phase 3] 智能决策层
            ├── 意图理解模块
            ├── 路由决策引擎
            ├── 推荐服务重构
            ├── 24小时模式智能调度
            └── 端到端测试

Week 7      [Phase 4] 多源聚合
            ├── Pixabay API 接入
            ├── 结果去重融合
            └── 容灾测试

Week 8      [稳定化 & 文档]
            ├── 性能优化
            ├── 异常处理完善
            ├── 文档更新
            └── 用户验收
```

---

## 八、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Jamendo API 限流/下线 | L3 层失效 | Phase 4 多源聚合，引入 Pixabay fallback |
| 实时搜索延迟高（>3s） | 24小时模式卡顿 | 预加载机制：播当前歌时预搜下一批 |
| audio_url 外链失效 | 播放失败 | 定时任务验证 URL 可用性，失效自动更新 |
| 数据库 5000 首后性能下降 | 查询变慢 | 加复合索引 (genre, mood, tempo)，必要时分表 |
| LLM 解析意图不稳定 | 推荐偏离 | Mock 模式保留关键词映射表兜底 |

---

## 九、关键指标（KPI）

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 本地库存歌曲数 | 8 | ≥ 5000 |
| 24小时模式不重复播放时长 | ~10 分钟 | ≥ 4 小时 |
| 用户意图匹配成功率 | ~30%（随机） | ≥ 70% |
| 平均推荐响应时间 | ~200ms | < 500ms（含 L3） |
| audio_url 可用率 | 100% | ≥ 95% |
| 外部 API 调用成功率 | N/A | ≥ 90% |

---

*计划制定时间: 2026-05-05*
*版本: v1.0*
