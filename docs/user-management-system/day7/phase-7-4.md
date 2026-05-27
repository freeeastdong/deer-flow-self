# Phase 7.4 — 代码清理与格式化

- [x] 完成
- **开始时间**：2026-04-30
- **结束时间**：2026-04-30
- **执行的命令**：
  ```bash
  # 前端
  cd frontend
  npx eslint --fix src/app/register/page.tsx src/app/login/page.tsx \
    src/app/profile/page.tsx src/app/admin/users/page.tsx \
    src/components/workspace/workspace-nav-menu.tsx

  # 后端
  cd backend
  uv run ruff check --fix app/gateway/auth_deps.py \
    app/gateway/routers/admin.py app/gateway/routers/threads.py \
    app/gateway/services.py tests/test_thread_isolation.py
  ```

---

## 1. 删除开发过程中的 console.log

| 文件 | 操作 |
|------|------|
| `frontend/src/app/register/page.tsx` | 删除 `console.warn("昵称同步失败:", ...)` |

> 其他文件中的 `console.warn` / `console.error` 为项目原有代码，不属于本次开发引入，未作改动。

---

## 2. 前端 ESLint 修复（`pnpm lint` 相关文件）

### 自动修复（`eslint --fix`）
- **import/order**：按规范重新排序了所有新增/修改页面中的 import 分组和顺序

### 手动修复

| 文件 | 问题 | 修复方式 |
|------|------|---------|
| `register/page.tsx` | `||` 应使用 `??` | `signUpError.message || "..."` → `signUpError.message ?? "..."` |
| `register/page.tsx` | 赋值表达式可用 `??=` | `if (!fieldErrors[path]) { fieldErrors[path] = ... }` → `fieldErrors[path] ??= ...` |
| `register/page.tsx` | 未使用变量 `data` / `err` | 删除解构中的 `data`；`catch (err)` → `catch` |
| `login/page.tsx` | `||` 应使用 `??` | `signInError.message || "..."` → `signInError.message ?? "..."` |
| `login/page.tsx` | 未使用变量 `data` / `err` | 删除解构中的 `data`；`catch (err)` → `catch` |
| `profile/page.tsx` | `||` 应使用 `??`（多处） | 全部替换为 `??` |
| `profile/page.tsx` | Promise reject 应传 Error | `Promise.reject()` → `Promise.reject(new Error("..."))` |
| `admin/users/page.tsx` | Promise reject 应传 Error | `Promise.reject()` → `Promise.reject(new Error("..."))` |
| `workspace-nav-menu.tsx` | `||` 应使用 `??` | `nickname || name || email` → `nickname ?? name ?? email` |

---

## 3. 后端 Ruff 修复

| 文件 | 问题 | 修复方式 |
|------|------|---------|
| `app/gateway/auth_deps.py` | Import block 未排序 | `ruff check --fix` 自动整理 |
| `app/gateway/auth_deps.py` | UP015 不必要的 mode 参数 | `open(..., "r", encoding=...)` → `open(..., encoding=...)` |
| `app/gateway/auth_deps.py` | UP017 `timezone.utc` → `UTC` | `datetime.now(timezone.utc)` → `datetime.now(UTC)` |
| `app/gateway/routers/admin.py` | Import block 未排序 | `ruff check --fix` 自动整理 |
| `app/gateway/routers/threads.py` | F841 未使用变量 `store` | 删除 `store = get_store(request)` |
| `app/gateway/services.py` | F401 未使用 import `time` | 删除 `import time` |
| `tests/test_thread_isolation.py` | Import block 未排序 | `ruff check --fix` 自动整理 |

---

## 4. 验证结果

```bash
# 前端目标文件：0 errors, 0 warnings
npx eslint src/app/register/page.tsx src/app/login/page.tsx \
  src/app/profile/page.tsx src/app/admin/users/page.tsx \
  src/components/workspace/workspace-nav-menu.tsx

# 后端目标文件：All checks passed!
uv run ruff check app/gateway/auth_deps.py app/gateway/routers/admin.py \
  app/gateway/routers/threads.py app/gateway/services.py \
  tests/test_thread_isolation.py
```

---

## 遗留说明

- 项目原有代码（`external/`、`.tmp_pkgs/` 及部分旧页面）仍存在大量 lint 警告，不属于本次用户管理系统开发范围，未作改动。
