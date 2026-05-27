# DeerFlow 用户管理系统小白指南

> 本文用**生活化的比喻** + **实际代码**讲解 `deer-flow-0502` 用户管理系统的 7 个核心设计点。
>
> 阅读前，先建立一个基本场景：
> **DeerFlow 是一个高级私人会所，每个用户是会员。会员要存东西（对话记录、文件、记忆），要进不同的房间（功能模块）。系统就是会所的安保+管家体系。**

---

## 第1点：JWT Cookie 认证
### （会员进门时的"门禁卡"系统）

### 生活中的例子

你去健身房办卡，前台给你一张**会员卡**。以后每次去，刷卡就能进，不用每次都填表报名。

但这里有个问题：卡丢了怎么办？别人捡到你的卡就能进去吗？

DeerFlow 的解决方案是：
- 不发实体卡，发**电子卡（Cookie）**
- 电子卡里不写你的真实姓名，写一串**加密密码（JWT）**
- 电子卡有效期7天，过期要重新登录

### 技术原理：JWT 是什么？

JWT（JSON Web Token）就像一个**防伪信封**，里面装着三样东西：

```
信封正面（Header）:  "我用 HS256 算法加密"
信封内容（Payload）: "会员ID: abc-123, 有效期到: 2026-05-09, 版本号: 0"
封条（Signature）:   用只有服务器知道的密钥生成的防伪码
```

**关键点**：封条是用**服务器的密钥**做的。黑客可以伪造信封内容，但做不了封条——因为不知道密钥。

### 在代码里怎么用？

**文件**：`backend/app/gateway/auth/jwt.py`

```python
# 1. 登录成功时，服务器给你"制卡"
def create_access_token(user_id: str, token_version: int = 0) -> str:
    payload = {
        "sub": user_id,           # sub = 这张卡属于谁（会员ID）
        "exp": 现在 + 7天,        # exp = 什么时候过期
        "iat": 现在,              # iat = 什么时候发的
        "ver": token_version      # ver = 卡的版本号（后面讲为什么重要）
    }
    return jwt.encode(payload, "服务器的秘密密钥", algorithm="HS256")
    # 结果：一串看起来像乱码的字符串 eyJhbGciOiJIUzI1NiIs...
```

```python
# 2. 你带着卡来访问时，服务器"验卡"
def decode_token(token: str):
    try:
        payload = jwt.decode(token, "服务器的秘密密钥", algorithms=["HS256"])
        return TokenPayload(**payload)  # 验卡成功，知道你是谁
    except jwt.ExpiredSignatureError:
        return TokenError.EXPIRED      # 卡过期了
    except jwt.InvalidSignatureError:
        return TokenError.INVALID_SIGNATURE  # 假卡！封条对不上
```

### Cookie 是什么意思？

Cookie 就是浏览器帮你**自动保管**这张卡的地方。你登录后，服务器说："把这张卡放你浏览器的 Cookie 盒子里，以后每次来都自动带上。"

**文件**：`backend/app/gateway/routers/auth.py`

```python
# 登录成功时，服务器把 JWT 放进 Cookie 发给你
response.set_cookie(
    key="access_token",      # Cookie 的名字
    value=token,             # 就是刚才生成的 JWT 字符串
    httponly=True,           # 重要！防止黑客用 JavaScript 偷走
    secure=True,             # 只用 HTTPS 传输，防止被窃听
    max_age=7*24*3600        # 7天有效期
)
```

**`httponly=True` 超级重要**：就像你的卡放在**防磁套**里，网页上的坏脚本（XSS攻击）摸不到它。

---

## 第2点：bcrypt 密码哈希
### （会员密码的"碎纸机"存储法）

### 生活中的例子

你在会所设了一个密码"123456"。如果前台把小纸条"密码：123456"贴在墙上，任何经过的人都能看到——太危险了！

正确的做法是：把密码放进**碎纸机**，只保存**纸屑**。下次你来，你说"123456"，前台也把它放进同一台碎纸机，比较两次的纸屑是否一样。一样就通过。

**即使黑客偷走了纸屑，也无法拼回原来的密码。**

### 技术原理：什么是 bcrypt？

bcrypt 是世界上最常用的**密码碎纸机**。

但有个小问题：bcrypt 有个"隐藏bug"——它最多只处理72字节。如果你的密码很长，超出的部分会被**静默忽略**！

