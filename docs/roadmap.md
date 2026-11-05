# 文档规划与阶段路线

当前路线已经从设计资料准备进入最小运行时实现和硬化阶段。每个阶段仍要区分“写入文档”“形成候选设计”和“经过验证”。

当前正式执行计划见 [`initial-development-plan.md`](initial-development-plan.md)。

## 当前执行进度

| 范围 | 状态 | 说明 |
|---|---|---|
| D0-D3 文档、边界和验收基线 | 已完成首轮 | 愿景、边界、术语、设计基线和回归场景已经建立。 |
| 阶段 1：最小 Kernel 与日志 | 已完成首轮 | Component、Capability、Run、Scope、Invocation、日志和生命周期已实现。 |
| 阶段 2：JSON 配置和编排输入 | 已完成首轮 | JSON 校验、密钥边界、权限、Composition Snapshot 和有限 composition 执行已实现。 |
| 阶段 3：可信离线插件 | 已完成首轮 | 本地发现、Manifest、依赖版本、注册回滚和停止释放已实现。 |
| 阶段 4：Workflow Composition | 已完成首轮 | 串行、路由、并行、Pipeline、Stream、EventBus、子 Workflow 和 Workflow Component 已验证。 |
| 阶段 5：安全与故障收束 | 部分完成 | 取消、超时、权限、日志故障和资源清理已验证；外部副作用策略、资源限制和背压仍待实现。 |
| 阶段 6：性能和稳定性 | 基线完成 | 已有可重复的本地基准；持续性能门禁、高并发和高速流专项验证仍待补充。 |
| 阶段 7：自动适配层 | 暂缓 | 作为底座之上的独立插件，不作为 Kernel 完成条件。 |

## 文档阶段

### D0：仓库和文档基线

目标：建立仓库、归档输入材料、统一文档目录和状态标记。

产物：README、愿景、设计边界、术语表、文档规则、首个架构决策。

### D1：边界审查

目标：逐项审查 Kernel、Component、Capability、Workflow、Scope、Event 和副作用边界，找出冲突或重复概念。

产物：边界修订记录、开放问题清单、需要形成决策的主题列表。

### D2：Kernel Contract RFC

目标：只定义第一阶段需要验证的最小公共契约，不设计远程协议或完整插件系统。

至少覆盖：

- Component 生命周期；
- Capability 声明和解析；
- Invocation 请求、结果和终态；
- Run、Scope 和父子关系；
- Stream 结束和取消；
- Event 订阅和注销；
- 权限拒绝和外部副作用边界。

底座设计基线见 [`base-design.md`](base-design.md)，设计进入 RFC 前应以该文档为共同起点。

### D3：验证方案

目标：为每一条公共契约写出可观察的验收行为，暂时可以只写测试场景，不实现测试代码。

重点场景：缺失能力、版本不匹配、歧义解析、父子取消、迟到结果、日志故障、权限拒绝和资源释放。首轮实现已经把其中的核心调用场景落成标准库测试。

设计验收清单见 [`acceptance.md`](acceptance.md)。

运行代际和热路径约束记录在 [`ADR-0002-run-generation-and-performance.md`](decisions/ADR-0002-run-generation-and-performance.md) 中；最小 Kernel 与外部适配层的边界记录在 [`ADR-0003-minimal-kernel-and-adapters.md`](decisions/ADR-0003-minimal-kernel-and-adapters.md) 中。

## 实现阶段

实现阶段已经开始。首轮只验证单进程 Python Runtime 和最小 Workflow 组合，不把远程部署、DSL、兼容层或完整领域迁移混入首个实现目标。当前进度见 [`implementation-status.md`](implementation-status.md)。

## 后续决策主题

- Capability 版本兼容是否从当前精确匹配扩展为范围匹配；
- Background Scope 如何在不破坏父子资源边界的情况下显式脱离父 Run；
- EventBus、Stream 和日志队列的有界资源与背压策略；
- 外部副作用的幂等键、重试安全声明和补偿边界；
- 权限决策是否需要独立的 Policy Component；
- 热更新时的 Generation 切换、旧 Generation 排空和失败回滚；
- 更完整的 Control（暂停、恢复、审批和重试）是否进入 Kernel。

这些问题应在对应 RFC 或实现阶段逐项决策；当前不把它们隐含进已完成的最小底座。

