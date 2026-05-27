# Phase 1.2 — 配置 better-auth 使用 SQLite（Docker 路径）

## 做了什么
修改 better-auth 配置文件，指定数据库文件路径为 Docker 容器内共享路径。

## 涉及文件
- `frontend/src/server/better-auth/config.ts`

## 配置内容
```ts
import { betterAuth } from "better-auth";
import Database from "better-sqlite3";

export const auth = betterAuth({
  database: new Database("/app/data/auth.db"), // Docker 容器内共享路径
  emailAndPassword: {
    enabled: true,
  },
});

export type Session = typeof auth.$Infer.Session;
```

## 关键点
- `/app/data/auth.db` 是容器内的绝对路径
- 通过 docker-compose Volume 挂载，宿主机对应 `./data/auth.db`
- 后端 FastAPI 也会通过同一个挂载点读取这个数据库文件

## 验证结果
- 配置文件已保存，路径正确指向容器内共享路径
- 无报错
