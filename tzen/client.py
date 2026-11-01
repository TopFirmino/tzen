"""Single-threaded test harness client with bounded receive deadlines."""
from collections import deque
from dataclasses import dataclass
import time
from ttp.python import ttp
from tzen import framing


class CommandError(RuntimeError):
    def __init__(self, response):
        self.response = response
        super().__init__(ttp.ResultCode.Name(response.status))


@dataclass(frozen=True)
class TestInfo:
    index: int
    name: str
    total_steps: int


@dataclass
class TestResult:
    run_id: int
    test: TestInfo
    status: int
    events: list

    @property
    def passed(self):
        return self.status == ttp.TestFinishedEvent.SUCCESS


class Client:
    """One client owns a transport. No concurrent requests or automatic retries.

    The supplied transport must provide read(size), write(bytes), close(). Its
    read must return periodically (SerialTransport uses a 50 ms read timeout).
    """
    def __init__(self, transport, timeout=5.0, max_queued_events=256):
        if timeout <= 0 or max_queued_events <= 0:
            raise ValueError("timeout and queue bound must be positive")
        self.transport = transport
        self.timeout = timeout
        self.max_queued_events = max_queued_events
        self._seq = self._run = 1
        self._events = deque()
        self._frame = bytearray()
        self._in_frame = self._dropping = False

    @classmethod
    def serial(cls, port, baudrate=115200, timeout=5.0, reset_wait=2.0):
        from .transport import SerialTransport
        return cls(SerialTransport(port, baudrate, reset_wait), timeout)

    def close(self):
        self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _wire(self, deadline):
        while time.monotonic() < deadline:
            chunk = self.transport.read(1)
            if not chunk:
                continue
            value = chunk[0]
            if value == 0:
                body = bytes(self._frame) if self._in_frame and not self._dropping else b""
                self._in_frame = True
                self._dropping = False
                self._frame.clear()
                if body:
                    return framing.decode_frame(body, ttp.TargetToHost)
            elif self._in_frame and not self._dropping:
                if len(self._frame) >= framing.MAX_FRAME_SIZE - 2:
                    self._dropping = True
                    self._frame.clear()
                else:
                    self._frame.append(value)
        raise TimeoutError("no complete TTP response before deadline; command outcome may be unknown")

    def request(self, command):
        if not isinstance(command, ttp.HostToTarget):
            raise TypeError("expected HostToTarget command")
        command.seq_id = self._seq
        self._seq = self._seq % 0xFFFFFFFF + 1
        self.transport.write(framing.encode_frame(command))
        deadline = time.monotonic() + self.timeout
        while True:
            response = self._wire(deadline)
            if response.seq_id == 0:
                if len(self._events) >= self.max_queued_events:
                    raise BufferError("too many queued harness events")
                self._events.append(response)
            elif response.seq_id == command.seq_id:
                if response.status != ttp.RESULT_OK:
                    raise CommandError(response)
                return response
            else:
                raise RuntimeError(f"unexpected response sequence {response.seq_id}")

    def receive(self, timeout=None):
        if self._events:
            return self._events.popleft()
        return self._wire(time.monotonic() + (self.timeout if timeout is None else timeout))

    def discover(self):
        response = self.request(ttp.make_get_tests())
        if response.WhichOneof("payload") != "tests_count":
            raise RuntimeError("missing test count")
        return [self.get_test_info(i) for i in range(response.tests_count.total_tests)]

    def get_test_info(self, index):
        response = self.request(ttp.make_get_test_info(index))
        if response.WhichOneof("payload") != "test_info" or response.test_info.index != index:
            raise RuntimeError("invalid test metadata")
        info = response.test_info
        return TestInfo(info.index, info.name, info.total_steps)

    def start(self, index, run_id=None):
        if run_id is None:
            run_id = self._run
            self._run = self._run % 0xFFFFFFFF + 1
        self.request(ttp.make_execute_test(index, run_id))
        return run_id

    def abort(self, run_id):
        return self.request(ttp.make_abort_test(run_id))

    def release(self, run_id, sync_id):
        return self.request(ttp.make_sync_release(run_id, sync_id))

    def run(self, test, on_event=None, on_sync=None, timeout=15.0):
        """Run by index/name. A sync callback returns True to release, False to abort.

        No callback means automatic release. Timeout attempts abort then raises;
        disconnection can prevent confirmation of cleanup on the target.
        """
        if timeout <= 0:
            raise ValueError("run timeout must be positive")
        info = next((t for t in self.discover() if t.name == test), None) if isinstance(test, str) else self.get_test_info(test)
        if info is None:
            raise KeyError(test)
        run_id = self.start(info.index)
        events = []
        deadline = time.monotonic() + timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("test run exceeded deadline")
                event = self.receive(min(self.timeout, remaining))
                if event.seq_id:
                    raise RuntimeError("unexpected command response in event stream")
                if len(events) >= self.max_queued_events:
                    raise BufferError("too many execution events")
                events.append(event)
                if event.WhichOneof("payload") == "test_event":
                    execution = event.test_event
                    if execution.run_id != run_id or execution.test_index != info.index:
                        raise RuntimeError("event belongs to another test run")
                    kind = execution.WhichOneof("event")
                    if on_event:
                        on_event(event)
                    if kind == "finished":
                        return TestResult(run_id, info, execution.finished.status, events)
                    if kind == "sync":
                        release = True if on_sync is None else on_sync(execution)
                        if release:
                            self.release(run_id, execution.sync.sync_id)
                        else:
                            self.abort(run_id)
                elif event.WhichOneof("payload") == "log":
                    if event.log.run_id != run_id or event.log.test_index != info.index:
                        raise RuntimeError("log belongs to another test run")
                    if on_event:
                        on_event(event)
                elif on_event:
                    on_event(event)
        except BaseException:
            try:
                self.abort(run_id)
            except Exception:
                pass
            raise
