# Personal 响应

这个插件把统一消息转换成模型请求，再把模型结果整理成可发送给 QQ 适配器的回复对象。

它通过当前 Workflow Run 的 `llm.generate` Capability 选择模型 Provider。Personal 只负责系统提示词、历史消息和当前用户消息的组织，不绑定 DeepSeek 或 MiniMax 的内部实现。
