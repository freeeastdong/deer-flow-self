# Phase 4.4 — 切换 nginx 到 Gateway 模式（对话隔离前置）

## 目标

修改环境变量，让 nginx 将 `/api/langgraph/*` 全部转发到 FastAPI gateway，而不是独立的 LangGraph Server。这样 gateway 才能对所有对话 API 做用户鉴权，前端代码无需任何改动。

## 涉及文件

- 项目根目录 `.env`
- `docker/docker-compose-dev.yaml`（只读参考，未修改）

## 关键发现：docker-compose 的 `.env` 加载行为

在执行过程中发现一个部署细节：**docker-compose 默认从 `docker-compose.yaml` 所在目录查找 `.env` 文件**，而非当前工作目录。

本项目 `docker-compose-dev.yaml` 位于 `docker/` 子目录，因此仅修改项目根目录的 `.env` 不会自动被 docker-compose 加载。解决方式：在启动容器前**显式导出**这两个环境变量到 PowerShell 会话中。

## 执行步骤

### 1. 在 `.env` 中声明变量（文档化 + 供其他工具读取）

项目根目录 `.env` 追加：

```env
LANGGRAPH_UPSTREAM=gateway:8001
LANGGRAPH_REWRITE=/api/
```

### 2. 显式导出环境变量并重建 nginx

```powershell
$env:LANGGRAPH_UPSTREAM = 'gateway:8001'
$env:LANGGRAPH_REWRITE = '/api/'
$env:HOME = $env:USERPROFILE
docker-compose -f docker/docker-compose-dev.yaml up -d --force-recreate nginx
```

### 3. nginx 配置生效原理

`docker-compose-dev.yaml` 中 nginx 服务的启动命令使用 `envsubst` 将环境变量注入模板：

```yaml
command:
  - sh
  - -c
  - |
    envsubst '$$LANGGRAPH_UPSTREAM $$LANGGRAPH_REWRITE' \
      < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
    exec nginx -g 'daemon off;'
```

生效后的关键配置：

```nginx
upstream langgraph {
    server gateway:8001;          # ← 原为 langgraph:2024
}

location /api/langgraph/ {
    rewrite ^/api/langgraph/(.*) /api/$1 break;   # ← 原为 /$1
    proxy_pass http://langgraph;
    ...
}
```

路由映射示例：

| 原始请求 | rewrite 后 | 目标 |
|----------|-----------|------|
| `/api/langgraph/threads/search` | `/api/threads/search` | gateway:8001 |
| `/api/langgraph/threads/{id}/runs/stream` | `/api/threads/{id}/runs/stream` | gateway:8001 |
| `/api/langgraph/assistants/search` | `/api/assistants/search` | gateway:8001 |

## 验证

### 验证 1：nginx 容器内环境变量

```bash
docker exec deer-flow-nginx env | grep LANGGRAPH
```

输出：
```
LANGGRAPH_REWRITE=/api/
LANGGRAPH_UPSTREAM=gateway:8001
```

✅ 环境变量正确传入容器。

### 验证 2：nginx 配置文件内容

```bash
docker exec deer-flow-nginx sh -c "grep -A2 'upstream langgraph' /etc/nginx/nginx.conf"
```

输出：
```nginx
upstream langgraph {
    server gateway:8001;
}
```

✅ upstream 已指向 gateway。

### 验证 3：API 连通性测试

| 端点 | 状态码 | 说明 |
|------|--------|------|
| `GET /api/models` | 200 | gateway 原生端点，确认 gateway 运行正常 |
| `POST /api/langgraph/threads/search` | 200 | rewrite 后到达 gateway，确认路由切换生效 |
| `POST /api/langgraph/assistants/search` | 200 | rewrite 后到达 gateway，确认 assistant API 可用 |

✅ 所有关键端点均通过 gateway 正确响应。

## 已知问题提醒

1. **Gateway 模式为 experimental**：社区 issues #1513（dev watcher 因 sandbox 文件变化无限重启）、#1516/#1837（nginx DNS 缓存策略调整）都与 gateway 模式相关。如遇异常优先检查 nginx 日志。
2. **某些 LangGraph Platform 特有端点可能 404**：如果切换到 gateway mode 后发现某些端点返回 404，说明 gateway 尚未实现该 stub，请在对应 router 中补充最小实现，或临时切回标准模式排查。

## 遇到的问题

### 问题：修改 `.env` 后 nginx 配置未生效

**现象**：直接在 `.env` 中添加 `LANGGRAPH_UPSTREAM` 和 `LANGGRAPH_REWRITE` 后重启容器，nginx 容器内环境变量仍然是默认值（`langgraph:2024` 和 `/`）。

**原因**：docker-compose 默认从 compose file 所在目录（`docker/`）查找 `.env`，而非当前工作目录（项目根目录）。

**解决**：在 PowerShell 中显式导出这两个环境变量后再执行 `docker-compose up`：

```powershell
$env:LANGGRAPH_UPSTREAM = 'gateway:8001'
$env:LANGGRAPH_REWRITE = '/api/'
```

这样既确保了容器能正确接收变量，也在 `.env` 中保留了配置文档化。
