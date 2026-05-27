# Phase 2.3 — 添加表单校验（zod）

- [x] 完成
- **开始时间**：
- **结束时间**：

---

## 修改的文件

- `frontend/src/app/register/page.tsx`

## 实现内容

使用 `zod` 定义注册数据的校验规则，并在表单提交时进行校验。

### 校验规则

```ts
const registerSchema = z
  .object({
    nickname: z.string().min(1, "昵称不能为空"),
    email: z.string().email("请输入有效的邮箱地址"),
    password: z.string().min(8, "密码至少 8 位"),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "两次输入的密码不一致",
    path: ["confirmPassword"],
  });
```

| 规则 | 说明 |
|------|------|
| `nickname.min(1)` | 昵称不能为空 |
| `email.email()` | 必须符合邮箱格式 |
| `password.min(8)` | 密码至少 8 位 |
| `.refine(...)` | 确认密码必须与密码一致 |

### 错误提示

- 校验失败时，在对应输入框下方显示红色错误提示（`text-destructive` 样式）。
- 输入内容时自动清除该字段的错误状态。

## 验证结果

- 输入错误内容（如短密码、无效邮箱、不一致密码）点击注册，能看到对应红色提示。
- 输入正确内容，所有错误提示消失。

## 遇到的问题

无

## 解决方法

无
