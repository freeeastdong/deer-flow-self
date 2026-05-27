# Playwright MCP 集成改动量分析

> 分析日期：2026-05-12
> 项目：DeerFlow

## 一、背景与目标

### 1.1 什么是 Playwright MCP

Playwright MCP 是基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 的浏览器自动化服务器，它允许 AI Agent 通过标准化的工具调用来操控真实浏览器，实现：

- 网页导航（`browser_navigate`）
- 元素点击、表单填写（`browser_click`, `browser_type`）
- 页面截图（`browser_screenshot`）
- DOM 提取与内容抓取（`browser_select`, `browser_evaluate`）
- 浏览器上下文管理

主流实现：

| 名称 | 包名/仓库 | 传输类型 | 运行方式 |
|------|----------|---------|---------|
| **Microsoft 官方** | `@playwright/mcp` | stdio | `npx @playwright/mcp@latest` |
| **社区版 (Python)** | `dbustosjr/playwright-mcp-server` | stdio/http | `python server.py` |

### 1.2 DeerFlow 现有 MCP 架构

DeerFlow 已具备完整的 MCP 集成框架：

- **支持类型**：stdio、sse、http 三种传输类型
- **配置管理**：通过 `extensions_config.json` 配置 MCP Server
- **前后端交互**：Gateway 提供 `GET/PUT /api/mcp/config` API
- **工具加载**：基于 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 自动加载 tools
- **OAuth 支持**：SSE/HTTP 类型支持自动 Token 注入
- **热重载**：配置文件修改后 LangGraph Server 自动感知并重新初始化

---

## 二、改动量评估

### 2.1 方案对比总览

| 方案 | 改动文件数 | 复杂度 | 用户体验 | 推荐度 |
|------|-----------|--------|---------|--------|
| **方案 A：纯配置集成** | 0（仅改 JSON 配置） | ⭐ 极低 | 需手动编辑配置文件 | ⭐⭐⭐ |
| **方案 B：内置默认配置** | 2-3 | ⭐⭐ 低 | 开箱即用，UI 开关控制 | ⭐⭐⭐⭐⭐ |
| **方案 C：前端 UI 增强** | 6-8 | ⭐⭐⭐⭐ 较高 | 完整的添加/编辑/删除 | ⭐⭐⭐⭐ |
| **方案 D：容器化部署** | 3-4 | ⭐⭐⭐ 中等 | 适合服务端部署 | ⭐⭐⭐⭐ |

---

### 2.2 方案 A：纯配置集成（零代码改动）

**原理**：DeerFlow 已支持任意 stdio MCP Server，只需在配置文件中添加 Playwright MCP 配置。

**操作步骤**：

1. 确保运行环境已安装 Node.js ≥ 18
2. 在 `extensions_config.json`（项目根目录或 backend 目录）中添加：

```json
{
  "mcpServers": {
    "playwright": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "env": {},
      "description": "Browser automation via Playwright MCP - navigate, click, type, screenshot"
    }
  }
}
```

3. 重启 DeerFlow 后端服务，或等待热重载

**改动量**：`0 个代码文件`，仅需修改 1 个 JSON 配置文件。

**限制**：
- 用户需要知道配置文件位置和格式
- 前端 UI 上只能看到 "playwright" 名称和开关，看不到具体配置
- 无法通过 UI 新增或修改参数

---

### 2.3 方案 B：内置默认配置（推荐）

**原理**：在代码中预置 Playwright MCP 的默认配置，用户无需手动编辑配置文件即可在 UI 中看到并启用。

**需要改动的文件**：

| # | 文件路径 | 改动内容 | 工作量 |
|---|---------|---------|--------|
| 1 | `backend/packages/harness/deerflow/config/extensions_config.py` | 在 `ExtensionsConfig` 默认值或加载逻辑中预置 `playwright` server 配置 | 小 |
| 2 | `frontend/src/core/i18n/locales/en-US.ts` | 添加 Playwright MCP 的名称和描述国际化文案 | 极小 |
| 3 | `frontend/src/core/i18n/locales/zh-CN.ts` | 同上，中文文案 | 极小 |

