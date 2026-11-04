# Astra 底座设计验收表

本文用于判断设计是否足以进入实现阶段。它描述可观察行为，不要求现在编写测试代码。

## 边界验收

- [ ] Kernel 不依赖 AG99、AG99live、AstrBot 或 Live2D 的具体类型。
- [ ] Persona、Memory、Agent、设备和平台逻辑都有明确的领域归属。
- [ ] Workflow 可以作为 Component，但不要求 Kernel 理解业务流程。
- [ ] Event 是事实通知，不隐式承担命令或请求响应职责。

## 能力验收

- [ ] Capability 有身份、版本、输入、输出和交互模式。
- [ ] Provider 缺失、版本不兼容和歧义解析会确定性失败。
- [ ] 一次 Invocation 会固定自己的 Provider Binding。
- [ ] 调用方替换 Provider 时无需依赖 Provider 内部实现。

## 执行验收

- [ ] Run、Invocation、Scope 和领域身份可以区分。
- [ ] 父 Run 取消会向子调用传播。
- [ ] 后台任务必须显式脱离父 Scope。
- [ ] 已结束执行不会接收迟到结果。
- [ ] Kernel 终态与领域完成事实不会混淆。

## 流和事件验收

- [ ] Stream 保持顺序并且只有一个终态。
- [ ] Stream 取消可以到达生产者并释放资源。
- [ ] Event 订阅绑定 Scope，Scope 停止时自动注销。
- [ ] 订阅者异常不会破坏其他订阅者或发布方。
- [ ] 第一阶段不会把 Token 或音频分块默认广播到 EventBus。

## 权限和副作用验收

- [ ] 权限拒绝发生在 Provider 执行之前。
- [ ] 外部副作用声明幂等性或不可安全重试。
- [ ] Runtime 停止不会假定外部业务副作用自动撤销。
- [ ] Managed Resource 的释放有明确 Owner。

## 进入实现阶段的门槛

所有边界验收必须有明确结论；执行、流、事件和权限验收可以先标记为“待实现验证”，但不能保留未定义的语义。

