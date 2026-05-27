# DeerFlow 前端内存优化计划

> **创建日期**: 2026-05-08
> **关联问题**: 前端开发模式下内存占用达到 3GB+
> **影响范围**: `docker/docker-compose-dev.yaml`

---

## 1. 背景与目标

### 1.1 当前问题

在本地开发模式（`pnpm dev`，使用 Turbopack）下，前端 Node.js 进程内存占用达到 **3GB+**，远超正常范围（500MB–1GB）。经排查，内存问题由 Turbopack 本身导致：

### 主导因素（~90% 内存占用）：Turbopack 开发服务器本身
Next.js 16 默认启用 Turbopack（`--turbo`），但 Turbopack 在复杂项目中存在严重的内存膨胀问题：
- 启动基线即达 **~2GB**（GitHub 社区大量报告）
- `.next/dev` 编译缓存持续累积（本项目实测 1.1GB）
- 每次路由编译增加 ~400MB，硬刷新每次增加 ~30MB

### 1.2 优化目标

- 将开发模式内存峰值控制在 **2GB 以下**（通过 Docker 容器硬限制）
- 不影响现有业务功能和用户体验

---

## 2. 优化项详细计划

### 2.1 优化项一（P0）：Turbopack 内存限制

#### 问题描述

Next.js 16 默认启用 Turbopack（`next dev`）作为开发服务器打包工具。Turbopack 使用 Rust 编写，理论上提供更快的编译速度和 HMR，但在复杂项目中存在严重的**内存膨胀问题**。

实测 DeerFlow 前端容器内存占用 **2.919 GiB**，其中 `next-server (v16.1.7)` 单个进程的物理内存（RSS）高达 **3,495 MB**。进程树分析显示大量 `tokio-runtime-w` 线程（Turbopack 的 Rust 运行时）和 1.1GB 的 `.next/dev` 编译缓存。

