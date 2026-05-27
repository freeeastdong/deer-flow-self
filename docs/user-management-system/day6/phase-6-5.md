# Phase 6.5 — 前端路由守卫

- [x] 完成
- **开始时间**：2026-04-30
- **结束时间**：2026-04-30
- **修改的文件**：`frontend/src/app/admin/users/page.tsx`
- **关键代码片段**：
  ```tsx
  useEffect(() => {
    if (!isPending) {
      if (!user) {
        router.push("/login");
      } else if ((user as Record<string, string>).role !== "admin") {
        router.push("/profile");
      }
    }
  }, [isPending, user, router]);
  ```
- **遇到的问题**：
  原有代码只对已登录的非 admin 用户做了跳转，但未登录用户在 `isPending` 结束后会落入 `return null`，页面显示为空白，体验不佳；同时拦截后的跳转目标应为个人资料页（`/profile`），因为"用户管理"入口位于个人资料页面。
- **解决方法**：
  在 `useEffect` 中增加对 `!user`（未登录）的判断，直接跳转到 `/login`；已登录但 `role !== "admin"` 的跳转到 `/profile`。页面顶部的"返回"按钮与后端 403 响应处理也统一指向 `/profile`。这样覆盖了所有非法访问场景，不会再出现空白页。
- **验证结果**：
  1. 未登录直接访问 `/admin/users` → 自动跳转到 `/login`
  2. 普通用户登录后访问 `/admin/users` → 自动跳转到 `/profile`
  3. admin 用户访问 `/admin/users` → 正常显示用户管理页面
