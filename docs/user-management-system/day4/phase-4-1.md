# Phase 4.1 — 后端安装必要依赖（Docker 环境下）

## 目标

为后端 Gateway 安装认证相关的 Python 依赖，为后续 Session 验证做准备。

## 执行步骤

### 1. 安装 pyjwt

```bash
cd backend
uv add pyjwt
```

执行后 `pyproject.toml` 新增：
```toml
"pyjwt>=2.12.0",
```

`uv.lock` 同步更新了 pyjwt 的解析锁定（共 8 处关联条目）。

### 2. 确认 sqlite3 可用

Python 3.12 标准库自带 `sqlite3`，**无需额外安装**。

### 3. Docker 容器同步

由于后端使用 Docker 部署，依赖更新后需要重启 gateway 容器才能生效：

```powershell
$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml restart gateway
```

容器启动时会自动执行 `uv sync`，将宿主机 `pyproject.toml`/`uv.lock` 的变更同步到容器内的 `.venv`。

## 验证

- `pyproject.toml` 中出现 `"pyjwt>=2.12.0"` ✅
- `uv.lock` 中出现 pyjwt 锁定条目 ✅

## 遇到的问题

无。