GitHub 社区有大量同类报告：
- [vercel/next.js #81161](https://github.com/vercel/next.js/issues/81161)：15 个空白路由内存达 8GB
- [vercel/next.js #78069](https://github.com/vercel/next.js/issues/78069)：路由越多内存越高，稳定后 9-10GB
- [vercel/next.js #70178](https://github.com/vercel/next.js/discussions/70178)：从 Next.js 12.x 开始就有此问题

#### 尝试回退 Webpack（已证实不可行）

> ⚠️ **重要发现**：Next.js 16 已**强制默认使用 Turbopack**，以下尝试均失败：
> - `npx next dev` → 仍然是 Turbopack
> - `npx next dev --no-turbo` → 参数不存在，容器崩溃
> - `TURBOPACK=0` / `NEXT_TURBOPACK=0` → 环境变量无效
>
> 因此无法通过简单配置回退到 Webpack，必须采用**内存限制**作为缓解方案。

#### 影响评估

| 维度 | 评估 |
|------|------|
| 严重程度 | 🔴 **极高** — 占总内存的 **~90%** |
| 触发条件 | 启动 dev server 即发生，无需用户操作 |
| 内存增长模式 | 基线 2GB+，随路由编译和页面刷新持续增长 |

#### 修改方案

**方案（推荐）：为前端容器添加内存硬限制 + Node.js heap 上限**

```yaml
frontend:
  environment:
    - NODE_ENV=development
    - WATCHPACK_POLLING=true
    - CI=true
    - DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001
    # Cap Node.js heap to prevent unbounded memory growth from Turbopack
    - NODE_OPTIONS=--max-old-space-size=1536
  deploy:
    resources:
      limits:
        memory: 2G
```

| 限制项 | 值 | 作用 |
|--------|-----|------|
| `NODE_OPTIONS=--max-old-space-size=1536` | 1.5 GB | Node.js V8 堆内存上限，触发更激进的 GC |
| `deploy.resources.limits.memory: 2G` | 2 GB | Docker 容器物理内存硬上限，超过后 OOM Killed |

#### 预期效果

| 指标 | 限制前 | 限制后 | 说明 |
|------|--------|--------|------|
| 容器内存上限 | 无限制（15.53GB） | **2GB** | 硬封顶 |
| Node.js heap 上限 | 无限制 | **1.5GB** | 触发 GC 更频繁 |
| 实际观测内存 | 2.9GB+ | **1.5–2.0GB** | Turbopack 被强制回收 |
| OOM 风险 | 系统级卡死 | **容器级重启** | 影响范围更小 |

> 注意：限制内存后，Turbopack 仍会在 2GB 范围内波动，但不会无限膨胀到 3GB+。

#### 风险与回滚策略

| 风险 | 缓解措施 |
|------|---------|
| 频繁 GC 导致编译卡顿 | 2GB 对 Turbopack 基线（~2GB）足够，一般不会频繁 GC |
| 容器 OOM 后重启丢失状态 | `restart: unless-stopped` 会自动重启，开发状态（代码）不受影响 |
| 回滚 | 删除 `NODE_OPTIONS` 和 `deploy.resources.limits` 即可 |

#### 实施步骤

```powershell
# 1. 停止当前前端容器
docker stop deer-flow-frontend

# 2. 修改 docker-compose-dev.yaml（添加 NODE_OPTIONS 和 memory 限制）

# 3. 重建并启动前端容器
cd f:\字节跳动开源项目\deer-flow-0502\docker
$env:HOME = $env:USERPROFILE
docker-compose -f docker-compose-dev.yaml up -d --force-recreate frontend

# 4. 验证内存限制生效
docker stats --no-stream deer-flow-frontend
# 预期输出: MEM USAGE / LIMIT 显示 xxxMiB / 2GiB
```

---

### 2.2 优化项二（P1）：全局容器内存限制

#### 问题描述

除 frontend 外，其他 Docker 容器同样运行在**无内存限制**的环境中。虽然当前占用不高，但存在以下风险：
- `deer-flow-gateway` 运行 LangGraph 流、Sandbox 生命周期管理，长期运行可能内存增长
- 任何容器的意外内存泄漏都可能拖垮整个 Docker VM 或宿主机
- 开发环境缺乏资源隔离，问题难以定位

#### 影响评估

| 维度 | 评估 |
|------|------|
| 严重程度 | 🟡 中 — 当前占用正常，但属于防御性架构优化 |
| 触发条件 | 长期运行、异常请求、数据量增长 |
| 内存增长模式 | 各容器独立，任一泄漏都会影响宿主机 |

#### 修改方案

**在 `docker-compose-dev.yaml` 中为所有服务添加 `deploy.resources.limits.memory`**

| 服务 | 当前内存 | 限制值 | 理由 |
|------|---------|--------|------|
| `deer-flow-frontend` | ~210MB | **2G** | Turbopack 基线高，已在前序优化中设置 |
| `deer-flow-gateway` | ~158MB | **1.5G** | 核心后端，AI 流式响应 + Sandbox 管理，波动最大 |
| `deer-flow-provisioner` | ~低 | **512M** | Python K8s 客户端，Kube API 缓存可能增长 |
| `deer-flow-nginx` | ~3MB | **128M** | C 程序，极稳定，128MB 绰绰有余 |
| `music-station-backend` | ~80MB | **512M** | Python FastAPI，当前 80MB，留足余量 |
| `music-station-db` | ~21MB | **1G** | PostgreSQL，开发环境数据量小，1GB 够用 |
| `music-station-redis` | ~4MB | **256M** | 缓存服务，当前 4MB，256MB 封顶安全 |

```yaml
# 示例：gateway 服务
gateway:
  deploy:
    resources:
      limits:
        memory: 1.5G
```

> **注意**：数据库类容器（PostgreSQL、Redis）的限制是**封顶保护**，不是性能优化。开发环境数据量小，限制不会负面影响性能。生产环境需根据实际数据量调整。

#### 预期效果

- 任一容器内存泄漏都不会超过预设上限
- 容器 OOM 后会由 `restart: unless-stopped` 自动重启，影响范围可控
- 整体系统资源使用更可预测

#### 风险与回滚策略

| 风险 | 缓解措施 |
|------|---------|
| PostgreSQL/Redis 限制过低影响性能 | 开发环境当前数据量极小，1GB/256MB 足够；生产环境需单独评估 |
| 容器 OOM 后状态丢失 | 数据库使用 Docker Volume 持久化，重启后数据不丢；应用容器无状态 |
| 回滚 | 删除对应服务的 `deploy.resources.limits` 配置即可 |

#### 实施步骤

```powershell
cd f:\字节跳动开源项目\deer-flow-0502\docker
$env:HOME = $env:USERPROFILE
docker-compose -f docker-compose-dev.yaml up -d

# 验证限制生效
docker stats --no-stream
# 预期：所有容器的 LIMIT 列都显示具体值（如 128MiB、1.5GiB 等）
```

---

## 3. 实施优先级与里程碑

### 优先级排序

| 优先级 | 优化项 | 原因 |
|--------|--------|------|
| **P0** | **2.1 Turbopack 内存限制** | **内存占用大头（~90%），立即见效** |
| P1 | 2.2 全局容器内存限制 | 防御性架构优化，防止任何容器泄漏拖垮系统 |

### 实施里程碑

```
Day 1: 完成 P0 + P1 优化（容器内存限制）
        └── 修改 docker-compose-dev.yaml
        └── 重建所有容器
        └── 验证内存限制生效（docker stats）
```

---

## 4. 验证方案

### 4.1 容器内存测试

```bash
# 验证所有容器的内存限制已生效
docker stats --no-stream
# 预期：所有容器的 LIMIT 列都显示具体值
```

### 4.2 预期指标

| 测试场景 | 限制前（参考） | 限制后目标 |
|---------|--------------|-----------|
| 前端容器内存 | 2.9GB+ | **≤ 2GB** |
| Gateway 容器内存 | ~158MB | **≤ 1.5GB** |
| 其他容器内存 | 正常 | **不超过各自限制** |

---

## 5. 附录

### 5.1 相关文件清单

| 文件 | 路径 | 改动类型 |
|------|------|---------|
| Docker Compose Dev | `docker/docker-compose-dev.yaml` | 修改 |

### 5.2 上游参考

- [vercel/next.js #81161](https://github.com/vercel/next.js/issues/81161) — Turbopack dev server memory issue
- [vercel/next.js #78069](https://github.com/vercel/next.js/issues/78069) — 路由越多内存越高
- [vercel/next.js #70178](https://github.com/vercel/next.js/discussions/70178) — 从 Next.js 12.x 开始就有此问题

### 5.3 术语说明

| 术语 | 说明 |
|------|------|
| Turbopack | Next.js 的 Rust 编写的增量打包工具 |
| DooD | Docker-out-of-Docker，在容器内通过挂载宿主机的 Docker socket 调用 Docker daemon |
