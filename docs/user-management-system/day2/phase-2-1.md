# Phase 2.1 — 创建注册页面路由

- [x] 完成
- **开始时间**：
- **结束时间**：

---

## 修改的文件

- `frontend/src/app/register/page.tsx`

## 实现内容

新建 Next.js 页面路由 `/register`，先放一个最简单的骨架，确保能访问。

```tsx
export default function RegisterPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <h1>注册</h1>
    </div>
  );
}
```

后续 Phase 2.2-2.4 在此文件上逐步完善表单、校验和 API 接入。

## 验证结果

- 浏览器访问 `http://localhost:2026/register` 正常显示注册页面（Docker 下走 nginx 入口）。

## 遇到的问题

无

## 解决方法

无
