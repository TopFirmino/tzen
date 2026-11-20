# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""A synchronous, run-scoped API for Python/C companion tests."""
from __future__ import annotations

import time

from ttp.python import ttp

from .client import Client, TestInfo, TestResult


class RemoteFailure(AssertionError):
    """The C part of a testcase did not finish successfully."""


class CaseRun:
    """One context-managed execution; sync requests require explicit release."""

    def __init__(self, client: Client, test: TestInfo, timeout: float, on_event,
                 on_broken, *, auto_sync: bool = False):
        self.client = client
        self.test = test
        self.timeout = timeout
        self.on_event = on_event
        self.on_broken = on_broken
        self.auto_sync = auto_sync
        self._inbox = None
        self.run_id: int | None = None
        self.result: TestResult | None = None
        self.events: list[ttp.TargetToHost] = []
        self.pending_sync: int | None = None
        self.deadline = 0.0

    def __enter__(self):
        if self.run_id is not None:
            raise RuntimeError("a run context cannot be reused")
        try:
            self.run_id, self._inbox = self.client._start_execution(self.test.index, self.on_event)
        except BaseException:
            self.on_broken()
            raise
        self.deadline = time.monotonic() + self.timeout
        return self

    def _receive(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("test run exceeded deadline")
        event = self.client._receive_execution(self._inbox, self.deadline)
        kind = event.WhichOneof("payload")
        if event.seq_id or kind not in ("test_event", "log"):
            raise RuntimeError("unexpected response in test event stream")
        identity = getattr(event, kind)
        run_id = self.run_id
        if run_id is None or identity.run_id != run_id or identity.test_index != self.test.index:
            raise RuntimeError("event belongs to another test run")
        if len(self.events) >= self.client.max_queued_events:
            raise BufferError("too many execution events")
        self.events.append(event)
        if kind == "test_event":
            execution = event.test_event
            detail = execution.WhichOneof("event")
            if detail == "finished":
                self.result = TestResult(run_id, self.test, execution.finished.status, self.events)
            elif detail == "sync":
                self.pending_sync = execution.sync.sync_id
        return event

    def wait_sync(self, sync_id: int) -> None:
        if self.run_id is None:
            raise RuntimeError("enter the run context before waiting")
        while self.pending_sync is None and self.result is None:
            self._receive()
        if self.result is not None:
            raise AssertionError(f"C test finished before sync {sync_id}")
        if self.pending_sync != sync_id:
            raise AssertionError(f"Expected sync {sync_id}, received {self.pending_sync}")

    def release(self, sync_id: int) -> None:
        if self.pending_sync != sync_id:
            raise RuntimeError(f"Sync {sync_id} is not pending")
        self.client.release(self.run_id, sync_id)
        self.pending_sync = None

    def _finish(self):
        while self.result is None:
            if self.pending_sync is not None:
                if not self.auto_sync:
                    raise AssertionError(f"Unreleased sync {self.pending_sync}")
                self.release(self.pending_sync)
            self._receive()
        if not self.result.passed:
            status = ttp.TestFinishedEvent.Status.Name(self.result.status)
            raise RemoteFailure(f"{self.test.name} (index {self.test.index}, run {self.run_id}): {status}")

    def _abort(self):
        if self.run_id is None or self.result is not None:
            return
        try:
            self.client.abort(self.run_id)
            self.deadline = time.monotonic() + self.client.timeout
            while self.result is None:
                self._receive()
        except Exception:
            self.on_broken()

    def __exit__(self, exc_type, exc, traceback):
        try:
            return self._exit(exc_type, exc, traceback)
        finally:
            if self._inbox is not None:
                self._inbox.close()

    def _exit(self, exc_type, exc, traceback):
        if exc_type is not None:
            if not issubclass(exc_type, AssertionError):
                self.on_broken()
            self._abort()
            return False
        try:
            self._finish()
        except BaseException as error:
            if not isinstance(error, AssertionError):
                self.on_broken()
            self._abort()
            raise
        return False


class TzenCase:
    """Fixture API: exactly one C execution belongs to each pytest testcase."""

    def __init__(self, client, test, timeout, on_event, on_broken):
        self._arguments = client, test, timeout, on_event, on_broken
        self.execution: CaseRun | None = None

    def run(self, *, auto_sync: bool = False) -> CaseRun:
        if self.execution is not None:
            raise RuntimeError("a testcase may execute its C counterpart only once")
        self.execution = CaseRun(*self._arguments, auto_sync=auto_sync)
        return self.execution

    def assert_completed(self):
        if self.execution is None or self.execution.result is None:
            raise AssertionError("Python companion must complete its C counterpart using 'with tzen_case.run()'")
        if not self.execution.result.passed:
            raise RemoteFailure("C counterpart did not succeed")
