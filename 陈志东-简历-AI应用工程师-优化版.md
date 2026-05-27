# 陈志东 - 简历

## 基本信息

**陈志东** | 男 | 29岁  
📱 13422177650 | 📧 478573380@qq.com  
**求职意向：AI应用工程师 / Python后端开发工程师** | 期望城市：杭州

---

## 个人优势

1. **AI应用工程化能力**：具备从0到1构建AI Agent平台的能力，熟悉LangGraph/LangChain智能体编排、RAG全流程、多模态AI生成（文生图/文生视频）集成与工程化落地。
2. **开源框架二次开发经验**：基于字节跳动开源 DeerFlow 2.0（LangGraph-based Super Agent Harness）完成管理后台、应用中心、ComfyUI本地生图/生视频能力的独立集成与改造。
3. **高性能后端开发**：3年Python后端经验，精通FastAPI异步架构、SQLAlchemy ORM、Pydantic数据验证，具备复杂系统的模块化设计与可测试性实践经验。
4. **大规模云平台运维**：具备OpenStack/OSP超百节点云平台的自动化部署与运维经验，擅长Shell/Python自动化脚本编写，能将基础设施经验反哺AI服务部署。

---

## 专业技能

| 方向 | 技术关键词 |
|------|-----------|
| **LLM & AI Agent** | LangGraph / LangChain / Agent Orchestration / RAG / Skill System / MCP |
| **前端开发** | Next.js 14 / React / TypeScript / iframe 集成 / i18n 国际化 |
| **后端开发** | Python / FastAPI / JWT / RBAC / 依赖注入 / SQLAlchemy / Pydantic |
| **AI生成** | ComfyUI / Stable Diffusion / 文生图 / 文生视频 / 工作流编排 |
| **数据存储** | Redis / Milvus 向量数据库 / MySQL |
| **运维部署** | Docker / Docker Compose / Kubernetes / Nginx / Shell |

---

## 项目经历

### AI Agent 平台功能扩展与实践（基于 DeerFlow 2.0）
**项目类型**：开源框架二次开发 + 本地 AI 生成能力集成 | **时间**：2025.03-至今

基于字节跳动开源 DeerFlow 2.0（LangGraph-based Super Agent Harness），在其多用户认证、数据隔离、长期记忆、子代理编排等框架基础上，独立完成管理后台、应用中心及 ComfyUI 本地生图/生视频能力的集成与改造。使用 FastAPI 开发 Admin 路由并实现 `require_admin` 权限依赖，基于 Next.js 开发 Admin Dashboard；通过 iframe 嵌入集成世界文学地图（Three.js 3D 地球可视化）与音乐电台（AI 语音助手 + TTS）两个垂直应用；将官方 Gemini API 方案替换为本地 ComfyUI 工作流调用，重写 `generate.py` 支持工作流提交、Prompt 动态注入、参考图上传、轮询获取结果，集成 Flux2 Klein 文生图与 Wan 文生视频工作流，实现 Agent 驱动的本地多模态 AI 生成。

**技术栈**：LangGraph / FastAPI / Next.js / React / TypeScript / ComfyUI API / iframe 嵌入 / Docker

---

### 智能问答系统（RAG 后端服务）
**项目类型**：个人项目 | **时间**：2025.09-至今

独立设计并实现基于检索增强生成（RAG）技术的智能问答后端系统，针对特定文档知识库提供精准、可溯源的问答服务。使用 LangChain 对文档进行文本分割，调用 DashScope Embeddings 将文本块转换为向量并存储至 Redis 向量数据库构建知识库；用户提问时从向量库检索最相关文档片段作为上下文，结合大语言模型生成答案。基于 FastAPI 构建异步 RESTful API，利用 Pydantic 进行数据验证和请求/响应模型定义，采用 SQLAlchemy 异步驱动管理元数据，确保代码模块化与可测试性。

**技术栈**：Python / FastAPI / LangChain / LangGraph / SQLAlchemy / Pydantic / Redis / RAG

---

## 工作经历

**中兴通讯股份有限公司** | Python 开发工程师 | 2022.07 - 2025.08 | 杭州

- **红帽 OSP 云平台自动化部署系统**

  为简化部署流程，开发红帽 OSP 云平台自动化部署系统，实现从裸机到基础云平台的高度自动化部署。设计基于 Kickstart 的 RHEL 操作系统无人值守批量安装流程，运用 Python 编写构建自动化脚本，完成超 100 节点 OSP 集群的配置与核心服务部署，将单次部署耗时从 7 天缩短至 5 小时，部署错误率降低 40%，该方案成功应用于多个海外项目。

  **技术栈**：Shell / Python / Kickstart / RedHat OSP

- **中移六期 OpenStack 云平台适配与部署**

  参与运营商大型 OpenStack 私有云平台的部署与实施，整合异构服务器硬件，完成平台规模化部署。参与制定标准化部署流程，确保多节点部署一致性，解决不同厂商服务器在统一部署流程中的兼容性问题，支持了超过百个节点规模的异构云平台一次性成功部署，并建立了可复用的标准化部署流程。

  **技术栈**：OpenStack / Linux / Python

---

## 教育经历

**杭州电子科技大学** | 硕士 | 物理学 | 2019 - 2022  
**华南农业大学** | 本科 | 光电信息科学与工程 | 2015 - 2019
