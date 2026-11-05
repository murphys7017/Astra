# Astra 本地性能基线

当前只提供可重复的本地测量脚本，不把单台机器上的结果写成固定性能承诺。

运行：

```powershell
python -m tools.benchmark_runtime --iterations 1000
```

需要把基准作为回归门禁时，可以显式传入本机已经校准的上限：

```powershell
python -m tools.benchmark_runtime --iterations 1000 --max-overhead-us 150
```

超过上限时脚本返回退出码 `2`。上限应由稳定的执行环境和历史样本校准，不把单台机器的一次测量结果写成跨环境承诺。

脚本比较：

- 组件内部直接函数调用；
- 经过 Runtime、Capability Resolver、Workflow Run 和 Invocation 的调用。

输出中的 `runtime_overhead_us` 用于观察底座机制的额外开销。后续增加 Stream、并行、事件和插件启动场景时，继续沿用同一脚本风格扩展独立测量项。
