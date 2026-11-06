# Astra 原生插件

这里放按照 Astra 公共契约实现的项目功能插件。每个插件包放在本目录的直接子目录中。

原生插件可以包含普通 Component、Workflow Component、Capability 和自己的配置 Schema。

当前原生迁移插件包括 `qq_adapter/`、`model_providers/` 和 `personal_response/`，共同组成 QQ → Personal → LLM → QQ 的消息链路。
