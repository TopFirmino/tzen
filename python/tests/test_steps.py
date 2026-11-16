"""Class collection, shared instance state, ordered steps and failure policy."""
import json
from xml.etree import ElementTree

import pytest

from test_companions import companion
from test_plugin import trace
from tzen import TzenTestCase, step
from tzen.cases import class_steps


SOURCE = '''
from pathlib import Path
import pytest
from tzen import TzenTestCase, step

@pytest.fixture
def resource():
    order = []
    yield {"value": 7, "order": order}
    Path("order.json").write_text(__import__("json").dumps(order))
    Path("fixture_closed").touch()

class TestRemote(TzenTestCase):
    """Exercise a class-based companion with shared state."""
    target = "remote"

    def __init__(self, resource):
        self.value = resource["value"]
        self.order = resource["order"]

    @step("Wait for C", critical=True)
    def z_wait(self):
        self.run.wait_sync(42)
        self.order.append("wait")

    @step("Verify shared state")
    def a_verify(self):
        assert self.value == 7
        self.value += 1
        self.order.append("verify")

    @step("Release C", critical=True)
    def m_release(self):
        assert self.value == 8
        self.order.append("release")
        self.run.release(42)

'''


def test_class_execution_and_step_reports(pytester):
    companion(pytester, SOURCE)
    pytester.runpytest("--tzen-docs=docs.json", "--junitxml=results.xml", "-q").assert_outcomes(passed=1)
    assert json.loads((pytester.path / "order.json").read_text()) == ["wait", "verify", "release"]
    assert (pytester.path / "fixture_closed").exists()
    assert trace(pytester).count("execute_test") == 1
    docs = json.loads((pytester.path / "docs.json").read_text())["testcases"][0]
    assert docs["companion"] is True
    assert [s["name"] for s in docs["steps"]] == ["z_wait", "a_verify", "m_release"]
    xml = ElementTree.parse(pytester.path / "results.xml")
    results = json.loads(xml.find(".//property[@name='tzen_steps']").get("value"))
    assert [s["outcome"] for s in results] == ["passed"] * 3


@pytest.mark.parametrize("critical", [False, True])
def test_assertion_policy_and_abort(pytester, critical):
    source = SOURCE.replace('@step("Verify shared state")', f'@step("Verify shared state", critical={critical})')
    source = source.replace("assert self.value == 7", 'assert False, "measurement mismatch"')
    source = source.replace("assert self.value == 8", "assert self.value == 7")
    companion(pytester, source)
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
    assert "measurement mismatch" in result.stdout.str()
    assert "Tzen Python steps" in result.stdout.str()
    assert "abort_test" in trace(pytester)
    assert ("sync_release" in trace(pytester)) is (not critical)
    assert json.loads((pytester.path / "order.json").read_text()) == (["wait"] if critical else ["wait", "release"])


def test_unexpected_error_stops_noncritical_step(pytester):
    companion(pytester, SOURCE.replace("assert self.value == 7", 'raise OSError("instrument lost")'))
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
    assert "ERROR: Verify shared state" in result.stdout.str()
    assert "NOT_RUN: Release C" in result.stdout.str()
    assert "sync_release" not in trace(pytester)
    assert "abort_test" in trace(pytester)


def test_collect_does_not_construct_or_execute_class(pytester):
    companion(pytester, SOURCE.replace('self.value = resource["value"]', 'raise AssertionError("setup must not run")'))
    result = pytester.runpytest("--collect-only", "--tzen-docs=docs.json", "-q")
    assert result.ret == 0
    assert "1 test collected" in result.stdout.str()
    assert not (pytester.path / "fixture_closed").exists()
    assert not (pytester.path / "order.json").exists()
    assert "execute_test" not in trace(pytester)


def test_constructor_failure_runs_cleanup_without_starting_c(pytester):
    companion(pytester, SOURCE.replace('self.value = resource["value"]', 'self.order = resource["order"]\n        raise RuntimeError("setup failed")'))
    pytester.runpytest("-q").assert_outcomes(failed=1)
    assert "execute_test" not in trace(pytester)
    assert (pytester.path / "order.json").exists()
    assert (pytester.path / "fixture_closed").exists()


def test_documentation_only_class_does_not_execute_steps(pytester):
    companion(pytester, SOURCE.replace('target = "remote"', 'target = "remote"\n    companion = False'))
    pytester.runpytest("--tzen-strict-docs", "-q").assert_outcomes(passed=1)
    assert "sync_release" in trace(pytester)
    assert not (pytester.path / "order.json").exists()
    assert not (pytester.path / "fixture_closed").exists()


def test_step_fixture_arguments(pytester):
    source = SOURCE.replace("def a_verify(self):", "def a_verify(self, tmp_path):\n        assert tmp_path.is_dir()")
    companion(pytester, source)
    pytester.runpytest("-q").assert_outcomes(passed=1)


def test_default_target_is_class_name(pytester):
    companion(pytester, SOURCE.replace("class TestRemote", "class remote").replace('    target = "remote"\n', ""))
    pytester.runpytest("-q").assert_outcomes(passed=1)


def test_no_duplicate_class_in_local_collection(pytester):
    companion(pytester, SOURCE)
    result = pytester.runpytest("case_board.py", "--collect-only", "-q")
    assert result.ret == 0
    assert "1 test collected" in result.stdout.str()


@pytest.mark.parametrize("change", [
    ('def __init__(self, resource):', 'def setup(self, resource):'),
    ('def z_wait(self):', 'async def z_wait(self):'),
    ('def z_wait(self):', 'def z_wait(self, *args):'),
    ('def z_wait(self):', 'def z_wait(self, value=1):'),
    ('@step("Wait for C", critical=True)', '@staticmethod\n    @step("Wait for C", critical=True)'),
])
def test_invalid_class_is_collection_error(pytester, change):
    companion(pytester, SOURCE.replace(*change))
    pytester.runpytest("-q").assert_outcomes(errors=1)
    assert not (pytester.path / "trace.txt").exists()


def test_step_inheritance_order():
    class Base(TzenTestCase):
        @step("first")
        def first(self): pass

        @step("second")
        def second(self): pass

    class Child(Base):
        @step("override")
        def first(self): pass

        def second(self): pass

        @step("new")
        def last(self): pass

    assert [(s.name, s.description) for s in class_steps(Child)] == [("first", "override"), ("last", "new")]
