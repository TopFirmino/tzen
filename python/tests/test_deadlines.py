"""A silent execution may legitimately outlast a command-response deadline."""
import time

from test_plugin import FAKE_SLAVE
from tzen import Client

from ttp.python import ttp


def test_execution_uses_test_timeout(tmp_path):
    namespace = {}
    exec(FAKE_SLAVE, namespace)
    FakeTransport = namespace["Transport"]
    class SlowTransport(FakeTransport):
        ready_at = 0.0

        def read(self, size):
            if time.monotonic() < self.ready_at:
                time.sleep(0.001)
                return b""
            return super().read(size)

    transport = SlowTransport(trace=tmp_path / "trace.txt", count=1)

    def on_event(event):
        if event.WhichOneof("payload") == "log":
            transport.ready_at = time.monotonic() + 0.04

    result = Client(transport, timeout=0.01).run(0, on_event=on_event, timeout=0.5)
    assert result.status == ttp.TestFinishedEvent.SUCCESS
