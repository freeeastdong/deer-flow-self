# Deer-Flow 项目 Sourcegraph 代码图谱构建计划

> 制定日期：2026-05-27
> 适用项目：deer-flow（LangGraph-based AI agent system）
> 目标：建立可私有化部署的代码图谱平台，实现代码搜索、跳转、依赖分析与可视化

---

## 一、项目背景与技术栈分析

### 1.1 项目结构
```
deer-flow/
├── backend/          # Python 后端 (FastAPI + LangGraph + uv workspace)
│   ├── app/          # 主应用代码
│   ├── packages/     # 子包 (harness 等)
│   ├── tests/        # 测试
│   └── pyproject.toml
├── frontend/         # Next.js 16 + React 19 + TypeScript 前端
│   ├── src/          # 源码
│   ├── tests/        # 测试
│   └── package.json
├── docker/           # Docker Compose 配置
├── scripts/          # 部署与工具脚本
├── comfyui_workflows/# ComfyUI 工作流定义
└── docs/             # 文档
```

### 1.2 核心技术栈
| 模块 | 技术 | Sourcegraph 语言支持 |
|------|------|---------------------|
| 后端 | Python 3.12+, FastAPI, LangGraph | ✅ Python (precise) |
| 前端 | Next.js 16, React 19, TypeScript 5.8 | ✅ TypeScript (precise) |
| 构建 | uv (Python), pnpm (Node) | - |
| 部署 | Docker, Docker Compose | - |
| 工作流 | JSON (ComfyUI) | ⚠️ 基础文本搜索 |

---

## 二、部署方案选择

### 2.1 推荐方案：Docker 单容器部署（`sourcegraph/server`）

**选择理由：**
- 项目规模适中（单仓库 < 10万行），单容器版功能完全足够
- 部署极简（一行命令），运维成本远低于 Docker Compose 多服务方案
- 支持代码搜索、代码智能（Code Intelligence）、Code Insights 等全部核心功能
- 资源占用可控（推荐 4GB 内存 / 4 CPU），与 deer-flow 项目共用开发机无压力
- 数据持久化通过单卷映射即可，备份恢复简单

> **为什么不选 Docker Compose 多服务方案？**
> Sourcegraph 官方 Docker Compose 部署涉及 8-10 个独立容器，需要 12GB+ 内存和复杂的服务间协调。对于 deer-flow 这类单仓库、团队内部使用的场景，单容器版性价比更高。

### 2.2 系统要求

| 资源 | 最低配置 | 推荐配置（本方案使用） |
|------|---------|----------------------|
| CPU | 2 核 | **4 核** |
| 内存 | 2 GB | **4 GB** |
| 磁盘 | 20 GB SSD | 50 GB+ SSD |
| 网络 | 内网访问 | 公网/内网均可 |

### 2.3 前置依赖
- Docker Engine 24.0+
- Docker Compose v2.20+
- Git 2.40+
- 服务器/本地机器满足上述配置要求

---

## 三、详细实施步骤

### Phase 1: 环境准备（预计 30 分钟）

#### 3.1.1 创建专用部署目录

**推荐位置：与 deer-flow 同级的外部独立目录**

Sourcegraph 是平台级工具（非业务代码），运行后会产生大量数据（数据库、代码索引、日志等，轻松达到 10GB+）。将其部署在业务仓库外部，可避免 Git 污染、简化备份策略，并保留未来索引多仓库的灵活性。

```bash
# Linux / Mac / WSL 服务器
mkdir -p /opt/sourcegraph-deerflow
cd /opt/sourcegraph-deerflow

# Windows 本地开发机（PowerShell）
mkdir F:\字节跳动开源项目\sourcegraph-deerflow
cd F:\字节跳动开源项目\sourcegraph-deerflow
```

**推荐目录结构：**
```
F:\字节跳动开源项目\
├── deer-flow-0502/              # 业务代码仓库（保持不变）
│   ├── backend/
│   ├── frontend/
│   └── ...
│
└── sourcegraph-deerflow/        # Sourcegraph 部署目录（本计划使用）
    ├── docker-compose.yaml
    ├── .env
    └── data/                    # 数据卷（已加入 .gitignore）
```

