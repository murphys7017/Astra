import asyncio
import unittest

from astra import (
    CapabilityAmbiguousError,
    CapabilityNotFoundError,
    CapabilityRequirement,
    CapabilitySpec,
    CapabilityVersionError,
    FunctionComponent,
    MemoryLogSink,
    RouteWorkflow,
    Runtime,
    SerialWorkflow,
    StructuredLogger,
    WorkflowComponent,
    WorkflowContext,
)
from astra.execution import Component


class FailingSink:
    def write(self, record):
        raise RuntimeError("sink failure")


class RuntimeTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_serial_route_and_child_workflow(self):
        async def scenario():
            sink = MemoryLogSink()
            runtime = Runtime(StructuredLogger([sink]))

            provider = FunctionComponent(
                "math",
                {"double": lambda request, invocation: request * 2},
            )
            runtime.register_component(provider)

            child = SerialWorkflow(
                "child",
                [lambda context, value: context.invoke("double", value)],
            )
            positive = SerialWorkflow("positive", [lambda context, value: value + 1])
            negative = SerialWorkflow("negative", [lambda context, value: value - 1])
            route = RouteWorkflow(
                "route",
                [(lambda context, value: value >= 0, positive)],
                fallback=negative,
            )
            runtime.register_workflow(child)
            runtime.register_workflow(route)
            await runtime.start()

            self.assertEqual(await runtime.run_workflow(child, 3), 6)
            self.assertEqual(await runtime.run_workflow(route, 2), 3)
            self.assertEqual(await runtime.run_workflow(route, -2), -3)
            self.assertTrue(any(record.event == "run_finished" for record in sink.records))
            await runtime.stop()

        self.run_async(scenario())

    def test_ambiguous_provider_requires_binding(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(FunctionComponent("one", {"echo": lambda request, inv: "one"}))
            runtime.register_component(FunctionComponent("two", {"echo": lambda request, inv: "two"}))
            workflow = SerialWorkflow("caller", [lambda context, value: context.invoke("echo", value)])
            await runtime.start()
            with self.assertRaises(CapabilityAmbiguousError):
                await runtime.run_workflow(workflow, "x")
            bound = CapabilityRequirement("echo", provider="two")
            workflow = SerialWorkflow("bound-caller", [lambda context, value: context.invoke(bound, value)])
            self.assertEqual(await runtime.run_workflow(workflow, "x"), "two")
            await runtime.stop()

        self.run_async(scenario())

    def test_missing_and_incompatible_capabilities_fail_deterministically(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(
                FunctionComponent(
                    "versioned",
                    {"echo": lambda request, inv: request},
                    capabilities={"echo": CapabilitySpec("echo", version="2")},
                )
            )
            await runtime.start()
            workflow = SerialWorkflow(
                "missing",
                [lambda context, value: context.invoke("missing", value)],
            )
            with self.assertRaises(CapabilityNotFoundError):
                await runtime.run_workflow(workflow, "x")
            workflow = SerialWorkflow(
                "wrong-version",
                [lambda context, value: context.invoke(CapabilityRequirement("echo", version="1"), value)],
            )
            with self.assertRaises(CapabilityVersionError):
                await runtime.run_workflow(workflow, "x")
            await runtime.stop()

        self.run_async(scenario())

    def test_log_sink_failure_does_not_fail_call_and_redacts_secret(self):
        async def scenario():
            sink = MemoryLogSink()
            runtime = Runtime(StructuredLogger([FailingSink(), sink]))
            runtime.register_component(
                FunctionComponent("echo", {"echo": lambda request, inv: request})
            )
            workflow = SerialWorkflow("log-test", [lambda context, value: context.invoke("echo", value)])
            await runtime.start()
            result = await runtime.run_workflow(workflow, {"api_key": "secret", "value": 1})
            self.assertEqual(result["value"], 1)
            records = sink.records
            self.assertTrue(records)
            self.assertTrue(all("secret" not in str(record.fields) for record in records))
            await runtime.stop()

        self.run_async(scenario())

    def test_workflow_component_can_be_invoked_as_capability(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            child = SerialWorkflow("child", [lambda context, value: value + 10])
            runtime.register_component(WorkflowComponent(child))
            caller = SerialWorkflow(
                "caller",
                [lambda context, value: context.invoke("workflow.child", value)],
            )
            await runtime.start()
            self.assertEqual(await runtime.run_workflow(caller, 2), 12)
            await runtime.stop()

        self.run_async(scenario())

    def test_component_lifecycle_and_scope_cleanup(self):
        async def scenario():
            events = []

            class LifecycleComponent(Component):
                def __init__(self):
                    super().__init__("lifecycle")

                async def start(self, runtime):
                    events.append("start")

                async def stop(self):
                    events.append("stop")

                async def release(self):
                    events.append("release")

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(LifecycleComponent())
            workflow = SerialWorkflow(
                "cleanup",
                [lambda context, value: context.run.scope.add_cleanup(lambda: events.append("cleanup")) or value],
            )
            await runtime.start()
            self.assertEqual(await runtime.run_workflow(workflow, "ok"), "ok")
            self.assertEqual(events, ["start", "cleanup"])
            await runtime.stop()
            self.assertEqual(events, ["start", "cleanup", "stop", "release"])

        self.run_async(scenario())

    def test_timeout_reaches_terminal_state_and_cancels_scope(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))

            async def slow(context, value):
                await context.run.scope.wait_cancelled()
                raise asyncio.CancelledError()

            workflow = SerialWorkflow("slow", [slow])
            await runtime.start()
            with self.assertRaises(asyncio.TimeoutError):
                await runtime.run_workflow(workflow, None, timeout=0.01)
            await runtime.stop()

        self.run_async(scenario())


if __name__ == "__main__":
    unittest.main()
