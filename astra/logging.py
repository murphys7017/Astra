"""Structured, replaceable and failure-isolated runtime logging."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import queue
import sys
import threading
import time
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Protocol, TextIO


_SECRET_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)
_MAX_TEXT = 4096


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SECRET_MARKERS)


def _redact(value: Any, key: Optional[str] = None) -> Any:
    if key is not None and _is_secret_key(key):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value) > _MAX_TEXT:
        return value[:_MAX_TEXT] + "…"
    return value


@dataclass(frozen=True)
class LogRecord:
    timestamp: str
    level: str
    event: str
    message: str
    run_id: Optional[str] = None
    invocation_id: Optional[str] = None
    scope_id: Optional[str] = None
    component: Optional[str] = None
    workflow: Optional[str] = None
    correlation_id: Optional[str] = None
    fields: Mapping[str, Any] = field(default_factory=dict)


class LogSink(Protocol):
    def write(self, record: LogRecord) -> None:
        ...


class MemoryLogSink:
    """A small sink useful for diagnostics and tests."""

    def __init__(self) -> None:
        self.records = []

    def write(self, record: LogRecord) -> None:
        self.records.append(record)


class FallbackLogSink:
    """A minimal sink that does not require a logging plugin."""

    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self.stream = stream or sys.stderr
        self._lock = threading.Lock()

    def write(self, record: LogRecord) -> None:
        line = "{} {} {} {}".format(record.timestamp, record.level, record.event, record.message)
        with self._lock:
            self.stream.write(line + "\n")
            self.stream.flush()


class NonBlockingLogSink:
    """Bounded queue wrapper that keeps slow sinks out of the execution path."""

    def __init__(self, sink: LogSink, maxsize: int = 1024) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be positive")
        self.sink = sink
        self._queue = queue.Queue(maxsize=maxsize)
        self._sentinel = object()
        self._closed = False
        self.dropped = 0
        self._worker = threading.Thread(target=self._drain, name="astra-log-sink", daemon=True)
        self._worker.start()

    def write(self, record: LogRecord) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    def flush(self) -> None:
        self._queue.join()

    def close(self, timeout: float = 1.0) -> None:
        if self._closed:
            return
        self._closed = True
        deadline = time.monotonic() + timeout
        while True:
            try:
                self._queue.put_nowait(self._sentinel)
                break
            except queue.Full:
                if time.monotonic() >= deadline:
                    return
                time.sleep(0.001)
        self._worker.join(max(0.0, deadline - time.monotonic()))
        close = getattr(self.sink, "close", None)
        if close is not None:
            close()

    def _drain(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is self._sentinel:
                    return
                try:
                    self.sink.write(item)
                except Exception:
                    pass
            finally:
                self._queue.task_done()


class StructuredLogger:
    """The runtime's single structured log entry point."""

    def __init__(
        self,
        sinks: Iterable[LogSink] = (),
        fallback: Optional[LogSink] = None,
    ) -> None:
        self._sinks = list(sinks)
        self._fallback = fallback or FallbackLogSink()

    @property
    def sinks(self):
        return tuple(self._sinks)

    def add_sink(self, sink: LogSink) -> None:
        self._sinks.append(sink)

    def emit(
        self,
        level: str,
        event: str,
        message: str,
        *,
        run_id: Optional[str] = None,
        invocation_id: Optional[str] = None,
        scope_id: Optional[str] = None,
        component: Optional[str] = None,
        workflow: Optional[str] = None,
        correlation_id: Optional[str] = None,
        fields: Optional[Mapping[str, Any]] = None,
    ) -> LogRecord:
        record = LogRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            event=event,
            message=_redact(message),
            run_id=run_id,
            invocation_id=invocation_id,
            scope_id=scope_id,
            component=component,
            workflow=workflow,
            correlation_id=correlation_id,
            fields=_redact(dict(fields or {})),
        )
        if not self._sinks:
            self._safe_fallback(record)
            return record
        for sink in tuple(self._sinks):
            try:
                sink.write(record)
            except Exception:
                self._safe_fallback(
                    LogRecord(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        level="error",
                        event="log_sink_failure",
                        message="log sink failed",
                        fields={"sink": type(sink).__name__},
                    )
                )
        return record

    def _safe_fallback(self, record: LogRecord) -> None:
        try:
            self._fallback.write(record)
        except Exception:
            # Diagnostics must never become a source of runtime failure.
            pass

    def bind(self, **context: Optional[str]) -> "BoundLogger":
        return BoundLogger(self, context)

    def close(self) -> None:
        for sink in tuple(self._sinks):
            close = getattr(sink, "close", None)
            if close is not None:
                close()


class BoundLogger:
    def __init__(self, logger: StructuredLogger, context: Mapping[str, Optional[str]]) -> None:
        self._logger = logger
        self._context = dict(context)

    def emit(self, level: str, event: str, message: str, *, fields: Optional[Mapping[str, Any]] = None) -> LogRecord:
        return self._logger.emit(level, event, message, **self._context, fields=fields)

