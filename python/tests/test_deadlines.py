"""A silent execution may legitimately outlast a command-response deadline."""
import time

from tzen import Client
from ttp.python import ttp
from tzen.tests.test_client import FakeTransport


def test_execution_uses_test_timeout():
    class SlowTransport(FakeTransport):
        ready_at = 0.0

        def read(self, size):
            if time.monotonic() < self.ready_at:
                time.sleep(0.001)
                return b""
            return super().read(size)

    transport = SlowTransport()

    def on_event(event):
        if event.WhichOneof("payload") == "log":
            transport.ready_at = time.monotonic() + 0.04

    result = Client(transport, timeout=0.01).run(0, on_event=on_event, timeout=0.5)
    assert result.status == ttp.TestFinishedEvent.SUCCESS