> **为什么不放在 deer-flow 内部？**
> 1. 职责分离：deer-flow 是业务代码，Sourcegraph 是基础设施
> 2. 避免 Git 污染：运行数据不应进入版本控制
> 3. 共享潜力：未来可索引 harness 子包或其他团队仓库
> 4. 备份独立：代码按 Git 管理，平台数据按存储卷管理

> **例外情况**：如果希望 Docker 编排配置纳入版本库供团队共享，可将 `docker-compose.yaml` 和 `.env.example` 存放在 `deer-flow-0502/tools/sourcegraph/` 中，但数据卷仍必须映射到外部目录。

#### 3.1.2 拉取 Sourcegraph 单容器镜像

```bash
# 拉取最新稳定版（当前使用 6.5.0）
docker pull sourcegraph/server:6.5.0

# 验证镜像
 docker images sourcegraph/server --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

#### 3.1.3 配置环境变量

```bash
# 创建 .env 文件
cat > .env << 'EOF'
# Sourcegraph 单容器部署配置
# 项目: deer-flow
# 版本: 6.5.0

# 外部访问配置
SOURCEGRAPH_HTTPS_DOMAIN=localhost
SOURCEGRAPH_HTTP_PORT=7080

# 资源限制（与 deer-flow 项目共享开发机，需合理分配）
# 当前系统: 12核CPU / 32GB内存
# 分配方案: Sourcegraph 4GB/4核， Deer-Flow 保留 20GB+/8核
SG_MEMORY_LIMIT=4g
SG_CPUS_LIMIT=4

# 数据卷路径（Windows 格式，Docker Desktop 自动转换）
SG_DATA_VOLUME=/opt/sourcegraph-deerflow/data
# Windows 示例: SG_DATA_VOLUME=F:/字节跳动开源项目/sourcegraph-deerflow/data
EOF
```

#### 3.1.4 创建启动脚本（含资源限制）

```bash
cat > start-sourcegraph.sh << 'SCRIPT'
#!/bin/bash
set -a
source "$(dirname "$0")/.env"
set +a

# 停止并移除旧容器（如果存在）
docker stop sourcegraph-deerflow 2>/dev/null
docker rm sourcegraph-deerflow 2>/dev/null

# 启动单容器（带资源限制）
docker run -d \
  --name sourcegraph-deerflow \
  --hostname sourcegraph-deerflow \
  --publish "${SOURCEGRAPH_HTTP_PORT}:7080" \
  --publish "127.0.0.1:3370:3370" \
  --memory="${SG_MEMORY_LIMIT}" \
  --cpus="${SG_CPUS_LIMIT}" \
  --restart=unless-stopped \
  --volume "${SG_DATA_VOLUME}:/var/opt/sourcegraph" \
  sourcegraph/server:6.5.0

echo "Sourcegraph 已启动: http://localhost:${SOURCEGRAPH_HTTP_PORT}"
SCRIPT

chmod +x start-sourcegraph.sh
```

**启动容器：**
```bash
./start-sourcegraph.sh

# 等待初始化完成（首次约 30-60 秒）
sleep 30

# 验证健康状态
curl http://localhost:7080/healthz
# 预期输出: 6.5.0
```

---

### Phase 2: 部署 Sourcegraph（预计 20-40 分钟）

#### 3.2.1 启动服务
```bash
docker compose up -d

# 查看启动状态
docker compose ps
docker compose logs -f sourcegraph-frontend-0
```

#### 3.2.2 初始化配置
1. 访问 `http://<服务器IP>:7080`
2. 创建管理员账户
3. 配置外部访问 URL（Site Configuration）
4. 配置邮件/通知（可选）

#### 3.2.3 验证核心服务健康状态
```bash
# 检查所有容器状态
docker compose ps

# 关键端点健康检查
curl http://localhost:7080/healthz
curl http://localhost:7080/-/ready
```

---

### Phase 3: 接入 Deer-Flow 代码仓库（预计 20 分钟）

#### 3.3.1 添加代码仓库