**可选增强**：

| # | 文件路径 | 改动内容 | 工作量 |
|---|---------|---------|--------|
| 4 | `frontend/src/components/workspace/settings/tool-settings-page.tsx` | 为内置 MCP Server 显示更友好的图标或标签 | 小 |
| 5 | `Install.md` / `README.md` | 文档中说明 Playwright MCP 已内置 | 极小 |

**总计**：约 **2-5 个文件**，每处改动量都很小（10-30 行）。

**优势**：
- 用户开箱即用
- 改动量极小，风险低
- 不需要改变现有架构

---

### 2.4 方案 C：前端 UI 增强（支持添加/编辑/删除 MCP Server）

**原理**：当前前端 UI 仅支持启用/禁用已有 MCP Server。如果希望用户在 UI 上直接添加 Playwright MCP（或其他 MCP Server），需要扩展管理功能。

**当前前端能力限制**：
- ❌ 不支持新增 MCP Server
- ❌ 不支持编辑 command/args/url 等参数
- ❌ 不支持删除 MCP Server
- ❌ 不支持配置 OAuth 参数
- ❌ `MCPServerConfig` TS 类型过于简略（只有 `enabled` 和 `description`）

**需要改动的文件**：

| # | 文件路径 | 改动内容 | 工作量 |
|---|---------|---------|--------|
| 1 | `frontend/src/core/mcp/types.ts` | 扩展 `MCPServerConfig` 接口，增加 `type`, `command`, `args`, `env`, `url`, `headers`, `oauth` 等字段 | 小 |
| 2 | `frontend/src/core/mcp/api.ts` | 已有 `updateMCPConfig`，通常无需改动 | 无 |
| 3 | `frontend/src/core/mcp/hooks.ts` | 新增 `useAddMCPServer`, `useUpdateMCPServer`, `useDeleteMCPServer` 等 hooks | 中 |
| 4 | `frontend/src/components/workspace/settings/tool-settings-page.tsx` | 大幅重构：添加表单（新增/编辑）、删除确认、类型切换（stdio/sse/http）、动态字段 | **大** |
| 5 | `frontend/src/core/i18n/locales/en-US.ts` | 新增大量表单标签、占位符、验证错误提示文案 | 中 |
| 6 | `frontend/src/core/i18n/locales/zh-CN.ts` | 同上，中文翻译 | 中 |
| 7 | `frontend/src/app/mock/api/mcp/config/route.ts` | Mock API 数据需要更新以匹配新类型定义 | 小 |
| 8 | 新增：表单验证 schema | 如使用 zod，需定义 `MCPServerConfigSchema` | 小 |

**总计**：约 **6-8 个文件**，其中 `tool-settings-page.tsx` 改动最大（可能新增 200-400 行表单逻辑）。

**工作量估算**：前端开发约 **1-3 人天**（取决于表单复杂度设计）。

---

### 2.5 方案 D：容器化部署（SSE/HTTP 模式）

**原理**：将 Playwright MCP Server 作为独立容器运行，DeerFlow 通过 SSE 或 HTTP 方式连接，适合服务端/生产环境部署。

**需要改动的文件**：

| # | 文件路径 | 改动内容 | 工作量 |
|---|---------|---------|--------|
| 1 | `docker-compose.yaml` | 新增 `playwright-mcp` service | 小 |
| 2 | 新增：`docker/playwright-mcp/Dockerfile` | 构建 Playwright MCP 镜像（Node.js + Playwright 浏览器依赖） | 中 |
| 3 | `backend/packages/harness/deerflow/config/extensions_config.py` | 预置 http/sse 类型的默认配置（指向容器服务名） | 极小 |
| 4 | `docs/` 文档 | 容器化部署说明 | 极小 |

