# Phase 2-D 实施报告 — 免版权音乐接入（含方案 C 预留）

## 目标

按 `plan.md` 方案 D（免版权音乐）实施真实音频播放，同时预留方案 C（用户自行上传）的改造空间。

---

## 实施内容概览

| 模块 | 改造点 | 状态 |
|------|--------|------|
| 数据库 | `songs` 表新增 `audio_url` 字段 | 已完成 |
| 后端模型 | `Song` 模型、`recommender._song_to_dict` 透传 `audio_url` | 已完成 |
| 后端脚本 | `scripts/import_songs.py` 批量导入工具 | 已完成 |
| 后端脚本 | `scripts/sync_royalty_free.py` 免版权音乐库爬虫/API 客户端 | 已完成 |
| 前端类型 | `Song` 接口新增 `audio_url` | 已完成 |
| 前端播放器 | `Player.tsx` 接入真实 `<audio>` 播放 | 已完成 |
| 前端交互 | `VoiceAssistant.tsx` 推荐卡片点击真正播放 | 已完成 |
| 前端布局 | `Home.tsx` 浮动播放器集成 | 已完成 |

---

## 1. 数据库变更

### Alembic 迁移

**文件**：`music-station/backend/alembic/versions/b2f8a9c1d3e4_add_audio_url_to_songs.py`

```python
op.add_column('songs', sa.Column('audio_url', sa.String(500), nullable=True))
```

**应用迁移**（在 backend 目录下执行）：

```bash
alembic upgrade b2f8a9c1d3e4
```

> 如果 alembic 环境未配置好，也可以直接由 FastAPI 启动时自动创建：`Base.metadata.create_all` 已包含新字段。

---

## 2. audio_url 字段设计（兼容方案 D + 方案 C）

为了同时支持免版权音乐直链（方案 D）和用户上传文件（方案 C），`audio_url` 的存储规范如下：

| 类型 | 存储格式 | 示例 |
|------|---------|------|
| 外部免版权音乐 URL | 完整 HTTP/HTTPS URL | `https://cdn.pixabay.com/download/audio/xxx.mp3` |
| 用户上传本地文件 | 相对路径（以 `/media/songs/` 开头） | `/media/songs/my_song.mp3` |

### 前端解析逻辑

前端统一通过 `resolveAudioUrl()` 函数处理：

```typescript
function resolveAudioUrl(url?: string): string {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  const base = window.location.origin
  return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`
}
```

后端导入脚本也包含同样的 `resolve_audio_url()` 函数，保证入库时路径统一。

---

## 3. 批量导入工具

**文件**：`music-station/backend/scripts/import_songs.py`

### 功能

支持两种导入模式，可单独或组合使用：

#### 模式 A：JSON 配置文件导入（方案 D — 免版权音乐库）

适用于已有免版权音乐直链的场景。将歌曲元数据和音频 URL 写入 JSON，一键入库。

```bash
cd music-station/backend
python scripts/import_songs.py --config scripts/royalty_free_catalog.json
```

#### 模式 B：本地音频文件扫描（方案 C — 用户上传）

适用于用户将自有音频文件放入 `media/songs/` 目录的场景。自动扫描并入库。

```bash
# 仅扫描
python scripts/import_songs.py --scan

