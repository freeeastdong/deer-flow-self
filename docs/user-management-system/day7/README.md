# Day 7 记录：测试、修复与总结

> 目标：把所有功能串起来跑通，修 bug，写文档

---

## Phase 7.1 — 全链路手动测试
- [x] 进行中
- **开始时间**：2026-04-30
- **结束时间**：
- **详细记录**：见 [phase-7-1.md](./phase-7-1.md)
- **遇到的问题**：
  1. 注册时填写的昵称未同步到 `/profile` 页面（已修复，见 phase-7-2.md #1）

## Phase 7.2 — 修复测试中发现的问题
- [ ] 完成
- **开始时间**：
- **结束时间**：
- **详细记录**：见 [phase-7-2.md](./phase-7-2.md)
- **Bug 列表**：
  | 序号 | 现象 | 原因 | 修复方法 | 状态 |
  |------|------|------|----------|------|
  | 1 | | | | |
  | 2 | | | | |

## Phase 7.3 — 编写对话隔离自动化测试
- [x] 完成
- **开始时间**：2026-04-30
- **结束时间**：2026-04-30
- **涉及文件**：`backend/tests/test_thread_isolation.py`
- **测试用例清单**：
  1. `test_user_only_sees_own_threads` —— 普通用户只能看到自己的对话 ✅
  2. `test_user_cannot_see_legacy_threads` —— 普通用户看不到无 `user_id` 的老数据 ✅
  3. `test_get_other_user_thread_forbidden` —— 访问他人对话返回 403 ✅
  4. `test_run_on_other_user_thread_forbidden` —— 向他人对话发送消息返回 403 ✅
  5. `test_admin_can_see_all_threads` —— admin 不受隔离限制 ✅
  6. `test_unauthenticated_search_returns_401` —— 未登录返回 401 ✅
  7. `test_get_legacy_thread_allowed` —— 单对话访问兼容老数据（无 403）✅
- **遇到的问题**：
  - FastAPI `dependency_overrides` 中 lambda 参数名会被解析为查询参数，导致 422。解决：使用无参数 lambda 返回 mock 用户。

## Phase 7.4 — 代码清理与格式化
- [x] 完成
- **开始时间**：2026-04-30
- **结束时间**：2026-04-30
- **详细记录**：见 [phase-7-4.md](./phase-7-4.md)
- **执行的命令**：
  ```bash
  cd frontend && npx eslint --fix ...
  cd backend && uv run ruff check --fix ...
  ```
- **遇到的问题**：
  - FastAPI `dependency_overrides` 的 lambda 参数会被解析为查询参数，导致 422
  - 前端 Promise.reject() 需要传入 Error 对象
  - 后端 `threads.py` 中存在未使用的 `store` 变量

## Phase 7.5 — 编写最终总结文档
- [x] 完成
- **开始时间**：2026-04-30
- **结束时间**：2026-04-30
- **详细记录**：见 [phase-7-5.md](./phase-7-5.md)
- **总结文档路径**：[`docs/user-management-system/summary.md`](../summary.md)
- **后续可扩展方向**：
  1. 迁移到 upstream 官方认证（`app/plugins/auth` + `actor_context`）
  2. 多副本部署支持（RFC #2471）
  3. 更细粒度的权限（capabilities-based authorization）
  4. 头像上传（`avatar` 字段已预留）

---

## Day 7 总结（最终感想）
- 整体感受：
- 学到的东西：
- 还可以改进的地方：