**潜在问题**：
- Playwright 浏览器依赖体积大（Chromium + 系统依赖），镜像可能 > 1GB
- 需要考虑浏览器沙箱安全（Docker 中运行 Chromium 需 `--no-sandbox`）
- SSE/HTTP 传输需要确认 `@playwright/mcp` 是否支持（官方主要支持 stdio）

**总计**：约 **3-4 个文件**，但 Docker 镜像构建和调试可能耗时。

---

## 三、风险评估

### 3.1 运行时依赖风险

| 风险项 | 等级 | 说明 |
|--------|------|------|
| Node.js 环境 | 中 | stdio 方式需要运行环境有 Node.js ≥ 18 和 npx |
| Playwright 浏览器下载 | 中 | 首次运行 `@playwright/mcp` 可能自动下载 Chromium，耗时且需网络 |
| 工具数量膨胀 | 低 | Playwright MCP 可能暴露 10-20 个 tools，会占用 LLM context |
| 沙箱安全 | 低 | 浏览器自动化本身有安全风险，但 MCP 框架已有权限隔离 |

### 3.2 与现有 E2E Playwright 的关系

项目中 `frontend/` 目录下已有 `@playwright/test` 用于 E2E 测试，**这与 Playwright MCP Server 是完全不同的东西**：

| 对比项 | `frontend/tests/e2e/` | Playwright MCP |
|--------|---------------------|----------------|
| 目的 | 前端自动化测试 | AI Agent 浏览器工具 |
| 包名 | `@playwright/test` | `@playwright/mcp` |
| 运行时机 | CI/CD 或本地测试 | 运行时由 Agent 调用 |
| 与项目关系 | 开发依赖 | 可选的运行时 MCP Server |

两者互不干扰，可以同时存在。

---

## 四、推荐方案

### 4.1 短期（最小改动）

采用 **方案 B：内置默认配置** + **方案 A 文档说明**。

- 在 `extensions_config.py` 中预置 Playwright MCP 默认配置（默认 `enabled: false`）
- 前端国际化文案补充
- 用户只需在前端 UI 打开开关即可启用
- 同时提供手动配置的文档

**改动量**：≈ **3 个文件，50 行以内代码**。

### 4.2 中期（体验优化）

采用 **方案 C：前端 UI 增强**。

- 在 `tool-settings-page.tsx` 中增加 MCP Server 的添加/编辑/删除表单
- 支持 stdio / sse / http 三种类型的动态字段切换
- 这样用户不仅可以启用 Playwright MCP，还可以自行添加其他 MCP Server

**改动量**：≈ **6-8 个文件，300-500 行代码**，约 1-3 人天。

### 4.3 长期（生产部署）

采用 **方案 D：容器化部署**。

- 将 Playwright MCP 作为独立容器，通过 SSE/HTTP 提供服务
- 多个 DeerFlow 实例可以共享同一个 Playwright MCP 服务
- 避免每个 LangGraph Server 进程都启动独立的 Playwright 子进程

---

## 五、结论

| 集成深度 | 改动文件数 | 代码行数 | 人天估算 |
|---------|-----------|---------|---------|
| 最小集成（配置级） | 0 | 0 | 0（仅文档） |
| 推荐集成（内置默认） | 2-3 | ~30-50 | 0.5 天 |
| 完整集成（UI 增强） | 6-8 | ~300-500 | 1-3 天 |
| 生产集成（容器化） | 3-4 + Docker | ~100 + Dockerfile | 1-2 天 |

**核心结论**：DeerFlow 的 MCP 框架设计已经非常完善，集成 Playwright MCP **不需要改动核心架构**。最简单的方式是零代码（配置文件），最推荐的方式是内置默认配置（2-3 个文件小改动），完整体验需要前端表单增强（1-3 人天）。
