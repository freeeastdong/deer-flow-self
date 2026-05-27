# Phase 1.3 — 创建共享数据目录并修改 docker-compose

## 做了什么
1. 在项目根目录创建 `data/` 目录（宿主机持久化目录）
2. 修改 `docker/docker-compose-dev.yaml` 和 `docker/docker-compose.yaml`，给 frontend 和 gateway 都挂载 `../data:/app/data`
3. 使用 better-auth CLI 生成/迁移数据库表结构

## 执行的命令

### 步骤 1：创建目录
```powershell
mkdir -p data
```

### 步骤 2：修改 docker-compose
在两个 compose 文件的 `frontend` 和 `gateway` 服务的 `volumes` 段落各添加：
```yaml
- ../data:/app/data
```

**注意**：修改 docker-compose 后必须重建容器才能让新挂载生效：
```powershell
$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d --force-recreate frontend gateway
```

### 步骤 3：运行迁移
在容器内执行迁移（推荐，避免宿主机环境差异）：
```powershell
$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d --force-recreate frontend

# 执行迁移（需指定配置文件路径，因为项目使用 config.ts 而非默认的 auth.ts）
docker exec -it deer-flow-frontend sh -c "cd /app/frontend && npx @better-auth/cli migrate --config src/server/better-auth/config.ts"
```

输入 `y` 确认后，迁移完成。

## 遇到的问题及解决

### 问题 1：迁移命令找不到配置文件
报错：
```
No configuration file found. Add a `auth.ts` file to your project or pass the path to the configuration file using the `--config` flag.
```

**原因**：better-auth CLI 默认查找当前目录下的 `auth.ts`，但项目实际配置文件是 `src/server/better-auth/config.ts`。

**解决**：在迁移命令后加上 `--config` 参数：
```bash
npx @better-auth/cli migrate --config src/server/better-auth/config.ts
```

### 问题 2：better-sqlite3 原生模块未编译
在首次执行迁移时报 `Could not locate the bindings file`，详见 [phase-1-1.md](phase-1-1.md)。

**解决**：在容器内手动触发编译：
```bash
docker exec -it deer-flow-frontend sh
cd /app/frontend/node_modules/.pnpm/better-sqlite3@12.9.0/node_modules/better-sqlite3
npm run install
```

编译成功后 `build/Release/better_sqlite3.node` 生成，再次执行迁移即可。

## 验证结果
- 宿主机出现 `data/auth.db` 文件（大小约 57KB）
- 容器内 `/app/data/auth.db` 可正常访问
- 数据库包含 `user`、`session`、`account`、`verification` 四张表
