"""Minimal in-memory fact events with scope-bound subscriptions."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
from types import MappingProxyType
import uuid
from typing import Any, Callable, Dict, Optional, Set

from .execution import Scope
from .logging import StructuredLogger


def _freeze_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_payload(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_payload(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_payload(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_payload(item) for item in value)
    return value


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: Any
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    event_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.event_id:
            object.__setattr__(self, "event_id", "event-" + uuid.uuid4().hex)
        if not self.created_at:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc).isoformat())
        object.__setattr__(self, "payload", _freeze_payload(self.payload))
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
    def __init__(self, logger: Optional[StructuredLogger] = None, max_pending: Optional[int] = None) -> None:
        if max_pending is not None and (
            isinstance(max_pending, bool) or not isinstance(max_pending, int) or max_pending < 1
        ):
            raise ValueError("max_pending must be a positive integer")
        self.logger = logger or StructuredLogger()
        self._subscribers: Dict[str, Dict[str, Callable[[Event], Any]]] = {}
        self._pending: Dict[str, Set[asyncio.Task]] = {}
        self._pending_count = 0
        self._workflow_pending: Set[asyncio.Task] = set()
        self.max_pending = max_pending
        self.dropped = 0

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
        scope: Optional[Scope] = None,
    ) -> EventSubscription:
        if not event_type or not event_type.strip():
            raise ValueError("event type must not be empty")
        if scope is not None and scope.closed:
            raise RuntimeError("cannot subscribe with a closed scope")
        token = uuid.uuid4().hex
        self._subscribers.setdefault(event_type, {})[token] = handler
        subscription = EventSubscription(self, event_type, token)
        if scope is not None:
            scope.add_cleanup(subscription.close)
        return subscription

    async def publish(self, event: Event) -> None:
        handlers = tuple(self._subscribers.get(event.event_type, {}).items())
        for token, handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    if self.max_pending is not None and self._pending_total() >= self.max_pending:
                        self.dropped += 1
                        self.logger.emit(
                            "warning",
                            "event_backpressure_drop",
                            "event handler dropped because the pending limit was reached",
                            fields={"event_type": event.event_type, "max_pending": self.max_pending},
                        )
                        close = getattr(result, "close", None)
                        if close is not None:
                            close()
                        continue
                    self._schedule(token, event.event_type, result)
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
            if self.max_pending is not None and len(self._workflow_pending) >= self.max_pending:
                self.dropped += 1
                self.logger.emit(
                    "warning",
                    "event_backpressure_drop",
                    "event-triggered workflow dropped because the pending limit was reached",
                    fields={
                        "event_type": event.event_type,
                        "workflow": workflow.name,
                        "max_pending": self.max_pending,
                    },
                )
                return
            task = asyncio.create_task(
                runtime.run_workflow(workflow, event.payload, correlation_id=event.correlation_id)
            )
            tasks.add(task)
            self._workflow_pending.add(task)

            def discard_workflow(completed: asyncio.Task) -> None:
                tasks.discard(completed)
                self._workflow_pending.discard(completed)

            task.add_done_callback(discard_workflow)

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
            async def cancel_tasks() -> None:
                pending = tuple(tasks)
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

            scope.add_cleanup(cancel_tasks)
        return subscription

    def _pending_total(self) -> int:
        return self._pending_count + len(self._workflow_pending)

    def _unsubscribe(self, event_type: str, token: str) -> None:
        handlers = self._subscribers.get(event_type)
        if handlers is None:
            return
        handlers.pop(token, None)
        pending = self._pending.pop(token, ())
        self._pending_count -= len(pending)
        for task in tuple(pending):
            task.cancel()
        if not handlers:
            self._subscribers.pop(event_type, None)

    def _schedule(self, token: str, event_type: str, awaitable: Any) -> None:
        task = asyncio.create_task(awaitable)
        self._pending.setdefault(token, set()).add(task)
        self._pending_count += 1

        def consume_result(completed: asyncio.Task) -> None:
            pending = self._pending.get(token)
            if pending is not None:
                if completed in pending:
                    pending.discard(completed)
                    self._pending_count -= 1
                if not pending:
                    self._pending.pop(token, None)
            if completed.cancelled():
                return
            try:
                completed.result()
            except Exception as exc:
                self.logger.emit(
                    "error",
                    "event_handler_failed",
                    "event handler failed",
                    fields={"event_type": event_type, "error_type": type(exc).__name__},
                )

        task.add_done_callback(consume_result)
