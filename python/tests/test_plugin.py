"""Exercise pytest itself against a slave speaking real framed TTP messages."""
import pytest

from tzen.config import ConfigurationError, Settings
from tzen.transport import TzenTransport


FAKE_SLAVE = '''
from collections import deque
from pathlib import Path
from tzen import framing
from ttp.python import ttp

class Transport:
    def __init__(self, trace="trace.txt", mode="normal", count=3):
        self.rx = deque()
        self.trace = Path(trace)
        self.mode = mode
        self.count = count
        self.trace.write_text("open\\n")

    def record(self, text):
        with self.trace.open("a") as stream:
            stream.write(text + "\\n")

    def read(self, size=1):
        return bytes([self.rx.popleft()]) if self.rx else b""

    def push(self, message):
        self.rx.extend(framing.encode_frame(message))

    def write(self, data):
        command = framing.decode_frame(data[1:-1], ttp.HostToTarget)
        kind = command.WhichOneof("cmd")
        self.record(kind)
        if self.mode == "disconnected":
            raise OSError("device disconnected")
        response = ttp.TargetToHost(seq_id=command.seq_id)
        if kind == "get_tests":
            response.tests_count.total_tests = self.count
        elif kind == "get_test_info":
            response.test_info.index = command.get_test_info.index
            response.test_info.name = "remote" if command.get_test_info.index == 0 else f"remote{command.get_test_info.index}"
            response.test_info.total_steps = 1
        self.push(response)
        if kind == "execute_test":
            self.run_id = command.execute_test.run_id
            self.index = command.execute_test.index
            if self.mode == "silent":
                return
            self.push(ttp.TargetToHost(log=ttp.LogEvent(
                run_id=self.run_id, test_index=self.index, message="slave diagnostic")))
            self.push(ttp.TargetToHost(test_event=ttp.TestEvent(
                run_id=self.run_id, test_index=self.index, sync=ttp.SyncWaitEvent(sync_id=42))))
        elif kind in ("sync_release", "abort_test"):
            self.push(ttp.TargetToHost(test_event=ttp.TestEvent(
                run_id=self.run_id, test_index=self.index,
                finished=ttp.TestFinishedEvent(status=self.index))))

    def close(self):
        self.record("close")
'''


def prepare(pytester, *, mode="normal", count=3, filename="tzen.toml", declarations=True):
    pytester.makepyfile(fake_slave=FAKE_SLAVE)
    pytester.syspathinsert()
    path = pytester.path / filename
    path.write_text(f"""[tzen]
command_timeout = 0.03
test_timeout = 0.08
[tzen.transport]
class = "fake_slave:Transport"
[tzen.transport.parameters]
mode = "{mode}"
count = {count}
""")
    if declarations:
        source = "from tzen import TzenRemoteTestCase\n"
        for index in range(count):
            target = "remote" if index == 0 else f"remote{index}"
            source += f'class Remote{index}(TzenRemoteTestCase):\n    """Remote test {index}."""\n    target = "{target}"\n'
        (pytester.path / "test_board.py").write_text(source)
    return path


def trace(pytester):
    return (pytester.path / "trace.txt").read_text().splitlines()


def test_results_sync_logs_and_cleanup(pytester):
    prepare(pytester)
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1, failed=2)
    result.stdout.fnmatch_lines(["*slave diagnostic*", "*ABORTED*"])
    operations = trace(pytester)
    assert operations.count("get_tests") == 1
    assert operations.count("get_test_info") == 3
    assert operations.count("sync_release") == 3
    assert operations[-1] == "close"


def test_collect_only_never_executes(pytester):
    prepare(pytester)
    result = pytester.runpytest("--collect-only", "-q")
    assert result.ret == 0
    for index in range(3):
        assert f"test_board.py::Remote{index}" in result.stdout.str()
    assert "execute_test" not in trace(pytester)


def test_positional_nodeid_selection(pytester):
    prepare(pytester)
    pytester.runpytest("test_board.py::Remote0", "-q").assert_outcomes(passed=1)
    assert trace(pytester).count("execute_test") == 1


def test_explicit_config_and_keyword_selection(pytester):
    prepare(pytester, filename="board.toml")
    pytester.runpytest("--tzen-config=board.toml", "-k", "Remote0", "-q").assert_outcomes(passed=1, deselected=2)


