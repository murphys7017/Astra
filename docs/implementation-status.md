# Astra 实现状态

**状态**：Stage 4 首轮实现进行中
**日期**：2026-11-05

## 已实现

当前实现是标准库优先的单进程、本地异步 Runtime，位于仓库根目录的 `astra/` 包中。

- Component 的注册、启动、停止和释放；
- CapabilitySpec、CapabilityRequirement 和 Provider 解析；
- 缺失能力、版本不匹配和 Provider 歧义的确定性失败；
- Scope 的父子关系、取消信号和逆序清理；
- Workflow Run、Invocation、Provider Binding 和基础终态；
- 一次 Run 内固定组合代际和 Provider Binding；
- Python 显式定义的串行 Workflow；
- 路由 Workflow 和子 Workflow 调用；
- Workflow 作为 Workflow Component 对外提供 Capability；
- 统一结构化日志入口、内存 Sink 和最小备用 Sink；
- 日志 Sink 故障隔离、字段脱敏和长度限制；
- JSON RuntimeConfig 的结构校验、敏感配置边界和不可变 Composition Snapshot；
- 可信本地 Plugin Manifest 发现、入口加载、依赖排序和注册事务回滚；
- JSON 选择启用组件、Workflow 和 Capability Provider Binding。
- 并行 Workflow 的结果汇合；
- Scope 绑定的内存 EventBus 和事件触发 Workflow；
- Provider 执行前的最小权限检查。

插件回滚当前只覆盖 Runtime 注册表；由于插件在进程内执行，导入或工厂副作用仍要求插件自身保持可控。

## 当前验证

使用以下命令验证：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q astra tests
```

当前测试覆盖组件生命周期、Capability 歧义绑定、串行和路由 Workflow、子 Workflow、Workflow Component、日志故障隔离、敏感字段脱敏、超时收束、JSON 配置和临时本地插件加载。

## 尚未实现

以下内容按开发计划保留在后续阶段：

- Stream、Pipeline 和更完整的 Control 语义；
- JSON 组合声明到实际图执行的组合引擎；当前由显式 Python Workflow 执行；
- Runtime 运行中的配置热更新、Generation 切换和旧组合排空；
- 资源限制、背压和更完整的故障策略；
- 性能基线和热路径测量；
- 外部模块自动适配。

当前代码没有引入具体模型、平台、设备或外部项目兼容逻辑。