比如密码是 `"我爱编程我爱编程我爱编程..."`（100个字），bcrypt 只取前72字节。黑客如果知道这一点，可以尝试更短的版本。

### DeerFlow 的解决方案（`$dfv2$` 版本）

```python
# 步骤1：先给密码"套个固定长度的壳"
sha256_hash = hashlib.sha256(password.encode()).hexdigest()  # 变成64个字符的固定长度
# 步骤2：再送进 bcrypt
bcrypt_hash = bcrypt.hashpw(sha256_hash.encode(), bcrypt.gensalt())
# 最终存储：$dfv2$ + bcrypt_hash
```

**为什么要先 SHA-256？**
- SHA-256 把任意长度的密码变成**固定64字符**
- 再喂给 bcrypt，彻底避开72字节截断问题

### 在代码里怎么用？

**文件**：`backend/app/gateway/auth/password.py`

```python
# 注册时：把明文密码变成"纸屑"
async def hash_password_async(password: str) -> str:
    # v2 版本：SHA-256 预处理 + bcrypt
    sha256_hash = hashlib.sha256(password.encode()).hexdigest()
    bcrypt_hash = await asyncio.to_thread(bcrypt.hashpw, sha256_hash.encode(), bcrypt.gensalt())
    return f"$dfv2${bcrypt_hash.decode()}"  # 标记这是 v2 版本

# 登录时：验证用户输入的密码是否匹配
async def verify_password_async(password: str, hash: str) -> bool:
    if hash.startswith("$dfv2$"):
        sha256_hash = hashlib.sha256(password.encode()).hexdigest()
        return bcrypt.checkpw(sha256_hash.encode(), hash[6:].encode())
    elif hash.startswith("$dfv1$"):
        # 兼容旧版本
        ...
    else:
        # 兼容更旧的 bare bcrypt
        ...
```

### `token_version` 的巧妙设计（和JWT联动）

假设你怀疑密码泄露了，改了新密码。服务器会把数据库里你的 `token_version` 从 `0` 变成 `1`。

但黑客如果已经偷走了你旧的 JWT（卡），那张卡里写的是 `"ver": 0`。服务器一比对：`0 != 1`，直接拒绝！

**文件**：`backend/app/gateway/deps.py`

```python
# 验卡时检查版本号
if user.token_version != payload.ver:  # payload.ver 是卡上的版本
    raise HTTPException(401, "Token revoked (password changed)")
```

这就像你换了锁，旧钥匙立刻失效——**即使小偷复制了钥匙也没用**。

---

## 第3点：ContextVar + AUTO Sentinel
### （隐形的"会员身份手环"）

### 生活中的例子

想象会所给每个会员发一个**隐形的身份手环**。你一进大门，手环就自动激活。之后你去餐厅、健身房、储物柜，所有服务员都能"感应"到你的身份，自动为你服务。

你不需要每次都掏会员卡说"我是张三"。手环在后台默默传递你的身份。

当你离开会所（请求结束），手环自动失效。

### 技术原理：ContextVar 是什么？

在计算机里，服务器要**同时服务很多用户**（并发请求）。问题来了：我怎么知道**当前这行代码**是在为**哪个用户**执行？

传统方法是：把用户ID从函数A传给函数B，再传给函数C，再传给函数D……每层都要传，非常烦。

**ContextVar 是 Python 的"魔法手环"**：
- 它是**任务级别**的——每个用户的请求是一个独立任务
- 设置一次，**之后所有代码都能读取**
- 不用一层层传递参数

```python
from contextvars import ContextVar

# 创建一个"全局手环"
_current_user = ContextVar("deerflow_current_user", default=None)

# 中间件：用户进门时戴上手环
set_current_user(user)  # 手环激活

# 任意深层代码：感应手环
user = _current_user.get()  # 知道当前是谁
```

**asyncio 的妙处**：每个 HTTP 请求在 Python 里是一个 async 任务，ContextVar 自动**按任务隔离**。用户A的手环不会影响用户B。

### AUTO Sentinel 是什么？

这是 DeerFlow 最精妙的设计。想象你是仓库管理员，每次出库都要写"领用人"。

有三种情况：
1. **正常情况**：不写领用人，自动看手环知道是谁 → **`AUTO`**
2. **特殊情况**：明确写"这是给张三的" → **显式字符串**
3. **管理员盘点**：不用管是谁的，全部显示 → **`None`**

**文件**：`backend/packages/harness/deerflow/runtime/user_context.py`

