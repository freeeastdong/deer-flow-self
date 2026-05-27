# Phase 2.2 — 创建注册表单 UI

- [x] 完成
- **开始时间**：
- **结束时间**：

---

## 修改的文件

- `frontend/src/app/register/page.tsx`

## 实现内容

在注册页中加入完整的注册表单，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| 昵称 | text | 用户显示名称 |
| 邮箱 | email | 登录账号 |
| 密码 | password | 至少 8 位（校验在 Phase 2.3） |
| 确认密码 | password | 与密码保持一致 |

使用了项目已有的 UI 组件：
- `@/components/ui/button` —— 提交按钮
- `@/components/ui/input` —— 输入框
- `@/components/ui/card` —— 卡片容器（Card, CardHeader, CardTitle, CardDescription, CardContent）

布局采用居中卡片形式，背景使用 `bg-background`，整体风格与项目现有设计保持一致。

## 关键代码片段

```tsx
<Card className="w-full max-w-md">
  <CardHeader className="space-y-1">
    <CardTitle className="text-2xl">注册账号</CardTitle>
    <CardDescription>填写以下信息创建你的 DeerFlow 账号</CardDescription>
  </CardHeader>
  <CardContent>
    <form className="space-y-4">
      {/* 昵称、邮箱、密码、确认密码输入框 */}
      <Button type="submit" className="w-full">注册</Button>
    </form>
  </CardContent>
</Card>
```

## 验证结果

- 页面上能看到四个输入框和"注册"按钮，布局正常。

## 遇到的问题

无

## 解决方法

无
