# 原生消息链路迁移

当前迁移目标是一条真实的最小消息闭环：

```text
QQ / OneBot
    ↓
QQ Adapter
    ↓
Personal Response
    ↓
DeepSeek 或 MiniMax Provider
    ↓
QQ Adapter
```

## 当前插件

- `plugins/native/qq_adapter/` 负责 OneBot 11 事件解析和 QQ 文本发送，提供 `qq.message.receive` 与 `qq.message.send`；
- `plugins/native/model_providers/` 提供可配置的 OpenAI 兼容模型 Provider，支持 DeepSeek、MiniMax 或其他兼容端点，提供 `llm.generate`；
- `plugins/native/personal_response/` 负责系统提示词、历史消息和当前用户消息组织，通过 `llm.generate` 获取模型响应；
- `tools/run_qq_personal.py` 注册并执行 `qq-personal-response` Workflow。

Workflow 的步骤是：

1. 解析 OneBot 消息事件；
2. 生成统一消息对象；
3. Personal 组织模型消息；
4. 通过当前 Runtime Binding 调用模型 Provider；
5. 将模型文本交给 QQ 适配器发送。

一次 Run 固定这次使用的 Provider Binding。Personal 不绑定 DeepSeek 或 MiniMax 的内部实现，模型选择由 JSON 配置完成。

## 配置边界

模型 API Key 和 QQ Access Token 使用环境变量引用：

```json
{
  "api_key": {"ref": "env:DEEPSEEK_API_KEY"},
  "access_token": {"ref": "env:ASTRA_QQ_ACCESS_TOKEN"}
}
```

模型调用需要 `network.llm` 权限，QQ 发送需要 `network.qq` 权限。QQ 适配器支持启动 HTTP 接收入口，接收到的 OneBot 事件可以直接触发配置的 Workflow。

## 本地验证

```powershell
python tools/run_qq_personal.py "你好" --dry-run
```

该命令使用真实的 Workflow、Personal 和模型 HTTP 协议。QQ 发送可以使用 `--qq-api-url` 指向 OneBot HTTP API，模型端点可以使用 `--endpoint` 指向 DeepSeek、MiniMax 或本地兼容服务。

端到端回归测试位于 `tests/test_native_qq_personal_flow.py`。测试通过本地 HTTP 服务验证 OneBot 输入、模型请求和 QQ 发送请求之间的完整数据流。

## 当前边界

这条链路已经覆盖输入适配、Personal 编排、模型 Provider 和输出适配。Personal 的完整行为策略、会话持久化、流式响应和更复杂的 QQ 消息段仍按后续迁移切片逐步加入。
