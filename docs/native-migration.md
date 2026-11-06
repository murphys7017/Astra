# 原生插件迁移第一条链路

本文记录从真实外部模块开始接入 Astra 的第一个最小切片。它用于验证迁移后的模块可以遵循 Astra 的 Plugin、Component、Capability 和 Workflow 边界运行。

## 当前切片

`plugins/native/message_response/` 提供一个原生插件实例。它声明 `message.respond` Capability，接收字符串或包含 `text`、`metadata` 的消息对象，返回规范化的响应对象。

当前切片保留了原消息输出清理逻辑中的两个行为：移除隐藏的 `system_reminder` 标记，压缩连续空行。响应前缀通过插件配置传入，插件配置仍然由统一 JSON 入口提供。

## 运行链路

1. `PluginLoader` 从 `plugins/` 递归发现原生插件 Manifest。
2. Runtime 根据实例配置创建 `native.message-response` Component。
3. JSON 绑定将 `message.respond` 指向该 Component 的版本 `1` Provider。
4. 宿主注册一个串行 Workflow，由 Workflow 通过 Capability 发起响应。
5. Runtime 固定本次 Run 的组合和 Provider Binding，并返回响应结果。

这条链路没有把插件内部函数名暴露给 Workflow。Workflow 只依赖公开的 Capability，插件内部可以继续替换实现。

## 本地验证

```powershell
python tools/run_native_message.py "hello <system_reminder>private</system_reminder>"
```

预期输出：

```json
{"text": "Astra: hello", "metadata": {}}
```

对应的回归测试位于 `tests/test_native_message_plugin.py`。当前 Workflow 在宿主启动脚本中注册，后续若需要由插件直接声明 Workflow，再补充独立的 Workflow 导出契约，不扩大本次迁移切片的底座范围。

## 当前边界

这是一条可运行的原生迁移验证链路，不代表外部项目的全部业务功能已经迁移。下一条迁移应继续选择一个输入、调用或输出边界清晰的系统功能，并保持同样的 Capability 与 Workflow 验证方式。
