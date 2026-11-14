"""Discover TTP slave tests as pytest items and execute them sequentially."""
from __future__ import annotations

from pathlib import Path

import pytest
from ttp.python import ttp

from .client import Client, TestInfo
from .config import Settings


class RemoteFailure(Exception):
    """An embedded test finished without success."""


def pytest_addoption(parser):
    group = parser.getgroup("tzen", "Embedded tests over TTP")
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


class Slave(pytest.Collector):
    def __init__(self, *, config_path: Path, **kwargs):
        super().__init__(**kwargs)
        self.config_path = config_path

    client: Client
    settings: Settings
    broken = False

    def collect(self):
        # Each xdist worker would otherwise open the same configured slave.
        if getattr(self.config.option, "numprocesses", None) or hasattr(self.config, "workerinput"):
            raise self.CollectError("Tzen requires sequential execution; disable pytest-xdist (-n 0)")
        try:
            self.settings = Settings.load(self.config_path)
            transport = self.settings.open_transport()
            self.config.add_cleanup(transport.close)
            self.client = Client(transport, self.settings.command_timeout, self.settings.max_events)
            tests = self.client.discover()
        except Exception as exc:
            raise self.CollectError(f"Tzen discovery failed: {exc}") from exc
        for test in tests:
            # Index ensures distinct node IDs even when slave names are identical.
            name = test.name.replace("::", "_").replace("\n", " ").replace("\r", " ")
            yield SlaveItem.from_parent(self, name=f"{name}[{test.index}]", test=test)


class SlaveItem(pytest.Item):
    def __init__(self, *, test: TestInfo, **kwargs):
        super().__init__(**kwargs)
        self.test = test
        self.add_marker("tzen")

    def runtest(self):
        slave = self.parent
        if slave.broken:
            pytest.skip("Slave connection is unusable after an earlier protocol/transport error")
        diagnostics = []

        def record(event):
            kind = event.WhichOneof("payload")
            if kind == "log":
                diagnostics.append(f"{ttp.LogEvent.Level.Name(event.log.level)}: {event.log.message}")
            elif kind == "test_event":
                execution = event.test_event
                if execution.WhichOneof("event") == "step":
                    outcome = "PASS" if execution.step.success else "FAIL"
                    diagnostics.append(f"Step {execution.step.step_number}: {outcome}")
                elif execution.WhichOneof("event") == "sync":
                    diagnostics.append(f"Sync {execution.sync.sync_id}: released")

        try:
            result = slave.client.run(self.test, on_event=record, timeout=slave.settings.test_timeout)
        except BaseException:
            # Abort is best effort in Client.run; do not send further executions
            # when the target state or pending response stream is uncertain.
            slave.broken = True
            raise
        finally:
            if diagnostics:
                self.add_report_section("call", "Tzen", "\n".join(diagnostics))
        self.user_properties.extend([("tzen_index", self.test.index), ("tzen_run_id", result.run_id)])
        if not result.passed:
            status = ttp.TestFinishedEvent.Status.Name(result.status)
            raise RemoteFailure(f"{self.test.name} (index {self.test.index}, run {result.run_id}): {status}")

    def repr_failure(self, excinfo, style=None):
        if isinstance(excinfo.value, RemoteFailure):
            return str(excinfo.value)
        return super().repr_failure(excinfo, style=style)

    def reportinfo(self):
        return self.path, None, self.name
