"""Fixture lifetime boundaries within a single collected C/Python testcase."""
import json

import pytest
from test_companions import companion
from test_plugin import trace

SOURCE = '''
from pathlib import Path
import pytest
from tzen import TzenCompanionTestCase, step

events = []
def record(value):
    events.append(value)
    Path("events.json").write_text(__import__("json").dumps(events))

@pytest.fixture
def persistent():
    record("persistent open")
    yield object()
    record("persistent close")

@pytest.fixture
def dependency():
    record("dependency open")
    yield object()
    record("dependency close")

@pytest.fixture
def transient(dependency, request):
    record("transient open")
    request.addfinalizer(lambda: record("transient finalizer"))
    yield object()
    record("transient close")

class remote(TzenCompanionTestCase):
    """Class name binds to C without an explicit target."""
    def __init__(self, persistent):
        self.persistent = persistent
        record("constructor")

    @step("First")
    def first(self, transient, persistent):
        assert persistent is self.persistent
        self.first_resource = transient
        record("first")
        self.run.wait_sync(42)

    @step("Second")
    def second(self, transient):
        assert transient is not self.first_resource
        record("second")
        self.run.release(42)
'''


def events(pytester):
    return json.loads((pytester.path / "events.json").read_text())


def test_step_fixture_recreated_and_dependencies_close_in_reverse_order(pytester):
    companion(pytester, SOURCE)
    pytester.runpytest("-q").assert_outcomes(passed=1)
    assert events(pytester) == [
        "persistent open", "constructor",
        "dependency open", "transient open", "first", "transient close", "transient finalizer", "dependency close",
        "dependency open", "transient open", "second", "transient close", "transient finalizer", "dependency close",
        "persistent close",
    ]


@pytest.mark.parametrize("critical", [False, True])
def test_step_fixtures_close_on_assertion_and_skipped_steps_do_not_open(pytester, critical):
    source = SOURCE.replace('@step("First")', f'@step("First", critical={critical})')
    source = source.replace('self.run.wait_sync(42)', 'self.run.wait_sync(42)\n        assert False, "failed step"')
    companion(pytester, source)
    pytester.runpytest("-q").assert_outcomes(failed=1)
    values = events(pytester)
    assert values[-1] == "persistent close"
    assert values.count("transient close") == (1 if critical else 2)
    assert ("second" in values) is (not critical)
    assert "abort_test" in trace(pytester)


def test_fixture_setup_failure_cleans_dependencies_and_stops(pytester):
    source = SOURCE.replace('    yield object()\n    record("transient close")',
                            '    assert False, "fixture setup failed"\n    yield object()\n    record("transient close")')
    companion(pytester, source)
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
    assert "FixtureSetupError" in result.stdout.str()
    assert events(pytester)[-3:] == ["transient finalizer", "dependency close", "persistent close"]
    assert "first" not in events(pytester) and "second" not in events(pytester)


def test_fixture_finalizer_failure_runs_remaining_cleanup_and_stops(pytester):
    source = SOURCE.replace('    record("transient close")',
                            '    record("transient close")\n    raise RuntimeError("cleanup failed")')
    companion(pytester, source)
    result = pytester.runpytest("-q")
    result.assert_outcomes(failed=1)
    assert "FixtureTeardownError" in result.stdout.str()
    assert events(pytester)[-3:] == ["transient finalizer", "dependency close", "persistent close"]
    assert "second" not in events(pytester)


def test_constructor_failure_still_finalizes_constructor_fixture(pytester):
    companion(pytester, SOURCE.replace('record("constructor")', 'record("constructor")\n        raise RuntimeError("bad constructor")'))
    pytester.runpytest("-q").assert_outcomes(failed=1)
    assert events(pytester) == ["persistent open", "constructor", "persistent close"]
    assert "execute_test" not in trace(pytester)


def test_shared_constructor_dependency_is_not_finalized_by_step(pytester):
    source = SOURCE.replace("def transient(dependency, request):", "def transient(dependency, persistent, request):")
    companion(pytester, source)
    pytester.runpytest("-q").assert_outcomes(passed=1)
    assert events(pytester).count("persistent open") == 1
    assert events(pytester).count("persistent close") == 1
    assert events(pytester)[-1] == "persistent close"


def test_module_scope_is_preserved(pytester):
    source = SOURCE.replace('@pytest.fixture\ndef transient', '@pytest.fixture(scope="module")\ndef transient')
    source = source.replace('@pytest.fixture\ndef dependency', '@pytest.fixture(scope="module")\ndef dependency')
    source = source.replace('assert transient is not self.first_resource', 'assert transient is self.first_resource')
    companion(pytester, source)
    pytester.runpytest("-q").assert_outcomes(passed=1)
    assert events(pytester).count("transient open") == 1
    assert events(pytester)[-3:] == ["transient close", "transient finalizer", "dependency close"]


def test_optional_constructor_and_default_target(pytester):
    companion(pytester, '''
import pytest
from pathlib import Path
from tzen import TzenCompanionTestCase, step

@pytest.fixture
def probe():
    yield 42
    Path("closed").touch()

class remote(TzenCompanionTestCase):
    """No constructor and no target override are necessary."""
    @step("Synchronize")
    def synchronize(self, probe):
        self.run.wait_sync(probe)
        self.run.release(probe)

    @step("Verify previous step cleanup")
    def verify(self):
        assert Path("closed").exists()
''')
    pytester.runpytest("-q").assert_outcomes(passed=1)
