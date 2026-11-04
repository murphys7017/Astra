# 文档规划与阶段路线

当前路线先完成设计资料和边界确认，再按阶段进入最小运行时实现。每个阶段都要区分“写入文档”“形成候选设计”和“经过验证”。

当前正式执行计划见 [`implementation-plan.md`](implementation-plan.md)。

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

## 开放问题

- Capability 版本兼容的后续范围是否需要从当前精确匹配扩展为范围匹配？
- 多 Provider 的策略绑定如何由 JSON 表达？
- Background Scope 如何显式脱离父 Run？
- EventBus 第一版是否需要有界队列和背压？
- 权限决策由 Runtime 内置策略、Policy Component，还是两者组合提供？
- Stream 的终态是否统一为一种结构，还是按 Capability 定义？

这些问题应在 Kernel Contract RFC 中逐项决策或标记为待验证。

