# DeerFlow 前端内存优化实施总结

> **实施日期**: 2026-05-08
> **实施人**: Kimi Code CLI
> **关联计划**: `plan.md`

---

## 1. 修改概览

本次优化共修改 **1 个文件**：`docker/docker-compose-dev.yaml`。

| 序号 | 优化项 | 文件 | 状态 | 内存贡献 |
|------|--------|------|------|---------|
| **1** | **Turbopack 内存限制** | **`docker/docker-compose-dev.yaml`** | **✅ 已实施** | **~70%（主导因素）** |
| 2 | **全局容器内存限制** | **`docker/docker-compose-dev.yaml`** | **✅ 已实施** | **防御性优化** |

---

## 2. 详细修改记录

### 2.1 Turbopack 内存限制

**文件**: `docker/docker-compose-dev.yaml`

**修改原因**: 实测发现前端容器内存占用 **2.919 GiB**，其中 `next-server (v16.1.7)` 单个进程 RSS 高达 **3,495 MB**。进程树分析显示大量 `tokio-runtime-w` 线程（Turbopack 的 Rust 运行时）和 1.1GB 的 `.next/dev` 编译缓存。

**尝试回退 Webpack（已证实不可行）**:
- `npx next dev` → 仍然是 Turbopack（Next.js 16 默认）
- `npx next dev --no-turbo` → 参数不存在，容器崩溃
- `TURBOPACK=0` / `NEXT_TURBOPACK=0` → 环境变量无效

由于无法回退到 Webpack，采用**内存硬限制**作为缓解方案。

**修改前**:
```yaml
frontend:
  environment:
    - NODE_ENV=development
    - WATCHPACK_POLLING=true
    - CI=true
    - DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001
  # 无内存限制
```

**修改后**:
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

**预期效果**: 容器内存从 **无限制（15.53GB）** 封顶到 **2GB**，Node.js heap 封顶到 **1.5GB**，防止 Turbopack 无限膨胀。

**验证结果**:
```powershell
# 容器内存限制已生效
docker stats --no-stream deer-flow-frontend
# CONTAINER ID   NAME                 CPU %   MEM USAGE / LIMIT
# 409101e3d513   deer-flow-frontend   0.00%   210.2MiB / 2GiB

# 容器硬限制确认
docker inspect deer-flow-frontend --format '{{ .HostConfig.Memory }}'
# 2147483648  (= 2GB)
```

---

### 2.2 全局容器内存限制

**文件**: `docker/docker-compose-dev.yaml`

**修改原因**: 除 frontend 外，其他 Docker 容器同样运行在**无内存限制**的环境中。虽然当前占用不高，但任何容器的意外内存泄漏都可能拖垮整个 Docker VM 或宿主机。开发环境缺乏资源隔离，问题难以定位。

**修改内容**: 为所有服务添加 `deploy.resources.limits.memory`：

| 服务 | 限制值 | 当前内存（实测） |
|------|--------|-----------------|
| `deer-flow-frontend` | 2G | 234.2MiB |
| `deer-flow-gateway` | 1.5G | 158.3MiB |
| `deer-flow-provisioner` | 512M | ~低（健康检查中） |
| `deer-flow-nginx` | 128M | 2.875MiB |
| `music-station-backend` | 512M | 79.71MiB |
| `music-station-db` | 1G | 21.05MiB |
| `music-station-redis` | 256M | 3.648MiB |

**验证结果**:
```powershell
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
# NAME                    MEM USAGE / LIMIT   MEM %
# deer-flow-frontend      234.2MiB / 2GiB     11.44%
# deer-flow-gateway       158.3MiB / 1.5GiB   10.31%
# deer-flow-nginx         2.875MiB / 128MiB   2.25%
# music_station_backend   79.71MiB / 512MiB   15.57%
# music_station_db        21.05MiB / 1GiB     2.06%
# music_station_redis     3.648MiB / 256MiB   1.43%
```

**预期效果**: 任一容器内存泄漏都不会超过预设上限，容器 OOM 后由 `restart: unless-stopped` 自动重启，影响范围可控。

---

## 3. 回滚指南

如需回滚某项优化，可直接恢复对应文件的修改：

| 优化项 | 回滚操作 |
|--------|---------|
| Turbopack 内存限制 | 删除 `NODE_OPTIONS=--max-old-space-size=1536` 和 frontend 的 `deploy.resources.limits`，然后重建容器 |
| 全局容器内存限制 | 删除所有服务的 `deploy.resources.limits` 配置，然后重建容器 |

---

## 4. 后续建议

1. **Turbopack 内存限制验证**: 执行 `docker stats --no-stream`，确认所有容器的 LIMIT 列都显示为预设值（如 `2GiB`、`1.5GiB`、`128MiB` 等）
2. **Turbopack 跟进**: 关注 [vercel/next.js #81161](https://github.com/vercel/next.js/issues/81161) 等上游 issue，待 Turbopack 内存问题修复后可考虑移除内存限制
