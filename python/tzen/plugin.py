"""Discover TTP slave tests as pytest items and execute them sequentially."""
from __future__ import annotations

from pathlib import Path
from functools import wraps
from types import ModuleType
import warnings
import inspect
import json
from dataclasses import asdict

import pytest
from ttp.python import ttp

from .client import Client, TestInfo
from .config import Settings
from .declarations import load_declarations, documentation_record, write_documentation, collection_description
from .execution import RemoteFailure, TzenCase
from .cases import TzenTestCase, class_fixtures
from .steps import StepFailure, execute_steps


def pytest_addoption(parser):
    group = parser.getgroup("tzen", "Embedded tests over TTP")
    group.addoption("--tzen-docs", metavar="PATH", help="Export selected testcase documentation as JSON")
    group.addoption("--tzen-strict-docs", action="store_true", help="Fail collection if testcase documentation is missing")
    group.addoption("--tzen-config", metavar="PATH", help="Configure the TTP slave using a TOML file")


_CONFIG_PATH = pytest.StashKey[Path]()


def pytest_configure(config):
    config.addinivalue_line("markers", "tzen: test discovered on an embedded TTP slave")
    selected = config.getoption("tzen_config")
    path = Path(selected).resolve() if selected else config.rootpath / "tzen.toml"
    if selected and (not path.is_file() or path.suffix != ".toml"):
        raise pytest.UsageError("--tzen-config must name an existing .toml file")
    if selected or path.is_file():
        config.stash[_CONFIG_PATH] = path
        if not config.option.file_or_dir:
            # A configured slave replaces implicit cwd/testpaths discovery.
            # Explicit local paths still opt into collecting Python tests.
            config.args.clear()
    elif config.getoption("tzen_docs") or config.getoption("tzen_strict_docs"):
        raise pytest.UsageError("Documentation collection requires a configured slave; use 'python -m tzen docs' for offline export")


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    """Add the slave alongside any explicitly requested filesystem collectors."""
    report = yield
    if isinstance(collector, pytest.Session) and report.passed:
        path = collector.config.stash.get(_CONFIG_PATH, None)
        if path is not None:
            report.result.append(Slave.from_parent(
                collector, name="slave", nodeid="slave", config_path=path,
                path=collector.config.rootpath,
            ))
    return report


class Slave(pytest.Module):
    """A synthetic pytest module gives companions ordinary fixture lifecycles."""

    def __init__(self, *, config_path: Path, **kwargs):
        super().__init__(**kwargs)
        self.config_path = config_path
        self.broken = False
        self.cases = {}

    def _getobj(self):
        return self.module_object

    def collect(self):
        if getattr(self.config.option, "numprocesses", None) or hasattr(self.config, "workerinput"):
            raise self.CollectError("Tzen requires sequential execution; disable pytest-xdist (-n 0)")
        try:
            self.settings = Settings.load(self.config_path)
            declarations, modules = load_declarations(self.settings.companion_paths)
            transport = self.settings.open_transport()
            self.config.add_cleanup(transport.close)
            self.client = Client(transport, self.settings.command_timeout, self.settings.max_events)
            tests = self.client.discover()
            names = [test.name for test in tests]
            for target in declarations:
                if names.count(target) != 1:
                    raise ValueError(f"Declaration target {target!r} must match exactly one C testcase")
            missing = [test.name for test in tests if test.name not in declarations
                       or not declarations[test.name].documentation.description]
            if missing:
                message = "Missing testcase documentation: " + ", ".join(missing)
                if self.config.getoption("tzen_strict_docs"):
                    raise ValueError(message)
                warnings.warn(pytest.PytestWarning(message), stacklevel=2)
            self.module_object = ModuleType("_tzen_slave")
            # Module-local fixtures are shared within this slave's module scope.
            # Reject ambiguous symbols rather than silently choose a definition.
            for module in modules:
                for name, value in vars(module).items():
                    if (name.startswith("__") or hasattr(value, "__tzen_documentation__")
                            or (inspect.isclass(value) and issubclass(value, TzenTestCase))):
                        continue
                    previous = vars(self.module_object).get(name, value)
                    if previous is not value:
                        raise ValueError(f"Companion modules define conflicting symbol {name!r}; use a shared fixture module")
                    setattr(self.module_object, name, value)
            for test in tests:
                declaration = declarations.get(test.name)
                function = self._function(declaration)
                key = f"test_tzen_{test.index}"
                setattr(self.module_object, key, function)
                self.cases[key] = (test, declaration)
        except Exception as exc:
            raise self.CollectError(f"Tzen discovery failed: {exc}") from exc
        yield from super().collect()

    @staticmethod
    def _function(declaration):
        if declaration is not None and declaration.documentation.companion:
            function = declaration.implementation
            if any(mark.name == "parametrize" for mark in getattr(function, "pytestmark", ())):
                raise ValueError("Companion parametrization is not supported; one declaration binds one C testcase")

            if inspect.isclass(function):
                steps = declaration.documentation.steps
                names = dict.fromkeys(("tzen_case", "request", *class_fixtures(function, steps)))

                def execute_class(**kwargs):
                    execute_steps(function, steps, kwargs["tzen_case"], kwargs,
                                  kwargs["request"].node.step_results)

                execute_class.__signature__ = inspect.Signature([
                    inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY) for name in names
                ])
                execute_class.__doc__ = collection_description(declaration)
                execute_class.pytestmark = getattr(function, "pytestmark", [])
                return execute_class

            @wraps(function)
            def execute(**kwargs):
                function(**kwargs)
                kwargs["tzen_case"].assert_completed()

            execute.__test__ = True
            return execute

        def execute(tzen_case):
            with tzen_case.run(auto_sync=True):
                pass

        if declaration is not None:
            execute.__doc__ = collection_description(declaration)
        return execute


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makeitem(collector, name, obj):
    if not isinstance(collector, Slave):
        return None
    if name not in collector.cases:
        return []
    test, declaration = collector.cases[name]
    label = test.name.replace("::", "_").replace("\n", " ").replace("\r", " ")
    return SlaveItem.from_parent(collector, name=f"{label}[{test.index}]",
                                 callobj=obj, test=test, declaration=declaration)


