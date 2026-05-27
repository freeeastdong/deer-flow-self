# Phase 2：修改 thread_state ViewedImageData 结构

## 目标

将 `ViewedImageData` 从存储完整 base64 改为存储图片虚拟路径。

## 修改文件

`backend/packages/harness/deerflow/agents/thread_state.py`

```diff
 class ViewedImageData(TypedDict):
-    base64: str
+    image_path: str
     mime_type: str
```

## 向后兼容

`merge_viewed_images` reducer 使用 `{**existing, **new}` 合并字典，新写入的图片会使用新格式，旧的 base64 数据会在 reducer 中被覆盖或自然淘汰。

由于 `ViewImageMiddleware` 和 `view_image_tool` 会同步修改（Phase 3 和 4），系统内部始终使用一致的格式，不需要处理新旧格式共存的情况。
