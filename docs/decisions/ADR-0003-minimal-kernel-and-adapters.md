# ADR-0003：最小 Kernel 与外部适配层分离

## 状态

已决定。

## 背景

Astra 未来需要接入其他项目中的模块、Agent、Workflow 和社区插件。直接把这些项目的兼容规则写入底座，会让 Kernel 依赖具体领域结构，增加实现负担，并使最小运行时难以验证。

## 决策

1. Astra Kernel 只实现通用的 Component、Capability、Workflow、Run、Scope、生命周期、取消、资源和诊断语义。
2. 外部项目接入通过底座之上的 Adapter Layer 完成。
3. Adapter 可以手工编写，也可以在底座稳定后根据模块元数据自动生成插件壳。
4. Adapter 负责把外部模块映射为 Component 和 Capability，并补充生命周期、依赖、权限和输入输出信息。
5. 外部项目的领域类型和业务流程不进入 Kernel。
6. 第一阶段不以任何外部项目兼容为完成条件。

## 结果

底座可以先以最小范围独立实现和验证；未来接入 AG99 模块、Agent、Workflow 或 AstrBot 社区插件时，只需要增加适配层，而不需要改变核心运行语义。

## 后续验证

在底座完成最小实现后，选择一个小型外部模块验证自动包装流程：识别可调用入口，生成 Component/Capability 声明，绑定生命周期和权限，并通过统一验收场景运行。

