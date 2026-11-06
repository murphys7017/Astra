# Astra 实现状态

**状态**：最小底座与首轮硬化门槛已完成，已接入第一条原生消息响应链路
**日期**：2026-11-06

## 已实现

当前实现是标准库优先的单进程、本地异步 Runtime，位于仓库根目录的 `astra/` 包中。

- Component 的注册、启动、停止和释放；
- CapabilitySpec、CapabilityRequirement 和 Provider 解析；
- 缺失能力、版本不匹配和 Provider 歧义的确定性失败；
- Scope 的父子关系、取消信号和逆序清理；
- Workflow Run、Invocation、Provider Binding 和基础终态；
- 一次 Run 内固定组合代际和 Provider Binding；
- 配置级 Generation 切换、旧代际 active Run 排空和失败回滚；
- Python 显式定义的串行 Workflow；
- 路由 Workflow 和子 Workflow 调用；
- Workflow 作为 Workflow Component 对外提供 Capability；
- 统一结构化日志入口、内存 Sink 和最小备用 Sink；
- 日志 Sink 故障隔离、字段脱敏和长度限制；
- JSON RuntimeConfig 的结构校验、敏感配置边界和不可变 Composition Snapshot；
- 插件实例命名空间、全局启用开关、插件自声明 Schema、默认值、版本迁移和校验；
- `plugins/` 目录下的原生插件与外部生态兼容插件分类入口，以及递归 Manifest 发现；
- 可信本地 Plugin Manifest 发现、入口加载、依赖排序和注册事务回滚；
- JSON 选择启用组件、Workflow 和 Capability Provider Binding，并在应用前校验能力和版本匹配。
- JSON composition 可编译为固定的配置 Workflow，支持串行顺序、连续并行组和无条件单出边跳转；
- 并行 Workflow 的结果汇合；
- Scope 绑定的内存 EventBus 和事件触发 Workflow；
- 有序异步 Stream、生产者取消和单一终态；
- Pipeline Workflow 的有序数据传递；
- Provider 执行前的最小权限检查。
- External Effect 的重试安全声明和幂等键契约校验；
- `resources.max_concurrent_children` 并行子 Workflow 限制和 EventBus 待处理上限；
- Capability 声明与实际处理器的一致性校验；
- 可重复的本地直接调用与 Workflow/Capability 调用性能基线脚本；
- 非阻塞日志 Sink、事件 payload 冻结和取消/资源释放诊断。
- EventBus 事件触发 Workflow 的全局待处理上限，以及 NonBlockingLogSink 的有界队列和丢弃计数；
- `plugins/native/message_response` 第一条原生插件迁移切片，以及通过 PluginLoader、Capability 和 Workflow 的端到端运行入口；

插件回滚当前只覆盖 Runtime 注册表；由于插件在进程内执行，导入或工厂副作用仍要求插件自身保持可控。

## 当前验证

使用以下命令验证：

```powershell
python -m unittest discover -s tests -v
pytest -q
python -m compileall -q astra tests tools
python -m tools.benchmark_runtime --iterations 1000
python -m tools.benchmark_runtime --iterations 1000 --max-overhead-us 150
```

当前测试包含 44 个用例，覆盖组件生命周期、Capability 契约归一化、绑定校验、串行/路由/并行/Pipeline/Stream Workflow、子 Workflow、Workflow Component、日志故障隔离、非阻塞日志、敏感字段脱敏、取消/超时收束、JSON 配置与组合执行、资源上限、事件背压、默认拒绝权限、事件订阅、Generation 切换、停止边界、临时本地插件加载、插件配置 Schema、Schema 校验、插件配置热重载边界和原生消息响应插件链路。

## 明确保留在底座之外的后续能力

以下内容按开发计划保留在后续阶段：

- 已启动插件组件集合的热替换及其生命周期切换；配置级 Generation 切换和旧组合排空已经完成；
- 更复杂的 Stream 缓存策略和跨组件统一资源配置；当前 Stream 采用消费者驱动、单步读取，EventBus 与日志 Sink 已有有界策略；
- 不同机器和部署环境的长期性能样本库；当前本地性能基线支持显式阈值门禁；
- 外部模块自动发现、扫描和适配壳生成。

当前代码没有引入具体模型、平台、设备或外部项目兼容逻辑。

## 进入插件接入阶段前的硬化门槛

以下项目是从“首轮可运行”到“可以承载真实插件”的完成条件：

- [x] External Effect 的重试安全声明具有幂等键约束，未声明安全策略的能力不会被 Runtime 自动重试；
- [x] 并行任务、Stream、EventBus 和日志队列具有明确的资源边界或背压行为；Stream 当前没有内部无界缓存，EventBus 和日志 Sink 使用有界待处理任务；
- [x] 取消、停止、超时和资源释放能够区分请求、终止和释放事实；
- [x] Composition Generation 支持固定快照、配置级切换和旧代际 active Run 排空；插件组件替换仍需单独设计；
- [x] 性能基线提供本地重复测量和显式阈值门禁，消息热路径不执行插件发现和依赖扫描；
- [x] 上述门槛均有回归测试和文档说明。

底座完成条件已经满足。第一条原生插件链路已经接入，下一阶段继续迁移边界清晰的系统功能。插件组件热替换和自动适配仍作为独立能力推进。
