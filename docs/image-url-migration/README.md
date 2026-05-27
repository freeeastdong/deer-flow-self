# Image URL Migration（图片注入方式改造）

## 背景

当前 `ViewImageMiddleware` 将完整 base64 图片数据以 data URL 形式注入 LLM 消息，导致：
- 单张 1024×1024 PNG 图片的 base64 可达 1-3MB
- 注入 LLM 消息后，image + text 总 token 数极易超出模型限制
- 触发错误：`Total tokens of image and text exceed max message tokens`（400 BadRequest）

## 改造目标

1. 去掉完整 base64 注入，改用 **HTTP URL** 方式让 LLM 引用图片
2. 新增 Gateway 图片文件服务端点，提供认证保护
3. 保持前端图片展示能力不变

## 整体架构

```
Before:
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────┐
│ view_image_tool │────→│ viewed_images.base64 │────→│ ViewImage   │────→ LLM 消息
│ 读取图片→base64  │     │ (完整 base64 数据)    │     │ Middleware  │       (data:image/png;base64,AAA...)
└─────────────────┘     └──────────────────────┘     └─────────────┘

After:
┌─────────────────┐     ┌────────────────────────┐     ┌─────────────┐     ┌────────────────────┐
│ view_image_tool │────→│ viewed_images.image_path│────→│ ViewImage   │────→│ Gateway /api/files │────→ 图片文件
│ 读取图片→存路径  │     │ (虚拟路径)              │     │ Middleware  │     │ /image/{path}      │
└─────────────────┘     └────────────────────────┘     └─────────────┘     └────────────────────┘
                                                                        │
                                                                        ↓
                                                                   LLM 消息
                                                                   (image_url: http://...)
```

## 关键修改文件

| 文件 | 作用 |
|------|------|
| `backend/app/gateway/routers/image_files.py` | 新增：图片文件服务路由 |
| `backend/app/gateway/app.py` | 注册新路由 |
| `backend/app/gateway/routers/__init__.py` | 导出新路由模块 |
| `backend/packages/harness/deerflow/agents/thread_state.py` | 修改 `ViewedImageData` 结构 |
| `backend/packages/harness/deerflow/tools/builtins/view_image_tool.py` | 不再 base64，存储 `image_path` |
| `backend/packages/harness/deerflow/agents/middlewares/view_image_middleware.py` | 使用 URL 注入 |

## 状态跟踪

- [x] Phase 1: 新增 Gateway 图片文件服务路由
- [x] Phase 2: 修改 thread_state ViewedImageData 结构
- [x] Phase 3: 修改 view_image_tool 生成 URL
- [x] Phase 4: 修改 ViewImageMiddleware URL 注入
- [x] Phase 5: 验证
