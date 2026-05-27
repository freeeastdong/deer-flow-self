# Phase 7.2 — 修复测试中发现的问题

- [ ] 完成
- **开始时间**：
- **结束时间**：

---

## Bug 修复记录

| 序号 | 现象 | 原因 | 修复方法 | 涉及文件 | 状态 |
|------|------|------|---------|---------|------|
| 1 | 注册时填写的昵称在 `/profile` 页面显示为"未设置" | 注册仅写入 `user.name`，未同步到 `additionalFields.nickname` | 注册成功后调用 `authClient.updateUser({ nickname })` | `frontend/src/app/register/page.tsx` | ✅ |
| 2 | | | | | ⬜ |
| 3 | | | | | ⬜ |
| 4 | | | | | ⬜ |
| 5 | | | | | ⬜ |

---

## 详细说明

### Bug #1 — 注册昵称未同步到 Profile 页

**现象**：
在注册页面填写昵称并提交注册后，进入 `/profile` 个人资料页，昵称显示为"未设置"。

**原因**：
注册时调用 `authClient.signUp.email({ name: formData.nickname })` 只将昵称写入了 better-auth 默认的 `user.name` 列，而 `/profile` 页面优先读取的是 `additionalFields` 中定义的 `nickname` 字段。由于 `nickname` 未被赋值（保持默认空字符串），导致页面显示回退到"未设置"。

**修复方法**：
在注册成功后，额外调用 `authClient.updateUser({ nickname: formData.nickname })` 将昵称显式同步到 `nickname` 字段：

```tsx
const { error: updateError } = await authClient.updateUser({
  nickname: formData.nickname,
});
```

若同步失败，不影响注册主流程，仅控制台打印警告。

**验证结果**：
注册后进入 `/profile`，昵称正确显示为注册时填写的内容。

---

### Bug #2

**现象**：

**原因**：

**修复方法**：

**验证结果**：

---

## 遗留问题

> 本轮测试中未解决或需要后续跟进的事项：

1. 
2. 
