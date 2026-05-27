# 个人音乐 Agent 实施计划

> 基于 DeerFlow 2.0 框架，构建一个能够理解用户音乐品味、实时推荐歌曲、编排歌单的个性化音乐 Agent。
>
> 计划目标：从零开始，在 DeerFlow 中搭建完整的音乐推荐 Skill 体系 + 工具集成 + 记忆初始化。

---

## 一、项目架构概览

```
技能目录: skills/custom/music-agent/
工具模块: backend/packages/harness/deerflow/community/music/
数据目录: docs/music-agent/data/

最终交付物:
├── skills/custom/music-memory-init/     # 听歌记录导入 Skill
├── skills/custom/music-recommender/     # 单曲推荐 Skill
├── skills/custom/playlist-curator/      # 歌单编排 Skill
├── skills/custom/music-discovery/       # 新音乐发现 Skill
├── backend/packages/harness/deerflow/community/music/  # 音乐 API 工具
├── docs/music-agent/data/               # 用户听歌记录 JSON
└── docs/music-agent/SOUL.md             # Agent 性格定义
```

---

## 二、Phase 1：数据准备（Day 1）

### 1.1 听歌记录导出与清洗

**数据来源**：
- 网易云音乐：年度听歌报告、听歌排行（全部时间/最近一周）、自建歌单
- 可选补充：Spotify/Apple Music 数据

**清洗标准**：
```json
{
  "track_id": "歌曲唯一标识",
  "track": "歌名",
  "artist": "艺人",
  "album": "专辑",
  "genre": "流派",
  "play_count": 播放次数,
  "is_liked": true,
  "rank": 排名,
  "source": "netease/spotify/apple",
  "timestamp_range": "2024-01~2024-12",
  "context_tags": ["深夜", "驾车", "工作"]
}
```

**验收标准**：
- [ ] 至少导出 Top 200 首听歌记录
- [ ] 字段完整率 > 90%（允许部分歌曲缺失 genre/album）
- [ ] 保存到 `docs/music-agent/data/listening_history.json`

### 1.2 创建音乐品味摘要（手动冷启动）

编写一份结构化的品味说明书 `docs/music-agent/data/taste_profile.md`：
- 核心偏好（最爱/可接受/排斥的流派）
- 高频场景-音乐映射
- 常听艺人 Top 20
- 特殊偏好（长前奏、排斥 Auto-Tune 等）

---

## 三、Phase 2：Memory 初始化（Day 1-2）

### 2.1 目标
将听歌记录和品味摘要写入 DeerFlow 的长期记忆系统（memory.json facts），让 Agent 在每次对话时都能读取到用户的音乐偏好。

### 2.2 实现方式

**方案 A（推荐）：开发 `music-memory-init` Skill**

创建一个一次性使用的 Skill，指导 Agent 读取听歌记录 JSON 并批量写入 memory facts：

```yaml
---
name: music-memory-init
description: >-
  Initialize the agent's music memory by importing listening history and taste profile.
  Trigger when: "导入我的听歌记录", "初始化音乐记忆", "加载我的音乐品味", "set up my music agent".
---
```

Skill 工作流程：
1. 读取 `docs/music-agent/data/listening_history.json`
2. 读取 `docs/music-agent/data/taste_profile.md`
3. 提取关键 facts（Top 艺人、偏好的流派、场景偏好）
4. 调用 DeerFlow 的 memory API 写入 facts（category=preference，confidence=0.9）
5. 确认写入成功，返回统计信息

**关键发现**：DeerFlow 提供以下方式写入 memory：
- Python API：`deerflow.agents.memory.updater.create_memory_fact()`
- REST API：`POST /api/memory/facts`
- 自动 summarization（对话中提取，confidence 较低）

本 Skill 将使用 **Python 脚本**直接调用 updater API，确保 facts 写入成功且 confidence 高。

### 2.3 脚本设计

```python
# skills/custom/music-memory-init/scripts/init_memory.py
# 功能：
# 1. 解析 listening_history.json
# 2. 生成结构化 facts
# 3. 调用 DeerFlow memory API 批量写入
# 4. 去重（避免重复写入相同 fact）
```

