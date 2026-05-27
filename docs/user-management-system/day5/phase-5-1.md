# Phase 5.1 — 扩展 better-auth 用户表字段

## 目标

在 better-auth 配置中给 `user` 表增加 `nickname`、`avatar` 和 `role` 字段，为后续的用户资料页和角色权限系统做准备。

## 涉及文件

- `frontend/src/server/better-auth/config.ts`

## 实现内容

### 修改 better-auth 配置

在 `config.ts` 的 `betterAuth` 配置中新增 `user.additionalFields`：

```typescript
export const auth = betterAuth({
  database: new Database("/app/data/auth.db"),
  emailAndPassword: {
    enabled: true,
  },
  user: {
    additionalFields: {
      nickname: {
        type: "string",
        required: false,
        defaultValue: "",
      },
      avatar: {
        type: "string",
        required: false,
        defaultValue: "",
      },
      role: {
        type: "string",
        required: false,
        defaultValue: "user",
        input: false, // 用户注册时不能自己选角色
      },
    },
  },
});
```

**字段说明**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `nickname` | string | 否 | `""` | 用户昵称，资料页展示用 |
| `avatar` | string | 否 | `""` | 头像 URL，暂用文字占位 |
| `role` | string | 否 | `"user"` | 用户角色，`input: false` 表示注册时不可自选 |

> `role` 字段虽然主要在 Day 6 使用，但在这里一并添加可以避免后续再执行一次迁移。

---

## 验证

### 步骤 1：运行数据库迁移

先进入 frontend 容器，再执行迁移命令：

```bash
docker exec -it deer-flow-frontend sh
```

进入容器后：

```bash
cd /app/frontend
npx @better-auth/cli migrate --config src/server/better-auth/config.ts
```

> 如果容器名不同，先在宿主机确认容器名：`docker ps --format "table {{.Names}}\t{{.Status}}"`

完成后输入 `exit` 退出容器。

### 步骤 2：确认数据库表结构

进入 frontend 容器：

```bash
docker exec -it deer-flow-frontend sh
```

在容器内查看 `user` 表结构：

```bash
sqlite3 /app/data/auth.db '.schema user'
```

完成后输入 `exit` 退出容器。

**预期输出**（节选）应包含 `nickname`、`avatar`、`role` 三个字段：

```sql
CREATE TABLE "user" (
  "id" text NOT NULL PRIMARY KEY,
  "name" text NOT NULL,
  "email" text NOT NULL,
  "emailVerified" integer NOT NULL,
  "image" text,
  "createdAt" date NOT NULL,
  "updatedAt" date NOT NULL,
  "nickname" text,
  "avatar" text,
  "role" text
);
```

### 步骤 3：确认已有用户的默认值

进入 frontend 容器：

```bash
docker exec -it deer-flow-frontend sh
```

在容器内查询：

```bash
sqlite3 /app/data/auth.db 'SELECT id, email, nickname, avatar, role FROM user LIMIT 3;'
```

完成后输入 `exit` 退出容器。

**预期结果**：已有用户的 `nickname` 和 `avatar` 为空字符串，`role` 为 `"user"`。

### 步骤 4：重启前端容器使配置生效

```bash
$env:HOME = $env:USERPROFILE; docker-compose -f docker/docker-compose-dev.yaml restart frontend
```

> 修改了 better-auth 配置文件，需要重启容器让 Next.js 重新加载配置。

---

## 遇到的问题

无。
