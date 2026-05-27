# 简历

## 项目经历

### AI Agent 平台功能扩展与实践（基于 DeerFlow 2.0）

**项目类型**：开源框架二次开发 + 本地 AI 生成能力集成

**项目概述**：基于字节跳动开源的 DeerFlow 2.0（LangGraph-based Super Agent Harness），在其已有的多用户认证、数据隔离、长期记忆、子代理编排等框架基础上，独立完成**管理后台**、**应用中心**、以及**ComfyUI 本地生图/生视频能力**的集成与改造。

**核心工作与技术实践**：

1. **管理后台开发**
   - 使用 FastAPI 开发 Admin 路由（`/api/admin/users`），实现 `require_admin` 权限依赖，支持管理员查看注册用户列表（ID、邮箱、角色、注册时间）；
   - 基于 Next.js 开发 Admin Dashboard 前端页面，与现有 RBAC 权限体系对接，完成前后端联调与权限边界测试。

2. **应用中心搭建**
   - 在 DeerFlow 工作区前端新增 Application Hub 入口页面，扩展平台的多模态内容展示能力；
   - 通过 **iframe 嵌入** 集成两个独立垂直应用：**世界文学地图**（3D 地球可视化）与 **音乐电台**（AI 语音助手 + TTS），解决样式隔离、全屏支持、与主平台导航打通等问题；
   - 调整工作区导航与布局，新增应用中心与管理后台入口，完善中英文国际化支持。

3. **ComfyUI 本地 AI 生成能力集成**
   - **替换官方 Gemini API 方案**：将 `image-generation` 和 `video-generation` 两个 Skill 的底层实现，从 Google Gemini 云端 API 迁移为**本地 ComfyUI 工作流调用**；
   - 重写 `generate.py`：支持 ComfyUI API 工作流提交、Prompt 动态注入、尺寸调整、参考图上传、种子随机化、Checkpoint 切换、轮询获取结果；
   - 集成 Flux2 Klein 文生图工作流与 Wan 文生视频工作流，通过环境变量 `COMFYUI_BASE_URL` / `COMFYUI_WORKFLOW_PATH` / `COMFYUI_CHECKPOINT` 实现灵活配置；
   - 更新 Skill 文档（`SKILL.md`），使 Agent 能够正确调用本地 ComfyUI 完成生图/生视频任务。

**技术栈**：LangGraph / FastAPI / Next.js / React / TypeScript / ComfyUI API / iframe 嵌入 / Docker

---

## 专业技能

| 方向 | 技术关键词 |
|------|-----------|
| LLM 应用 | LangGraph / LangChain / Agent Orchestration / Skill System / MCP |
| 前端 | Next.js 14 / React / TypeScript / iframe 集成 / i18n 国际化 |
| 后端 | Python / FastAPI / JWT / RBAC / 依赖注入 |
| AI 生成 | ComfyUI / Stable Diffusion / 文生图 / 文生视频 / 工作流编排 |
| 部署 | Docker / Docker Compose / Nginx |

---

## 面试要点

### Q1：ComfyUI 是怎么集成的？

DeerFlow 的 Skill 系统通过 `SKILL.md` 定义工作流，Agent 在对话中识别到生图/生视频需求时自动加载对应 Skill。我替换了官方 0502 版本中的 Gemini API 方案，重写了 `image-generation/scripts/generate.py` 和 `video-generation/scripts/generate.py`：读取用户 JSON Prompt → 加载 ComfyUI 工作流 JSON → 注入 prompt/尺寸/种子/参考图 → 提交到本地 ComfyUI API (`/prompt`) → 轮询 `/history` 获取结果 → 下载输出文件。支持 Flux2 Klein 生图和 Wan 生视频两个工作流。

### Q2：应用中心是怎么嵌入独立应用的？

通过 iframe 嵌入。我在 Next.js 前端新建了 `/workspace/applications` 路由作为入口，里面用 iframe 加载独立构建的静态页面（文学地图是 Three.js 3D 地球，音乐电台是独立 React 项目）。关键点：iframe 的 `allow="fullscreen"` 支持全屏、通过 `className="size-full border-0"` 消除边框、与主平台导航通过 URL 路由打通。

### Q3：管理后台的权限怎么控制的？

复用了 DeerFlow 已有的 RBAC 框架。后端 `admin.py` 中定义 `require_admin` 依赖，检查 `user.system_role == "admin"`，非管理员返回 403。前端 admin 页面通过常规路由渲染，实际的权限拦截在后端 API 层完成。
