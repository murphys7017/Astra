"""Measure the current local Runtime overhead without external dependencies."""

import argparse
import asyncio
import json
from statistics import mean
import time

from astra import FunctionComponent, MemoryLogSink, Runtime, SerialWorkflow, StructuredLogger


async def measure(iterations: int) -> dict:
    handler = lambda request, invocation: request
    direct_component = FunctionComponent("benchmark", {"echo": handler})
    runtime = Runtime(StructuredLogger([MemoryLogSink()]))
    runtime.register_component(direct_component)
    workflow = SerialWorkflow("benchmark-workflow", [lambda context, value: context.invoke("echo", value)])
    await runtime.start()
    try:
        for _ in range(10):
            await runtime.run_workflow(workflow, 1)

        direct_samples = []
        for _ in range(iterations):
            started = time.perf_counter()
            handler(1, None)
            direct_samples.append(time.perf_counter() - started)

        capability_samples = []
        for _ in range(iterations):
            started = time.perf_counter()
            await runtime.run_workflow(workflow, 1)
            capability_samples.append(time.perf_counter() - started)

        direct_mean = mean(direct_samples)
        capability_mean = mean(capability_samples)
        return {
            "iterations": iterations,
            "direct_call_mean_us": direct_mean * 1_000_000,
            "workflow_capability_mean_us": capability_mean * 1_000_000,
            "runtime_overhead_us": (capability_mean - direct_mean) * 1_000_000,
        }
    finally:
        await runtime.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    print(json.dumps(asyncio.run(measure(args.iterations)), indent=2))


if __name__ == "__main__":
    main()
