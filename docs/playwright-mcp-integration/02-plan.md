# Playwright MCP 集成修改计划

> 状态：待执行
> 基于分析文档：`01-analysis.md`

## 一、目标

将 Playwright MCP 集成到 DeerFlow 项目中，使用户能够通过 AI Agent 操控浏览器进行网页自动化操作。

## 二、采用方案

**推荐方案 B（内置默认配置）为主，方案 C（前端 UI 增强）为辅。**

理由：
- 改动量小，风险低
- 用户体验好（开箱即用）
- 后续可平滑升级到完整 UI 管理

---

## 三、阶段划分

### 阶段 1：后端内置默认配置（P0 - 必需）

**目标**：让 Playwright MCP 出现在前端 Tools 设置页面，默认禁用，用户可一键启用。

**任务清单**：

- [ ] **Task 1.1**：修改 `backend/packages/harness/deerflow/config/extensions_config.py`
  - 在 `ExtensionsConfig` 的默认值或加载逻辑中，预置 `playwright` MCP Server 配置
  - 配置内容：
    ```json
    {
      "enabled": false,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "env": {},
      "description": "Browser automation via Playwright MCP"
    }
    ```
  - 确保与现有用户配置合并时，用户自定义配置优先级更高

- [ ] **Task 1.2**：测试配置加载
  - 验证无配置文件时，默认配置能正确加载
  - 验证已有配置文件中存在 `playwright` 时，不覆盖用户配置
  - 验证 `GET /api/mcp/config` 返回包含 `playwright`

- [ ] **Task 1.3**：环境依赖检查
  - 在 `scripts/check.py` 或 `scripts/doctor.py` 中增加 Node.js 版本检测提示
  - 在 `Install.md` 中补充 Playwright MCP 的运行环境要求

**预期改动文件**：
- `backend/packages/harness/deerflow/config/extensions_config.py`
- `scripts/check.py`（可选）

---

### 阶段 2：前端国际化与 UI 优化（P1 - 重要）

**目标**：前端正确显示 Playwright MCP 的名称和描述。

**任务清单**：

- [ ] **Task 2.1**：修改 `frontend/src/core/i18n/locales/en-US.ts`
  - 在 `settings.tools` 下添加 Playwright MCP 的显示文案
  - 考虑增加一个 `mcpServerDescriptions` 映射，让不同 MCP Server 显示不同描述

- [ ] **Task 2.2**：修改 `frontend/src/core/i18n/locales/zh-CN.ts`
  - 同上，中文翻译

- [ ] **Task 2.3**：优化 `frontend/src/components/workspace/settings/tool-settings-page.tsx`
  - 为内置 MCP Server 显示更友好的名称（优先使用 i18n 文案，fallback 到 server name）
  - 添加 Playwright 相关图标或标识（可选）

**预期改动文件**：
- `frontend/src/core/i18n/locales/en-US.ts`
- `frontend/src/core/i18n/locales/zh-CN.ts`
- `frontend/src/components/workspace/settings/tool-settings-page.tsx`（可选小改）

---

### 阶段 3：文档更新（P1 - 重要）

**目标**：让用户知道 Playwright MCP 已可用，以及如何手动配置。

**任务清单**：

- [ ] **Task 3.1**：更新 `README.md` 或 `README_zh.md`
  - 在功能特性列表中提及 MCP 支持，并特别说明内置 Playwright MCP

- [ ] **Task 3.2**：更新 `Install.md`
  - 添加 Playwright MCP 启用步骤
  - 说明运行环境要求（Node.js ≥ 18）
  - 提供手动配置 `extensions_config.json` 的示例

- [ ] **Task 3.3**：在本目录下创建 `03-implementation.md`
  - 记录实际实现细节和决策

**预期改动文件**：
- `README.md`
- `Install.md`
- `docs/playwright-mcp-integration/03-implementation.md`（新增）

---

### 阶段 4：前端 UI 增强（P2 - 可选）

**目标**：支持在 UI 上直接添加/编辑/删除任意 MCP Server。

**任务清单**：

- [ ] **Task 4.1**：扩展类型定义
  - 修改 `frontend/src/core/mcp/types.ts`，补全所有 MCP Server 配置字段

- [ ] **Task 4.2**：新增 React Query Hooks
  - `useAddMCPServer`
  - `useUpdateMCPServer`
  - `useDeleteMCPServer`

