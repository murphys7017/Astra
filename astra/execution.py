"""The minimal local execution kernel."""

import asyncio
from dataclasses import dataclass
from enum import Enum
import inspect
import uuid
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Mapping, Optional, Sequence, Set, Tuple, Union

from .contracts import CapabilityRequirement, CapabilitySpec, InvocationMode
from .errors import (
    CapabilityAmbiguousError,
    CapabilityModeError,
    CapabilityNotFoundError,
    CapabilityVersionError,
    ComponentLifecycleError,
    ConfigurationError,
    PermissionDeniedError,
)
from .logging import StructuredLogger


def _new_id(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _await_with_deadline(
    awaitable: Awaitable[Any],
    timeout: Optional[float],
    on_timeout: Callable[[], None],
) -> Tuple[Any, bool]:
    task = asyncio.ensure_future(awaitable)
    timed_out = False
    timer = None
    if timeout is not None:
        loop = asyncio.get_running_loop()

        def expire() -> None:
            nonlocal timed_out
            timed_out = True
            on_timeout()
            task.cancel()

        timer = loop.call_later(timeout, expire)
    try:
        result = await task
        return result, timed_out
    except asyncio.CancelledError:
        if timed_out:
            return None, True
        raise
    finally:
        if timer is not None:
            timer.cancel()


class RunState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class InvocationState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class Scope:
    """A cancellation, ownership and cleanup boundary."""

    def __init__(self, parent: Optional["Scope"] = None, logger: Optional[StructuredLogger] = None) -> None:
        self.scope_id = _new_id("scope")
        self.parent = parent
        self._logger = logger or (parent._logger if parent is not None else None)
        self._cancel_event = asyncio.Event()
        self._closed = False
        self._children: Set[Scope] = set()
        self._cleanups = []
        if parent is not None:
            parent._children.add(self)
            if parent.cancelled:
                self.cancel("parent already cancelled")

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def closed(self) -> bool:
        return self._closed

    def cancel(self, reason: str = "cancelled") -> None:
        if self._closed:
            return
        if not self._cancel_event.is_set():
            self._cancel_event.set()
        for child in tuple(self._children):
            child.cancel(reason)

    async def wait_cancelled(self) -> None:
        await self._cancel_event.wait()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError()

    def add_cleanup(self, cleanup: Callable[[], Any]) -> None:
        if self._closed:
            raise RuntimeError("cannot add cleanup to a closed scope")
        self._cleanups.append(cleanup)

    async def close(self) -> None:
        if self._closed:
            return
        self.cancel("scope closing")
        self._closed = True
        for cleanup in reversed(self._cleanups):
            try:
                await _maybe_await(cleanup())
            except BaseException as exc:
                if self._logger is not None:
                    self._logger.emit(
                        "error",
                        "scope_cleanup_failed",
                        "scope cleanup failed",
                        scope_id=self.scope_id,
                        fields={"error_type": type(exc).__name__},
                    )
        self._cleanups.clear()
        for child in tuple(self._children):
            await child.close()
        self._children.clear()
        if self.parent is not None:
            self.parent._children.discard(self)
        # Cleanup errors are deliberately not propagated into the main execution.
        return None


class Component:
    """Base class for a lifecycle-managed capability provider."""

    def __init__(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("component name must not be empty")
        self.name = name

    @property
    def capabilities(self) -> Sequence[CapabilitySpec]:
        return ()

    async def start(self, runtime: "Runtime") -> None:
        return None

    async def stop(self) -> None:
        return None

    async def release(self) -> None:
        return None

    async def invoke(self, capability: str, request: Any, invocation: "Invocation") -> Any:
        raise NotImplementedError("component {} does not implement invoke".format(self.name))

    def stream(self, capability: str, request: Any, invocation: "Invocation") -> AsyncIterator[Any]:
        raise NotImplementedError("component {} does not implement stream".format(self.name))


class FunctionComponent(Component):
    """Small adapter for tests and simple local components."""

    def __init__(
        self,
        name: str,
        handlers: Optional[Mapping[str, Callable[[Any, "Invocation"], Any]]] = None,
        capabilities: Optional[Mapping[str, CapabilitySpec]] = None,
        stream_handlers: Optional[Mapping[str, Callable[[Any, "Invocation"], AsyncIterator[Any]]]] = None,
    ) -> None:
        super().__init__(name)
        self._handlers = dict(handlers or {})
        self._stream_handlers = dict(stream_handlers or {})
        specs = capabilities or {}
        unknown_specs = set(specs) - set(self._handlers) - set(self._stream_handlers)
        if unknown_specs:
            raise ValueError(
                "capability declarations have no handler: {}".format(
                    ", ".join(sorted(map(str, unknown_specs)))
                )
            )
        names = tuple(dict.fromkeys(tuple(self._handlers) + tuple(self._stream_handlers)))
        generated_specs = []
        for key in names:
            if key in specs:
                spec = specs[key]
                if spec.name != key:
                    raise ValueError("capability declaration name does not match handler: {}".format(key))
                if spec.mode in (InvocationMode.INVOKE, InvocationMode.INVOKE_AND_STREAM) and key not in self._handlers:
                    raise ValueError("invoke capability has no handler: {}".format(key))
                if spec.mode in (InvocationMode.STREAM, InvocationMode.INVOKE_AND_STREAM) and key not in self._stream_handlers:
                    raise ValueError("stream capability has no handler: {}".format(key))
                generated_specs.append(spec)
            elif key in self._handlers and key in self._stream_handlers:
                generated_specs.append(CapabilitySpec(key, mode=InvocationMode.INVOKE_AND_STREAM))
            elif key in self._stream_handlers:
                generated_specs.append(CapabilitySpec(key, mode=InvocationMode.STREAM))
            else:
                generated_specs.append(CapabilitySpec(key))
        self._capabilities = tuple(generated_specs)

    @property
    def capabilities(self) -> Sequence[CapabilitySpec]:
        return self._capabilities

    async def invoke(self, capability: str, request: Any, invocation: "Invocation") -> Any:
        if capability not in self._handlers:
            raise KeyError("component {} has no capability {}".format(self.name, capability))
        invocation.raise_if_cancelled()
        return await _maybe_await(self._handlers[capability](request, invocation))

    def stream(self, capability: str, request: Any, invocation: "Invocation") -> AsyncIterator[Any]:
        if capability not in self._stream_handlers:
            raise KeyError("component {} has no stream capability {}".format(self.name, capability))
        invocation.raise_if_cancelled()
        return self._stream_handlers[capability](request, invocation)


@dataclass(frozen=True)
class ProviderBinding:
    capability: CapabilitySpec
    component_name: str
    generation: int


class Invocation:
    def __init__(self, run: "WorkflowRun", binding: ProviderBinding) -> None:
        self.invocation_id = _new_id("inv")
        self.run = run
        self.binding = binding
        self.state = InvocationState.CREATED
        self._cancel_event = asyncio.Event()

    @property
    def scope(self) -> Scope:
        return self.run.scope

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set() or self.scope.cancelled

    def cancel(self) -> None:
        self._cancel_event.set()
        if self.state in (InvocationState.CREATED, InvocationState.RUNNING):
            self.state = InvocationState.CANCEL_REQUESTED
            self.run.runtime.logger.emit(
                "warning",
                "invocation_cancel_requested",
                "capability invocation cancellation requested",
                run_id=self.run.run_id,
                invocation_id=self.invocation_id,
                scope_id=self.run.scope.scope_id,
                component=self.binding.component_name,
                workflow=self.run.workflow_name,
                correlation_id=self.run.correlation_id,
            )

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError()


class WorkflowRun:
    def __init__(
        self,
        runtime: "Runtime",
        scope: Scope,
        workflow_name: str,
        parent: Optional["WorkflowRun"] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        self.run_id = _new_id("run")
        self.runtime = runtime
        self.scope = scope
        self.workflow_name = workflow_name
        self.parent = parent
        self.correlation_id = correlation_id or (parent.correlation_id if parent else _new_id("corr"))
        self.generation = runtime.generation
        self.state = RunState.CREATED
        self._task: Optional[asyncio.Task] = None

    async def execute(self, workflow: Any, value: Any, timeout: Optional[float] = None) -> Any:
        self.state = RunState.RUNNING
        self._task = asyncio.current_task()
        self.runtime._active_runs.add(self)
        self.runtime.logger.emit(
            "info",
            "run_started",
            "workflow run started",
            run_id=self.run_id,
            scope_id=self.scope.scope_id,
            workflow=self.workflow_name,
            correlation_id=self.correlation_id,
        )
        try:
            from .workflow import WorkflowContext

            result, timed_out = await _await_with_deadline(
                workflow.execute(WorkflowContext(self), value),
                timeout,
                lambda: self.scope.cancel("run timed out"),
            )
            if timed_out:
                self.state = RunState.TIMED_OUT
                raise asyncio.TimeoutError()
            if self.scope.cancelled:
                self.state = RunState.CANCELLED
                raise asyncio.CancelledError()
            self.state = RunState.SUCCEEDED
            self.runtime.logger.emit(
                "info",
                "run_finished",
                "workflow run finished",
                run_id=self.run_id,
                scope_id=self.scope.scope_id,
                workflow=self.workflow_name,
                correlation_id=self.correlation_id,
                fields={"state": self.state.value},
            )
            return result
        except asyncio.TimeoutError:
            self.scope.cancel("run timed out")
            self.state = RunState.TIMED_OUT
            self.runtime.logger.emit(
                "warning",
                "run_finished",
                "workflow run timed out",
                run_id=self.run_id,
                scope_id=self.scope.scope_id,
                workflow=self.workflow_name,
                correlation_id=self.correlation_id,
                fields={"state": self.state.value},
            )
            raise
        except asyncio.CancelledError:
            self.scope.cancel("run cancelled")
            self.state = RunState.CANCELLED
            self.runtime.logger.emit(
                "warning",
                "run_finished",
                "workflow run cancelled",
                run_id=self.run_id,
                scope_id=self.scope.scope_id,
                workflow=self.workflow_name,
                correlation_id=self.correlation_id,
                fields={"state": self.state.value},
            )
            raise
        except Exception as exc:
            self.state = RunState.FAILED
            self.runtime.logger.emit(
                "error",
                "run_finished",
                "workflow run failed",
                run_id=self.run_id,
                scope_id=self.scope.scope_id,
                workflow=self.workflow_name,
                correlation_id=self.correlation_id,
                fields={"state": self.state.value, "error_type": type(exc).__name__},
            )
            raise
        finally:
            self._task = None
            self.runtime._active_runs.discard(self)
            await self.scope.close()
            self.runtime.logger.emit(
                "debug",
                "scope_released",
                "workflow scope resources released",
                run_id=self.run_id,
                scope_id=self.scope.scope_id,
                workflow=self.workflow_name,
                correlation_id=self.correlation_id,
                fields={"resources_released": True},
            )

    async def invoke(
        self,
        requirement: Union[str, CapabilityRequirement],
        request: Any,
        timeout: Optional[float] = None,
    ) -> Any:
        return await self.runtime.invoke(requirement, request, run=self, timeout=timeout)

    async def run_child(self, workflow: Any, value: Any, timeout: Optional[float] = None) -> Any:
        self.runtime._ensure_workflow_enabled(workflow.name)
        child_scope = Scope(self.scope)
        child = WorkflowRun(self.runtime, child_scope, workflow.name, parent=self)
        return await child.execute(workflow, value, timeout=timeout)

    def cancel(self, reason: str = "cancel requested") -> None:
        if self.state in (RunState.CREATED, RunState.RUNNING):
            self.state = RunState.CANCEL_REQUESTED
            self.runtime.logger.emit(
                "warning",
                "run_cancel_requested",
                "workflow run cancellation requested",
                run_id=self.run_id,
                scope_id=self.scope.scope_id,
                workflow=self.workflow_name,
                correlation_id=self.correlation_id,
                fields={"reason": reason},
            )
        self.scope.cancel(reason)
        if self._task is not None and self._task is not asyncio.current_task():
            self._task.cancel()

    @property
    def parameters(self) -> Mapping[str, Any]:
        if self.runtime._config is None:
            return {}
        return self.runtime._config.workflow_params.get(self.workflow_name, {})


class Runtime:
    """A single-process, local component runtime."""

    def __init__(self, logger: Optional[StructuredLogger] = None) -> None:
        self.logger = logger or StructuredLogger()
        self.generation = 1
        self._components: Dict[str, Component] = {}
        self._providers: Dict[str, list] = {}
        self._workflows: Dict[str, Any] = {}
        self._config = None
        self._composition = None
        self._configured_workflow = None
        self._allowed_permissions = frozenset()
        self._started = False
        self._started_component_names: Tuple[str, ...] = ()
        self._active_runs: Set[WorkflowRun] = set()

    @property
    def started(self) -> bool:
        return self._started

    def register_component(self, component: Component) -> None:
        if self._started:
            raise ComponentLifecycleError("components cannot be registered after runtime start")
        if component.name in self._components:
            raise ComponentLifecycleError("component already registered: {}".format(component.name))
        names = [spec.name for spec in component.capabilities]
        if len(names) != len(set(names)):
            raise ComponentLifecycleError("component exposes duplicate capabilities: {}".format(component.name))
        self._components[component.name] = component

    def unregister_component(self, name: str) -> Component:
        if self._started:
            raise ComponentLifecycleError("components cannot be unregistered after runtime start")
        try:
            return self._components.pop(name)
        except KeyError as exc:
            raise ComponentLifecycleError("component is not registered: {}".format(name)) from exc

    def apply_config(self, config: Any) -> None:
        """Apply a validated RuntimeConfig before starting the runtime."""
        if self._started:
            raise ConfigurationError("configuration cannot change after runtime start")
        config.validate_registered(self._components, self._workflows)
        from .config import CompositionSnapshot

        configured_workflow = None
        if config.workflow_order or config.parallel_groups or config.branches:
            configured_workflow = self._compile_composed_workflow(config, "configured-composition")
        self._config = config
        self._composition = CompositionSnapshot(self.generation, config)
        self._configured_workflow = configured_workflow
        allowed = config.permissions.get("allow")
        self._allowed_permissions = frozenset() if allowed is None else frozenset(allowed)

    @property
    def composition(self) -> Any:
        return self._composition

    def register_workflow(self, workflow: Any, expose: bool = True) -> None:
        if workflow.name in self._workflows:
            raise ComponentLifecycleError("workflow already registered: {}".format(workflow.name))
        if expose:
            from .workflow import WorkflowComponent

            self.register_component(WorkflowComponent(workflow))
        self._workflows[workflow.name] = workflow

    async def start(self) -> None:
        if self._started:
            return
        started = []
        attempted = []
        try:
            selected = self._selected_component_names()
            for name in selected:
                component = self._components[name]
                attempted.append(component)
                await component.start(self)
                started.append(component)
                for spec in component.capabilities:
                    self._providers.setdefault(spec.name, []).append((component, spec))
            self._started_component_names = tuple(component.name for component in started)
            self._started = True
            self.logger.emit("info", "runtime_started", "runtime started")
        except Exception as exc:
            for component in reversed(attempted):
                try:
                    await component.stop()
                except Exception:
                    pass
                try:
                    await component.release()
                except Exception:
                    pass
            self._providers.clear()
            self._started_component_names = ()
            raise ComponentLifecycleError("runtime start failed: {}".format(type(exc).__name__)) from exc

    async def stop(self) -> None:
        if not self._started:
            return
        active_tasks = []
        for run in tuple(self._active_runs):
            run.cancel("runtime stopping")
            if run._task is not None:
                active_tasks.append(run._task)
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        for name in reversed(self._started_component_names):
            component = self._components[name]
            try:
                await component.stop()
            except Exception as exc:
                self.logger.emit(
                    "error",
                    "component_stop_failed",
                    "component stop failed",
                    component=component.name,
                    fields={"error_type": type(exc).__name__},
                )
            try:
                await component.release()
            except Exception as exc:
                self.logger.emit(
                    "error",
                    "component_release_failed",
                    "component release failed",
                    component=component.name,
                    fields={"error_type": type(exc).__name__},
                )
        self._providers.clear()
        self._started_component_names = ()
        self._started = False
        self.logger.emit("info", "runtime_stopped", "runtime stopped")

    def resolve(
        self,
        requirement: Union[str, CapabilityRequirement],
        generation: Optional[int] = None,
    ) -> ProviderBinding:
        if isinstance(requirement, str):
            requirement = CapabilityRequirement(requirement)
        requirement = self._configured_requirement(requirement)
        candidates = list(self._providers.get(requirement.name, ()))
        if not candidates:
            raise CapabilityNotFoundError("no provider for capability {}".format(requirement.name))
        if requirement.version is not None:
            candidates = [(component, spec) for component, spec in candidates if spec.version == requirement.version]
            if not candidates:
                raise CapabilityVersionError(
                    "no provider for {} satisfies version {}".format(requirement.name, requirement.version)
                )
        if requirement.provider is not None:
            candidates = [(component, spec) for component, spec in candidates if component.name == requirement.provider]
        if not candidates:
            raise CapabilityNotFoundError("no selected provider for capability {}".format(requirement.name))
        if len(candidates) > 1:
            providers = ", ".join(sorted(component.name for component, _ in candidates))
            raise CapabilityAmbiguousError(
                "capability {} has ambiguous providers: {}".format(requirement.name, providers)
            )
        component, spec = candidates[0]
        return ProviderBinding(spec, component.name, self.generation if generation is None else generation)

    async def invoke(
        self,
        requirement: Union[str, CapabilityRequirement],
        request: Any,
        *,
        run: WorkflowRun,
        timeout: Optional[float] = None,
    ) -> Any:
        if not self._started:
            raise ComponentLifecycleError("runtime is not started")
        run.scope.raise_if_cancelled()
        binding = self.resolve(requirement, generation=run.generation)
        component = self._components[binding.component_name]
        if binding.capability.mode not in (InvocationMode.INVOKE, InvocationMode.INVOKE_AND_STREAM):
            raise CapabilityModeError("capability {} does not support invoke".format(binding.capability.name))
        required_permissions = binding.capability.permissions
        if self._allowed_permissions is not None and not required_permissions.issubset(self._allowed_permissions):
            self.logger.emit(
                "warning",
                "invocation_denied",
                "capability permission denied",
                run_id=run.run_id,
                scope_id=run.scope.scope_id,
                component=component.name,
                workflow=run.workflow_name,
                correlation_id=run.correlation_id,
                fields={"capability": binding.capability.name},
            )
            raise PermissionDeniedError("permission denied for capability {}".format(binding.capability.name))
        invocation = Invocation(run, binding)
        invocation.state = InvocationState.RUNNING
        self.logger.emit(
            "info",
            "invocation_started",
            "capability invocation started",
            run_id=run.run_id,
            invocation_id=invocation.invocation_id,
            scope_id=run.scope.scope_id,
            component=component.name,
            workflow=run.workflow_name,
            correlation_id=run.correlation_id,
            fields={"capability": binding.capability.name, "generation": binding.generation},
        )
        try:
            result, timed_out = await _await_with_deadline(
                component.invoke(binding.capability.name, request, invocation),
                timeout,
                invocation.cancel,
            )
            if timed_out:
                invocation.state = InvocationState.TIMED_OUT
                raise asyncio.TimeoutError()
            if invocation.cancelled:
                invocation.state = InvocationState.CANCELLED
                raise asyncio.CancelledError()
            invocation.state = InvocationState.SUCCEEDED
            return result
        except asyncio.TimeoutError:
            invocation.cancel()
            invocation.state = InvocationState.TIMED_OUT
            raise
        except asyncio.CancelledError:
            invocation.cancel()
            invocation.state = InvocationState.CANCELLED
            raise
        except Exception:
            invocation.state = InvocationState.FAILED
            raise
        finally:
            level = "info" if invocation.state == InvocationState.SUCCEEDED else (
                "error" if invocation.state == InvocationState.FAILED else "warning"
            )
            self.logger.emit(
                level,
                "invocation_finished",
                "capability invocation finished",
                run_id=run.run_id,
                invocation_id=invocation.invocation_id,
                scope_id=run.scope.scope_id,
                component=component.name,
                workflow=run.workflow_name,
                correlation_id=run.correlation_id,
                fields={"capability": binding.capability.name, "state": invocation.state.value},
            )

    async def stream(
        self,
        requirement: Union[str, CapabilityRequirement],
        request: Any,
        *,
        run: WorkflowRun,
    ) -> AsyncIterator[Any]:
        if not self._started:
            raise ComponentLifecycleError("runtime is not started")
        run.scope.raise_if_cancelled()
        binding = self.resolve(requirement, generation=run.generation)
        component = self._components[binding.component_name]
        if binding.capability.mode not in (InvocationMode.STREAM, InvocationMode.INVOKE_AND_STREAM):
            raise CapabilityModeError("capability {} does not support stream".format(binding.capability.name))
        required_permissions = binding.capability.permissions
        if self._allowed_permissions is not None and not required_permissions.issubset(self._allowed_permissions):
            self.logger.emit(
                "warning",
                "stream_denied",
                "stream capability permission denied",
                run_id=run.run_id,
                scope_id=run.scope.scope_id,
                component=component.name,
                workflow=run.workflow_name,
                correlation_id=run.correlation_id,
                fields={"capability": binding.capability.name},
            )
            raise PermissionDeniedError("permission denied for capability {}".format(binding.capability.name))
        invocation = Invocation(run, binding)
        invocation.state = InvocationState.RUNNING
        self.logger.emit(
            "info",
            "stream_started",
            "capability stream started",
            run_id=run.run_id,
            invocation_id=invocation.invocation_id,
            scope_id=run.scope.scope_id,
            component=component.name,
            workflow=run.workflow_name,
            correlation_id=run.correlation_id,
            fields={"capability": binding.capability.name, "generation": binding.generation},
        )
        produced = None
        scope_cancel_task = None
        iterator = None
        try:
            produced = component.stream(binding.capability.name, request, invocation)
            if inspect.isawaitable(produced):
                produced = await produced
            iterator = produced.__aiter__()
            scope_cancel_task = asyncio.create_task(run.scope.wait_cancelled())
            while True:
                next_task = asyncio.create_task(iterator.__anext__())
                done, _ = await asyncio.wait(
                    (next_task, scope_cancel_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if scope_cancel_task in done:
                    next_task.cancel()
                    await asyncio.gather(next_task, return_exceptions=True)
                    invocation.cancel()
                    raise asyncio.CancelledError()
                try:
                    item = next_task.result()
                except StopAsyncIteration:
                    break
                invocation.raise_if_cancelled()
                yield item
            if invocation.cancelled:
                invocation.state = InvocationState.CANCELLED
                raise asyncio.CancelledError()
            invocation.state = InvocationState.SUCCEEDED
        except asyncio.CancelledError:
            invocation.cancel()
            invocation.state = InvocationState.CANCELLED
            raise
        except GeneratorExit:
            invocation.cancel()
            invocation.state = InvocationState.CANCELLED
            raise
        except Exception:
            invocation.state = InvocationState.FAILED
            raise
        finally:
            if scope_cancel_task is not None and not scope_cancel_task.done():
                scope_cancel_task.cancel()
                await asyncio.gather(scope_cancel_task, return_exceptions=True)
            if produced is not None and hasattr(produced, "aclose"):
                try:
                    await produced.aclose()
                except BaseException as exc:
                    self.logger.emit(
                        "error",
                        "stream_close_failed",
                        "stream producer close failed",
                        run_id=run.run_id,
                        invocation_id=invocation.invocation_id,
                        scope_id=run.scope.scope_id,
                        component=component.name,
                        workflow=run.workflow_name,
                        correlation_id=run.correlation_id,
                        fields={"error_type": type(exc).__name__},
                    )
            if invocation.state == InvocationState.RUNNING:
                invocation.cancel()
                invocation.state = InvocationState.CANCELLED
            level = "info" if invocation.state == InvocationState.SUCCEEDED else (
                "error" if invocation.state == InvocationState.FAILED else "warning"
            )
            self.logger.emit(
                level,
                "stream_finished",
                "capability stream finished",
                run_id=run.run_id,
                invocation_id=invocation.invocation_id,
                scope_id=run.scope.scope_id,
                component=component.name,
                workflow=run.workflow_name,
                correlation_id=run.correlation_id,
                fields={"capability": binding.capability.name, "state": invocation.state.value},
            )

    async def run_workflow(
        self,
        workflow: Any,
        value: Any,
        timeout: Optional[float] = None,
        correlation_id: Optional[str] = None,
    ) -> Any:
        if not self._started:
            raise ComponentLifecycleError("runtime is not started")
        if isinstance(workflow, str):
            try:
                workflow = self._workflows[workflow]
            except KeyError as exc:
                raise KeyError("unknown workflow: {}".format(workflow)) from exc
        self._ensure_workflow_enabled(workflow.name)
        run = WorkflowRun(self, Scope(logger=self.logger), workflow.name, correlation_id=correlation_id)
        return await run.execute(workflow, value, timeout=timeout)

    def build_composed_workflow(self, name: str = "configured-composition") -> Any:
        """Compile the current startup composition into a WorkflowDefinition."""
        if self._config is None:
            raise ConfigurationError("a RuntimeConfig is required for composition execution")
        if name == "configured-composition" and self._configured_workflow is not None:
            return self._configured_workflow
        if not (self._config.workflow_order or self._config.parallel_groups or self._config.branches):
            raise ConfigurationError("RuntimeConfig does not define a composition")
        return self._compile_composed_workflow(self._config, name)

    def _compile_composed_workflow(self, config: Any, name: str) -> Any:
        from .workflow import ConfiguredWorkflow

        workflow_names = config.workflow_names
        if workflow_names is None:
            selected = tuple(self._workflows)
        else:
            selected = workflow_names
        workflows = {workflow_name: self._workflows[workflow_name] for workflow_name in selected}
        order = config.workflow_order
        return ConfiguredWorkflow(
            name,
            workflows,
            order,
            config.parallel_groups,
            config.branches,
        )

    async def run_composition(
        self,
        value: Any,
        *,
        name: str = "configured-composition",
        timeout: Optional[float] = None,
        correlation_id: Optional[str] = None,
    ) -> Any:
        """Execute the validated startup composition as one Workflow Run."""
        if not self._started:
            raise ComponentLifecycleError("runtime is not started")
        workflow = self.build_composed_workflow()
        run = WorkflowRun(self, Scope(logger=self.logger), name, correlation_id=correlation_id)
        return await run.execute(workflow, value, timeout=timeout)

    def _ensure_workflow_enabled(self, workflow_name: str) -> None:
        if self._config is not None and self._config.workflow_names is not None:
            if workflow_name not in self._config.workflow_names:
                raise ConfigurationError("workflow is not enabled: {}".format(workflow_name))

    def _selected_component_names(self) -> Tuple[str, ...]:
        if self._config is None or self._config.component_names is None:
            return tuple(self._components)
        return self._config.component_names

    def _configured_requirement(self, requirement: CapabilityRequirement) -> CapabilityRequirement:
        if self._config is None:
            return requirement
        configured = self._config.bindings.get(requirement.name)
        if configured is None:
            return requirement
        return CapabilityRequirement(
            requirement.name,
            requirement.version if requirement.version is not None else configured.version,
            requirement.provider if requirement.provider is not None else configured.provider,
        )

