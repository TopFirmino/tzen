# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Collect explicit Tzen classes through pytest's normal Python discovery."""
from __future__ import annotations

import inspect
import json
import logging
import warnings
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import pytest

from ttp.python import ttp

from .cases import (
    TzenCompanionTestCase,
    TzenRemoteTestCase,
    TzenTestCase,
    class_fixtures,
)
from .client import Client, TestInfo
from .config import Settings
from .declarations import (
    collection_description,
    declare,
    documentation_record,
    write_documentation,
)
from .execution import RemoteFailure, TzenCase
from .steps import StepFailure, execute_steps


def pytest_addoption(parser):
    group = parser.getgroup("tzen", "Embedded tests over TTP")
    group.addoption("--tzen-config", metavar="PATH", help="Configure the TTP slave using TOML")
    group.addoption("--tzen-docs", metavar="PATH", help="Export selected testcase documentation as JSON")
    group.addoption("--tzen-strict-docs", action="store_true", help="Reject missing testcase descriptions")
    group.addoption("--tzen-offline", action="store_true", help="Collect documentation without contacting a slave (requires --collect-only)")


_STATE = pytest.StashKey["SessionState"]()


class SessionState:
    """One lazily opened connection and registry shared by all test modules."""

    def __init__(self, config: pytest.Config, path: Path | None):
        self.config = config
        self.path = path
        self.offline = config.getoption("tzen_offline")
        self.client: Client | None = None
        self.registry: list[TestInfo] | None = None
        self.settings: Settings | None = None
        self.loaded_path: Path | None = None
        self.broken = False
        self.error: str | None = None
        self.targets: dict[str, str] = {}

    def bind(self, declaration, nodeid, module):
        target = declaration.documentation.target
        previous = self.targets.get(target)
        if previous is not None and previous != nodeid:
            raise ValueError(f"Duplicate declaration for {target!r}: {previous} and {nodeid}")
        self.targets[target] = nodeid
        if self.offline:
            return None
        path = self.path
        if path is None:
            for directory in module.parents:
                path = next((directory / name for name in ("tzen-host.toml", "tzen.toml")
                             if (directory / name).is_file()), None)
                if path or directory == self.config.rootpath:
                    break
            if self.registry is not None and self.loaded_path != path:
                raise ValueError("Multiple Tzen configurations selected; specify --tzen-config")
        if self.error is not None:
            raise RuntimeError(self.error)
        if self.registry is None:
            try:
                if path is None:
                    raise ValueError("Tzen tests require --tzen-config, tzen-host.toml or tzen.toml")
                if getattr(self.config.option, "numprocesses", None) or hasattr(self.config, "workerinput"):
                    raise ValueError("Tzen requires sequential execution; disable pytest-xdist (-n 0)")
                self.loaded_path = path
                self.settings = Settings.load(path)
                self.client = self.settings.open_client()
                self.config.add_cleanup(self.client.close)
                self.registry = self.client.discover()
            except Exception as error:
                self.error = f"Tzen discovery failed: {error}"
                raise RuntimeError(self.error) from error
        matches = [test for test in self.registry if test.name == target]
        if len(matches) != 1:
            raise ValueError(f"Declaration target {target!r} must match exactly one C testcase")
        return matches[0]


def pytest_configure(config):
    config.addinivalue_line("markers", "tzen: test bound to an embedded TTP slave")
    if config.getoption("tzen_offline") and not config.getoption("collectonly"):
        raise pytest.UsageError("--tzen-offline requires --collect-only")
    selected = config.getoption("tzen_config")
    path: Path | None = Path(selected).resolve() if selected else None
    if path is not None and (not path.is_file() or path.suffix != ".toml"):
        raise pytest.UsageError("--tzen-config must name an existing .toml file")
    config.stash[_STATE] = SessionState(config, path)


