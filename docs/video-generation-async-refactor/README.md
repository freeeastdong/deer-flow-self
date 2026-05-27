# 视频生成异步化重构任务目录

## 目录说明

本目录存放"视频生成异步化重构"子方案 B（提交+查询分离）的所有计划文档、修改记录和辅助脚本。

## 文件结构

```
docs/video-generation-async-refactor/
├── README.md                 # 本文件
├── PLAN.md                   # 详细实施计划（主文档）
├── CHANGELOG.md              # 修改记录（执行时逐条追加）
└── scripts/
    └── backup-phase.sh       # Phase 备份脚本
```

## 使用方法

### 1. 创建 Git 分支（必须）

```bash
git checkout -b feature/video-generation-async
```

### 2. 开始执行 Phase

每个 Phase 开始前，先运行备份脚本：

```bash
# Windows (Git Bash / WSL)
bash docs/video-generation-async-refactor/scripts/backup-phase.sh phase1

# Linux / macOS
./docs/video-generation-async-refactor/scripts/backup-phase.sh phase1
```

### 3. 记录修改

完成每个 Step 后，在 `CHANGELOG.md` 末尾追加记录。

### 4. 提交代码

每个 Phase 完成后，建议单独 commit：

```bash
git add .
git commit -m "feat(video-gen): Phase X - 简述内容"
```

### 5. 完整回退

如需回退到某个 Phase 之前的状态：

```bash
# 方式 1：使用备份脚本自动回退
bash .backups/video-generation-async/phase1_20260510_121500/rollback.sh

# 方式 2：Git 回退（推荐）
git log --oneline          # 找到目标 commit
git reset --hard <commit>  # 回退到该 commit

# 方式 3：直接删除分支（最彻底）
git checkout main
git branch -D feature/video-generation-async
```

## 执行顺序

| 顺序 | Phase | 预计会话数 | 风险 |
|------|-------|-----------|------|
| 1 | Phase 1：基础数据层 | 1 | 低 |
| 2 | Phase 2：后台工作线程 | 1-2 | 中 |
| 3 | Phase 3：REST API 层 | 1 | 低 |
| 4 | Phase 4：`generate.py` 重构 | 1 | 中 |
| 5 | Phase 5：Agent 集成 | 1 | 中 |
| 6 | Phase 6：前端进度展示 | 2 | 中 |
| 7 | Phase 7：端到端测试 | 1 | 中 |

## 应急回退（无需回滚代码）

如果线上出现问题，可以临时关闭异步模式：

```yaml
# config.yaml
video_generation:
  async_mode: false   # 立即回退到同步模式
```

重启 Gateway 后生效。

## 联系

如有问题，请在项目 GitHub Issues 中提交，标签：`video-generation`, `async-refactor`。