```python
# AUTO 是一个单例哨兵对象，意思是"从手环自动读取"
AUTO = _AutoSentinel()

def resolve_user_id(value):
    if isinstance(value, _AutoSentinel):  # 如果是 AUTO
        user = _current_user.get()        # 读手环
        if user is None:
            raise RuntimeError("没戴手环就进仓库了！")
        return str(user.id)               # 返回当前用户ID
    return value                          # 否则直接用传入的值
```

### 使用示例

```python
# 路由层：创建线程，不指定 user_id，自动用手环
thread_store.create(thread_id="abc", user_id=AUTO)
# 实际变成：thread_store.create(thread_id="abc", user_id="用户123")

# 管理员后台：显式查询某个用户
thread_store.search(user_id="用户456")

# 数据迁移脚本： bypass 隔离，看全部
thread_store.list_all(user_id=None)
```

---

## 第4点：Repository 层默认过滤
### （仓库的"自动分拣员"）

### 生活中的例子

会所的仓库有很多储物柜。没有隔离时，任何人说"打开3号柜"就能打开——危险！

有了隔离后，仓库里有个**自动分拣员**。你说"打开3号柜"，他会先看你的隐形手环，然后只在你**自己的柜子区域**里找3号柜。如果3号柜不是你的，他会说"找不到"（而不是"这不是你的"——防止你探查别人有什么）。

### 在代码里怎么实现？

**文件**：`backend/packages/harness/deerflow/persistence/thread_meta/sql.py`

```python
class ThreadMetaRepository:
    async def get(self, thread_id: str, *, user_id: str | None | _AutoSentinel = AUTO):
        resolved = resolve_user_id(user_id)  # AUTO → 从手环读当前用户ID
        
        # SQL 查询：只查属于当前用户的记录
        query = select(ThreadMetaRow).where(
            ThreadMetaRow.thread_id == thread_id,
            ThreadMetaRow.user_id == resolved  # ← 自动加上的过滤条件
        )
        row = await session.execute(query)
        ...
    
    async def search(self, filter_dict, *, user_id: str | None | _AutoSentinel = AUTO):
        resolved = resolve_user_id(user_id)
        
        query = select(ThreadMetaRow)
        if resolved is not None:  # 如果 resolved 是用户ID（不是 None）
            query = query.where(ThreadMetaRow.user_id == resolved)  # 只搜自己的
        
        # 再叠加其他过滤条件
        ...
```

**关键是默认值 `= AUTO`**：
- 如果程序员忘了传 `user_id`，不会变成"查全部"，而是自动变成"查当前用户的"
- 只有**明确写 `user_id=None`** 才能 bypass（用于管理后台、迁移脚本）

### 同样的模式用在所有数据层

| 数据层 | 隔离方式 |
|--------|---------|
| ThreadMetaRepository.get() | WHERE user_id = ? |
| RunRepository.put() | 插入时写入 user_id |
| DbRunEventStore.list_messages() | WHERE user_id = ? |
| FeedbackRepository.create() | 写入时绑定 user_id |

这就是**防御性编程**：即使某个路由的开发者忘记加权限检查，数据层也会**自动隔离**，防止数据泄露。

---

## 第5点：文件系统目录隔离
### （每人一个独立的"储物间"）

### 生活中的例子

以前会所只有一个大储物室，所有人的东西都混在一起。现在会所给每个会员分配了**独立的储物间**：

```
会所仓库/
  ├── users/
  │    ├── 会员A/           ← 会员A的所有东西
  │    │    ├── memory.json      （个人记忆）
  │    │    └── threads/
  │    │         ├── thread-1/
  │    │         │    └── user-data/
  │    │         │         ├── uploads/    （上传的文件）
  │    │         │         ├── outputs/    （生成的结果）
  │    │         │         └── workspace/  （工作空间）
  │    │         └── thread-2/
  │    └── 会员B/           ← 会员B的所有东西
  │         └── ...
```

会员A永远看不到 `users/会员B/` 里的内容。

### 在代码里怎么实现？

**文件**：`backend/packages/harness/deerflow/config/paths.py`

