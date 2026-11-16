"""Combined collection, native pytest fixtures, documentation, and abort paths."""
import json
import subprocess
import sys

import pytest

from test_plugin import prepare, trace
from tzen.config import Settings
from tzen.declarations import load_declarations, documentation_record


def companion(pytester, source, *, count=1):
    path = prepare(pytester, count=count)
    path.write_text(path.read_text().replace("[tzen]\n", '[tzen]\ncompanion_paths = ["case_board.py"]\n'))
    (pytester.path / "case_board.py").write_text(source)
    return path


SOURCE = '''
import pytest
from tzen import testcase

@pytest.fixture
def instrument(tmp_path):
    path = tmp_path / "instrument"
    path.write_text("ready")
    yield path
    assert path.read_text() == "verified"

@testcase(target="remote", companion=True, requirements=["REQ-1"], tags=["io"])
def remote(tzen_case, instrument):
    """Check the host action while C waits at sync 42."""
    with tzen_case.run() as run:
        run.wait_sync(42)
        assert instrument.read_text() == "ready"
        instrument.write_text("verified")
        run.release(42)
    assert run.result.passed
'''


def test_companion_fixtures_and_documentation(pytester):
    companion(pytester, SOURCE)
    result = pytester.runpytest("--tzen-strict-docs", "--tzen-docs=docs.json", "--junitxml=report.xml", "-q")
    result.assert_outcomes(passed=1)
    assert trace(pytester).count("execute_test") == 1
    assert trace(pytester).count("sync_release") == 1
    document = json.loads((pytester.path / "docs.json").read_text())
    assert document["verified_against_slave"] is True
    record, = document["testcases"]
    assert record["requirements"] == ["REQ-1"]
    assert record["companion"] is True
    assert record["nodeid"] == "slave::remote[0]"
    assert record["description"].startswith("Check the host action")
    assert "tzen_documentation" in (pytester.path / "report.xml").read_text()


def test_collect_only_does_not_execute_companion_or_fixture(pytester):
    companion(pytester, SOURCE.replace('path.write_text("ready")', 'raise AssertionError("fixture must not run")'))
    result = pytester.runpytest("--collect-only", "--tzen-docs=docs.json", "-q")
    assert result.ret == 0
    assert "execute_test" not in trace(pytester)
    assert len(json.loads((pytester.path / "docs.json").read_text())["testcases"]) == 1


def test_documentation_only_function_is_never_called(pytester):
    companion(pytester, '''
from tzen import testcase
@testcase(target="remote", requirements=["REQ-STATIC"])
def describe():
    """C owns all execution for this test."""
    raise AssertionError("documentation-only body must never execute")
''')
    pytester.runpytest("--tzen-strict-docs", "-q").assert_outcomes(passed=1)
    assert trace(pytester).count("sync_release") == 1


@pytest.mark.parametrize("body", [
    'run.wait_sync(99)',
    'run.wait_sync(42)\n        assert False, "host verification failed"',
    'run.wait_sync(42)',  # An unreleased sync must not be released implicitly.
])
def test_python_failure_aborts_without_releasing_sync(pytester, body):
    companion(pytester, f'''
from tzen import testcase
@testcase(target="remote", companion=True)
def check(tzen_case):
    """Check abort on a failed host operation."""
    with tzen_case.run() as run:
        {body}
''')
    pytester.runpytest("-q").assert_outcomes(failed=1)
    assert "abort_test" in trace(pytester)
    assert "sync_release" not in trace(pytester)
    assert trace(pytester)[-1] == "close"


def test_companion_must_execute_c_counterpart(pytester):
    companion(pytester, '''
from tzen import testcase
@testcase(target="remote", companion=True)
def forgotten(tzen_case):
    """This companion accidentally omits C execution."""
''')
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
    assert "must complete its C counterpart" in result.stdout.str()
    assert "execute_test" not in trace(pytester)