**验收标准**：
- [ ] `music-memory-init` Skill 创建成功
- [ ] 运行后能成功写入 ≥30 条 music-related facts
- [ ] Facts 包含：Top 艺人、偏好流派、场景偏好、排斥类型
- [ ] 通过 `GET /api/memory` 可查询到写入的数据

---

## 四、Phase 3：核心推荐 Skill — music-recommender（Day 2-3）

### 3.1 功能目标
根据用户当前场景/心情 + 历史记忆，推荐 3-5 首歌曲，并附带推荐理由。

### 3.2 Skill 设计

```yaml
---
name: music-recommender
description: >-
  Recommend songs based on user's listening history, current mood/scene, and long-term taste.
  Trigger when: "推荐一首歌", "我想听歌", "现在适合听什么", "给我推荐音乐",
  "类似 XX 的歌", "适合工作听的歌", "晚上听什么", "推荐几首歌".
  Always use this skill when the user asks for music recommendations.
---
```

### 3.3 工作流程

```
用户输入(场景/心情) 
  → Skill 被触发
  → Step 1: 读取 memory（调用 memory API 获取用户音乐偏好 facts）
  → Step 2: 分析意图（当前场景、能量级别、偏好过滤）
  → Step 3: 调用音乐搜索工具获取候选歌曲
  → Step 4: LLM 排序并生成推荐理由
  → Step 5: 输出推荐列表（含播放链接）
```

### 3.4 脚本设计

```python
# skills/custom/music-recommender/scripts/recommend.py
# 输入：用户 query + memory facts（JSON）
# 输出：推荐列表（JSON）
#
# 逻辑：
# 1. 解析场景关键词（工作/运动/深夜/...）
# 2. 从 memory facts 提取用户偏好
# 3. 调用音乐 API（详见 Phase 5）搜索候选
# 4. 用 LLM 评分排序
# 5. 生成推荐理由
```

**验收标准**：
- [ ] `music-recommender` Skill 创建成功
- [ ] 能根据"给我推荐一首适合深夜听的歌"返回有效推荐
- [ ] 推荐理由与用户的记忆偏好相关联
- [ ] 推荐结果包含歌曲名、艺人、专辑、流派标签

---

## 五、Phase 4：歌单编排 Skill — playlist-curator（Day 3-4）

### 5.1 功能目标
编排一整段听歌体验，支持时长、能量曲线、场景连贯性。

### 5.2 Skill 设计

```yaml
---
name: playlist-curator
description: >-
  Create curated playlists with energy flow and scene coherence.
  Trigger when: "帮我做个歌单", "编一个 XX 分钟的歌单", "给我准备一个听歌列表",
  "安排一段听歌体验", "playlist", "歌单".
---
```

### 5.3 工作流程

1. 解析用户意图（总时长、场景、情绪基调）
2. 读取 memory 获取偏好
3. 分段规划（热身→发展→高潮→收尾）
4. 每段调用音乐搜索工具获取候选
5. 检查 BPM/能量曲线连贯性
6. 输出完整歌单 + 每段设计说明

### 5.4 脚本设计

```python
# skills/custom/playlist-curator/scripts/curate.py
# 输入：场景描述、目标时长、用户偏好
# 输出：分段歌单（JSON）
#
# 逻辑：
# 1. 将时长拆分为 3-4 段
# 2. 每段设定能量目标（energy_level: low/mid/high）
# 3. 调用音乐搜索获取候选
# 4. 按能量目标排序
# 5. 输出结构化歌单
```

**验收标准**：
- [ ] 能生成 30/60/90 分钟歌单
- [ ] 歌单有明确的能量曲线设计
- [ ] 每首歌附带推荐理由
- [ ] 支持"先热身后高潮再收尾"的经典结构

---

## 六、Phase 5：音乐 API 工具集成（Day 2-3，与 Phase 3 并行）

### 6.1 目标
接入外部音乐数据源，使 Agent 能真正搜索歌曲、获取相似推荐、查询艺人信息。

