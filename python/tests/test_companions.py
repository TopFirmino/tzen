# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Native Python collection, class binding, fixtures, and documentation."""
import json
import subprocess
import sys
from xml.etree import ElementTree

import pytest
from test_plugin import prepare, trace


def companion(pytester, source, *, count=1):
    path = prepare(pytester, count=count, declarations=False)
    (pytester.path / "test_board.py").write_text(source)
    return path


SOURCE = '''
import pytest
from tzen import TzenCompanionTestCase, step

@pytest.fixture
def instrument(tmp_path):
    path = tmp_path / "instrument"
    path.write_text("ready")
    yield path
    assert path.read_text() == "verified"

class remote(TzenCompanionTestCase):
    """Check the host action while C waits at sync 42."""
    def __init__(self, instrument):
        self.instrument = instrument

    @step("Verify the instrument", critical=True)
    def verify(self):
        self.run.wait_sync(42)
        assert self.instrument.read_text() == "ready"
        self.instrument.write_text("verified")
        self.run.release(42)
'''


def test_companion_fixtures_and_documentation(pytester):
    companion(pytester, SOURCE)
    pytester.runpytest("--tzen-strict-docs", "--tzen-docs=docs.json", "--junitxml=report.xml", "-q").assert_outcomes(passed=1)
    assert trace(pytester).count("execute_test") == 1
    assert trace(pytester).count("sync_release") == 1
    document = json.loads((pytester.path / "docs.json").read_text())
    assert document["verified_against_slave"] is True
    record, = document["testcases"]
    assert "requirements" not in record and "tags" not in record
    assert record["companion"] is True
    assert record["nodeid"] == "test_board.py::remote"
    assert record["description"].startswith("Check the host action")
    report = ElementTree.parse(pytester.path / "report.xml")
    assert report.find(".//property[@name='tzen_steps']") is not None


def test_collect_only_never_executes_fixtures(pytester):
    companion(pytester, SOURCE.replace('path.write_text("ready")', 'raise AssertionError("fixture must not run")'))
    assert pytester.runpytest("--collect-only", "--tzen-docs=docs.json", "-q").ret == 0
    assert "execute_test" not in trace(pytester)


def test_remote_declaration(pytester):
    companion(pytester, '''
from tzen import TzenRemoteTestCase
class remote(TzenRemoteTestCase):
    """C owns all execution for this test."""
''')
    pytester.runpytest("--tzen-strict-docs", "-q").assert_outcomes(passed=1)
    assert trace(pytester).count("sync_release") == 1


@pytest.mark.parametrize("source,message", [
    ('from tzen import TzenRemoteTestCase\nclass missing(TzenRemoteTestCase): pass', "must match exactly one"),
    ('from tzen import TzenTestCase\nclass remote(TzenTestCase): pass', "exactly one of"),
    ('from tzen import TzenCompanionTestCase\nclass remote(TzenCompanionTestCase): pass', "at least one"),
    ('from tzen import TzenRemoteTestCase\nclass remote(TzenRemoteTestCase):\n def __init__(self): pass', "cannot define"),
    (SOURCE.replace("TzenCompanionTestCase", "TzenRemoteTestCase"), "cannot define"),
    (SOURCE.replace('class remote(TzenCompanionTestCase):', 'class remote(TzenCompanionTestCase):\n    companion = True'), "not supported"),
])
def test_invalid_declarations(pytester, source, message):
    companion(pytester, source)
    result = pytester.runpytest("-q")
    result.assert_outcomes(errors=1)
    assert message in result.stdout.str()


def test_ambiguous_c_name(pytester):
    companion(pytester, SOURCE, count=2)
    fake = pytester.path / "fake_slave.py"
    fake.write_text(fake.read_text().replace('response.test_info.name = "remote" if command.get_test_info.index == 0 else f"remote{command.get_test_info.index}"', 'response.test_info.name = "remote"'))
    result = pytester.runpytest("-q")
    result.assert_outcomes(errors=1)
    assert "must match exactly one" in result.stdout.str()
    assert trace(pytester)[-1] == "close"


def test_duplicate_binding_across_modules(pytester):
    companion(pytester, SOURCE)
    (pytester.path / "test_other.py").write_text('from tzen import TzenRemoteTestCase\nclass remote(TzenRemoteTestCase): pass')
    result = pytester.runpytest("-q")
    result.assert_outcomes(errors=1)
    assert "Duplicate declaration" in result.stdout.str()
    assert trace(pytester).count("get_tests") == 1


