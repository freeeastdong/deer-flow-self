# Music Agent 配置示例

> 本项目采用 **独立 Agent 架构**：音乐记忆、偏好和推荐逻辑全部隔离在 `music-agent` 中，不污染全局 agent 的记忆。

---

## 1. 注册音乐工具到 config.yaml

在 `config.yaml` 的 `tools:` 段落中添加以下配置：

```yaml
tools:
  # ... 其他已有工具 ...

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

## 2. 环境变量

在运行 DeerFlow 前，设置 Last.fm API Key：

```bash
# Linux/macOS
export LASTFM_API_KEY="your_lastfm_api_key"

# Windows PowerShell
$env:LASTFM_API_KEY="your_lastfm_api_key"
```

获取 API Key：
1. 访问 https://www.last.fm/api/account/create
2. 创建应用（随便填名称和描述）
3. 复制 API Key

## 3. 独立 Agent 配置

`music-agent` 的配置已预置在：

```
backend/.deer-flow/agents/music-agent/
├── config.yaml      # Agent 配置（已创建）
└── SOUL.md          # Agent 性格定义（已创建）
```

配置内容：

```yaml
name: music-agent
description: Personal music curator agent with deep taste memory and recommendation skills
model: null
tool_groups:
  - file:read
  - music
skills:
  - music-memory-init
  - music-recommender
  - playlist-curator
  - music-discovery
```

### 切换 Agent 的方式

通过 API 调用时传入 `agent_name` 参数即可切换到 music-agent：

```bash
# 示例：在 music-agent 上下文中获取记忆
curl -s "http://localhost:8001/api/memory?agent_name=music-agent"

# 示例：在 music-agent 上下文中创建 fact
curl -s -X POST "http://localhost:8001/api/memory/facts?agent_name=music-agent" \
  -H "Content-Type: application/json" \
  -d '{"content": "...", "category": "preference", "confidence": 0.95}'
```

前端聊天时，需要选择或切换到 `music-agent` 才能触发音乐相关的 Skill 和记忆。

## 4. 记忆存储位置

| Agent | 记忆文件路径 |
|-------|-------------|
| 默认全局 Agent | `.deer-flow/users/{user_id}/memory.json` |
| music-agent | `.deer-flow/users/{user_id}/agents/music-agent/memory.json` |

两者完全隔离。全局 agent 看不到 music-agent 的记忆，music-agent 也看不到全局的记忆。

## 5. 启用自定义 Skills

自定义 Skills 放在 `skills/custom/` 目录下会自动被加载。确保以下目录存在：

```
skills/custom/
├── music-memory-init/
│   ├── SKILL.md
│   └── scripts/
│       └── init_memory.py
├── music-recommender/
│   └── SKILL.md
├── playlist-curator/
│   └── SKILL.md
└── music-discovery/
    └── SKILL.md
```

## 6. 重启 DeerFlow

修改配置后，重启 DeerFlow backend：

```bash
cd backend
make dev
# 或者
uvicorn app.gateway.main:app --reload
```

## 7. 验证工具注册

启动后，访问 API 文档确认工具已注册：

```bash
curl -s http://localhost:8001/api/skills
```

验证 music-agent 是否存在：

```bash
curl -s http://localhost:8001/api/agents
```

## 8. 初始化音乐记忆（重要）

准备好数据后，在 **music-agent 上下文**中运行初始化：

```bash
python skills/custom/music-memory-init/scripts/init_memory.py \
  --history docs/music-agent/data/listening_history.json \
  --taste docs/music-agent/data/taste_profile.md \
  --output docs/music-agent/data/music_facts.json \
  --agent-name music-agent \
  --import-to-memory
```

验证导入成功：

```bash
curl -s "http://localhost:8001/api/memory?agent_name=music-agent" | python -m json.tool | grep -c '"facts"'
```