- [ ] **Task 4.3**：重构 MCP Server 管理 UI
  - 在 `tool-settings-page.tsx` 中新增：
    - "添加 MCP Server" 按钮
    - 添加/编辑表单（支持 stdio/sse/http 类型切换）
    - 删除确认对话框
  - 表单字段：
    - 基础：名称、描述、启用开关、类型选择
    - stdio：命令、参数、环境变量
    - sse/http：URL、请求头
    - OAuth：可选的高级配置

- [ ] **Task 4.4**：表单验证
  - 使用 zod 或其他方式验证表单数据

- [ ] **Task 4.5**：Mock API 更新
  - 更新 `frontend/src/app/mock/api/mcp/config/route.ts`

**预期改动文件**：
- `frontend/src/core/mcp/types.ts`
- `frontend/src/core/mcp/hooks.ts`
- `frontend/src/components/workspace/settings/tool-settings-page.tsx`
- `frontend/src/core/i18n/locales/en-US.ts`
- `frontend/src/core/i18n/locales/zh-CN.ts`
- `frontend/src/app/mock/api/mcp/config/route.ts`

---

### 阶段 5：容器化部署（P2 - 可选）

**目标**：支持通过 Docker Compose 一键部署 Playwright MCP 服务。

**任务清单**：

- [ ] **Task 5.1**：创建 Dockerfile
  - 新建 `docker/playwright-mcp/Dockerfile`
  - 基于 Node.js 镜像，安装 `@playwright/mcp`
  - 安装 Chromium 浏览器依赖
  - 配置 `--no-sandbox` 运行参数

- [ ] **Task 5.2**：更新 `docker-compose.yaml`
  - 新增 `playwright-mcp` service
  - 配置网络互通（与 backend/gateway 同网络）

- [ ] **Task 5.3**：更新默认配置
  - 当使用 Docker 部署时，预置配置改为 `type: "sse"` 或 `type: "http"`
  - URL 指向 `http://playwright-mcp:3000`（假设端口）

- [ ] **Task 5.4**：文档说明
  - 补充 Docker 部署方式说明

**预期改动文件**：
- `docker-compose.yaml`
- `docker/playwright-mcp/Dockerfile`（新增）
- `backend/packages/harness/deerflow/config/extensions_config.py`

---

## 四、执行顺序

```
阶段 1（后端默认配置）
    │
    ▼
阶段 2（前端国际化） ──► 阶段 3（文档更新）
    │
    ▼
阶段 4（前端 UI 增强） [可选，可并行]
    │
    ▼
阶段 5（容器化部署） [可选，可并行]
```

---

## 五、验收标准

### 5.1 阶段 1 验收

- [ ] 全新安装的 DeerFlow，启动后 `GET /api/mcp/config` 返回包含 `playwright` server
- [ ] `playwright` 默认 `enabled: false`
- [ ] 用户在前端 Tools 设置页面能看到 Playwright MCP 条目
- [ ] 打开开关后，LangGraph Server 能正确初始化 Playwright MCP tools
- [ ] 用户已有 `extensions_config.json` 时，不会覆盖其现有配置

### 5.2 阶段 2 验收

- [ ] 前端 UI 显示 Playwright MCP 的友好名称（非原始 key）
- [ ] 中英文环境下均显示正确的本地化文案
- [ ] 描述文字清晰说明这是浏览器自动化工具

### 5.3 阶段 3 验收

- [ ] README 中有 Playwright MCP 的简要说明
- [ ] Install.md 中有启用步骤和环境要求

### 5.4 阶段 4 验收

- [ ] 用户能在 UI 上添加新的 MCP Server
- [ ] 用户能在 UI 上编辑已有 MCP Server 的配置
- [ ] 用户能在 UI 上删除自定义添加的 MCP Server（内置的不允许删除，可禁用）
- [ ] 表单验证能拦截无效输入

### 5.5 阶段 5 验收

- [ ] `docker-compose up` 能正确启动 Playwright MCP 容器
- [ ] DeerFlow backend 能通过 SSE/HTTP 连接到容器内的 Playwright MCP
- [ ] 浏览器自动化功能正常工作

---

## 六、回滚方案

如果集成出现问题，回滚方式如下：

1. **配置文件级回滚**：删除 `extensions_config.json` 中的 `playwright` 条目，或设置 `"enabled": false`
2. **代码级回滚**：
   - 阶段 1：移除 `extensions_config.py` 中的默认配置逻辑
   - 阶段 2：移除 i18n 文案
   - 阶段 4：回滚前端 UI 改动
   - 阶段 5：移除 docker-compose 中的 service

所有阶段均为增量改动，不涉及现有核心逻辑修改，回滚风险极低。
