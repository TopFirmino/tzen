# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Synchronous event subscriptions. No threads, transport ownership or retries."""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Protocol

from ttp.python import ttp

SOURCE_TEST = 0
EventCallback = Callable[[ttp.TargetToHost], None]


@dataclass(frozen=True)
class ExecutionRef:
    run_id: int
    test_index: int


class LogLevel(IntEnum):
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR


@dataclass(frozen=True)
class TargetLog:
    source: int
    level: LogLevel
    message: str
    execution: ExecutionRef | None


class LogHandler(Protocol):
    def __call__(self, record: TargetLog, /) -> None: ...


def _target_log(event: ttp.TargetToHost) -> TargetLog:
    log = event.log
    return TargetLog(log.source, LogLevel[ttp.LogEvent.Level.Name(log.level)],
                     log.message, execution_of(event))


class TestStatus(IntEnum):
    SUCCESS = ttp.TestFinishedEvent.SUCCESS
    FAIL = ttp.TestFinishedEvent.FAIL
    ABORTED = ttp.TestFinishedEvent.ABORTED


def execution_of(event: ttp.TargetToHost) -> ExecutionRef | None:
    kind = event.WhichOneof("payload")
    identity: ttp.TestEvent | ttp.LogEvent
    if kind == "test_event":
        identity = event.test_event
    elif kind == "log" and event.log.scope == ttp.LogEvent.EXECUTION:
        identity = event.log
    else:
        return None
    return ExecutionRef(identity.run_id, identity.test_index)


@dataclass(frozen=True)
class EventFilter:
    """None means any. source filters logs only; global_only excludes executions."""
    source: int | None = None
    execution: ExecutionRef | None = None
    kind: str | None = None
    global_only: bool = False

    def __post_init__(self):
        if self.source is not None and not 0 <= self.source <= 0xFFFFFFFF:
            raise ValueError("source must be a uint32")
        if self.global_only and self.execution is not None:
            raise ValueError("global_only and execution are mutually exclusive")

    def matches(self, event: ttp.TargetToHost) -> bool:
        kind = event.WhichOneof("payload")
        if event.seq_id or kind not in ("test_event", "log"):
            return False
        if self.kind is not None and kind != self.kind:
            return False
        if self.source is not None and (kind != "log" or event.log.source != self.source):
            return False
        identity = execution_of(event)
        return ((self.execution is None or identity == self.execution)
                and (not self.global_only or identity is None))


class Subscription:
    """An idempotently closable subscription, also usable as a context manager."""
    def __init__(self, dispatcher, callback, event_filter):
        self._dispatcher = dispatcher
        self.callback = callback
        self.filter = event_filter

    def close(self) -> None:
        if self._dispatcher is not None:
            self._dispatcher._subscriptions.remove(self)
            self._dispatcher = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class EventDispatcher:
    """Fan out in registration order; callbacks must not mutate the event or read
    the client recursively. Exceptions propagate to the caller (no retries).
    Changes to subscriptions take effect on the next event. No history is kept.
    """
    def __init__(self):
        self._subscriptions: list[Subscription] = []
        self.dispatching = False

    def subscribe(self, callback: EventCallback, *, source: int | None = None,
                  execution: ExecutionRef | None = None, kind: str | None = None,
                  global_only: bool = False) -> Subscription:
        if not callable(callback):
            raise TypeError("callback must be callable")
        subscription = Subscription(self, callback, EventFilter(source, execution, kind, global_only))
        self._subscriptions.append(subscription)
        return subscription

    def subscribe_logs(self, handler: LogHandler, *, source: int | None = None,
                       execution: ExecutionRef | None = None,
                       global_only: bool = False) -> Subscription:
        """Deliver immutable Python records for matching logs in receive order."""
        if not callable(handler):
            raise TypeError("handler must be callable")
        return self.subscribe(lambda event: handler(_target_log(event)), kind="log",
                              source=source, execution=execution, global_only=global_only)

    def dispatch(self, event: ttp.TargetToHost) -> int:
        if self.dispatching:
            raise RuntimeError("recursive event dispatch is not supported")
        self.dispatching = True
        try:
            callbacks = [s.callback for s in tuple(self._subscriptions) if s.filter.matches(event)]
            for callback in callbacks:
                callback(event)
            return len(callbacks)
        finally:
            self.dispatching = False


class _ExecutionInbox:
    """Default test routing uses the same subscriptions exposed to applications."""
    def __init__(self, dispatcher, execution, limit, on_received=None):
        self.on_received = on_received
        self.events: deque[ttp.TargetToHost] = deque()
        self.limit = limit
        self._subscriptions = [
            dispatcher.subscribe(self._append, execution=execution, kind="test_event"),
            dispatcher.subscribe(self._append, execution=execution, source=SOURCE_TEST),
        ]

    def _append(self, event):
        if len(self.events) >= self.limit:
            raise BufferError("too many queued execution events")
        self.events.append(event)
        if self.on_received is not None:
            self.on_received(event)

    def close(self):
        for subscription in self._subscriptions:
            subscription.close()
