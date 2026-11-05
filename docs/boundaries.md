# Astra 设计边界

本文定义当前必须守住的边界。边界是设计约束，不是对未来所有实现细节的预先规定。

## Microkernel 负责什么

Microkernel 可以负责：

- Component 注册、装载、启动、停止和释放；
- Capability 声明、索引、解析和绑定；
- Invoke 的请求、结果、错误和因果身份；
- Run、Invocation、Scope 及其父子关系；
- 取消、超时和资源清理；
- 运行时资源所有权；
- 权限执行边界；
- 基础诊断、Trace 和终态记录。

## Microkernel 不负责什么

Microkernel 不直接负责：

- Persona 规则和表达策略；
- Prompt 组织、Memory 检索和 Knowledge 语义；
- Agent Loop、Planner 或具体 Router 算法；
- 音频、图像、设备逐帧计算和播放时钟；
- 具体平台、设备或消息协议；
- 领域副作用的业务补偿逻辑；
- 某种固定的聊天、任务或主动行为流程。

## Component 边界

一个 Component 只有在需要独立装载、替换、组合或管理生命周期时才进入组件边界。Component 应声明身份、版本、提供的 Capability、依赖的 Capability、作用域要求、权限和资源，并拥有清晰的启动、停止和释放行为。

领域组件内部可以继续使用自己的对象、算法和任务结构，不要求所有函数都包装成 Component。

## Capability 边界

Capability 描述可被其他组件使用的稳定能力。至少需要能够说明：

- 标识和契约版本；
- 输入和输出类型；
- Invoke 或 Stream 等交互模式；
- 成功、失败、取消、超时等终态；
- 超时、取消和背压语义；
- 权限要求和副作用性质。

Capability 的存在、是否允许 Agent 调用，以及如何生成模型可见的 Tool Schema，是三个不同层次的问题。

## Workflow 边界

Workflow 是能力组合，不是内核预设的业务流程。它可以调用 Component 或其他 Workflow，也可以对外提供 Capability。

Workflow 内部仍使用 Python 进行显式编排。RuntimeConfig 可以把已经注册的 Workflow 组织成有限的串行、连续并行组和无条件单出边组合，但不定义步骤、条件表达式或组件内部行为。Workflow Definition、Workflow Run 和 Workflow Component 要保持概念区分，不提前设计完整 DSL、图形编辑器或序列化 IR。

## Invoke、Stream、Event 和 Control

- **Invoke**：一次明确的能力调用，有请求、结果、错误和因果身份。
- **Stream**：有序的增量数据，有明确的结束、错误和取消语义。
- **Event**：已经发生的事实，用于松耦合通知，不代替请求响应。
- **Control**：对正在执行的 Run 或 Invocation 发出取消、停止、暂停、恢复、重试或审批请求。

这些是交互语义，不要求实现为四套独立总线。当前 Kernel 首轮实现了取消、停止收束和超时路径；暂停、恢复、审批和通用重试仍属于后续 Control 设计。

## 第一阶段边界

进入第一阶段：

- 单进程、本地 Python 执行；
- Component、Capability、Scope、Run、Invocation 和生命周期；
- Invoke、Stream、Router 和内存 EventBus；
- 取消、权限拒绝、资源清理和迟到结果隔离；
- 至少两种能力提供者和多条可组合 Workflow；
- 可信本地插件的离线载入；
- 使用 JSON 表达当前组合、绑定和运行参数；
- 执行已注册 Workflow 的有限 JSON composition；
- 统一日志数据入口和最小备用输出。

暂缓到后续阶段：

- HTTP、WebSocket、IPC 和 Android Host；
- 服务发现、分布式调度和持久化任务；
- Workflow DSL、IR 和可视化编辑器；
- 外部项目兼容层和自动适配层；
- 热重载和完整插件市场；
- 运行时资源限制、背压和完整 Control；
- 任何外部项目的整体迁移。

## 必须守住的不变量

1. 调用方依赖 Capability，不依赖提供者内部实现。
2. 同一执行状态具有明确的唯一写入 Owner。
3. 子执行的取消和资源归属可以解释。
4. 外部副作用不会因为普通重试而被无条件重放。
5. Scope 停止后，其订阅、后台任务和运行时资源可以清理。
6. 事件不会被隐式当成命令，调用关系需要可追踪。
7. 缺失能力、权限拒绝和 Provider 歧义应确定性失败。
8. 内核不依赖任何外部项目、平台或设备的具体类型。

