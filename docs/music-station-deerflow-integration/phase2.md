# Phase 2: 用户接口适配 + 诊断端点

## 目标
1. 修改 `/login` 和 `/me` 接口支持 DeerFlow session cookie 自动登录
2. 添加 `/health/deerflow` 诊断端点验证连通性
3. 验证音乐电台后端 ↔ DeerFlow Gateway 网络连通

## 修改文件

### `music-station/backend/app/api/users.py`
- `/login` 接口：优先从 request cookie 读取 DeerFlow session，自动登录并返回 token
- `/me` 接口：优先从 DeerFlow session 获取用户，fallback 到本地第一个用户
- 如果 DeerFlow 用户不存在于本地数据库，自动创建映射记录

### `music-station/backend/app/main.py`
- 新增 `GET /health/deerflow` 诊断端点
- 调用 DeerFlow Gateway `/health` 验证连通性
- 返回 `{"status": "connected|degraded|disconnected", ...}`

## 验证结果

```bash
$ wget -qO- http://music-station-backend:8000/health/deerflow
{
  "status": "connected",
  "deerflow_url": "http://deer-flow-gateway:8001",
  "deerflow_health": {
    "status": "healthy",
    "service": "deer-flow-gateway"
  }
}
```

✅ 音乐电台后端 ↔ DeerFlow Gateway 连通正常

## 待办（Phase 3）
- 浏览器端验证：iframe 内 agent 聊天时是否注入 DeerFlow memory
- 浏览器端验证：聊天后 memory 是否正确回写
- 废弃音乐电台前端登录界面
