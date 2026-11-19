"""Application-owned presentation and expectations for the logging demo."""
import time

from tzen import ExecutionRef, execution_of
from ttp.python import ttp

SOURCE_NAMES = {0: "test", 1: "system", 7: "coverage"}
SUMMARY = "Demo coverage summary after TestFinished (synthetic)"


class LogOutput:
    def __init__(self, display=True):
        self.display = display
        self.summaries = set()
        self.finished = set()

    def __call__(self, event):
        identity = execution_of(event)
        if event.WhichOneof("payload") == "log":
            log = event.log
            origin = "global" if identity is None else f"run={identity.run_id} test={identity.test_index}"
            source = SOURCE_NAMES.get(log.source, str(log.source))
            if self.display:
                print(f"[{source} {origin} {ttp.LogEvent.Level.Name(log.level)}] {log.message}", flush=True)
            if log.source == 7 and log.message == SUMMARY:
                if identity not in self.finished:
                    raise AssertionError("Deferred coverage arrived before TestFinished")
                self.summaries.add(identity)
        elif event.WhichOneof("payload") == "test_event":
            execution = event.test_event
            if execution.WhichOneof("event") == "finished":
                self.finished.add(identity)
                status = ttp.TestFinishedEvent.Status.Name(execution.finished.status)
                if self.display:
                    print(f"[finished run={identity.run_id} test={identity.test_index}] {status}", flush=True)

    def wait_summary(self, client, result, timeout=2.0):
        # This example emits exactly one known summary per started test.
        # This is application policy, not a protocol completion event.
        identity = ExecutionRef(result.run_id, result.test.index)
        deadline = time.monotonic() + timeout
        while identity not in self.summaries:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Missing deferred demo coverage summary")
            client.receive(timeout=remaining)
        assert all(event.WhichOneof("payload") != "log" or event.log.source == 0
                   for event in result.events), "Custom messages leaked into testcase diagnostics"
