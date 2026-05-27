# Phase 3.4 — 导航栏显示用户状态 + 登出

- [x] 完成
- **开始时间**：
- **结束时间**：

---

## 修改的文件

- `frontend/src/components/workspace/workspace-nav-menu.tsx`

## 实现内容

在侧边栏底部的 **"设置与更多"下拉菜单**（`WorkspaceNavMenu`）中接入用户状态显示和登出功能。

### 获取登录状态

```tsx
const { data: sessionData, isPending } = authClient.useSession();
const user = sessionData?.user;
```

### 已登录状态

- 下拉菜单顶部显示用户名称（优先 `user.name`，fallback 到 `user.email`）和邮箱
- 提供 **"退出登录"** 选项（带 `LogOut` 图标）
- 点击后调用 `authClient.signOut()`，成功后执行 `window.location.reload()` 刷新页面

### 未登录状态

- 下拉菜单顶部显示 **"登录"**（链接到 `/login`）和 **"注册"**（链接到 `/register`）两个选项
- 分别带 `LogIn` 和 `UserPlus` 图标

### 加载中状态

- `isPending` 为 true 时，用户区域不显示任何内容，避免闪烁

## 验证结果

- [x] 登录后进入 `/workspace`，点击左下角"设置与更多"，能看到自己的用户名/邮箱和"退出登录"
- [x] 点击"退出登录"后页面刷新，状态恢复未登录
- [x] 未登录时进入 `/workspace`，点击左下角"设置与更多"，能看到"登录"和"注册"入口

## 遇到的问题

无

## 解决方法

无
