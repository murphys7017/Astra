# ADR-0004：JSON 只编排已注册 Workflow

## 状态

已决定，已完成首轮实现验证。

## 背景

RuntimeConfig 需要保存当前应用采用哪些 Workflow 以及它们的组合关系，但 JSON 不应变成第二套 Workflow DSL，也不应复制 Workflow 内部的步骤、条件或领域逻辑。

## 决策

1. JSON 只引用 Runtime 已注册并通过配置校验的 Workflow。
2. `composition.order` 表示顶层串行执行顺序。
3. `composition.parallel` 只能引用 `order` 中的连续成员；组内 Workflow 接收同一输入，结果按声明顺序组成列表并传给下一单元。
4. `composition.branches` 只表示无条件的单出边跳转；同一个 Workflow 不能声明多条出边，分支图不能成环或包含不可达边。
5. 条件判断仍由 Python `RouteWorkflow` 等显式 Workflow 实现，JSON 不包含条件表达式。
6. Runtime 在应用配置时编译并缓存 Configured Workflow；配置级重载先编译新 Generation，发布后只影响新的 Run，旧 Run 继续使用旧组合并完成排空。

## 结果

配置可以真正驱动有限的 Workflow 组合，同时保持 Workflow 内部语义由代码负责。非法引用、并行布局冲突、分支环和不可达分支会在启动前失败。更复杂的 DAG、条件路由、动态重组和可视化 DSL 仍需要单独的后续设计。

## 验证

当前回归测试覆盖串行组合、连续并行组、无条件分支、组合缓存、启动期拓扑错误和组合执行失败收束。
