"""Explicit Python workflow composition primitives."""

import asyncio
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple

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
        self.params = run.parameters

    async def invoke(self, capability: Any, request: Any, timeout: Optional[float] = None) -> Any:
        self.run.scope.raise_if_cancelled()
        return await self.run.invoke(capability, request, timeout=timeout)

    def stream(self, capability: Any, request: Any):
        self.run.scope.raise_if_cancelled()
        stream = self.run.runtime.stream(capability, request, run=self.run)

        async def close_stream() -> None:
            await stream.aclose()

        self.run.scope.add_cleanup(close_stream)
        return stream

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


class PipelineWorkflow(SerialWorkflow):
    """An explicitly named ordered data pipeline."""


class ConfiguredWorkflow(WorkflowDefinition):
    """Execute named workflows selected by a validated RuntimeConfig.

    The configuration only names existing WorkflowDefinitions. It does not
    define their internal steps or predicates. ``order`` is a serial path,
    ``parallel`` groups contiguous path members and returns an ordered list,
    and ``branches`` are unconditional single-edge jumps.
    """

    def __init__(
        self,
        name: str,
        workflows: Mapping[str, WorkflowDefinition],
        order: Sequence[str],
        parallel_groups: Sequence[Sequence[str]] = (),
        branches: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        super().__init__(name)
        self._workflows = dict(workflows)
        self._order = tuple(order)
        self._parallel_groups = tuple(tuple(group) for group in parallel_groups)
        self._branches = {}
        for branch in branches:
            source = str(branch["from"])
            target = str(branch["to"])
            if source in self._branches:
                raise WorkflowError("configured workflow has multiple branches from {}".format(source))
            self._branches[source] = target
        self._group_by_start = {}
        self._group_members = set()
        self._validate()

    def _validate(self) -> None:
        if not self._workflows:
            raise WorkflowError("configured workflow has no workflows")
        declared = set(self._workflows)
        if any(name not in declared for name in self._order):
            raise WorkflowError("configured workflow references an unknown workflow")
        for source, target in self._branches.items():
            if source not in declared or target not in declared:
                raise WorkflowError("configured branch references an unknown workflow")
            if source == target:
                raise WorkflowError("configured workflow branch cannot target itself")

        for group in self._parallel_groups:
            if not group:
                raise WorkflowError("configured parallel group must not be empty")
            if any(name not in declared for name in group):
                raise WorkflowError("configured parallel group references an unknown workflow")
            overlap = self._group_members.intersection(group)
            if overlap:
                raise WorkflowError("configured parallel groups overlap")
            self._group_members.update(group)
        if self._parallel_groups and not self._order:
            raise WorkflowError("configured parallel groups require an order")
        positions = {name: index for index, name in enumerate(self._order)}
        for group in self._parallel_groups:
            indexes = [positions.get(name) for name in group]
            if any(index is None for index in indexes):
                raise WorkflowError("configured parallel group must be included in order")
            first = min(indexes)
            expected = tuple(range(first, first + len(group)))
            if tuple(sorted(indexes)) != expected:
                raise WorkflowError("configured parallel group must be contiguous in order")
            self._group_by_start[self._order[first]] = group

        for source in self._branches:
            if source in self._group_members and source not in self._group_by_start:
                raise WorkflowError("configured branch cannot start inside a parallel group")
        for target in self._branches.values():
            if target in self._group_members and target not in self._group_by_start:
                raise WorkflowError("configured branch cannot target inside a parallel group")

        self._validate_branch_cycles()
        if not self._order:
            nodes = set(self._branches) | set(self._branches.values())
            roots = nodes - set(self._branches.values())
            if len(roots) != 1:
                raise WorkflowError("configured branches require one root workflow")
            self._root = next(iter(roots))
        else:
            self._root = self._order[0]
        self._validate_branch_reachability()

    def _validate_branch_cycles(self) -> None:
        for start in self._branches:
            seen = set()
            current = start
            while current in self._branches:
                if current in seen:
                    raise WorkflowError("configured workflow branches contain a cycle")
                seen.add(current)
                current = self._branches[current]

    def _next_in_order(self, name: str) -> Optional[str]:
        if name not in self._order:
            return None
        index = self._order.index(name) + 1
        return self._order[index] if index < len(self._order) else None

    def _validate_branch_reachability(self) -> None:
        reachable = set()
        current = self._root
        while current is not None:
            if current in reachable:
                raise WorkflowError("configured workflow execution contains a cycle")
            group = self._group_by_start.get(current)
            if group is not None:
                if any(name in reachable for name in group):
                    raise WorkflowError("configured workflow execution contains a cycle")
                reachable.update(group)
                branch_source = group[0]
                linear_next = self._next_in_order(group[-1])
            else:
                reachable.add(current)
                branch_source = current
                linear_next = self._next_in_order(current)
            current = self._branches.get(branch_source, linear_next)
        unreachable = set(self._branches) - reachable
        if unreachable:
            raise WorkflowError(
                "configured branch source is unreachable: {}".format(", ".join(sorted(unreachable)))
            )

    async def execute(self, context: "WorkflowContext", value: Any) -> Any:
        result = value
        current = self._root
        visited = set()
        while current is not None:
            if current in visited:
                raise WorkflowError("configured workflow revisited {}".format(current))
            group = self._group_by_start.get(current)
            if group is not None:
                tasks = [asyncio.create_task(context.child(self._workflows[name], result)) for name in group]
                try:
                    results = await asyncio.gather(*tasks)
                except BaseException:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise
                result = list(results)
                visited.update(group)
                branch_source = group[0]
                linear_next = self._next_in_order(group[-1])
            else:
                result = await context.child(self._workflows[current], result)
                visited.add(current)
                branch_source = current
                linear_next = self._next_in_order(current)
            current = self._branches.get(branch_source, linear_next)
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


class ParallelWorkflow(WorkflowDefinition):
    """Run child workflows concurrently and return results in declaration order."""

    def __init__(self, name: str, branches: Iterable[WorkflowDefinition]) -> None:
        super().__init__(name)
        self._branches = tuple(branches)
        if not self._branches:
            raise ValueError("parallel workflow must contain at least one branch")

    async def execute(self, context: WorkflowContext, value: Any) -> Any:
        tasks = [asyncio.create_task(context.child(branch, value)) for branch in self._branches]
        try:
            return await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise


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

