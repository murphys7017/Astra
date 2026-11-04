"""The minimal local execution kernel."""

import asyncio
from dataclasses import dataclass
from enum import Enum
import inspect
import uuid
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple, Union

from .contracts import CapabilityRequirement, CapabilitySpec
from .errors import (
    CapabilityAmbiguousError,
    CapabilityNotFoundError,
    CapabilityVersionError,
    ComponentLifecycleError,
)
from .logging import StructuredLogger


def _new_id(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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
        self._closed = True
        for cleanup in reversed(self._cleanups):
            try:
                await _maybe_await(cleanup())
            except Exception as exc:
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


class FunctionComponent(Component):
    """Small adapter for tests and simple local components."""

    def __init__(
        self,
        name: str,
        handlers: Mapping[str, Callable[[Any, "Invocation"], Any]],
        capabilities: Optional[Mapping[str, CapabilitySpec]] = None,
    ) -> None:
        super().__init__(name)
        self._handlers = dict(handlers)
        specs = capabilities or {}
        self._capabilities = tuple(specs.get(key, CapabilitySpec(key)) for key in self._handlers)

    @property
    def capabilities(self) -> Sequence[CapabilitySpec]:
        return self._capabilities

    async def invoke(self, capability: str, request: Any, invocation: "Invocation") -> Any:
        if capability not in self._handlers:
            raise KeyError("component {} has no capability {}".format(self.name, capability))
        invocation.raise_if_cancelled()
        return await _maybe_await(self._handlers[capability](request, invocation))


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
    ) -> None:
        self.run_id = _new_id("run")
        self.runtime = runtime
        self.scope = scope
        self.workflow_name = workflow_name
        self.parent = parent
        self.correlation_id = parent.correlation_id if parent else _new_id("corr")
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

            result = workflow.execute(WorkflowContext(self), value)
            if timeout is None:
                result = await result
            else:
                result = await asyncio.wait_for(result, timeout=timeout)
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

    async def invoke(
        self,
        requirement: Union[str, CapabilityRequirement],
        request: Any,
        timeout: Optional[float] = None,
    ) -> Any:
        return await self.runtime.invoke(requirement, request, run=self, timeout=timeout)

    async def run_child(self, workflow: Any, value: Any, timeout: Optional[float] = None) -> Any:
        child_scope = Scope(self.scope)
        child = WorkflowRun(self.runtime, child_scope, workflow.name, parent=self)
        return await child.execute(workflow, value, timeout=timeout)

    def cancel(self, reason: str = "cancel requested") -> None:
        if self.state in (RunState.CREATED, RunState.RUNNING):
            self.state = RunState.CANCEL_REQUESTED
        self.scope.cancel(reason)
        if self._task is not None and self._task is not asyncio.current_task():
            self._task.cancel()


class Runtime:
    """A single-process, local component runtime."""

    def __init__(self, logger: Optional[StructuredLogger] = None) -> None:
        self.logger = logger or StructuredLogger()
        self.generation = 1
        self._components: Dict[str, Component] = {}
        self._providers: Dict[str, list] = {}
        self._workflows: Dict[str, Any] = {}
        self._started = False
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
            for component in self._components.values():
                attempted.append(component)
                await component.start(self)
                started.append(component)
                for spec in component.capabilities:
                    self._providers.setdefault(spec.name, []).append((component, spec))
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
        for component in reversed(tuple(self._components.values())):
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
        self._started = False
        self.logger.emit("info", "runtime_stopped", "runtime stopped")

    def resolve(self, requirement: Union[str, CapabilityRequirement]) -> ProviderBinding:
        if isinstance(requirement, str):
            requirement = CapabilityRequirement(requirement)
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
        return ProviderBinding(spec, component.name, self.generation)

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
        binding = self.resolve(requirement)
        component = self._components[binding.component_name]
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
            result = component.invoke(binding.capability.name, request, invocation)
            if timeout is None:
                result = await result
            else:
                result = await asyncio.wait_for(result, timeout=timeout)
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

    async def run_workflow(self, workflow: Any, value: Any, timeout: Optional[float] = None) -> Any:
        if not self._started:
            raise ComponentLifecycleError("runtime is not started")
        if isinstance(workflow, str):
            try:
                workflow = self._workflows[workflow]
            except KeyError as exc:
                raise KeyError("unknown workflow: {}".format(workflow)) from exc
        run = WorkflowRun(self, Scope(logger=self.logger), workflow.name)
        return await run.execute(workflow, value, timeout=timeout)

