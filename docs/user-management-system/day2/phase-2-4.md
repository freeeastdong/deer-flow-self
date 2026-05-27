# Phase 2.4 — 接入 better-auth 注册 API

- [x] 完成
- **开始时间**：
- **结束时间**：

---

## 修改的文件

- `frontend/src/app/register/page.tsx`
- `frontend/src/server/better-auth/client.ts`（已存在，直接使用）

## 实现内容

点击注册按钮后，调用 `authClient.signUp.email()` 发送注册请求。

### 关键代码片段

```tsx
import { authClient } from "@/server/better-auth/client";

const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  // ... zod 校验通过 ...

  const { data, error } = await authClient.signUp.email({
    email: formData.email,
    password: formData.password,
    name: formData.nickname,
  });

  if (error) {
    setErrors({ form: error.message || "注册失败，请稍后重试" });
    return;
  }

  setSuccess(true);
  setTimeout(() => {
    router.push("/workspace");
  }, 1500);
};
```

### 交互设计

- **注册成功**：显示绿色成功提示"注册成功！正在跳转..."，1.5 秒后自动跳转到 `/workspace`。
- **注册失败**：在表单顶部显示红色错误提示（如"邮箱已存在"等）。
- **加载状态**：按钮显示 loading 动画，防止重复提交。

## 验证结果

- [x] 用真实邮箱密码注册成功
- [x] `./data/auth.db`（宿主机）中能看到新增的用户记录
- [x] 注册成功后正确跳转到 `/workspace`
- [x] 使用已存在邮箱注册时，能正确提示错误

## 遇到的问题

无

## 解决方法

无
