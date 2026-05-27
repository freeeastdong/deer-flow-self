# Phase 3.2 — 创建登录表单 UI

- [x] 完成
- **开始时间**：
- **结束时间**：

---

## 修改的文件

- `frontend/src/app/login/page.tsx`

## 实现内容

在登录页中加入完整的登录表单，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| 邮箱 | email | 登录账号 |
| 密码 | password | 用户密码 |

使用了项目已有的 UI 组件：
- `@/components/ui/button` —— 提交按钮
- `@/components/ui/input` —— 输入框
- `@/components/ui/card` —— 卡片容器（Card, CardHeader, CardTitle, CardDescription, CardContent）

布局采用居中卡片形式，背景使用 `bg-background`，图标使用 `LogIn` / `Loader2`（lucide-react），整体风格与注册页（`/register`）保持一致。

表单为受控组件，使用 `useState` 管理 `email` 和 `password`，提交时显示 loading 状态。

## 验证结果

- 页面上能看到邮箱、密码两个输入框和"登录"按钮，布局正常。
- 按钮在提交时显示 loading 动画。

## 遇到的问题

无

## 解决方法

无