**方式 A：直接添加本地 Git 仓库（推荐用于本地部署）**
1. 进入 Sourcegraph Web UI → Site Admin → Repositories → Manage code hosts
2. 选择 "Other" → "Add Git repositories by clone URL"
3. 填写：
   - Repository name: `deer-flow`
   - Clone URL: `file:///path/to/deer-flow-0502/.git`（本地路径）
   - 或远程 URL: `https://github.com/byteplus/DeerFlow.git`（如已开源）

**方式 B：通过 GitHub 代码主机集成（如使用 GitHub）**
1. Site Admin → Code hosts → Add GitHub code host
2. 配置 GitHub App / Personal Access Token
3. 设置仓库选择规则：`include deer-flow`

**方式 C：定期同步脚本（适用于无公网 Git 服务的情况）**
```bash
#!/bin/bash
# /opt/sourcegraph-deerflow/sync-repo.sh
REPO_DIR="/opt/sourcegraph-deerflow/mirrors/deer-flow"
SOURCE_DIR="/path/to/deer-flow-0502"

# 创建裸仓库镜像
if [ ! -d "$REPO_DIR" ]; then
    git clone --mirror "$SOURCE_DIR" "$REPO_DIR"
else
    cd "$REPO_DIR" && git remote update
fi
```

#### 3.3.2 触发首次代码索引
```bash
# 使用 src CLI 强制重新索引（如已安装 src）
src repos list
src repos get -repo=deer-flow
```

---

### Phase 4: 配置代码智能（Code Intelligence）（预计 40-60 分钟）

#### 3.4.1 Python 后端智能（FastAPI + LangGraph）

Sourcegraph 的 Python 精确代码智能基于 **SCIP**（前身 LSIF）。

**步骤：**

1. **安装 scip-python 索引工具**
```bash
# 在 deer-flow 后端环境中
cd /path/to/deer-flow-0502/backend

# 安装 scip-python（需 Node.js 环境）
npm install -g @sourcegraph/scip-python
# 或使用 pip 安装对应工具
pip install scip-python
```

2. **生成 SCIP 索引**
```bash
cd /path/to/deer-flow-0502/backend

# 创建虚拟环境并安装依赖（确保解析完整）
uv sync --all-groups

# 生成 SCIP 索引（针对 workspace 中所有包）
scip-python index \
  --project-name deer-flow \
  --output deer-flow.scip \
  .

# 或针对 workspace 逐个索引
for pkg in packages/*; do
  [ -d "$pkg" ] || continue
  scip-python index \
    --project-name "deer-flow/$(basename $pkg)" \
    --output "$(basename $pkg).scip" \
    "$pkg"
done
```

3. **上传 SCIP 索引到 Sourcegraph**
```bash
# 配置 src CLI
export SRC_ENDPOINT=http://localhost:7080
export SRC_ACCESS_TOKEN=<your-token>  # 从 Site Admin > Access tokens 获取

# 上传索引
src code-intel upload \
  -repo=deer-flow \
  -commit=$(git rev-parse HEAD) \
  -file=deer-flow.scip \
  -indexer=scip-python
```

#### 3.4.2 TypeScript/JavaScript 前端智能（Next.js + React）

**步骤：**

1. **安装 scip-typescript**
```bash
cd /path/to/deer-flow-0502/frontend
npm install -g @sourcegraph/scip-typescript
# 或使用 pnpm
pnpm add -g @sourcegraph/scip-typescript
```

2. **生成 SCIP 索引**
```bash
cd /path/to/deer-flow-0502/frontend

# 确保依赖已安装
pnpm install

# 生成索引（会自动读取 tsconfig.json）
scip-typescript index \
  --project-name deer-flow-frontend \
  --output deer-flow-frontend.scip
```

3. **上传索引**
```bash
src code-intel upload \
  -repo=deer-flow \
  -commit=$(git rev-parse HEAD) \
  -file=deer-flow-frontend.scip \
  -indexer=scip-typescript
```

#### 3.4.3 自动化索引流水线（CI 集成建议）

