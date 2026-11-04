import asyncio
import unittest

from astra import (
    CallableWorkflow,
    CapabilityAmbiguousError,
    CapabilityNotFoundError,
    CapabilityRequirement,
    CapabilitySpec,
    CapabilityVersionError,
    Event,
    EventBus,
    FunctionComponent,
    MemoryLogSink,
    ParallelWorkflow,
    RouteWorkflow,
    Runtime,
    SerialWorkflow,
    StructuredLogger,
    Scope,
    WorkflowComponent,
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

    def test_parallel_workflow_joins_results_in_declaration_order(self):
        async def scenario():
            async def first(context, value):
                await asyncio.sleep(0.01)
                return value + "-first"

            async def second(context, value):
                return value + "-second"

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            workflow = ParallelWorkflow(
                "parallel",
                [CallableWorkflow("first", first), CallableWorkflow("second", second)],
            )
            await runtime.start()
            self.assertEqual(await runtime.run_workflow(workflow, "value"), ["value-first", "value-second"])
            await runtime.stop()

        self.run_async(scenario())

    def test_event_subscriptions_are_scope_bound_and_trigger_workflow(self):
        async def scenario():
            sink = MemoryLogSink()
            logger = StructuredLogger([sink])
            bus = EventBus(logger)
            scope = Scope()
            seen = []
            bus.subscribe("fact", lambda event: seen.append(event.payload), scope=scope)
            bus.subscribe("fact", lambda event: (_ for _ in ()).throw(RuntimeError("isolated")))
            await bus.publish(Event("fact", 1))
            self.assertEqual(seen, [1])
            await scope.close()
            await bus.publish(Event("fact", 2))
            self.assertEqual(seen, [1])

            runtime = Runtime(logger)
            received = asyncio.Event()

            async def record(context, value):
                self.assertEqual(value, {"value": 3})
                received.set()
                return value

            workflow = CallableWorkflow("event-workflow", record)
            trigger_scope = Scope()
            bus.subscribe_workflow("trigger", workflow, runtime, scope=trigger_scope)
            await runtime.start()
            await bus.publish(Event("trigger", {"value": 3}, correlation_id="corr-event"))
            await asyncio.wait_for(received.wait(), timeout=1)
            self.assertTrue(
                any(record.event == "run_started" and record.correlation_id == "corr-event" for record in sink.records)
            )

            async def fail(context, value):
                raise ValueError("expected")

            bus.subscribe_workflow("bad", CallableWorkflow("bad-workflow", fail), runtime, scope=trigger_scope)
            await bus.publish(Event("bad", None))
            await asyncio.sleep(0.01)
            self.assertTrue(any(record.event == "event_workflow_failed" for record in sink.records))
            await trigger_scope.close()
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
