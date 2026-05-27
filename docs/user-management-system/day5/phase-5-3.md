# Phase 5.3 — 实现资料修改功能

## 目标

在 `/profile` 页面添加编辑表单，允许修改昵称。

## 涉及文件

- `frontend/src/app/profile/page.tsx`

## 实现内容

### 添加昵称编辑功能

在原有只读资料页的基础上，为"昵称"字段增加编辑模式：

- **编辑入口**：昵称右侧显示"编辑"按钮，点击后进入编辑模式
- **输入框**：显示 `Input` 组件，预填充当前昵称（或 `name` 作为 fallback）
- **保存**：调用 `authClient.updateUser({ nickname: ... })`
- **取消**：退出编辑模式，恢复原始值
- **加载状态**：保存时显示旋转图标并禁用按钮
- **错误提示**：保存失败时显示错误信息

### 核心代码

```tsx
const [isEditing, setIsEditing] = useState(false);
const [nickname, setNickname] = useState("");
const [isSaving, setIsSaving] = useState(false);

const handleSave = async () => {
  setIsSaving(true);
  const { error } = await authClient.updateUser({
    nickname: nickname.trim(),
  });
  if (error) {
    setSaveError(error.message || "保存失败");
  } else {
    setIsEditing(false); // 成功后自动退出编辑模式
  }
  setIsSaving(false);
};
```

> **头像**：本 Phase 不涉及文件上传，头像仍用文字首字母占位。

---

## 验证

### 验证 1：修改昵称并保存

1. 访问 `/profile`
2. 点击昵称右侧的"编辑"按钮
3. 输入新昵称，点击"保存"
4. **预期结果**：编辑框收起，页面上方和昵称字段都显示新昵称

### 验证 2：刷新页面后昵称仍然生效

1. 修改昵称并保存
2. 刷新页面
3. **预期结果**：新昵称仍然存在（说明已持久化到数据库）

### 验证 3：取消编辑不保存

1. 点击"编辑"
2. 修改输入框内容
3. 点击"取消"
4. **预期结果**：昵称恢复为修改前的值

## 遇到的问题

无。