```yaml
# .github/workflows/sourcegraph-index.yml
name: Sourcegraph Code Intelligence

on:
  push:
    branches: [main, develop]

jobs:
  index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install src-cli
        run: |
          curl -L https://sourcegraph.com/.api/src-cli/src_linux_amd64 -o /usr/local/bin/src
          chmod +x /usr/local/bin/src
      
      - name: Index Python
        working-directory: ./backend
        run: |
          pip install scip-python
          scip-python index --project-name deer-flow --output ../deer-flow.scip .
      
      - name: Index TypeScript
        working-directory: ./frontend
        run: |
          npm install -g @sourcegraph/scip-typescript
          pnpm install
          scip-typescript index --project-name deer-flow-frontend --output ../deer-flow-frontend.scip
      
      - name: Upload Indexes
        run: |
          export SRC_ENDPOINT=${{ secrets.SOURCEGRAPH_URL }}
          export SRC_ACCESS_TOKEN=${{ secrets.SOURCEGRAPH_TOKEN }}
          src code-intel upload -repo=deer-flow -commit=${{ github.sha }} -file=deer-flow.scip
          src code-intel upload -repo=deer-flow -commit=${{ github.sha }} -file=deer-flow-frontend.scip
```

---

### Phase 5: 高级功能配置（预计 30-60 分钟）

#### 3.5.1 搜索配置优化
```json
// Site Admin > Global Settings
{
  "search.index.symbols": true,
  "search.index.enabled": true,
  "search.largeFiles": ["*.ipynb", "*.json", "*.yaml", "*.yml"],
  "search.scopes": [
    {
      "name": "Backend Only",
      "value": "repo:deer-flow file:backend/"
    },
    {
      "name": "Frontend Only",
      "value": "repo:deer-flow file:frontend/"
    },
    {
      "name": "API Routes",
      "value": "repo:deer-flow file:backend/app/(api|routes)/"
    },
    {
      "name": "React Components",
      "value": "repo:deer-flow file:frontend/src/components/ lang:typescript"
    }
  ]
}
```

#### 3.5.2 代码监控与洞察（Code Insights）
创建以下常用监控面板：
- **LangGraph 节点数量趋势**：搜索 `langgraph` 或 `class.*Node`
- **API 端点增长**：搜索 `@router.get|post|put|delete`
- **组件库使用情况**：搜索 `@radix-ui/react-` 引用
- **TODO/FIXME 追踪**：搜索 `TODO|FIXME` 注释

#### 3.5.3 批注与代码审查集成（可选）
- 配置与 GitHub/GitLab PR 的集成
- 启用浏览器插件（Sourcegraph browser extension）

---

## 四、项目特有配置注意事项

### 4.1 uv Workspace 处理
Deer-Flow 后端使用 `uv` 作为包管理器并包含 workspace 结构：
```
backend/
├── pyproject.toml      # 主项目 + workspace 定义
└── packages/
    └── harness/        # workspace member
        └── pyproject.toml
```

**建议：**
- 在生成 SCIP 索引时，从 `backend/` 根目录运行，确保 workspace 依赖关系被正确解析
- 或在 CI 中为每个 workspace member 单独生成并上传索引（使用不同的 `-root` 路径）

### 4.2 Next.js App Router 结构
前端使用 Next.js 15+ 的 App Router：
```
frontend/src/
├── app/               # App Router 目录
├── components/        # React 组件
└── lib/               # 工具函数
```

**建议：**
- `scip-typescript` 默认会读取 `tsconfig.json`，确保 `include` 字段覆盖 `src/**/*`
- 如使用路径别名（`@/components` 等），需在 `tsconfig.json` 中正确配置 `paths`，SCIP 索引器会自动解析

### 4.3 Docker 网络整合（可选）
如需将 Sourcegraph 与现有 deer-flow Docker Compose 网络整合：

```yaml
# 在 deer-flow/docker-compose.yaml 中追加网络配置
networks:
  deerflow-network:
    driver: bridge
  sourcegraph-network:
    external: true  # 指向 Sourcegraph 的网络
```

---

## 五、验证清单

部署完成后，按以下清单验证功能：