```python
class Paths:
    def user_dir(self, user_id: str) -> Path:
        return self.base_dir / "users" / user_id  # base_dir/users/会员ID/
    
    def thread_dir(self, thread_id: str, *, user_id: str | None = None) -> Path:
        if user_id:
            return self.user_dir(user_id) / "threads" / thread_id
        else:
            return self.base_dir / "threads" / thread_id  # 遗留兼容
    
    def sandbox_uploads_dir(self, thread_id: str, user_id: str) -> Path:
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "uploads"
    
    def sandbox_outputs_dir(self, thread_id: str, user_id: str) -> Path:
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "outputs"
```

**文件**：`backend/packages/harness/deerflow/uploads/manager.py`

```python
def get_uploads_dir(thread_id: str) -> Path:
    user_id = get_effective_user_id()  # 从"手环"读取当前用户
    return get_paths().sandbox_uploads_dir(thread_id, user_id)
    # 结果：users/当前用户/threads/thread-id/user-data/uploads/
```

### 记忆文件隔离

```python
# 文件：backend/packages/harness/deerflow/agents/memory/storage.py
def _get_memory_file_path(self, user_id: str | None):
    if user_id:
        return f"{base_dir}/users/{user_id}/memory.json"
    else:
        return f"{base_dir}/memory.json"  # 没用户时的默认位置
```

每个用户的记忆是**独立的文件**，不会互相污染。A用户教AI喜欢红色，B用户教AI喜欢蓝色，两家互不影响。

---

## 第6点：RBAC 权限控制
### （会所的"会员等级制度"）

### 生活中的例子

会所有两种会员：
- **普通会员（user）**：能用自己的储物柜、自己的对话记录
- **管理员（admin）**：能查看所有会员的信息、管理系统

你不能让普通会员进管理员办公室。所以需要**角色-权限**检查。

### 在代码里怎么实现？

**文件**：`backend/app/gateway/authz.py`

```python
# 定义权限常量
class Permissions:
    THREADS_READ = "threads:read"      # 查看对话
    THREADS_WRITE = "threads:write"    # 创建对话
    THREADS_DELETE = "threads:delete"  # 删除对话
    RUNS_CREATE = "runs:create"        # 运行AI
    RUNS_READ = "runs:read"            # 查看运行结果

# 上下文对象：封装"你是谁+你能做什么"
class AuthContext:
    def __init__(self, user, permissions):
        self.user = user
        self.permissions = permissions
    
    def has_permission(self, resource, action):
        return f"{resource}:{action}" in self.permissions

# 目前所有登录用户都拥有全部基础权限
_ALL_PERMISSIONS = [THREADS_READ, THREADS_WRITE, THREADS_DELETE, RUNS_CREATE, RUNS_READ, RUNS_CANCEL]
```

### 使用装饰器保护路由

```python
# 文件：backend/app/gateway/routers/threads.py

@router.get("/{thread_id}")
@require_auth                    # 第1道门：必须先登录（有手环）
@require_permission("threads", "read", owner_check=True)  # 第2道门：必须拥有这个对话
async def get_thread(thread_id: str, request: Request):
    ...
```

### `owner_check=True` 是什么意思？

这是更细粒度的检查：你虽然有 `threads:read` 权限（所有会员都有），但这个**具体的对话**必须是你创建的。

```python
# require_permission 内部逻辑：
if owner_check:
    # 去数据库查：这个 thread_id 的 user_id 是不是当前用户？
    allowed = await thread_store.check_access(thread_id, str(auth.user.id))
    if not allowed:
        raise HTTPException(status_code=404, detail="Thread not found")
        # 注意是404不是403！故意隐藏"这个对话存在但不属于你"的信息
```

### 管理员路由

```python
# 文件：backend/app/gateway/routers/admin.py

async def require_admin(request, user=Depends(get_current_user_from_request)):
    if user.system_role != "admin":  # 检查角色
        raise HTTPException(403, "您没有管理员权限")  # 403 = 知道你是谁，但你不配

@router.get("/users")
async def list_users(request, _: None = Depends(require_admin)):
    # 只有 admin 能执行到这里
    return [所有用户信息...]
```

### 为什么管理员查用户返回403，而查别人对话返回404？

- **403**：你知道这个房间存在，但你不被允许进（管理员接口明确告诉你没权限）
- **404**：你根本不知道这个对话是否存在（防止恶意用户遍历猜测别人的对话ID）

这是**安全设计的重要细节**。

---

## 第7点：Fail-Closed 安全设计
### （"默认锁门"原则）

### 生活中的例子

有两种安保哲学：
- **Fail-Open（故障开放）**：停电了，所有门自动打开——方便但危险
- **Fail-Closed（故障关闭）**：停电了，所有门自动锁死——不方便但安全

