# ADR-0005：Composition Generation 的固定与排空

## 状态

已实现首轮边界。已支持配置 Generation 切换、Run 固定绑定和旧代际排空，插件组件替换仍另行设计。

## 背景

Astra 需要让一条 Workflow Run 在执行期间使用稳定的配置、Workflow、权限和 Provider Binding。真实插件接入后，配置或插件变化不能直接改变已经开始的运行。

首轮 Runtime 在启动前创建配置 Generation，并让每个 Run 记录一个 Generation 编号。配置级切换已经收敛为独立的 Generation 状态对象，插件组件集合仍由启动和插件生命周期管理。

## 目标决策

1. 每个 Generation 保存不可变的 RuntimeConfig、Composition Snapshot、已编译的配置 Workflow、权限集合和可见 Workflow 引用。
2. 新 Run 只绑定当前 Generation。Run、Invocation、Provider Binding 和 Workflow 参数都从绑定的 Generation 读取。
3. 配置切换先校验并编译新 Generation，成功后才发布为当前 Generation。失败不能改变当前 Generation。
4. 旧 Generation 进入 retired 状态，等待其 active Run 数量归零后释放快照。
5. 首轮切换只覆盖已注册 Component 和 Workflow 的配置、绑定与权限变化。插件选择、插件实例配置、插件 Component 的替换和组件生命周期切换另行设计。
6. 插件实例配置在启动前由 Schema 解析为只读配置，并传给插件初始化工厂。
7. `reload_config(...)` 遇到插件开关、插件配置目录或实例配置变化时拒绝发布新 Generation，避免在当前 Runtime 内隐式替换组件。
8. Generation 切换不改变已开始 Run 的 Scope、Provider Binding 和资源 Owner。

## 当前实现边界

当前 Runtime 允许在已启动状态下重新加载配置。重新加载只改变已注册组件和 Workflow 的配置、绑定、权限、参数及资源策略，不改变已启动组件集合。插件配置变化要求重新经历组件生命周期转换，因此不会通过这条路径发布。每个 Run 保存 Generation 状态引用，旧 Generation 在 active Run 清零后释放。

## 验证要求

- 长运行 Run 在配置切换后继续使用旧 Generation 的权限、绑定和 Workflow 参数；
- 切换后的新 Run 使用新 Generation；
- 新配置校验或编译失败时，当前 Generation 不改变；
- 旧 Generation 的 active Run 清零后才释放；
- Runtime 停止时等待所有 Generation 的 active Run 完成并释放资源。