- [ ] Web UI 可正常访问 (`http://<host>:7080`)
- [ ] Deer-Flow 仓库已克隆并显示在 Repositories 列表
- [ ] 全局文本搜索可返回结果（尝试搜索 `FastAPI` 或 `LangGraph`）
- [ ] Python 代码智能生效：点击 backend 中的函数名可跳转到定义
- [ ] TypeScript 代码智能生效：点击 frontend 中的组件可跳转到定义
- [ ] 跨文件/跨语言引用查找可用（Find References）
- [ ] 符号搜索可用（Ctrl+Space 或点击搜索框的 Symbol 选项）
- [ ] Code Insights 面板可创建并显示数据

---

## 六、维护与故障排除

### 6.1 日常维护命令（单容器版）
```bash
# 查看容器状态
docker ps --filter name=sourcegraph-deerflow

# 查看日志
docker logs -f --tail=100 sourcegraph-deerflow

# 重启容器
docker restart sourcegraph-deerflow

# 更新到新版
export NEW_VERSION="6.6.0"  # 以实际最新版为准
docker stop sourcegraph-deerflow
docker rm sourcegraph-deerflow
docker pull sourcegraph/server:${NEW_VERSION}
# 修改 start-sourcegraph.sh 中的版本号后重新启动
./start-sourcegraph.sh

# 查看资源使用
docker stats --no-stream sourcegraph-deerflow

# 清理未使用的 Docker 缓存
docker system prune -a
```

### 6.2 常见问题

| 问题 | 解决方案 |
|------|---------|
| 索引上传失败 | 检查 `SRC_ENDPOINT` 和 `SRC_ACCESS_TOKEN`；确认 commit hash 存在于仓库中 |
| Python 跳转不准确 | 确保 `scip-python` 在正确的虚拟环境中运行；检查 `pyproject.toml` 依赖是否完整安装 |
| TypeScript 跳转缺失 | 确认 `tsconfig.json` 包含所有源文件路径；重新运行 `pnpm install` |
| 搜索无结果 | 检查仓库是否已完成索引（Site Admin > Repositories 查看状态）；检查仓库权限 |
| 内存不足 OOM | 增加 Docker 内存限制（`--memory`）或关闭其他占用内存的应用 |
| 端口冲突 | 修改 `.env` 中的 `SOURCEGRAPH_HTTP_PORT` 避免与 deer-flow 服务冲突 |

### 6.3 备份策略
```bash
# 备份数据目录（建议每周执行，单容器版备份非常简单）
BACKUP_DIR="/backup/sourcegraph/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# 方式 1：直接压缩数据目录（推荐，因为数据已映射到宿主机）
tar czf "$BACKUP_DIR/sourcegraph-data.tar.gz" -C /opt/sourcegraph-deerflow/data .

# 方式 2：通过容器备份（如果数据在 Docker 卷中）
docker run --rm \
  -v sourcegraph-deerflow_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/sourcegraph-data.tar.gz -C /data .
```

---

## 七、资源参考

- [Sourcegraph 官方文档](https://docs.sourcegraph.com/)
- [单容器部署指南](https://docs.sourcegraph.com/admin/deploy/docker-single-container)
- [SCIP Python 索引器](https://github.com/sourcegraph/scip-python)
- [SCIP TypeScript 索引器](https://github.com/sourcegraph/scip-typescript)
- [src-cli 使用文档](https://github.com/sourcegraph/src-cli)

---

## 八、时间规划总结

| 阶段 | 预计耗时 | 依赖 |
|------|---------|------|
| Phase 1: 环境准备 | 15 分钟 | Docker 环境就绪 |
| Phase 2: 部署 Sourcegraph | 5-10 分钟 | Phase 1 完成 |
| Phase 3: 接入仓库 | 10 分钟 | Phase 2 完成 |
| Phase 4: 代码智能配置 | 30-40 分钟 | Phase 3 完成 |
| Phase 5: 高级功能 | 20-30 分钟 | Phase 4 完成 |
| **总计** | **1 - 1.5 小时** | - |

---

*文档版本: v1.0*
*维护者: 项目开发团队*
