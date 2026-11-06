# Astra 插件目录

这里存放可以被 Astra Runtime 离线载入的插件包。`astra/` 保存底座运行时和插件加载协议，`plugins/` 保存实际扩展。

当前按插件来源划分两个目录：

- `native/` 保存按照 Astra Component、Capability 和 Workflow 原生实现的项目功能插件；
- `compatibility/` 保存外部生态兼容插件，例如社区插件兼容宿主。

每个实际插件放在对应分类目录的子目录中，并包含自己的 `astra.plugin.json`。PluginLoader 从指定的 `plugins/` 根目录递归发现 Manifest，插件包之间通过 Manifest 和 Capability 发生关系。

```text
plugins/
├─ native/
│  └─ <plugin-id>/
│     ├─ astra.plugin.json
│     └─ plugin.py
└─ compatibility/
   └─ <adapter-id>/
      ├─ astra.plugin.json
      └─ plugin.py
```

插件配置继续由根 Runtime JSON 的 `plugins.instances` 管理。插件目录本身保存代码和 Manifest，运行参数、密钥引用和启用状态进入统一配置入口。
