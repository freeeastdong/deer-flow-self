# Phase 1.4 — 更新环境变量配置

## 做了什么
确保 `.env` 和 `.env.example` 包含认证所需的环境变量，并验证容器能正确加载。

## 涉及文件
- `frontend/.env`
- `frontend/.env.example`
- `docker/docker-compose-dev.yaml`
- `docker/docker-compose.yaml`

## 配置内容

### `frontend/.env`
```env
BETTER_AUTH_SECRET=VtneoJ0kSKPGjBOuc1F7QMUT6fixqYCD
BETTER_AUTH_URL=http://localhost:2026
```

**说明**：
- `BETTER_AUTH_SECRET`：用于加密 Session 和签名 Cookie，至少 32 位随机字符串
- `BETTER_AUTH_URL`：Docker 下走 nginx 统一入口，不是 `localhost:3000`

### `frontend/.env.example`
同步添加模板（供其他开发者参考，不含真实密钥）：
```env
# Better Auth configuration
# Required for authentication/session security.
# Generate a random string at least 32 characters long.
BETTER_AUTH_SECRET=your-super-secret-key-at-least-32-chars-long
BETTER_AUTH_URL=http://localhost:2026
```

## 遇到的问题及解决

### 问题 1：容器内读取不到环境变量
修改 `frontend/.env` 后，执行 `docker-compose restart frontend`，但容器内 `BETTER_AUTH_SECRET` 仍为空。

**原因**：`docker-compose restart` 只是重启同一个容器，不会重新读取 `env_file` 配置。必须重建容器才能让新的环境变量注入。

**解决**：使用 `--force-recreate` 重建容器：
```powershell
$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml up -d --force-recreate frontend
```

### 问题 2：Windows 下 `HOME` 环境变量未设置
执行 docker-compose 时报错：
```
required variable HOME is missing a value: HOME must be set
```

**原因**：`docker-compose-dev.yaml` 中使用了 `${HOME:?HOME must be set}` 来挂载 CLI 认证目录（`.claude`、`.codex`），但 Windows 默认没有 `HOME` 环境变量。

**解决**：执行 docker-compose 前先设置 `HOME`：
```powershell
$env:HOME = $env:USERPROFILE
```

## 验证结果
- `docker exec deer-flow-frontend sh -c 'echo "$BETTER_AUTH_SECRET"'` 正确输出密钥
- `docker exec deer-flow-frontend sh -c 'echo "$BETTER_AUTH_URL"'` 正确输出 `http://localhost:2026`
- 容器日志（`/app/logs/frontend.log`）无报错，Next.js 正常启动