def _execution_function(declaration):
    cls = declaration.implementation
    execute: Callable[..., None]
    if declaration.documentation.companion:
        steps = declaration.documentation.steps
        names = dict.fromkeys(("tzen_case", "request", *class_fixtures(cls, steps)))

        def execute_companion(**kwargs):
            execute_steps(cls, steps, kwargs["tzen_case"], kwargs,
                          kwargs["request"].node.step_results)

        setattr(execute_companion, "__signature__", inspect.Signature([
            inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY) for name in names
        ]))
        execute = execute_companion
    else:
        def execute_remote(tzen_case):
            with tzen_case.run(auto_sync=True):
                pass
        execute = execute_remote

    execute.__doc__ = collection_description(declaration)
    setattr(execute, "pytestmark", getattr(cls, "pytestmark", []))
    return execute


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makeitem(collector, name, obj):
    if not inspect.isclass(obj) or not issubclass(obj, TzenTestCase):
        return None
    if obj in (TzenTestCase, TzenRemoteTestCase, TzenCompanionTestCase) or inspect.isabstract(obj):
        return []
    if not isinstance(collector, pytest.Module):
        return []
    # Imported helper bases and explicit opt-outs are not concrete declarations.
    if obj.__module__ != collector.obj.__name__ or obj.__dict__.get("__test__") is False:
        return []
    try:
        declaration = declare(obj, collector.path)
        if not declaration.documentation.description:
            message = f"Missing testcase documentation: {name}"
            if collector.config.getoption("tzen_strict_docs"):
                raise ValueError(message)
            warnings.warn(pytest.PytestWarning(message), stacklevel=2)
        state = collector.config.stash[_STATE]
        test = state.bind(declaration, f"{collector.nodeid}::{name}", collector.path)
        return TzenItem.from_parent(
            collector, name=name, callobj=_execution_function(declaration),
            test=test, declaration=declaration,
        )
    except Exception as error:
        raise collector.CollectError(str(error)) from error


class TzenItem(pytest.Function):
    def __init__(self, *, test, declaration, **kwargs):
        super().__init__(**kwargs)
        self.test = test
        self.declaration = declaration
        self.step_results = []
        self.add_marker("tzen")
        self.documentation = documentation_record(declaration)
        self.documentation["nodeid"] = self.nodeid
        if test is not None:
            self.documentation.update(index=test.index, total_steps=test.total_steps)
        self.user_properties.append(("tzen_documentation", self.documentation["description"]))

    def repr_failure(self, excinfo, style=None):
        if isinstance(excinfo.value, (RemoteFailure, StepFailure)):
            return str(excinfo.value)
        return super().repr_failure(excinfo)


@pytest.fixture(scope="session")
def tzen_client(request):
    """Shared client: subscribe through client.events, or receive after a run."""
    state = request.config.stash[_STATE]
    if state.broken:
        pytest.skip("Slave connection is unusable after an earlier protocol/transport error")
    if state.client is None:
        raise RuntimeError("tzen_client requires a configured target")
    return state.client


@pytest.fixture
def tzen_case(request):
    """Provide run-scoped control to the Python counterpart."""
    item = request.node
    if not isinstance(item, TzenItem):
        raise RuntimeError("tzen_case is only available to declared Tzen companions")
    slave = item.config.stash[_STATE]
    if slave.broken:
        pytest.skip("Slave connection is unusable after an earlier protocol/transport error")
    settings = slave.settings
    client = slave.client
    if settings is None or client is None or item.test is None:
        raise RuntimeError("tzen_case requires a configured target")
    logger = logging.getLogger(f"tzen.target.test[{item.test.name}]")

    def broken():
        slave.broken = True

    def record(event):
        if event.WhichOneof("payload") == "log":
            level = ttp.LogEvent.Level.Name(event.log.level)
            logger.log(logging.getLevelName(level), "%s", event.log.message)
        elif event.test_event.WhichOneof("event") == "step":
            step = event.test_event.step
            logger.info("Step %d: %s", step.step_number, "PASS" if step.success else "FAIL")
        elif event.test_event.WhichOneof("event") == "sync":
            logger.info("Sync %d: waiting", event.test_event.sync.sync_id)

    case = TzenCase(client, item.test, settings.test_timeout, record, broken)
    yield case
    # Covers misuse such as entering a context manually and abandoning it.
    if case.execution is not None:
        case.execution._abort()
        if case.execution._inbox is not None:
            case.execution._inbox.close()
        if case.execution.run_id is not None:
            item.user_properties.extend([("tzen_index", item.test.index),
                                         ("tzen_run_id", case.execution.run_id)])
        if case.execution.result is not None:
            settings.receive_after_test(client, case.execution.result)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if isinstance(item, TzenItem) and call.when == "call":
        if item.step_results:
            serialized = json.dumps([asdict(result) for result in item.step_results])
            item.user_properties.append(("tzen_steps", serialized))
            report.user_properties.append(("tzen_steps", serialized))
    return report


def pytest_collection_finish(session):
    output = session.config.getoption("tzen_docs")
    if output and not session.testsfailed:
        records = [item.documentation for item in session.items if isinstance(item, TzenItem)]
        state = session.config.stash[_STATE]
        write_documentation(Path(output), records, verified=state.registry is not None and not state.offline)
