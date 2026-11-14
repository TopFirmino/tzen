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
            response.test_info.name = "remote"
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


def prepare(pytester, *, mode="normal", count=3, filename="tzen.toml"):
    pytester.makepyfile(fake_slave=FAKE_SLAVE)
    pytester.syspathinsert()
    path = pytester.path / filename
    path.write_text(f'''[tzen]
command_timeout = 0.03
test_timeout = 0.08
[tzen.transport]
class = "fake_slave:Transport"
[tzen.transport.parameters]
mode = "{mode}"
count = {count}
''')
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
    assert operations.count("close") == 1
    assert operations[-1] == "close"


def test_collect_only_never_executes(pytester):
    prepare(pytester)
    result = pytester.runpytest("--collect-only", "-q")
    assert result.ret == 0
    for index in range(3):
        assert f"slave::remote[{index}]" in result.stdout.str()
    assert "execute_test" not in trace(pytester)
    assert trace(pytester)[-1] == "close"


def test_explicit_config_and_selection(pytester):
    prepare(pytester, filename="board.toml")
    result = pytester.runpytest("--tzen-config=board.toml", "-k", "remote[0]", "-q")
    result.assert_outcomes(passed=1, deselected=2)
    assert trace(pytester).count("execute_test") == 1


def test_remote_selection(pytester):
    prepare(pytester)
    result = pytester.runpytest("-k", "remote[0]", "-q")
    result.assert_outcomes(passed=1, deselected=2)
    assert trace(pytester).count("execute_test") == 1


def test_discovery_failure_closes_transport(pytester):
    prepare(pytester, mode="disconnected")
    result = pytester.runpytest("-q")
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*device disconnected*"])
    assert trace(pytester)[-1] == "close"


def test_timeout_aborts_and_stops_further_execution(pytester):
    prepare(pytester, mode="silent")
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1, skipped=2)
    operations = trace(pytester)
    assert operations.count("execute_test") == 1
    assert "abort_test" in operations
    assert operations[-1] == "close"


def test_empty_registry(pytester):
    prepare(pytester, count=0)
    result = pytester.runpytest("-q")
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
    assert trace(pytester)[-1] == "close"


def test_ordinary_python_tests_unchanged(pytester):
    pytester.makepyfile("def test_local(): assert True")
    pytester.runpytest("-q").assert_outcomes(passed=1)


def test_stop_on_failure_closes_transport(pytester):
    prepare(pytester)
    result = pytester.runpytest("-x", "-q")
    result.assert_outcomes(passed=1, failed=1)
    assert trace(pytester).count("execute_test") == 2
    assert trace(pytester)[-1] == "close"


def test_junit_report(pytester):
    from xml.etree import ElementTree

    prepare(pytester)
    pytester.runpytest("--junitxml=results.xml", "-q").assert_outcomes(passed=1, failed=2)
    report = ElementTree.parse(pytester.path / "results.xml")
    cases = report.findall(".//testcase")
    assert len(cases) == 3
    assert len(report.findall(".//failure")) == 2
    assert cases[0].find("properties/property[@name='tzen_run_id']").get("value") == "1"


def test_invalid_configuration_does_not_open_transport(pytester):
    path = prepare(pytester)
    path.write_text(path.read_text().replace("test_timeout = 0.08", "test_timeout = -1"))
    pytester.runpytest("-q").assert_outcomes(errors=1)
    assert not (pytester.path / "trace.txt").exists()


@pytest.mark.parametrize("setting", [
    "test_timeout = -1", "test_timeout = nan", "command_timeout = true",
    "max_events = 0", "max_events = 2.5", "typo = 3",
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
    assert "<Slave slave>" in result.stdout.str()
    assert "board.toml" not in result.stdout.str()
    assert "SlaveFile" not in result.stdout.str()


@pytest.mark.parametrize("explicit", [False, True])
def test_normal_discovery_with_slave(pytester, explicit):
    prepare(pytester, filename="board.toml")
    pytester.makepyfile(test_local="def test_local(): pass")
    args = ["test_local.py"] if explicit else []
    result = pytester.runpytest(*args, "--tzen-config=board.toml", "-q")
    result.assert_outcomes(passed=2 if explicit else 1, failed=2)
    assert trace(pytester).count("get_tests") == 1


def test_testpaths_and_marker_selection(pytester):
    prepare(pytester)
    pytester.makeini("[pytest]\ntestpaths = local")
    local = pytester.path / "local"
    local.mkdir()
    (local / "test_local.py").write_text("def test_local(): pass")
    result = pytester.runpytest("local", "-m", "not tzen", "-q")
    result.assert_outcomes(passed=1, deselected=3)
    assert "execute_test" not in trace(pytester)


@pytest.mark.parametrize("explicit_config", [False, True])
def test_slave_only_does_not_import_local_tests(pytester, explicit_config):
    prepare(pytester)
    pytester.makeini("[pytest]\ntestpaths = .")
    pytester.makepyfile(test_local="raise RuntimeError('must not import local tests')")
    args = ["--tzen-config=tzen.toml"] if explicit_config else []
    result = pytester.runpytest(*args, "--collect-only", "-v")
    assert result.ret == 0
    output = result.stdout.str()
    assert "collected 3 items" in output
    assert "<Slave slave>" in output
    assert "<Dir " not in output
    assert "test_local" not in output
    assert "execute_test" not in trace(pytester)
