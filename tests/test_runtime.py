import asyncio
import threading
import time
import unittest

from astra import (
    CallableWorkflow,
    CapabilityAmbiguousError,
    CapabilityModeError,
    CapabilityNotFoundError,
    CapabilityRequirement,
    CapabilitySpec,
    CapabilityVersionError,
    ComponentLifecycleError,
    Event,
    EventBus,
    FunctionComponent,
    InvocationMode,
    MemoryLogSink,
    NonBlockingLogSink,
    ParallelWorkflow,
    PipelineWorkflow,
    RouteWorkflow,
    Runtime,
    RuntimeConfig,
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
            sink = MemoryLogSink()
            runtime = Runtime(StructuredLogger([sink]))
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

    def test_capability_contract_normalizes_permissions_and_mode(self):
        spec = CapabilitySpec("normalized", mode="stream", permissions={"network.read"})
        self.assertEqual(spec.mode, InvocationMode.STREAM)
        self.assertEqual(spec.permissions, frozenset({"network.read"}))
        with self.assertRaises(ValueError):
            FunctionComponent("missing", capabilities={"unknown": CapabilitySpec("unknown")})
        with self.assertRaises(ValueError):
            FunctionComponent(
                "wrong-mode",
                {"call": lambda request, inv: request},
                capabilities={"call": CapabilitySpec("call", mode=InvocationMode.STREAM)},
            )
        with self.assertRaises(ValueError):
            CapabilitySpec("send", side_effect="external_effect", retry_safe=True)
        safe = CapabilitySpec(
            "send",
            side_effect="external_effect",
            retry_safe=True,
            idempotency_key="request.id",
        )
        self.assertEqual(safe.idempotency_key, "request.id")

    def test_missing_and_incompatible_capabilities_fail_deterministically(self):
        async def scenario():
            sink = MemoryLogSink()
            runtime = Runtime(StructuredLogger([sink]))
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

    def test_nonblocking_sink_does_not_hold_the_execution_path(self):
        class SlowSink:
            def __init__(self):
                self.records = []

            def write(self, record):
                time.sleep(0.03)
                self.records.append(record)

        slow = SlowSink()
        sink = NonBlockingLogSink(slow, maxsize=8)
        logger = StructuredLogger([sink])
        started = time.perf_counter()
        logger.emit("info", "nonblocking", "queued")
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.02)
        sink.flush()
        sink.close()
        self.assertEqual(len(slow.records), 1)

    def test_nonblocking_sink_drops_when_its_queue_is_full(self):
        class PausedSink:
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()

            def write(self, record):
                self.started.set()
                self.release.wait(1)

        slow = PausedSink()
        sink = NonBlockingLogSink(slow, maxsize=1)
        logger = StructuredLogger([sink])
        logger.emit("info", "queued", "first")
        self.assertTrue(slow.started.wait(1))
        logger.emit("info", "queued", "second")
        logger.emit("info", "queued", "third")
        self.assertGreaterEqual(sink.dropped, 1)
        slow.release.set()
        sink.flush()
        sink.close()

    def test_nonblocking_sink_close_discards_queued_records_before_timeout(self):
        class PausedSink:
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()

            def write(self, record):
                self.started.set()
                self.release.wait(1)

        slow = PausedSink()
        sink = NonBlockingLogSink(slow, maxsize=1)
        logger = StructuredLogger([sink])
        logger.emit("info", "queued", "first")
        self.assertTrue(slow.started.wait(1))
        logger.emit("info", "queued", "second")
        sink.close(timeout=0.01)
        self.assertGreaterEqual(sink.dropped, 1)
        slow.release.set()
        sink._worker.join(1)
        self.assertFalse(sink._worker.is_alive())

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

    def test_parallel_workflow_respects_configured_child_limit(self):
        async def scenario():
            active = 0
            peak = 0

            async def work(context, value):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1
                return value

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.apply_config(
                RuntimeConfig.from_dict({"resources": {"max_concurrent_children": 1}})
            )
            workflow = ParallelWorkflow(
                "limited-parallel",
                [CallableWorkflow("first", work), CallableWorkflow("second", work)],
            )
            await runtime.start()
            self.assertEqual(await runtime.run_workflow(workflow, "value"), ["value", "value"])
            self.assertEqual(peak, 1)
            await runtime.stop()

        self.run_async(scenario())

    def test_child_slot_wait_is_cancelled_without_leaking_the_semaphore(self):
        async def scenario():
            with self.assertRaises(ValueError):
                Scope(max_concurrent_children=1.5)
            scope = Scope(max_concurrent_children=1)
            held = await scope.acquire_child_slot()
            waiter = asyncio.create_task(scope.acquire_child_slot())
            await asyncio.sleep(0)
            scope.cancel("slot waiter cancellation")
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            scope.release_child_slot(held)
            await scope.close()

        self.run_async(scenario())

    def test_pipeline_and_stream_preserve_order_and_terminal_state(self):
        async def scenario():
            producer_closed = asyncio.Event()

            async def chunks(request, invocation):
                try:
                    for item in request:
                        invocation.raise_if_cancelled()
                        yield item
                finally:
                    producer_closed.set()

            sink = MemoryLogSink()
            runtime = Runtime(StructuredLogger([sink]))
            runtime.register_component(
                FunctionComponent(
                    "streamer",
                    stream_handlers={"tokens": chunks},
                    capabilities={"tokens": CapabilitySpec("tokens", mode=InvocationMode.STREAM)},
                )
            )
            runtime.register_component(FunctionComponent("invoke-only", {"echo": lambda request, inv: request}))

            async def collect(context, value):
                result = []
                async for item in context.stream("tokens", value):
                    result.append(item)
                return result

            pipeline = PipelineWorkflow("pipeline", [lambda context, value: [item * 2 for item in value], collect])
            await runtime.start()
            self.assertEqual(await runtime.run_workflow(pipeline, [1, 2, 3]), [2, 4, 6])
            producer_closed.clear()

            async def take_one(context, value):
                stream = context.stream("tokens", value)
                async for item in stream:
                    return item

            self.assertEqual(
                await runtime.run_workflow(CallableWorkflow("take-one", take_one), [9, 10]),
                9,
            )
            await asyncio.wait_for(producer_closed.wait(), timeout=1)
            self.assertTrue(
                any(
                    record.event == "stream_finished"
                    and record.fields.get("state") == "cancelled"
                    for record in sink.records
                )
            )

            async def wrong_mode(context, value):
                async for _ in context.stream("echo", value):
                    pass

            with self.assertRaises(CapabilityModeError):
                await runtime.run_workflow(
                    SerialWorkflow("wrong-mode", [wrong_mode]),
                    "value",
                )
            await runtime.stop()

        self.run_async(scenario())

    def test_event_subscriptions_are_scope_bound_and_trigger_workflow(self):
        async def scenario():
            failure_seen = asyncio.Event()

            class EventSink(MemoryLogSink):
                def write(self, record):
                    super().write(record)
                    if record.event == "event_workflow_failed":
                        failure_seen.set()

            sink = EventSink()
            logger = StructuredLogger([sink])
            bus = EventBus(logger)
            immutable = Event("immutable", {"values": [1]})
            with self.assertRaises(TypeError):
                immutable.payload["values"] = (2,)
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
            await asyncio.wait_for(failure_seen.wait(), timeout=1)
            await trigger_scope.close()
            await runtime.stop()

        self.run_async(scenario())

    def test_event_bus_drops_async_handlers_at_pending_limit(self):
        with self.assertRaises(ValueError):
            EventBus(max_pending=0)

        async def scenario():
            started = asyncio.Event()
            released = asyncio.Event()
            completed = asyncio.Event()

            async def handler(event):
                started.set()
                await released.wait()
                completed.set()

            bus = EventBus(StructuredLogger([MemoryLogSink()]), max_pending=1)
            bus.subscribe("fact", handler)
            await bus.publish(Event("fact", 1))
            await asyncio.wait_for(started.wait(), timeout=1)
            await bus.publish(Event("fact", 2))
            await asyncio.sleep(0)
            self.assertEqual(bus.dropped, 1)
            released.set()
            await asyncio.wait_for(completed.wait(), timeout=1)

        self.run_async(scenario())

    def test_event_workflow_subscription_applies_pending_limit_to_runs(self):
        async def scenario():
            started = asyncio.Event()
            released = asyncio.Event()
            received = []

            async def handle(context, value):
                started.set()
                await released.wait()
                received.append(value)
                return value

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            workflow = CallableWorkflow("event-work", handle)
            await runtime.start()
            bus = EventBus(StructuredLogger([MemoryLogSink()]), max_pending=1)
            scope = Scope()
            bus.subscribe_workflow("fact", workflow, runtime, scope=scope)
            await bus.publish(Event("fact", 1))
            await asyncio.wait_for(started.wait(), timeout=1)
            await bus.publish(Event("fact", 2))
            await asyncio.sleep(0)
            self.assertEqual(bus.dropped, 1)
            released.set()
            for _ in range(20):
                if received == [1]:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(received, [1])
            await scope.close()
            await runtime.stop()

        self.run_async(scenario())

    def test_closed_scope_cannot_leave_a_subscription_behind(self):
        async def scenario():
            bus = EventBus(StructuredLogger([MemoryLogSink()]))
            scope = Scope()
            await scope.close()
            with self.assertRaises(RuntimeError):
                bus.subscribe("closed", lambda event: None, scope=scope)
            self.assertEqual(bus._subscribers, {})

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

    def test_runtime_stop_rejects_calls_from_an_active_run(self):
        async def scenario():
            runtime = Runtime(StructuredLogger([MemoryLogSink()]))

            async def stop_from_workflow(context, value):
                with self.assertRaises(ComponentLifecycleError):
                    await context.run.runtime.stop()
                return value

            workflow = CallableWorkflow("stop-from-run", stop_from_workflow)
            await runtime.start()
            self.assertEqual(await runtime.run_workflow(workflow, "value", timeout=1), "value")
            self.assertTrue(runtime.started)
            await runtime.stop()

        self.run_async(scenario())

    def test_stubborn_provider_cannot_publish_late_success_after_timeout(self):
        async def scenario():
            async def stubborn(request, invocation):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    return "late"
                return "done"

            sink = MemoryLogSink()
            runtime = Runtime(StructuredLogger([sink]))
            runtime.register_component(FunctionComponent("stubborn", {"call": stubborn}))
            workflow = SerialWorkflow(
                "stubborn-workflow",
                [lambda context, value: context.invoke("call", value, timeout=0.01)],
            )
            await runtime.start()
            with self.assertRaises(asyncio.TimeoutError):
                await runtime.run_workflow(workflow, None)
            self.assertTrue(
                any(
                    record.event == "invocation_finished"
                    and record.fields.get("state") == "timed_out"
                    for record in sink.records
                )
            )
            await runtime.stop()

        self.run_async(scenario())

    def test_run_cancellation_reaches_provider_and_closes_stream(self):
        async def scenario():
            producer_closed = asyncio.Event()

            async def endless(request, invocation):
                try:
                    while True:
                        invocation.raise_if_cancelled()
                        yield 1
                        await asyncio.sleep(0)
                finally:
                    producer_closed.set()

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(
                FunctionComponent(
                    "streamer",
                    stream_handlers={"tokens": endless},
                    capabilities={"tokens": CapabilitySpec("tokens", mode=InvocationMode.STREAM)},
                )
            )

            async def consume(context, value):
                async for _ in context.stream("tokens", value):
                    await asyncio.sleep(0)

            await runtime.start()
            task = asyncio.create_task(runtime.run_workflow(CallableWorkflow("cancel", consume), None))
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(producer_closed.wait(), timeout=1)
            await runtime.stop()

        self.run_async(scenario())

    def test_scope_cancellation_interrupts_a_blocked_stream(self):
        async def scenario():
            producer_started = asyncio.Event()
            producer_closed = asyncio.Event()

            async def blocked(request, invocation):
                producer_started.set()
                try:
                    await asyncio.Future()
                    yield 1
                finally:
                    producer_closed.set()

            runtime = Runtime(StructuredLogger([MemoryLogSink()]))
            runtime.register_component(
                FunctionComponent(
                    "blocked-stream",
                    stream_handlers={"tokens": blocked},
                    capabilities={"tokens": CapabilitySpec("tokens", mode=InvocationMode.STREAM)},
                )
            )

            async def cancel_scope(context, value):
                stream = context.stream("tokens", value)
                next_item = asyncio.create_task(stream.__anext__())
                await producer_started.wait()
                context.run.scope.cancel("test cancellation")
                with self.assertRaises(asyncio.CancelledError):
                    await next_item

            await runtime.start()
            with self.assertRaises(asyncio.CancelledError):
                await runtime.run_workflow(CallableWorkflow("cancel-scope", cancel_scope), None)
            await asyncio.wait_for(producer_closed.wait(), timeout=1)
            await runtime.stop()

        self.run_async(scenario())


if __name__ == "__main__":
    unittest.main()
