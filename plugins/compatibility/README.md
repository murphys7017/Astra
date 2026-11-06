# 外部生态兼容插件

这里放对外部插件生态提供适配的 Astra 插件。兼容插件负责外部插件的发现、加载、宿主接口转换、生命周期映射和 Component 包装。

兼容层的内部实现可以包含多个适配模块，但对 Runtime 只暴露 Astra Component、Capability 和 Workflow。
