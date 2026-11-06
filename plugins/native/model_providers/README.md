# 常见大模型 Provider

这个插件提供可配置的 OpenAI 兼容 Chat Completions Provider。配置可以同时声明 DeepSeek、MiniMax 或其他兼容服务，每个服务都会成为一个独立的 `llm.*` Component。

当前 Capability：

- `llm.generate`：接收 `messages`，返回模型文本和基础元数据。

API Key 通过插件配置中的环境变量引用读取，例如 `{"ref": "env:DEEPSEEK_API_KEY"}`。真实调用需要 `network.llm` 权限。
