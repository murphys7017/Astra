# Native message response

这是 Astra 迁移链路的第一个原生插件切片。它提供 `message.respond` Capability，接收字符串或带有 `text`、`metadata` 的消息对象，返回规范化后的响应对象。

当前实现保留 AG99live Adapter 中消息输出清理的核心行为，会移除隐藏的 `system_reminder` 标记并压缩多余空行。响应前缀通过插件配置传入。
