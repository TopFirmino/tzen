from collections import deque
import unittest
from tzen import Client, CommandError
from ttp.python import ttp
from tzen import framing


class FakeTransport:
    def __init__(self):
        self.rx = deque()
        self.commands = []
        self.closed = False

    def push(self, message):
        self.rx.extend(framing.encode_frame(message))

    def read(self, size):
        return bytes([self.rx.popleft()]) if self.rx else b""

    def write(self, frame):
        command = framing.decode_frame(frame[1:-1], ttp.HostToTarget)
        self.commands.append(command)
        response = ttp.TargetToHost(seq_id=command.seq_id)
        kind = command.WhichOneof("cmd")
        if kind == "get_tests":
            response.tests_count.total_tests = 1
        elif kind == "get_test_info":
            response.test_info.index = 0
            response.test_info.name = "example"
            response.test_info.total_steps = 2
        self.push(response)
        if kind == "execute_test":
            self.run_id = command.execute_test.run_id
            self.push(ttp.TargetToHost(log=ttp.LogEvent(message="hello", run_id=self.run_id)))
            self.push(ttp.TargetToHost(test_event=ttp.TestEvent(
                run_id=self.run_id, sync=ttp.SyncWaitEvent(sync_id=42))))
        elif kind in ("abort_test", "sync_release"):
            self.push(ttp.TargetToHost(test_event=ttp.TestEvent(run_id=self.run_id,
                finished=ttp.TestFinishedEvent(status=2 if kind == "abort_test" else 0))))

    def close(self):
        self.closed = True


class ClientTests(unittest.TestCase):
    def test_discovery_run_release_and_abort(self):
        transport = FakeTransport()
        with Client(transport) as client:
            self.assertEqual(client.discover()[0].total_steps, 2)
            self.assertTrue(client.run("example").passed)
            result = client.run(0, on_sync=lambda event: False)
            self.assertEqual(result.status, ttp.TestFinishedEvent.ABORTED)
            self.assertEqual([c.seq_id for c in transport.commands], list(range(1, len(transport.commands)+1)))
        self.assertTrue(transport.closed)

    def test_interleaved_events_are_preserved(self):
        transport = FakeTransport()
        transport.push(ttp.TargetToHost(log=ttp.LogEvent(message="before response")))
        client = Client(transport)
        self.assertEqual(len(client.discover()), 1)
        self.assertEqual(client.receive().log.message, "before response")
        client._seq = 0xFFFFFFFF
        client.discover()
        self.assertEqual([c.seq_id for c in transport.commands][-2:], [0xFFFFFFFF, 1])

    def test_timeout_queue_bound_and_command_error(self):
        transport = FakeTransport()
        client = Client(transport, timeout=0.01, max_queued_events=1)
        with self.assertRaises(TimeoutError):
            client.receive()
        for _ in range(2):
            transport.push(ttp.TargetToHost(log=ttp.LogEvent(message="queued")))
        with self.assertRaises(BufferError):
            client.discover()
        error = CommandError(ttp.TargetToHost(seq_id=1, status=ttp.RESULT_ERR_BUSY))
        self.assertIn("RESULT_ERR_BUSY", str(error))

    def test_corruption_rejected(self):
        transport = FakeTransport()
        raw = bytearray(framing.cobs_decode(framing.encode_frame(ttp.TargetToHost(seq_id=1))[1:-1]))
        raw[-1] ^= 1
        transport.rx.extend(b"\0" + framing.cobs_encode(raw) + b"\0")
        with self.assertRaisesRegex(ValueError, "CRC16 mismatch"):
            Client(transport).receive()

    def test_logs_are_connected_to_execution(self):
        result = Client(FakeTransport()).run(0)
        logs = [event.log for event in result.events if event.WhichOneof("payload") == "log"]
        self.assertTrue(logs)
        self.assertTrue(all(log.run_id == result.run_id and log.test_index == result.test.index for log in logs))

        class OtherRunLog(FakeTransport):
            def push(self, message):
                if message.WhichOneof("payload") == "log":
                    message.log.run_id = 999
                super().push(message)

        with self.assertRaisesRegex(RuntimeError, "log belongs to another test run"):
            Client(OtherRunLog()).run(0)

    def test_maximum_log_frame_with_identity(self):
        message = ttp.TargetToHost(seq_id=0xFFFFFFFF, status=ttp.RESULT_ERR_INVALID,
            log=ttp.LogEvent(level=ttp.LogEvent.ERROR, message="x" * 63,
                run_id=0xFFFFFFFF, test_index=0xFFFFFFFF))
        self.assertEqual(len(ttp.encode_message(message)), 89)
        self.assertLessEqual(len(framing.encode_frame(message)), framing.MAX_FRAME_SIZE)
        transport = FakeTransport()
        transport.push(message)
        self.assertEqual(Client(transport).receive(), message)
