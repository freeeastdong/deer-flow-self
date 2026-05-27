# Phase 3.3 — 接入 better-auth 登录 API

- [x] 完成
- **开始时间**：
- **结束时间**：

---

## 修改的文件

- `frontend/src/app/login/page.tsx`

## 实现内容

点击登录按钮后，调用 `authClient.signIn.email()` 发送登录请求。

### 关键代码片段

```tsx
import { useRouter } from "next/navigation";
import { authClient } from "@/server/better-auth/client";

const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  setError("");
  setIsLoading(true);

  try {
    const { data, error: signInError } = await authClient.signIn.email({
      email: formData.email,
      password: formData.password,
    });

    if (signInError) {
      setError(signInError.message || "邮箱或密码错误");
      return;
    }

    // 登录成功，跳转到工作区
    router.push("/workspace");
  } catch (err) {
    setError("网络错误，请检查连接后重试");
  } finally {
    setIsLoading(false);
  }
};
```

### 交互设计

- **登录成功**：跳转到 `/workspace`
- **登录失败**（账号/密码错误）：在表单顶部显示红色错误提示
- **网络异常**：显示"网络错误，请检查连接后重试"
- **加载状态**：按钮显示 loading 动画并禁用，防止重复提交

## 验证结果

- [x] 用 Day 2 注册的账号能正常登录
- [x] 登录成功后正确跳转到 `/workspace`
- [x] 输入错误密码时显示"邮箱或密码错误"
- [x] 登录成功后浏览器自动保存 `better-auth.session_token` cookie

## 遇到的问题

无

## 解决方法

无