def test_missing_docs_strict_and_warning_modes(pytester):
    companion(pytester, 'from tzen import TzenRemoteTestCase\nclass remote(TzenRemoteTestCase): pass')
    result = pytester.runpytest("--tzen-strict-docs", "-q")
    result.assert_outcomes(errors=1)
    assert "Missing testcase documentation" in result.stdout.str()
    assert not (pytester.path / "trace.txt").exists()
    result = pytester.runpytest("-q")
    result.assert_outcomes(passed=1)
    assert "Missing testcase documentation" in result.stdout.str()


def test_offline_export_never_imports_transport(pytester):
    path = companion(pytester, SOURCE)
    path.write_text(path.read_text().replace("fake_slave:Transport", "nonexistent_device:Transport"))
    output = pytester.path / "offline.json"
    result = subprocess.run([sys.executable, "-m", "tzen", "docs", "test_board.py",
                             "--output", str(output), "-q"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (pytester.path / "trace.txt").exists()
    offline = json.loads(output.read_text())
    assert offline["verified_against_slave"] is False
    assert offline["testcases"][0]["target"] == "remote"
    assert "index" not in offline["testcases"][0]


def test_offline_mode_requires_collect_only(pytester):
    companion(pytester, SOURCE)
    result = pytester.runpytest("--tzen-offline", "-q")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert not (pytester.path / "trace.txt").exists()


def test_module_fixtures_are_isolated_and_registry_is_shared(pytester):
    companion(pytester, SOURCE, count=2)
    other = SOURCE.replace("class remote(", "class remote1(").replace('"ready"', '"other"')
    (pytester.path / "test_other.py").write_text(other)
    # Both C tests succeed in this fixture isolation check.
    fake = pytester.path / "fake_slave.py"
    fake.write_text(fake.read_text().replace("status=self.index", "status=0"))
    pytester.runpytest("-q").assert_outcomes(passed=2)
    assert trace(pytester).count("get_tests") == 1


def test_nested_conftest_and_package_imports(pytester):
    companion(pytester, SOURCE)
    nested = pytester.path / "nested"
    nested.mkdir()
    (nested / "__init__.py").touch()
    (nested / "helpers.py").write_text("TARGET = 'remote'")
    (nested / "conftest.py").write_text("import pytest\n@pytest.fixture\ndef nested_value(): return 42")
    (pytester.path / "test_board.py").unlink()
    (nested / "test_board.py").write_text('''
from .helpers import TARGET
from tzen import TzenCompanionTestCase, step
class Case(TzenCompanionTestCase):
    """Use real package imports and directory-local fixtures."""
    target = TARGET
    @step("Synchronize")
    def synchronize(self, nested_value):
        self.run.wait_sync(nested_value)
        self.run.release(nested_value)
''')
    pytester.runpytest("-q").assert_outcomes(passed=1)


def test_imported_helper_base_is_not_collected(pytester):
    companion(pytester, SOURCE)
    (pytester.path / "helpers.py").write_text("from tzen import TzenCompanionTestCase\nclass Base(TzenCompanionTestCase): pass")
    p = pytester.path / "test_board.py"
    p.write_text("from helpers import Base\n" + p.read_text().replace("class remote(TzenCompanionTestCase)", "class remote(Base)"))
    pytester.runpytest("-q").assert_outcomes(passed=1)


def test_custom_source_fixture_uses_shared_dispatcher(pytester):
    companion(pytester, SOURCE)
    fake = pytester.path / "fake_slave.py"
    fake.write_text(fake.read_text().replace('self.run_id = command.execute_test.run_id',
        'self.push(ttp.TargetToHost(log=ttp.LogEvent(source=7, scope=ttp.LogEvent.GLOBAL, message="coverage")))\n            self.run_id = command.execute_test.run_id'))
    (pytester.path / "conftest.py").write_text('''import pytest
@pytest.fixture(scope="session", autouse=True)
def coverage(tzen_client):
    received = []
    with tzen_client.events.subscribe(received.append, source=7):
        yield
    assert len(received) == 1
    assert received[0].log.message == "coverage"
''')
    pytester.runpytest("-q").assert_outcomes(passed=1)