def test_discovery_failure_closes_transport(pytester):
    prepare(pytester, mode="disconnected")
    result = pytester.runpytest("-q")
    result.assert_outcomes(errors=1)
    assert "device disconnected" in result.stdout.str()
    assert trace(pytester)[-1] == "close"
    assert trace(pytester).count("open") == 1


def test_timeout_aborts_and_stops_further_execution(pytester):
    prepare(pytester, mode="silent")
    pytester.runpytest("-q").assert_outcomes(failed=1, skipped=2)
    assert trace(pytester).count("execute_test") == 1
    assert "abort_test" in trace(pytester)


def test_no_declarations_never_connects(pytester):
    import json

    prepare(pytester, declarations=False)
    result = pytester.runpytest("--tzen-docs=empty.json", "-q")
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
    assert not (pytester.path / "trace.txt").exists()
    report = json.loads((pytester.path / "empty.json").read_text())
    assert report["testcases"] == []
    assert report["verified_against_slave"] is False


def test_undeclared_c_tests_are_not_added(pytester):
    prepare(pytester)
    (pytester.path / "test_board.py").write_text('from tzen import TzenRemoteTestCase\nclass remote(TzenRemoteTestCase):\n    """Only this C test is selected."""\n')
    pytester.runpytest("-q").assert_outcomes(passed=1)
    assert trace(pytester).count("execute_test") == 1


def test_normal_python_discovery_continues(pytester):
    prepare(pytester)
    pytester.makepyfile(test_local="def test_local(): pass")
    pytester.runpytest("-q").assert_outcomes(passed=2, failed=2)


def test_local_selection_does_not_connect(pytester):
    prepare(pytester)
    pytester.makepyfile(test_local="def test_local(): pass")
    pytester.runpytest("test_local.py", "-q").assert_outcomes(passed=1)
    assert not (pytester.path / "trace.txt").exists()


def test_missing_configuration_is_collection_error(pytester):
    prepare(pytester).unlink()
    result = pytester.runpytest("-q")
    result.assert_outcomes(errors=1)
    assert "require --tzen-config" in result.stdout.str()


def test_stop_on_failure_closes_transport(pytester):
    prepare(pytester)
    pytester.runpytest("-x", "-q").assert_outcomes(passed=1, failed=1)
    assert trace(pytester).count("execute_test") == 2
    assert trace(pytester)[-1] == "close"


def test_invalid_configuration_does_not_open_transport(pytester):
    path = prepare(pytester)
    path.write_text(path.read_text().replace("test_timeout = 0.08", "test_timeout = -1"))
    pytester.runpytest("-q").assert_outcomes(errors=1)
    assert not (pytester.path / "trace.txt").exists()


@pytest.mark.parametrize("setting", [
    "test_timeout = -1", "test_timeout = nan", "command_timeout = true",
    "max_events = 0", "max_events = 2.5", "typo = 3", 'companion_paths = ["cases"]',
])
def test_invalid_settings(tmp_path, setting):
    path = tmp_path / "tzen.toml"
    path.write_text(f'[tzen]\n{setting}\n[tzen.transport]\nclass = "x:Y"\n')
    with pytest.raises(ConfigurationError):
        Settings.load(path)


def test_structural_transport_protocol():
    namespace = {}
    exec(FAKE_SLAVE, namespace)
    assert issubclass(namespace["Transport"], TzenTransport)


def test_config_is_not_a_collection_node(pytester):
    prepare(pytester, filename="board.toml")
    result = pytester.runpytest("--tzen-config=board.toml", "--collect-only", "-v")
    assert result.ret == 0
    assert "<Module test_board.py>" in result.stdout.str()
    assert "board.toml" not in result.stdout.str()
    assert "<TzenItem Remote0>" in result.stdout.str()


def test_configured_file_patterns_and_testpaths(pytester):
    prepare(pytester)
    folder = pytester.path / "chosen"
    folder.mkdir()
    (pytester.path / "test_board.py").rename(folder / "board_cases.py")
    pytester.makeini("[pytest]\ntestpaths = chosen\npython_files = *_cases.py")
    pytester.makepyfile(test_ignored="raise AssertionError('should not be imported')")
    assert pytester.runpytest("--collect-only", "-q").ret == 0
    assert trace(pytester).count("get_tests") == 1
