# Astra 核心术语

| 术语 | 当前定义 | 关键边界 |
|---|---|---|
| Component | 可独立装载、提供能力并接受 Runtime 生命周期管理的功能实体 | 不是所有函数都需要成为组件 |
| Capability | 组件之间稳定、可版本化的调用契约 | 不等于具体实现，也不等于模型 Tool Schema |
| Provider | 当前提供某项 Capability 的 Component | Provider 是角色，不是独立基础类型 |
| Workflow | 调用和组合其他能力的可执行结构 | 可以作为 Component 对外提供能力 |
| Workflow Definition | 工作流的组合定义 | 不等于一次运行 |
| Workflow Run | 一次工作流执行 | 有自己的身份、Scope、终态和资源归属 |
| Invocation | 一次明确的 Capability 调用 | 属于某个 Run 或父 Invocation |
| Scope | 确定资源、订阅、权限和取消范围的运行环境 | 不等于全局可变上下文 |
| Context | 调用时可访问的受限运行环境 | 不应成为任意共享的全局字典 |
| Run ID | 一次执行的通用身份 | 用于因果关联和诊断 |
| Domain ID | 领域组件自己的身份，例如 turn_id、task_id | 不由 Kernel 解释其业务语义 |
| Stream | 有序的连续数据传递 | 必须有终态、取消和资源释放语义 |
| Event | 已发生的不可变事实通知 | 不隐含要求订阅者执行动作 |
| Router | 根据输入和上下文选择后续路径的能力 | 不自动拥有工具权限或执行职责 |
| Control | 改变执行状态的请求 | 是否支持由具体契约决定 |
| Application / Composition | 一组组件、能力绑定和工作流的当前运行组合 | 不等于 Runtime 本身；Profile 管理不属于第一阶段 |

## 关系图

```text
Application / Composition
        |
        v
Component --provides--> Capability
    |                       ^
    | requires               |
    +-----------------------+
        |
        v
Workflow --runs as--> Workflow Run --contains--> Invocation
                                      |
                                      v
                                    Scope
```

## 尚未冻结的词

以下词汇目前只作为讨论用语，尚未形成公共 API：`Binding`、`Contribution`、`Policy`、`Agent`、`Profile`、`Bundle`、`Workflow IR` 和 `Remote Host`。