# 扫描 + sidecar 元数据补充
python scripts/import_songs.py --scan --sidecar scripts/song_metadata.json
```

#### 模式 C：混合导入

```bash
python scripts/import_songs.py --config scripts/royalty_free_catalog.json --scan
```

### JSON 配置文件格式

```json
[
  {
    "title": "Dreams",
    "artist": "Benjamin Tissot",
    "album": "Royalty Free Music",
    "cover_url": "https://cdn.pixabay.com/audio/2022/05/27/02-126%-570.jpg",
    "audio_url": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
    "duration": 186,
    "genre": "Ambient",
    "tags": ["relaxing", "dreamy", "electronic"],
    "tempo": 85,
    "energy": 0.3,
    "valence": 0.6,
    "danceability": 0.2,
    "acousticness": 0.4
  }
]
```

### 免版权音乐库同步工具（自动化接入）

**文件**：`music-station/backend/scripts/sync_royalty_free.py`

这是一个统一的免版权音乐同步客户端，支持从多个平台自动抓取/同步歌曲：

#### 支持的平台

| 平台 | 接入方式 | 需要 API Key | 特点 |
|------|---------|-------------|------|
| **Jamendo** | 官方 REST API | 是（免费） | 50万+ CC 授权音乐，支持按关键词/流派/情绪搜索 |
| **Pixabay Music** | 网页爬虫 | 否 | 免费可商用，无需署名 |
| **Incompetech** | 聚合站爬虫 | 否 | Kevin MacLeod 作品，经典背景音乐 |

#### 用法示例

```bash
cd music-station/backend

# 1. 从 Jamendo 同步 30 首 chill 音乐到 JSON
python scripts/sync_royalty_free.py --source jamendo --keyword "chill" --limit 30 --output chill_songs.json

# 2. 从 Jamendo 直接导入数据库
export JAMENDO_CLIENT_ID="your-client-id"
python scripts/sync_royalty_free.py --source jamendo --keyword "rock" --limit 20 --import-db

# 3. 从 Pixabay 抓取
python scripts/sync_royalty_free.py --source pixabay --keyword "relaxing" --limit 20 --output pixabay_songs.json

# 4. 从 Incompetech 抓取 Kevin MacLeod 作品
python scripts/sync_royalty_free.py --source incompetech --limit 50 --output incompetech_songs.json
```

#### Jamendo API Client ID 申请

1. 访问 https://developer.jamendo.com/v3.0
2. 注册账号并创建应用
3. 获取 Client ID，填入环境变量：
   ```bash
   export JAMENDO_CLIENT_ID="your-client-id"
   ```
   或写入 `music-station/backend/.env` 文件：
   ```
   JAMENDO_CLIENT_ID=your-client-id
   ```

#### 同步到数据库后的流程

同步完成后，歌曲已带有 `audio_url`（外部直链），前端可以直接播放：
```
Jamendo API → sync_royalty_free.py → 数据库 → 前端 Player 直接播放
```

### 手动导入方式（备选）

如果不需要自动化同步，也可以使用手动方式：

| 平台 | 网址 | 特点 |
|------|------|------|
| **Pixabay Music** | https://pixabay.com/music/ | 免费可商用，无需署名，提供直链下载 |
| **Free Music Archive** | https://freemusicarchive.org/ | 曲库丰富，需按授权类型筛选 |
| **YouTube Audio Library** | https://www.youtube.com/audiolibrary | Google 官方，YouTube 项目可用 |
| **Incompetech** | https://incompetech.com/music/ | Kevin MacLeod 作品，CC 授权 |
| **Bensound** | https://www.bensound.com/ | 部分免费，需署名 |

**已提供示例配置**：`scripts/royalty_free_catalog.example.json`（8 首示例，均来自 Pixabay 可商用音乐）

---

## 4. 前端播放器改造

### Player.tsx — 真实音频播放

**核心变更**：
- 移除 `demoSongs` 假数据，完全从 `usePlayerStore` 读取
- 引入隐藏的 `<audio>` 元素，通过 ref 控制真实播放
- 进度条绑定 `audio.currentTime` / `audio.duration`，支持点击跳转
- 播放结束自动切换下一首
- 音量控制
- 错误处理（音频加载失败时显示提示）

### VoiceAssistant.tsx — 推荐卡片真正可播放

**核心变更**：
- `playRecommendedSong` 现在会：
  1. 检查 `song.audio_url` 是否存在，不存在则友好提示
  2. 将当前推荐列表批量设为 `playlist`
  3. 调用 `setCurrentSong(song)` 触发全局播放器加载音频
  4. 自动开始播放
- 收藏歌曲时也保存 `audio_url`，方便后续从收藏直接播放

### Home.tsx — 浮动播放器

**核心变更**：
- 右下角引入 `Player` 组件作为浮动迷你播放器
- 仅当 `currentSong` 存在时显示
- 不遮挡主交互区域（聊天卡片在底部中央）

---

## 5. 如何接入自己的音乐（方案 C 预留路径）

当前代码已完全兼容方案 C，只需执行以下步骤即可从「免版权直链」切换到「本地文件」：

### 步骤 1：准备音频文件

将你的 MP3/FLAC 文件放入：

```
music-station/backend/media/songs/
```

### 步骤 2：批量导入数据库

```bash
cd music-station/backend
python scripts/import_songs.py --scan
```

可选：准备 `sidecar` JSON 补充封面、流派等信息：

```json
[
  {
    "filename": "my_song.mp3",
    "title": "我的歌",
    "artist": "我自己",
    "genre": "Pop",
    "tags": ["happy", "summer"],
    "cover_url": "https://example.com/cover.jpg"
  }
]
```

```bash
python scripts/import_songs.py --scan --sidecar scripts/my_metadata.json
```

### 步骤 3：确认静态文件服务

后端 `main.py` 已挂载 `/media` 目录：

```python
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")
```

访问 `http://<backend>/media/songs/my_song.mp3` 即可直接播放。

