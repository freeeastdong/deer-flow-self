# Phase 5：测试验证记录

## 验证目标

确保全链路语言传递机制工作正常，中文用户始终收到中文回复，英文用户始终收到英文回复，且未引入回归问题。

## 验证矩阵

| 测试项 | 类型 | 预期结果 |
|--------|------|---------|
| 前端 context 携带 locale | 集成 | `thread.submit()` 的 context 中包含 `"locale": "zh-CN"` |
| Gateway 转发 locale | 集成 | `config.configurable.locale` == `"zh-CN"` |
| Lead Agent prompt 含强制指令 | 单元 | `apply_prompt_template(locale="zh-CN")` 输出含 `YOU MUST respond ONLY in zh-CN` |
| Subagent prompt 含强制指令 | 单元 | `SubagentExecutor(locale="zh-CN")._create_agent()` 的 system_prompt 含 `<LANGUAGE_CONSTRAINT>` |
| Subagent 初始消息含锚点 | 单元 | `SubagentExecutor(locale="zh-CN")._build_initial_state()` 的 messages 含语言提醒 SystemMessage |
| 中文提问 → 中文回复 | 端到端 | 用户发送中文消息，Lead Agent 用中文回复 |
| 中文提问 + 子代理 → 中文回复 | 端到端 | 用户发送中文复杂任务，子代理用中文返回结果 |
| 英文提问 → 英文回复 | 端到端 | 用户发送英文消息，Lead Agent 用英文回复 |
| 未传 locale → 行为不变 | 回归 | 旧客户端未传 locale，system prompt 使用默认语言描述 |
| 前端切换语言 → locale 变化 | 集成 | 用户在前端从中文切换到英文，后续消息 context 中 locale 变为 `"en-US"` |

## 测试脚本参考

### 后端单元测试示例

```python
# tests/test_language_consistency.py

from deerflow.agents.lead_agent.prompt import apply_prompt_template


def test_apply_prompt_template_with_zh_cn_locale():
    prompt = apply_prompt_template(locale="zh-CN")
    assert "YOU MUST respond ONLY in zh-CN" in prompt
    assert "Language Constraint" in prompt


def test_apply_prompt_template_without_locale():
    prompt = apply_prompt_template()
    assert "the same language as the user's" in prompt
    assert "Language Constraint" in prompt  # 指令仍在，但使用默认描述


def test_subagent_executor_injects_language_constraint():
    from deerflow.subagents.executor import SubagentExecutor
    from deerflow.subagents.config import SubagentConfig

    config = SubagentConfig(
        name="test",
        description="test",
        system_prompt="You are a test agent.",
    )
    executor = SubagentExecutor(
        config=config,
        tools=[],
        locale="zh-CN",
    )
    
    # 由于 _create_agent 内部调用 create_agent，可通过 mock 验证
    # 或者添加一个获取 system_prompt 的辅助方法
```

### 前端集成测试验证方式

1. 打开浏览器 DevTools → Network 面板
2. 切换到 WebSocket/SSE 过滤器
3. 发送一条中文消息
4. 找到 `runs/stream` 请求，检查 payload：
   ```json
   {
     "input": { "messages": [...] },
     "context": {
       "locale": "zh-CN",
       ...
     }
   }
   ```

### 端到端验证对话示例

**测试用例 1：简单中文对话**
```
用户：你好，请介绍一下你自己
AI：你好！我是 Deer-Flow 的 Lead Agent...
（验证：回复为中文）
```

**测试用例 2：触发子代理的复杂任务**
```
用户：请帮我写一个 Python 脚本，计算斐波那契数列的前 20 项
AI：好的，我来为你编写这个脚本。
    [task 工具调用 → 子代理执行]
    子代理返回：我已经完成了斐波那契数列脚本的编写...
（验证：子代理的返回内容为中文）
```

**测试用例 3：工具输出为英文时的语言保持**
```
用户：搜索一下 Python asyncio 的最佳实践
AI：我来帮你搜索相关信息。
    [web_search 工具调用 → 搜索结果可能为英文]
    根据搜索结果，Python asyncio 的最佳实践包括：...
（验证：即使搜索结果是英文，AI 的总结仍为中文）
```

## 回归测试检查清单

- [ ] 未升级的旧前端客户端可以正常使用（不传递 locale）
- [ ] 英文界面用户（`locale: "en-US"`）的对话不受影响
- [ ] 不触发子代理的简单任务正常运作
- [ ] 触发子代理的复杂任务正常运作
- [ ] 系统提示词总长度增加在可接受范围内（约 +50 tokens）

## 性能影响评估

| 指标 | 变化 | 说明 |
|------|------|------|
| System Prompt 长度 | +~50 tokens | 语言约束指令 |
| Subagent System Prompt | +~30 tokens | `<LANGUAGE_CONSTRAINT>` 区块 |
| Subagent 初始 messages | +1 条 SystemMessage | 语言锚点 |
| 网络传输 | 无显著变化 | `locale` 字段仅 5-7 字节 |
| 推理延迟 | 无显著变化 | 额外 token 数量极少 |

## 已知限制

1. **模型不 100% 遵守**：即使使用 `"YOU MUST"` 等强约束词汇，部分 LLM（尤其是开源模型）仍可能偶尔切换语言。如出现这种情况，需要在 Phase 4 后考虑更激进的方案（如在模型层配置 `language` 参数）。
2. **locale 只传递不检测**：当前方案依赖前端声明的语言，而非后端检测用户输入的实际语言。如果用户用中文界面但发送英文消息，模型会按 `zh-CN` 回复。这是预期行为，与前端 UI 语言保持一致。

## 验证记录

| 日期 | 测试人 | 测试项 | 结果 | 备注 |
|------|--------|--------|------|------|
| 2026-05-07 | Kimi Code | 前端 TypeScript 类型检查 | ✅ 通过 | `tsc --noEmit` exit code 0 |
| 2026-05-07 | Kimi Code | 后端 Python 语法检查 | ✅ 通过 | 6/6 文件 ast.parse 通过 |
| 2026-05-07 | Kimi Code | prompt.py 内容逻辑检查 | ✅ 通过 | 强制指令、fallback、format 占位符均正确 |
| 2026-05-07 | Kimi Code | executor.py 内容逻辑检查 | ✅ 通过 | locale 属性、LANGUAGE_CONSTRAINT、语言锚点均正确 |
| 2026-05-07 | Kimi Code | task_tool.py 内容逻辑检查 | ✅ 通过 | runtime 读取 locale 并传递正确 |