@pytest.mark.parametrize("source,count,message", [
    (SOURCE.replace('target="remote"', 'target="missing"'), 1, "must match exactly one"),
    (SOURCE, 2, "must match exactly one"),
    (SOURCE + '\n@testcase(target="remote")\ndef duplicate(): pass\n', 1, "Duplicate declaration"),
])
def test_invalid_bindings_are_collection_errors(pytester, source, count, message):
    companion(pytester, source, count=count)
    result = pytester.runpytest("-q")
    result.assert_outcomes(errors=1)
    assert message in result.stdout.str()
    if (pytester.path / "trace.txt").exists():
        assert "execute_test" not in trace(pytester)
        assert trace(pytester)[-1] == "close"


def test_missing_docs_strict_and_warning_modes(pytester):
    prepare(pytester, count=1)
    result = pytester.runpytest("--tzen-strict-docs", "-q")
    result.assert_outcomes(errors=1)
    assert "Missing testcase documentation" in result.stdout.str()
    assert "execute_test" not in trace(pytester)
    result = pytester.runpytest("-q")
    result.assert_outcomes(passed=1)
    assert "Missing testcase documentation" in result.stdout.str()


def test_offline_export_never_imports_or_opens_transport(pytester):
    path = companion(pytester, SOURCE)
    path.write_text(path.read_text().replace("fake_slave:Transport", "nonexistent_device:Transport"))
    output = pytester.path / "offline.json"
    result = subprocess.run([sys.executable, "-m", "tzen", "docs", "--config", str(path),
                             "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (pytester.path / "trace.txt").exists()
    document = json.loads(output.read_text())
    assert document["verified_against_slave"] is False
    assert document["testcases"][0]["target"] == "remote"


def test_paths_are_relative_to_config_and_offline_docs_match(pytester):
    path = companion(pytester, SOURCE)
    settings = Settings.load(path)
    assert settings.companion_paths == (pytester.path / "case_board.py",)
    declarations, _ = load_declarations(settings.companion_paths)
    pytester.runpytest("--collect-only", "--tzen-docs=docs.json", "-q")
    live = json.loads((pytester.path / "docs.json").read_text())["testcases"][0]
    offline = json.loads(json.dumps(documentation_record(declarations["remote"])))
    assert all(live[key] == value for key, value in offline.items())


def test_c_failure_cannot_be_hidden_by_companion(pytester):
    companion(pytester, SOURCE)
    fake = pytester.path / "fake_slave.py"
    fake.write_text(fake.read_text().replace("status=self.index", "status=1"))
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
    assert "remote (index 0, run 1): FAIL" in result.stdout.str()


def test_successful_abort_allows_next_test(pytester):
    companion(pytester, '''
from tzen import testcase
@testcase(target="remote", companion=True)
def check(tzen_case):
    """Abort while waiting at sync 42."""
    with tzen_case.run() as run:
        run.wait_sync(42)
        assert False, "host assertion"
''', count=2)
    fake = pytester.path / "fake_slave.py"
    fake.write_text(fake.read_text().replace('response.test_info.name = "remote"',
                    'response.test_info.name = "remote" if command.get_test_info.index == 0 else "second"')
                    .replace("status=self.index", "status=0"))
    pytester.runpytest("-q").assert_outcomes(failed=1, passed=1)
    assert trace(pytester).count("execute_test") == 2
    assert trace(pytester).count("abort_test") == 1


def test_python_setup_error_does_not_start_c(pytester):
    companion(pytester, SOURCE.replace('path.write_text("ready")', 'raise OSError("instrument unavailable")'))
    pytester.runpytest("-q").assert_outcomes(errors=1)
    assert "execute_test" not in trace(pytester)


def test_explicit_local_path_does_not_duplicate_declaration(pytester):
    companion(pytester, SOURCE)
    result = pytester.runpytest("case_board.py", "--collect-only", "-q")
    assert result.ret == 0
    assert "1 test collected" in result.stdout.str()
