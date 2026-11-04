"""Explicit Python workflow composition primitives."""

import inspect
from typing import Any, Awaitable, Callable, Iterable, List, Optional, Sequence, Tuple

from .contracts import CapabilitySpec
from .errors import WorkflowError
from .execution import Component, Invocation, WorkflowRun, _maybe_await


class WorkflowDefinition:
    def __init__(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("workflow name must not be empty")
        self.name = name

    async def execute(self, context: "WorkflowContext", value: Any) -> Any:
        raise NotImplementedError


class WorkflowContext:
    def __init__(self, run: WorkflowRun) -> None:
        self.run = run

    async def invoke(self, capability: Any, request: Any, timeout: Optional[float] = None) -> Any:
        self.run.scope.raise_if_cancelled()
        return await self.run.invoke(capability, request, timeout=timeout)

    async def child(self, workflow: WorkflowDefinition, value: Any, timeout: Optional[float] = None) -> Any:
        self.run.scope.raise_if_cancelled()
        return await self.run.run_child(workflow, value, timeout=timeout)


WorkflowStep = Callable[[WorkflowContext, Any], Any]
Predicate = Callable[[WorkflowContext, Any], Any]


class CallableWorkflow(WorkflowDefinition):
    def __init__(self, name: str, function: WorkflowStep) -> None:
        super().__init__(name)
        self._function = function

    async def execute(self, context: WorkflowContext, value: Any) -> Any:
        context.run.scope.raise_if_cancelled()
        return await _maybe_await(self._function(context, value))


class SerialWorkflow(WorkflowDefinition):
    def __init__(self, name: str, steps: Iterable[WorkflowStep]) -> None:
        super().__init__(name)
        self._steps = tuple(steps)
        if not self._steps:
            raise ValueError("serial workflow must contain at least one step")

    async def execute(self, context: WorkflowContext, value: Any) -> Any:
        result = value
        for step in self._steps:
            context.run.scope.raise_if_cancelled()
            result = await _maybe_await(step(context, result))
        return result


class RouteWorkflow(WorkflowDefinition):
    def __init__(
        self,
        name: str,
        branches: Iterable[Tuple[Predicate, WorkflowDefinition]],
        fallback: Optional[WorkflowDefinition] = None,
    ) -> None:
        super().__init__(name)
        self._branches = tuple(branches)
        self._fallback = fallback
        if not self._branches and fallback is None:
            raise ValueError("route workflow must contain a branch or fallback")

    async def execute(self, context: WorkflowContext, value: Any) -> Any:
        for predicate, workflow in self._branches:
            selected = await _maybe_await(predicate(context, value))
            if selected:
                return await context.child(workflow, value)
        if self._fallback is not None:
            return await context.child(self._fallback, value)
        raise WorkflowError("route workflow {} has no matching branch".format(self.name))


class ChildWorkflow(WorkflowDefinition):
    def __init__(self, name: str, child: WorkflowDefinition) -> None:
        super().__init__(name)
        self.child_workflow = child

    async def execute(self, context: WorkflowContext, value: Any) -> Any:
        return await context.child(self.child_workflow, value)


class WorkflowComponent(Component):
    """Expose a workflow as a normal capability provider."""

    def __init__(self, workflow: WorkflowDefinition) -> None:
        super().__init__("workflow:" + workflow.name)
        self.workflow = workflow
        self._capability = CapabilitySpec("workflow." + workflow.name)

    @property
    def capabilities(self) -> Sequence[CapabilitySpec]:
        return (self._capability,)

    async def invoke(self, capability: str, request: Any, invocation: Invocation) -> Any:
        if capability != self._capability.name:
            raise KeyError("unknown workflow capability: {}".format(capability))
        invocation.raise_if_cancelled()
        return await invocation.run.run_child(self.workflow, request)