DeerFlow 选择 **Fail-Closed**：**只要我不确定你是谁，就拒绝你。**

### 在代码里怎么体现？

**文件**：`backend/app/gateway/auth_middleware.py`

```python
class AuthMiddleware:
    async def dispatch(self, request, call_next):
        # 1. 检查是不是公开路径（登录页、注册页、健康检查）
        if _is_public(request.url.path):
            return await call_next(request)  # 公开路径直接放行
        
        # 2. 非公开路径：必须有 Cookie
        if not request.cookies.get("access_token"):
            return JSONResponse(status_code=401, detail="没卡不能进")
        
        # 3. 有Cookie还不够，必须能验明正身
        try:
            user = await get_current_user_from_request(request)
        except HTTPException:
            return JSONResponse(status_code=401, detail="假卡或过期卡")
        
        # 4. 验明正身后，戴上"手环"
        request.state.user = user
        request.state.auth = AuthContext(user=user, permissions=_ALL_PERMISSIONS)
        set_current_user(user)
        
        try:
            return await call_next(request)  # 放行去执行业务
        finally:
            reset_current_user(token)  # 请求结束，摘下手环
```

### Fail-Closed 体现在哪里？

| 情况 | Fail-Open 的行为 | Fail-Closed 的行为 |
|------|----------------|------------------|
| 没有 Cookie | 让你进（匿名访问） | **401 拒绝** |
| Cookie 是乱填的字符串 | 可能让你进 | **401 拒绝** |
| JWT 过期了 | 可能缓存旧身份 | **401 拒绝** |
| 用户被删除了但 Cookie 还在 | 可能让你进 | **401 拒绝**（查数据库验证） |
| token_version 不匹配 | 可能让你进 | **401 拒绝**（密码改了，旧卡失效） |

**文件**：`backend/app/gateway/authz.py` 里的 `require_auth` 是**第二道保险**：

```python
def require_auth(func):
    async def wrapper(*args, **kwargs):
        request = kwargs.get("request")
        
        # 即使中间件失效了，这里再验一次
        auth_context = await _authenticate(request)
        if not auth_context.is_authenticated:
            raise HTTPException(401, "Authentication required")
        
        return await func(*args, **kwargs)
    return wrapper
```

这就像会所的大门有**两道锁**：
1. 大门保安（Middleware）先看卡
2. 房间门口的保安（`@require_auth`）再看一次卡

哪怕大门保安睡着了（中间件被意外禁用），房间门口的保安仍然会拦人。

---

## 总结：7个点串起来看

```
用户打开网页
    ↓
输入邮箱密码登录
    ↓
[第2点] 密码用 bcrypt（碎纸机）比对
    ↓
[第1点] 服务器生成 JWT（防伪信封），放进 Cookie（浏览器自动保管）
    ↓
用户点击"新建对话"
    ↓
[第7点] AuthMiddleware 检查：有Cookie吗？JWT有效吗？用户存在吗？
         → 任何一步失败 = 401 拒绝（Fail-Closed）
    ↓
[第3点] 验证通过后，set_current_user() 戴上"隐形手环"
    ↓
[第6点] @require_permission("threads", "write", owner_check=True)
         检查：你有创建权限吗？（有，所有登录用户都有）
    ↓
[第4点] thread_store.create(thread_id, user_id=AUTO)
         AUTO → resolve_user_id() 从"手环"读取用户ID
         SQL 执行：INSERT INTO threads_meta (thread_id, user_id, ...)
                   VALUES ('abc', '用户123', ...)
    ↓
[第5点] 同时创建文件目录：users/用户123/threads/abc/user-data/
    ↓
用户上传文件
    ↓
文件被保存到：users/用户123/threads/abc/user-data/uploads/文件.pdf
    ↓
另一个用户登录，尝试访问同一个 thread_id
    ↓
[第4点] thread_store.get('abc', user_id=AUTO)
         → 解析为 user_id='用户456'
         → SQL：SELECT * FROM threads_meta WHERE thread_id='abc' AND user_id='用户456'
         → 查无结果 → 返回 None
    ↓
[第6点] require_permission 的 owner_check 发现没权限
         → 返回 404 "Thread not found"（隐藏真实原因）
```

这就是 DeerFlow-0502 用户管理系统的完整运作流程。

**核心设计思想：默认拒绝、自动隔离、多层防御、最小权限。**
