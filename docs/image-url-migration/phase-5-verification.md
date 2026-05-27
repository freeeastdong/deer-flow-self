# Phase 5：测试验证

## 验证矩阵

| 测试项 | 预期结果 |
|--------|---------|
| Gateway 路由可访问 | `GET /api/threads/{tid}/files/image/outputs/cat.png` 返回图片文件 |
| 路由认证生效 | 未登录访问返回 401 |
| 路由权限生效 | 无权访问 thread 返回 403 |
| 路径遍历防护 | 访问 `/../../etc/passwd` 返回 403 |
| view_image_tool 存储格式 | `viewed_images` 中存储 `{image_path, mime_type}`，无 base64 |
| ViewImageMiddleware URL 注入 | 消息中包含 `image_url`（HTTP URL），无 base64 data URL |
| 环境变量未设置 | 回退到文本描述，不注入图片 URL |
| LLM 调用不再 token 超限 | 同一对话之前触发 400，改造后正常 |

## 回归测试

- [ ] 未设置 `APP_BASE_URL` 时系统正常运行
- [ ] `present_files` 工具仍能正常展示图片
- [ ] 前端图片渲染正常
