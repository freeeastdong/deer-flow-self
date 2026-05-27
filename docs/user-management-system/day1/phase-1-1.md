# Phase 1.1 — 安装 SQLite 驱动

## 做了什么
给前端（Next.js）安装 `better-sqlite3`，这是 better-auth 推荐的 SQLite 驱动。

## 执行的命令
```powershell
cd frontend
pnpm add better-sqlite3
pnpm add -D @types/better-sqlite3
```

## 遇到的问题及解决

### 问题 1：容器内 better-sqlite3 编译失败
在后续执行迁移时发现容器内缺少 `better_sqlite3.node` 原生绑定文件，报错：
```
Could not locate the bindings file. Tried:
→ .../build/Release/better_sqlite3.node
```

**原因**：`node:22-alpine` 镜像缺少 C++ 编译工具（`python3`、`make`、`g++`），导致 `better-sqlite3` 在安装时无法编译原生扩展。

**解决**：修改 `frontend/Dockerfile`，在 `base` 阶段添加 Alpine 构建依赖：
```dockerfile
RUN apk add --no-cache python3 make g++
```

然后重新构建前端镜像：
```powershell
$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d --build frontend
```

## 验证结果
- `frontend/package.json` 中已出现 `better-sqlite3` 和 `@types/better-sqlite3` 依赖
- 容器内 `better-sqlite3` 的 `build/Release/better_sqlite3.node` 已正确生成
