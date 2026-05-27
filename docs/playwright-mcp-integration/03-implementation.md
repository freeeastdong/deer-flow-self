# Playwright MCP 集成实施记录

> 实施日期：2026-05-12
> 方案：内置默认配置（方案 B）

---

## 一、已完成的改动

### 1. 后端：预置 Playwright MCP 默认配置

**文件**：`backend/packages/harness/deerflow/config/extensions_config.py`

**改动内容**：
- 在 `ExtensionsConfig.from_file()` 方法中，加载配置文件后调用 `_apply_builtin_defaults()`
- 新增 `_apply_builtin_defaults()` 方法，当 `mcp_servers` 中不存在 `playwright` 时，自动注入默认配置
- **默认配置**：
  - `enabled: false`（默认禁用，用户需手动开启）
  - `type: "stdio"`
  - `command: "npx"`
  - `args: ["-y", "@playwright/mcp@latest"]`
  - `description`: 说明这是浏览器自动化工具

**设计决策**：
- 用户已有配置文件中若已存在 `playwright`，**不会覆盖**，确保用户自定义配置优先级最高
- 无配置文件的新用户也能在 UI 中看到 Playwright MCP 条目

### 2. 前端：国际化文案 + UI 显示优化

**文件 1**：`frontend/src/core/i18n/locales/types.ts`
- 在 `settings.tools` 类型定义中新增 `mcpLabels: Record<string, { name: string; description: string }>`

**文件 2**：`frontend/src/core/i18n/locales/en-US.ts`
- 添加 `mcpLabels.playwright` 英文文案：
  - name: `"Playwright Browser Automation"`
  - description: 说明功能及环境要求（Node.js ≥ 18）

**文件 3**：`frontend/src/core/i18n/locales/zh-CN.ts`
- 添加 `mcpLabels.playwright` 中文文案：
  - name: `"Playwright 浏览器自动化"`
  - description: 中文功能说明及环境要求

**文件 4**：`frontend/src/components/workspace/settings/tool-settings-page.tsx`
- `MCPServerList` 组件中新增 `useI18n()` 调用
- 为每个 MCP Server 条目查找对应的 `mcpLabels` 映射
- 显示逻辑：优先使用国际化友好名称（`label.name`），fallback 到原始 server key；描述同理

**设计决策**：
- 采用 `mcpLabels` 映射表而非直接修改后端描述，因为：
  1. 后端 `description` 字段用户可自定义，不应被代码写死覆盖
  2. 国际化应由前端统一管理
  3. 后续添加其他内置 MCP Server 时，只需新增映射条目即可

---

## 二、改动统计

| 项目 | 数量 |
|------|------|
| 修改文件数 | 4 |
| 新增文件数 | 1（本文档） |
| 后端代码行数变化 | +22 行 |
| 前端代码行数变化 | +22 行（i18n）+ 8 行（UI） |

---

## 三、验证结果

- [x] 后端 `extensions_config.py` 语法检查通过 (`python -m py_compile`)
- [x] 前端修改文件 TypeScript 编译无新增错误 (`tsc --noEmit`)

---

## 四、用户启用方式

### 方式一：前端 UI（推荐）

1. 打开 DeerFlow 设置 → Tools 标签页
2. 找到 **"Playwright Browser Automation"** / **"Playwright 浏览器自动化"**
3. 打开右侧开关
4. 确保运行环境已安装 Node.js ≥ 18（首次使用会自动下载 `@playwright/mcp`）

### 方式二：手动配置文件

在 `extensions_config.json` 中添加：

```json
{
  "mcpServers": {
    "playwright": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "description": "Browser automation via Playwright MCP"
    }
  }
}
```

---

## 五、后续可选优化

1. **前端 UI 增强**（阶段 4）：支持在 UI 上直接添加/编辑/删除任意 MCP Server
2. **容器化部署**（阶段 5）：将 Playwright MCP 作为 Docker 服务独立部署
3. **环境检查脚本**：在 `scripts/check.py` 或 `scripts/doctor.py` 中增加 Node.js 版本检测提示
