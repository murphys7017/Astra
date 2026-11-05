# Astra

Astra 是一个以 Component 和 Capability 为基础的可组合智能系统运行时。

开发者可以自由组织 Workflow。Workflow 可以消费其他组件提供的能力，也可以作为 Component 对外提供能力，并通过显式调用、流式连接、路由决策和事件通知进行协作。

当前仓库已完成**最小底座首轮闭环**：本地异步 Runtime、Workflow 组合、可信离线插件、JSON 启动配置、结构化日志、权限检查、流与事件收束以及性能基线均已有可运行实现和回归验证。

## 当前基线

- Python 是首选实现语言。
- 第一阶段只考虑单进程、本地执行。
- Component 是装载、替换和生命周期管理单位。
- Capability 是组件之间的稳定契约。
- Workflow 是能力组合，可以自身成为 Component。
- Runtime 负责通用运行机制，不负责具体智能业务。
- 外部项目和社区生态的接入属于后续适配层，不是底座运行时依赖。

## 文档入口

- [项目愿景](docs/vision.md)：Astra 要解决的问题和长期方向。
- [设计边界](docs/boundaries.md)：内核、组件、能力、工作流和事件的责任边界。
- [底座设计基线](docs/base-design.md)：核心对象、执行语义、生命周期、权限和第一阶段范围。
- [设计与实现验收表](docs/acceptance.md)：底座边界、首轮实现和后续未完成项的验收状态。
- [初步开发计划](docs/initial-development-plan.md)：从最小 Runtime、日志基础、插件和 Workflow 到后续适配层的详细阶段计划。
- [实现状态](docs/implementation-status.md)：当前已实现范围、验证结果和下一步工作。
- [JSON 配置与离线插件](docs/config-and-plugin.md)：启动配置、权限边界和本地插件载入行为。
- [性能基线](docs/performance-baseline.md)：本地 Runtime 路径的可重复测量方法。
- [核心术语](docs/terms.md)：当前统一词汇及其关系。
- [文档规划与路线](docs/roadmap.md)：文档阶段、验证阶段和暂缓事项。
- [架构决策](docs/decisions/ADR-0001-document-first.md)：为什么先做文档和边界设计。
- [组合编排决策](docs/decisions/ADR-0004-configured-composition.md)：JSON 组合语义和 Workflow 边界。
- [Vision 1.1 原文归档](docs/reference/vision-1.1.md)：用户提供的完整基线文档。

## 当前不承诺

本仓库尚未冻结 Python API、序列化格式、远程协议、Workflow DSL、插件兼容层或分布式调度模型。任何公共接口都应先经过用例、边界和验证标准的审查。

