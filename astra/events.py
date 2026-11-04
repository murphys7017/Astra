"""Minimal in-memory fact events with scope-bound subscriptions."""

import asyncio
from dataclasses import dataclass
import uuid
from typing import Any, Callable, Dict, Optional, Set

from .execution import Scope, _maybe_await
from .logging import StructuredLogger


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: Any
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    event_id: str = ""

    def __post_init__(self) -> None:
        if not self.event_id:
            object.__setattr__(self, "event_id", "event-" + uuid.uuid4().hex)
        if not self.event_type or not self.event_type.strip():
            raise ValueError("event type must not be empty")


class EventSubscription:
    def __init__(self, bus: "EventBus", event_type: str, token: str) -> None:
        self._bus = bus
        self.event_type = event_type
        self.token = token
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._bus._unsubscribe(self.event_type, self.token)


class EventBus:
    def __init__(self, logger: Optional[StructuredLogger] = None) -> None:
        self.logger = logger or StructuredLogger()
        self._subscribers: Dict[str, Dict[str, Callable[[Event], Any]]] = {}

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
        scope: Optional[Scope] = None,
    ) -> EventSubscription:
        if not event_type or not event_type.strip():
            raise ValueError("event type must not be empty")
        token = uuid.uuid4().hex
        self._subscribers.setdefault(event_type, {})[token] = handler
        subscription = EventSubscription(self, event_type, token)
        if scope is not None:
            scope.add_cleanup(subscription.close)
        return subscription

    async def publish(self, event: Event) -> None:
        handlers = tuple(self._subscribers.get(event.event_type, {}).values())
        for handler in handlers:
            try:
                await _maybe_await(handler(event))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.emit(
                    "error",
                    "event_handler_failed",
                    "event handler failed",
                    fields={"event_type": event.event_type, "error_type": type(exc).__name__},
                )

    def subscribe_workflow(
        self,
        event_type: str,
        workflow: Any,
        runtime: Any,
        scope: Optional[Scope] = None,
    ) -> EventSubscription:
        tasks: Set[asyncio.Task] = set()

        async def handler(event: Event) -> None:
            task = asyncio.create_task(
                runtime.run_workflow(workflow, event.payload, correlation_id=event.correlation_id)
            )
            tasks.add(task)
            task.add_done_callback(tasks.discard)

            def consume_result(completed: asyncio.Task) -> None:
                if completed.cancelled():
                    return
                try:
                    completed.result()
                except Exception as exc:
                    self.logger.emit(
                        "error",
                        "event_workflow_failed",
                        "event-triggered workflow failed",
                        fields={"workflow": workflow.name, "error_type": type(exc).__name__},
                    )

            task.add_done_callback(consume_result)

        subscription = self.subscribe(event_type, handler, scope=scope)
        if scope is not None:
            def cancel_tasks() -> None:
                for task in tuple(tasks):
                    task.cancel()

            scope.add_cleanup(cancel_tasks)
        return subscription

    def _unsubscribe(self, event_type: str, token: str) -> None:
        handlers = self._subscribers.get(event_type)
        if handlers is None:
            return
        handlers.pop(token, None)
        if not handlers:
            self._subscribers.pop(event_type, None)
