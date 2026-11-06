# Astra JSON 配置、编排与离线插件首轮实现

本文记录当前已经落地的 JSON 配置、编排与离线插件最小行为。它不是最终配置 DSL，也不提供管理界面。

## JSON 配置

RuntimeConfig 接受一个 JSON 对象，当前支持：

- `schema_version`：当前必须为 `1`；
- `plugins`：要载入的本地插件 ID，或带有全局开关和实例配置的对象；
- `components`：启用的组件名称；省略时使用已注册组件；
- `workflows`：启用的 Workflow 及其运行参数；
- `bindings`：Capability 到 Provider 和精确版本的绑定；
- `composition.order`：Workflow 顺序描述；
- `composition.parallel`：并行 Workflow 名称组；
- `composition.branches`：Workflow 之间的分支关系描述；
- `permissions`：当前组合的权限元数据；
- `resources.max_concurrent_children`：单个 Run 允许同时运行的子 Workflow 上限；
- `secrets`：密钥引用或受保护的内联密钥。

JSON 只选择当前组合和参数，不定义组件内部行为，也不取代 Python Workflow 的执行语义。Runtime 在启动前校验组件、Workflow、绑定的能力和版本以及组合引用，并生成不可变 Composition Snapshot。调用 `runtime.run_composition(...)` 时，`composition.order` 作为串行执行顺序，`composition.parallel` 中的连续成员以同一输入并行执行并按声明顺序汇合，`composition.branches` 作为无条件的单出边跳转。条件路由仍由 Python `RouteWorkflow` 提供，JSON 不因此变成完整 Workflow DSL。

并行组必须完整出现在 `composition.order` 的连续位置，不能互相重叠；分支图不能有环，也不能从同一个 Workflow 声明多条出边。分支不能从或指向并行组内部成员，只能以并行组的首节点作为跳转点。组合入口会固定当前已注册 Workflow 和 Composition Generation，运行中不会替换其中的成员。

资源配置当前支持 `resources.max_concurrent_children`。它限制同一 Run Scope 下并行子 Workflow 的数量，额度耗尽时新的子 Workflow 等待，Scope 取消会中断等待。EventBus 对普通异步订阅和事件触发 Workflow 分别设置待处理上限，超过对应上限的事件处理会被丢弃并记录诊断。

最小调用方式如下：

```python
config = RuntimeConfig.from_json("runtime.json")
runtime.apply_config(config)
await runtime.start()
result = await runtime.run_composition(input_value)
```

如果 Capability 声明了权限，配置可以用 `permissions.allow` 提供允许集合。调用前由 Runtime 检查，缺少权限时 Provider 不会执行；没有显式允许集合时，带权限的 Capability 默认拒绝。

密钥只能使用以下两种形式：

```json
{
  "secrets": {
    "provider_key": {"ref": "env:ASTRA_PROVIDER_KEY"},
    "temporary_key": {"value": "...", "protected": true}
  }
}
```

敏感字段不能散落在普通配置、Workflow 参数或权限对象中。配置的诊断输出只保留密钥名称，不保留密钥值。

日志接口对结构化字段按敏感键自动脱敏。组件和插件不得把密钥直接拼入日志消息文本。

## 插件实例配置

插件配置采用统一入口和插件自声明字段的两层结构。旧的插件 ID 数组仍可读取，带配置时使用对象形式：

```json
{
  "plugins": {
    "enabled": true,
    "config_dir": "./configs",
    "instances": {
      "demo": {
        "enabled": true,
        "schema_version": 1,
        "config": {
          "timeout": 30,
          "api_key": {"ref": "env:DEMO_KEY"}
        }
      }
    }
  }
}
```

统一层只负责插件总开关、实例启用状态、配置命名空间、版本号和不可变快照。示例中的 `config_dir` 当前作为配置目录元数据保留，不会触发额外文件扫描或合并。插件模块可以提供 `create_config_schema()`，返回自己的默认值、校验器和版本迁移器；提供该 Schema 后，入口工厂接收已经解析的只读配置。没有 Schema 的插件只能使用空配置，配置中出现字段会在载入前失败。

插件拥有自己的字段定义和初始化逻辑，核心不为具体插件增加配置分支。Schema 版本变化必须由插件提供迁移逻辑，校验失败不会注册任何组件。插件配置中的敏感字段只能使用密钥引用对象，Runtime 不在消息热路径解析或记录密钥值。

插件配置在 Runtime 启动前载入并初始化。当前 `reload_config(...)` 只切换已注册组件和 Workflow 的配置 Generation，插件配置、插件组件集合和组件生命周期变更会被拒绝，因此一次运行期间不会发生组件替换。配置编辑器、YAML、导入导出、加密存储和可视化管理属于后续配置插件能力。

## 离线插件

首轮插件是可信、本地、进程内的目录。每个插件目录包含 `astra.plugin.json` 和一个入口 Python 文件：

```text
plugins/
└─ native/
   └─ echo/
      ├─ astra.plugin.json
      └─ plugin.py
```

最小 Manifest：

```json
{
  "id": "echo",
  "version": "1",
  "entrypoint": "plugin.py:create_components",
  "components": ["echo.provider"],
  "dependencies": [{"id": "base", "version": "1"}]
}
```

入口工厂返回一个 Component 或 Component 可迭代对象。PluginLoader 会先发现并校验 Manifest，再按依赖和精确版本约束排序载入；组件注册发生在 Runtime 启动前，任何冲突都会回滚本次 Runtime 注册表批次。由于插件是可信进程内代码，模块导入或工厂执行产生的外部副作用无法被运行时回滚。

当前不支持在线安装、包管理、沙箱、跨进程隔离、不可信代码执行和热加载。插件停止时由 Runtime 统一执行 Component 的停止和释放。

## 最小使用顺序

```python
from astra import PluginLoader, Runtime, RuntimeConfig

config = RuntimeConfig.from_json("runtime.json")
runtime = Runtime()
PluginLoader("plugins").load_configured(runtime, config)
runtime.apply_config(config)
await runtime.start()
```

这段顺序体现了当前边界：插件负责提供 Component，JSON 负责选择组合，Runtime 负责启动和执行。原生插件和兼容插件可以放在不同分类目录中，由同一个插件根统一发现。

配置通常在 Runtime 启动前应用。Runtime 启动后可以通过 `reload_config(...)` 校验并发布新的配置 Generation，切换只影响新的 Run，旧 Run 继续使用原代际并在结束后排空。组件集合、插件载入和组件生命周期不在这条配置切换路径中改变。
