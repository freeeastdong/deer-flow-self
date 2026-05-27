# Phase 3：修改 view_image_tool 生成 URL

## 目标

`view_image_tool` 不再读取完整图片内容并 base64 编码，而是只做路径校验和 MIME 类型检测，将图片虚拟路径存入 `viewed_images`。

## 修改文件

`backend/packages/harness/deerflow/tools/builtins/view_image_tool.py`

### 变更点

1. **去掉 base64 读取和编码逻辑**
2. **保留所有安全校验**（路径白名单、文件头魔数检测、大小限制）
3. **存储 `{image_path, mime_type}` 到 `viewed_images`**

```diff
-    # Read image file and convert to base64
-    try:
-        with open(actual_path, "rb") as f:
-            image_data = f.read()
-            image_base64 = base64.b64encode(image_data).decode("utf-8")
-    except Exception as e:
-        return Command(
-            update={"messages": [ToolMessage(f"Error reading image file: {str(e)}", tool_call_id=tool_call_id)]},
-        )
-
     # Update viewed_images in state
-    new_viewed_images = {image_path: {"base64": image_base64, "mime_type": mime_type}}
+    new_viewed_images = {image_path: {"image_path": image_path, "mime_type": mime_type}}
```

## 安全保留

以下校验逻辑全部保留：
- `_ALLOWED_IMAGE_VIRTUAL_ROOTS` 虚拟路径白名单
- `_MAX_IMAGE_BYTES = 20 * 1024 * 1024` 大小限制
- `_detect_image_mime()` 文件头魔数检测（防止扩展名欺骗）
- 扩展名与内容一致性校验
