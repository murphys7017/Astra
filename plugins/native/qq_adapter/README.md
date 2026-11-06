# QQ / OneBot 消息适配器

这个插件把 OneBot 11 消息事件转换成 Astra 的统一消息对象，并通过 OneBot HTTP API 发送回复。

它提供两个 Capability：

- `qq.message.receive`：解析 OneBot 消息事件；
- `qq.message.send`：向私聊或群聊发送文本回复。

`qq.message.send` 需要 `network.qq` 权限。开发和测试时可以启用 `dry_run`，只生成发送请求，不访问 QQ 服务。

启用 `listen_enabled` 后，组件会在 Runtime 启动时打开一个本地 HTTP 接收入口，并把收到的 OneBot 事件交给配置中的 `workflow_name`。