### 6.2 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Spotify API** | 音频特征丰富（danceability/energy/valence），生态完善 | 需要翻墙，国内曲库不全 | ★★★★☆ |
| **网易云 API** | 国内曲库最全 | 非官方，有风控风险 | ★★★☆☆ |
| **Last.fm API** | 免费，相似艺人/歌曲数据丰富 | 不能直接播放，信息偏社交 | ★★★★☆ |
| **多源聚合** | 最大化覆盖 | 实现复杂 | ★★★★★ |

### 6.3 推荐实现：Last.fm + Spotify（或纯 Last.fm）

**理由**：
- Last.fm 免费、稳定，适合相似推荐和艺人信息
- Spotify 适合音频特征分析（如果网络允许）
- 初期可只用 Last.fm 验证核心流程，后续再接入 Spotify

### 6.4 工具实现

创建 `backend/packages/harness/deerflow/community/music/tools.py`：

```python
from langchain.tools import tool

@tool("music_search", parse_docstring=True)
def music_search_tool(query: str, limit: int = 5) -> str:
    """Search for songs/artists/albums using Last.fm API.
    Args:
        query: Search keywords (song name, artist, or genre).
        limit: Maximum results to return.
    """
    ...

@tool("music_similar_tracks", parse_docstring=True)
def music_similar_tracks_tool(artist: str, track: str, limit: int = 5) -> str:
    """Get similar tracks based on a given song.
    Args:
        artist: Artist name.
        track: Track name.
        limit: Maximum similar tracks to return.
    """
    ...

@tool("music_artist_info", parse_docstring=True)
def music_artist_info_tool(artist: str) -> str:
    """Get artist information including top tracks, tags, and similar artists.
    Args:
        artist: Artist name.
    """
    ...
```

### 6.5 注册到 config.yaml

```yaml
tools:
  - name: music_search
    group: music
    use: deerflow.community.music.tools:music_search_tool
    api_key: $LASTFM_API_KEY

  - name: music_similar_tracks
    group: music
    use: deerflow.community.music.tools:music_similar_tracks_tool
    api_key: $LASTFM_API_KEY

  - name: music_artist_info
    group: music
    use: deerflow.community.music.tools:music_artist_info_tool
    api_key: $LASTFM_API_KEY
```

**验收标准**：
- [ ] 3 个音乐工具在 DeerFlow 中注册成功
- [ ] `music_search` 能返回有效歌曲列表
- [ ] `music_similar_tracks` 能根据输入歌曲返回相似推荐
- [ ] `music_artist_info` 能返回艺人信息和 Top 曲目

---

## 七、Phase 6：新音乐发现 Skill — music-discovery（Day 4）

### 7.1 功能目标
帮助用户发现新音乐，但不偏离口味太远。

### 7.2 Skill 设计

```yaml
---
name: music-discovery
description: >-
  Help the user discover new music aligned with their taste but not too familiar.
  Trigger when: "给我找点新歌", "发现新音乐", "有什么新歌", "推荐我没听过的",
  "类似 XX 的新艺人", "最近有什么新专辑".
---
```

### 7.3 工作流程

1. 读取 memory 获取用户喜欢的艺人
2. 调用 `music_similar_tracks` 或 `music_artist_info` 找相似艺人
3. 过滤掉用户已知的艺人（通过 listening_history 排除）
4. 输出"新发现"列表 + 为什么推荐

**验收标准**：
- [ ] 能推荐用户没听过但风格接近的艺人/歌曲
- [ ] 推荐结果排除 listening_history 中已有的记录

---

## 八、Phase 7：Agent 性格定义 — SOUL.md（Day 1）

### 8.1 目标
定义音乐 Agent 的沟通风格、自主程度和边界。

### 8.2 文件位置
`docs/music-agent/SOUL.md`

### 8.3 内容框架