---

## 6. 验证清单

- [ ] 执行 `alembic upgrade` 或重启后端，确认 `songs.audio_url` 字段已创建
- [ ] 运行 `python scripts/import_songs.py --config scripts/royalty_free_catalog.example.json` 导入示例歌曲
- [ ] 打开音乐电台页面，确认自动开场后推荐卡片出现
- [ ] 点击推荐卡片的播放按钮，确认右下角浮动播放器弹出并开始播放真实音频
- [ ] 确认进度条随播放推进，点击进度条可跳转
- [ ] 确认上一首/下一首按钮正常工作
- [ ] 确认收藏按钮正常工作，收藏的歌曲可在侧边栏查看
- [ ] 确认 TTS 语音（主播说话）与音乐播放互不干扰

---

## 7. 已知限制

| 限制 | 说明 | 后续计划 |
|------|------|---------|
| 需要网络连接 | 方案 D 使用外部 CDN 直链，离线时无法播放 | 方案 C 切换到本地文件后可离线播放 |
| 音频元数据提取 | 导入脚本未自动提取 MP3 ID3 标签 | 可接入 `mutagen` 库自动读取 |
| 播放器 UI 位置 | 浮动播放器在右下角，移动端可能遮挡 | 后续增加响应式布局或底部迷你条 |
| 连续流自动播放 | 仍需点击「继续收听」按钮 | Phase 1.5 可实现 TTS 结束自动触发 |

---

## 8. 文件变更汇总

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `backend/alembic/versions/b2f8a9c1d3e4_add_audio_url_to_songs.py` | 新增 | 数据库迁移：添加 audio_url 字段 |
| `backend/app/models/song.py` | 修改 | Song 模型添加 audio_url 列 |
| `backend/app/services/recommender.py` | 修改 | `_song_to_dict` 返回 audio_url |
| `backend/scripts/import_songs.py` | 新增 | 批量导入工具（JSON + 本地扫描） |
| `backend/scripts/sync_royalty_free.py` | 新增 | 免版权音乐库同步爬虫/API 客户端 |
| `backend/scripts/royalty_free_catalog.example.json` | 新增 | 免版权音乐示例配置 |
| `frontend/src/types/index.ts` | 修改 | Song 接口添加 audio_url |
| `frontend/src/components/Player.tsx` | 重写 | 接入真实 audio 播放 |
| `frontend/src/components/VoiceAssistant.tsx` | 修改 | playRecommendedSong 真正播放音频 |
| `frontend/src/pages/Home.tsx` | 修改 | 集成浮动 Player 组件 |
