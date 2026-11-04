# Astra 底座实施计划

本文把 Base Design 0.2 转换为可执行的工程阶段。当前计划仍然以单进程、本地 Python 为第一范围，不提前实现远程组件、DSL 或完整插件市场。

## 阶段 0：基线和测量准备

目标是让后续的设计验证和 AG99 迁移有共同参照。

交付内容：

- 固定当前文档基线和术语；
- 记录 AG99 当前的关键请求和实时路径；
- 建立启动时间、首响应、首 Token、完整响应、取消和资源占用的测量方法；
- 明确哪些代码属于消息热路径，哪些代码属于启动或管理路径。

完成标准：在不引入 Astra 的情况下，可以重复测量当前系统的主要性能指标。

## 阶段 1：最小 Component Runtime

目标是验证 Component、Capability、Scope 和生命周期语义。

交付内容：

- Component 的发现、注册、启动、停止和释放；
- Capability 的声明、查询、解析和唯一绑定；
- Provider 缺失、版本不兼容和歧义时的确定性错误；
- Run、Invocation、Scope、父子关系和取消传播；
- 运行时资源的归属和清理；
- 基础 Trace 和终态记录。

完成标准：两个不同的组件可以提供同一能力，调用方无需修改即可切换；停止 Scope 可以释放订阅和后台任务。

## 阶段 2：离线 Plugin 和 Profile

目标是验证组件和工作流可以作为本地插件被管理。

交付内容：

- 本地插件目录或已安装包的发现；
- Plugin Manifest 的最小语义；
- 插件包含多个 Component、Capability 或 Workflow 的能力；
- 本地依赖检查和注册事务；
- 插件启用、禁用、停止和排空；
- Profile Generation；
- 插件载入失败时的回滚和诊断。

完成标准：插件变更影响新的 Run，现有 Run 继续使用旧 Generation；插件卸载不会遗留已注册能力、订阅或后台任务。

## 阶段 3：Workflow Composition

目标是验证多条 Workflow 的串行、并行、路由、管道和事件协作。

第一批 Workflow：

- InputWorkflow：接收和规范化输入；
- RouterWorkflow：选择后续路径；
- ConversationWorkflow：提供普通回复和流式输出；
- TaskWorkflow：执行多步骤任务；
- RecordWorkflow：订阅事实并记录结果。

交付内容：

- Workflow Definition 与 Workflow Run 的区分；
- Workflow 作为 Workflow Component 对外提供 Capability；
- 串行调用和明确结果传递；
- 并行子 Run 和合并规则；
- Route 分支；
- Stream 连接和终态；
- Event 触发独立 Workflow；
- Contribute 作为结构化上下文贡献；
- 失败、取消和迟到结果隔离。

完成标准：开发者可以只依赖公开 Capability 组合出新的 Workflow，且一次 Run 内的 Definition、Generation 和 Provider Binding 保持稳定。

## 阶段 4：性能不回退验证

目标是证明 Runtime 的通用机制不会降低现有请求和实时表现。

交付内容：

- Astra 空运行时开销测量；
- 直接本地调用与 Capability 调用的对比；
- 串行、并行和流式流程的对比；
- 首响应、首 Token、完整响应和取消延迟对比；
- 高速流和实时输出的压力测试；
- Trace、权限和事件功能开启前后的开销对比。

完成标准：热路径额外开销在预算内，关键性能指标不低于当前基线；发现回退时先修复底座边界或调用路径，再继续迁移。

## 阶段 5：AG99 薄适配

目标是把已有 AG99 能力接入 Astra，同时保持原有内部实现和行为。

建议顺序：

1. Context Contributor；
2. Router；
3. Memory / Knowledge；
4. Agent Loop 或 Task Workflow；
5. Persona Expression；
6. Output 和 AG99live 高层接口。

每接入一项能力，都需要同时验证：输入输出、生命周期、取消、权限、性能和领域状态 Owner。

## 阶段 6：按需求扩展

只有前述阶段验证完成后，才考虑：

- HTTP、WebSocket 和 IPC Component Host；
- 持久化任务和可靠事件；
- Workflow IR、DSL 和可视化编辑器；
- 热重载和更复杂的 Profile 管理；
- AstrBot 兼容层；
- 更完整的插件生态。

## 实施原则

- 先测量，再抽象；
- 先适配现有能力，再重构内部实现；
- 先固定一次 Run 的组合，再讨论热更新；
- 让高频实时数据留在领域 Runtime 内部；
- 让每个公共状态只有一个明确 Owner；
- 公共契约的每次变化都记录需求、影响和验证结果。

