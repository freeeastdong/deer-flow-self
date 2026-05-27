# Phase 4 实施报告 — 废弃自建认证，复用 DeerFlow 单点登录

## 实施时间
2026-05-04

## 目标
废弃音乐电台自建 JWT 认证体系，完全复用 DeerFlow session cookie 实现无感知单点登录（SSO）。

## 实施内容

### 1. 后端认证强制化

#### `app/api/agent.py`
- `get_current_user_id` 移除 legacy JWT fallback 和默认用户 fallback
- 仅保留 DeerFlow cookie 认证路径，未登录时直接返回 **401**

```python
async def get_current_user_id(request: Request, db: AsyncSession = Depends(get_db)) -> int:
    """强制从 DeerFlow session cookie 解析用户。未登录直接 401。"""
    cookie = request.headers.get("cookie")
    df_user = await get_current_user_from_deerflow(cookie=cookie)
    if df_user and df_user.get("id"):
        # 同步/创建本地映射用户...
        return user.id
    raise HTTPException(status_code=401, detail="Unauthorized: DeerFlow session required")
```

#### `app/api/users.py`
- `/login` 废弃用户名密码校验，仅保留 DeerFlow cookie 自动登录逻辑
- `/me` 移除默认用户 fallback，无 DeerFlow session 时返回 **401**

### 2. 前端移除自建 Token 注入

#### `src/api/client.ts`
- 移除 `localStorage.getItem('token')` 及 `Authorization: Bearer <token>` header 注入
- 完全依赖 iframe 同源 cookie 自动透传

```typescript
// 修改前
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 修改后：完全依赖同源 cookie 自动携带
```

### 3. 前端源码同步前期修复

重新构建前端时，将之前对编译产物的手动修复同步回源码：
- `App.tsx`: `path="/"` → `path="*"`（支持 iframe 任意路径）
- `Home.tsx`: 默认背景路径 `/bg-default.jpg` → `/applications/music-station/bg.jpg`
- `Home.tsx`: `background: '#000000'` → `background: 'transparent'`
- `Home.tsx` + `VoiceAssistant.tsx`: 背景图片 localStorage 持久化

## 测试结果

### TC-1: 无 DeerFlow Session → 401

```
POST /api/v1/agent/chat (no cookie)
→ Status: 401
→ Body: {"detail":"Unauthorized: DeerFlow session required"}
```

✅ **通过**

---

### TC-2: 有效 DeerFlow Session → 200

```
POST /api/v1/agent/chat (with access_token cookie)
→ Status: 200
→ Reply: "你好呀！👋 欢迎来到小音的音乐电台！..."
```

Agent 正常回复，且能引用 DeerFlow memory 中的历史偏好。

✅ **通过**

---

### TC-3: `/me` 端点认证

| 条件 | 状态 | 响应 |
|------|------|------|
| 有 DeerFlow cookie | 200 | `{"id": 2, "username": "...", ...}` |
| 无 cookie | 401 | `{"detail":"DeerFlow session required"}` |

✅ **通过**

---

### TC-4: 前端产物验证

新构建的 JS 产物 `index-BNwqtn-M.js` 中不再包含 `localStorage.getItem('token')` 逻辑。

```bash
$ grep "localStorage.*token" index-BNwqtn-M.js
# 无输出 ✅
```

✅ **通过**

---

### TC-5: nginx 静态文件服务

```bash
$ wget -qO- http://frontend:3000/applications/music-station/index.html
→ 返回新的 index.html，引用新的 JS/CSS assets
```

✅ **通过**

## 架构变化

### Phase 4 前
```
用户 → DeerFlow 登录 → 进入音乐电台 → 前端 localStorage token → 
Authorization: Bearer <自建JWT> → 后端 fallback 验证 → 可能使用默认用户
```

### Phase 4 后
```
用户 → DeerFlow 登录（设置 access_token cookie）→ 进入音乐电台（iframe）→ 
cookie 自动透传 → 后端仅验证 DeerFlow session → 无登录态直接 401
```

## 用户感知变化

- **登录前**：打开音乐电台 iframe，Agent 聊天返回 "请先登录 DeerFlow"
- **登录后**：打开音乐电台 iframe，无需任何操作即可直接使用 Agent，且记忆互通

## 遗留说明

- `/login` 端点仍保留但不再校验用户名密码，仅作为 DeerFlow cookie 自动登录的桥梁
- 前端 `localStorage` 中可能残留旧 `token`，但不再被读取
- 数据库中的自建用户记录仍保留，作为 DeerFlow 用户的本地映射

## 结论

Phase 4 **实施完成** ✅

音乐电台已完全废弃自建认证，实现 DeerFlow 单点登录。未登录用户访问 API 会收到 401 提示，已登录用户无感知使用全部功能。