class SlaveItem(pytest.Function):
    def __init__(self, *, test: TestInfo, declaration, **kwargs):
        super().__init__(**kwargs)
        self.test = test
        self.declaration = declaration
        self.step_results = []
        self.add_marker("tzen")
        self.documentation = (
            documentation_record(declaration) if declaration else
            dict(target=test.name, description="", companion=False, source=None)
        )
        self.documentation.update(index=test.index, total_steps=test.total_steps, nodeid=self.nodeid)
        self.user_properties.append(("tzen_documentation", self.documentation["description"]))

    def repr_failure(self, excinfo, style=None):
        if isinstance(excinfo.value, (RemoteFailure, StepFailure)):
            return str(excinfo.value)
        return super().repr_failure(excinfo)


@pytest.fixture
def tzen_case(request):
    """Provide run-scoped control to the Python counterpart."""
    item = request.node
    if not isinstance(item, SlaveItem):
        raise RuntimeError("tzen_case is only available to declared Tzen companions")
    slave = item.parent
    if slave.broken:
        pytest.skip("Slave connection is unusable after an earlier protocol/transport error")
    diagnostics = []

    def broken():
        slave.broken = True

    def record(event):
        if event.WhichOneof("payload") == "log":
            diagnostics.append(f"{ttp.LogEvent.Level.Name(event.log.level)}: {event.log.message}")
        else:
            execution = event.test_event
            if execution.WhichOneof("event") == "step":
                outcome = "PASS" if execution.step.success else "FAIL"
                diagnostics.append(f"Step {execution.step.step_number}: {outcome}")
            elif execution.WhichOneof("event") == "sync":
                diagnostics.append(f"Sync {execution.sync.sync_id}: waiting")

    case = TzenCase(slave.client, item.test, slave.settings.test_timeout, record, broken)
    yield case
    # Covers misuse such as entering a context manually and abandoning it.
    if case.execution is not None:
        case.execution._abort()
        if case.execution.run_id is not None:
            item.user_properties.extend([("tzen_index", item.test.index),
                                         ("tzen_run_id", case.execution.run_id)])
    if diagnostics:
        item.add_report_section("teardown", "Tzen", "\n".join(diagnostics))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    # Make slave diagnostics visible on the call report, not only teardown.
    report = yield
    if isinstance(item, SlaveItem) and call.when == "call":
        if item.step_results:
            report.sections.append(("Tzen Python steps", "\n".join(
                f"{result.outcome.upper()}: {result.description}"
                + (f" — {result.message}" if result.message else "") for result in item.step_results
            )))
            serialized = json.dumps([asdict(result) for result in item.step_results])
            item.user_properties.append(("tzen_steps", serialized))
            report.user_properties.append(("tzen_steps", serialized))
        case = item.funcargs.get("tzen_case")
        if case is not None and case.execution is not None:
            logs = []
            for event in case.execution.events:
                if event.WhichOneof("payload") == "log":
                    logs.append(event.log.message)
                elif event.test_event.WhichOneof("event") == "step":
                    step = event.test_event.step
                    logs.append(f"Step {step.step_number}: {'PASS' if step.success else 'FAIL'}")
            if logs:
                report.sections.append(("Tzen", "\n".join(logs)))
    return report


def pytest_collection_finish(session):
    output = session.config.getoption("tzen_docs")
    if output and not session.testsfailed:
        records = [item.documentation for item in session.items if isinstance(item, SlaveItem)]
        write_documentation(Path(output), records, verified=True)
