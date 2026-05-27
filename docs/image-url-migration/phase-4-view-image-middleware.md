# Phase 4：修改 ViewImageMiddleware URL 注入

## 目标

`ViewImageMiddleware` 不再注入完整 base64 data URL，而是构造指向 Gateway 图片服务端点的 HTTP URL。

## 修改文件

`backend/packages/harness/deerflow/agents/middlewares/view_image_middleware.py`

### 变更点

1. **_create_image_details_message**: 使用 `image_url` 字段构造 HTTP URL，替代 base64 data URL
2. **URL 构造**: 从 `runtime.context` 获取 `thread_id`，从环境变量获取 `APP_BASE_URL`

```python
import os
from urllib.parse import quote

def _create_image_details_message(self, state: ViewImageMiddlewareState, runtime: Runtime) -> list[str | dict]:
    viewed_images = state.get("viewed_images", {})
    if not viewed_images:
        return [{"type": "text", "text": "No images have been viewed."}]

    content_blocks: list[str | dict] = [{"type": "text", "text": "Here are the images you've viewed:"}]

    # Get thread_id from runtime context
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    base_url = os.getenv("APP_BASE_URL", "").rstrip("/")

    for image_path, image_data in viewed_images.items():
        mime_type = image_data.get("mime_type", "unknown")

        content_blocks.append({"type": "text", "text": f"\n- **{image_path}** ({mime_type})"})

        # Construct HTTP URL instead of base64 data URL
        if thread_id and base_url:
            # Remove /mnt/user-data prefix for URL path
            relative_path = image_path
            if relative_path.startswith("/mnt/user-data/"):
                relative_path = relative_path[len("/mnt/user-data/"):]
            encoded_path = quote(relative_path, safe="/")
            image_url = f"{base_url}/api/threads/{thread_id}/files/image/{encoded_path}"
            content_blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                }
            )
        else:
            # Fallback: just mention the path without image content
            content_blocks.append(
                {"type": "text", "text": f"  (Image URL not available for {image_path})"}
            )

    return content_blocks
```

### 接口签名变更

`before_model` 和 `abefore_model` 需要把 `runtime` 传给 `_create_image_details_message`：

```diff
-        image_content = self._create_image_details_message(state)
+        image_content = self._create_image_details_message(state, runtime)
```

同时 `_inject_image_message` 也需要接收 `runtime`：

```diff
-    def _inject_image_message(self, state: ViewImageMiddlewareState) -> dict | None:
+    def _inject_image_message(self, state: ViewImageMiddlewareState, runtime: Runtime) -> dict | None:
         if not self._should_inject_image_message(state):
             return None
-        image_content = self._create_image_details_message(state)
+        image_content = self._create_image_details_message(state, runtime)
```

## 环境变量配置

用户需要在后端环境变量中设置：
```bash
APP_BASE_URL=https://deerflow.example.com  # Gateway 的公网地址
```

如果未设置，middleware 会回退到只注入图片路径文本（LLM 看不到图片内容，但不会 token 爆炸）。
