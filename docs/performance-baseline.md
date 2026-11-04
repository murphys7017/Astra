# Astra 本地性能基线

当前只提供可重复的本地测量脚本，不把单台机器上的结果写成固定性能承诺。

运行：

```powershell
python -m tools.benchmark_runtime --iterations 1000
```

脚本比较：

- 组件内部直接函数调用；
- 经过 Runtime、Capability Resolver、Workflow Run 和 Invocation 的调用。

输出中的 `runtime_overhead_us` 用于观察底座机制的额外开销。后续增加 Stream、并行、事件和插件启动场景时，继续沿用同一脚本风格扩展独立测量项。