```markdown
# 音乐 Agent SOUL

## 角色定位
你是一个懂用户口味的音乐策展人，不是算法机器人。
每次推荐都附带一句话解释（"这首的吉他和弦和你常听的 Radiohead 很像"）。

## 沟通风格
- 温暖、有品味，不过度热情
- 推荐时给出具体理由，引用用户的历史偏好
- 能接受用户说"不喜欢"，并记录反馈

## 自主程度
- 用户主动询问时才推荐
- 不会未经允许主动打断用户
- 可以在用户创建歌单后追问"这个歌单感觉如何？"

## 边界
- 绝不推荐用户明确排斥的流派
- 同一艺人连续推荐不超过 2 首
- 每次推荐 3-5 首，不一次性给太多
```

**验收标准**：
- [ ] SOUL.md 完成并通过 Bootstrap 流程导入
- [ ] Agent 的推荐语符合定义的风格

---

## 九、Phase 8：反馈闭环与迭代（Day 4-5）

### 9.1 目标
让推荐越来越准。

### 9.2 实现

每次推荐后，Agent 主动询问：
- "这首你喜欢吗？"
- "这个歌单符合你的预期吗？"

用户反馈通过以下方式记录：
1. **自动记忆**：对话中的反馈会被 MemoryMiddleware 自动提取为 facts
2. **手动 API**：Skill 中显式调用 `create_memory_fact` 记录强反馈

### 9.3 评估指标

| 指标 | 目标 |
|------|------|
| 推荐接受率 | ≥ 60% |
| 反馈后推荐改进率 | 用户明确表示"这次更好了" |
| 记忆准确度 | 推荐理由与 facts 一致 |

---

## 十、实施时序与依赖关系

```
Day 1 ──┬── 数据准备（Phase 1）
        └── SOUL.md 编写（Phase 7）

Day 1-2 ── music-memory-init Skill（Phase 2）
           └── 依赖：Phase 1 数据完成

Day 2-3 ──┬── music-recommender Skill（Phase 3）
          └── 音乐 API 工具（Phase 5）
              └── 两者可并行

Day 3-4 ── playlist-curator Skill（Phase 4）
           └── 依赖：Phase 3 + Phase 5

Day 4 ── music-discovery Skill（Phase 6）
         └── 依赖：Phase 3 + Phase 5

Day 4-5 ── 反馈闭环与迭代（Phase 8）
           └── 依赖：Phase 3 完成并运行
```

---

## 十一、配置清单

### 环境变量
```bash
export LASTFM_API_KEY="your_lastfm_api_key"      # 从 last.fm/api 申请
export SPOTIFY_CLIENT_ID="..."                   # 可选
export SPOTIFY_CLIENT_SECRET="..."               # 可选
```

### config.yaml 修改
```yaml
tools:
  - name: music_search
    group: music
    use: deerflow.community.music.tools:music_search_tool
    api_key: $LASTFM_API_KEY

  - name: music_similar_tracks
    group: music
    use: deerflow.community.music.tools:music_similar_tracks_tool
    api_key: $LASTFM_API_KEY

  - name: music_artist_info
    group: music
    use: deerflow.community.music.tools:music_artist_info_tool
    api_key: $LASTFM_API_KEY
```

---

## 十二、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 网易云 API 风控 | 无法获取数据 | 提前导出数据为本地 JSON，不依赖实时 API |
| Last.fm API 限流 | 工具调用失败 | 加缓存层，减少重复请求 |
| 记忆 facts 过多 | 注入 prompt 超限 | 定期清理低 confidence facts，只保留 Top 50 |
| 推荐质量不高 | 用户体验差 | 初期靠 SOUL.md + taste_profile 冷启动，后期靠反馈迭代 |

---

## 十三、验收总清单

- [ ] 听歌记录 JSON 文件准备完成
- [ ] music-memory-init Skill 能成功导入记忆
- [ ] 3 个音乐 API 工具注册成功并可调用
- [ ] music-recommender 能根据场景返回推荐
- [ ] playlist-curator 能生成结构化歌单
- [ ] music-discovery 能推荐新艺人/歌曲
- [ ] SOUL.md 定义并通过 Bootstrap 导入
- [ ] 用户反馈能被记录到 memory
