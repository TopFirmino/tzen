"""Validated TOML configuration and user transport construction."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import logging
import math
import time
from functools import partial

from .client import Client
from .events import ExecutionRef, TargetLog
from pathlib import Path
from typing import Any

from .events import LogHandler
from .sinks import FileLogSink

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from .transport import TzenTransport


class ConfigurationError(ValueError):
    """An invalid Tzen configuration or transport declaration."""


def _positive_number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be a finite positive number")
    return float(value)


def _write_log(logger, record: TargetLog):
    logger.log(record.level, "%s", record.message)


def _log_then_write(handler, sink, record):
    handler(record)
    sink.write(record)


@dataclass(frozen=True)
class SinkSettings:
    factory: type
    parameters: dict[str, Any]

    @classmethod
    def parse(cls, table, directory):
        if not isinstance(table, dict) or table.keys() - {"class", "parameters"}:
            raise ConfigurationError("Log sink accepts class and parameters")
        spec = table.get("class")
        if not isinstance(spec, str) or spec.count(":") != 1 or not all(spec.split(":")):
            raise ConfigurationError("sink.class must be 'module:ClassName'")
        module, name = spec.split(":")
        try:
            factory = getattr(import_module(module), name)
        except (ImportError, AttributeError) as exc:
            raise ConfigurationError(f"Cannot import log sink {spec}") from exc
        if not isinstance(factory, type) or not callable(getattr(factory, "write", None)):
            raise ConfigurationError("Log sink class must implement write(record)")
        parameters = table.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ConfigurationError("sink.parameters must be a TOML table")
        if factory is FileLogSink:
            path = parameters.get("path")
            if not isinstance(path, str) or not path:
                raise ConfigurationError("FileLogSink requires a path")
            parameters = dict(parameters, path=str(directory / path))
        return cls(factory, parameters)


@dataclass(frozen=True)
class LogRoute:
    source: int
    handler: LogHandler
    after_test_timeout: float | None
    sink: SinkSettings | None = None


def _log_routes(table, directory):
    if not isinstance(table, dict) or table.keys() - {"sources"}:
        raise ConfigurationError("[tzen.logging] accepts sources")
    sources = table.get("sources", [])
    if not isinstance(sources, list):
        raise ConfigurationError("tzen.logging.sources must be an array of tables")
    routes = []
    seen = set()
    for entry in sources:
        if not isinstance(entry, dict) or entry.keys() - {"source", "logger", "handler", "after_test_timeout", "sink"}:
            raise ConfigurationError("Invalid tzen.logging.sources entry")
        source = entry.get("source")
        if type(source) is not int or not 1 <= source <= 0xffffffff or source in seen:
            raise ConfigurationError("Custom log source must be a unique positive uint32")
        name = entry.get("logger")
        if "handler" in entry:
            spec = entry["handler"]
            if name is not None or not isinstance(spec, str) or spec.count(":") != 1:
                raise ConfigurationError("Specify either logger or handler='module:function'")
            module, function = spec.split(":")
            if not module or not function:
                raise ConfigurationError("handler requires module:function")
            try:
                handler = getattr(import_module(module), function)
            except (AttributeError, ImportError) as exc:
                raise ConfigurationError(f"Cannot import log handler {spec}") from exc
            if not callable(handler):
                raise ConfigurationError(f"Log handler {spec} must be callable")
        else:
            if not isinstance(name, str) or not name.strip():
                raise ConfigurationError("Log route requires a logger name or handler")
            handler = partial(_write_log, logging.getLogger(name))
        timeout = entry.get("after_test_timeout")
        if timeout is not None:
            timeout = _positive_number(timeout, "after_test_timeout")
        sink = SinkSettings.parse(entry["sink"], directory) if "sink" in entry else None
        routes.append(LogRoute(source, handler, timeout, sink))
        seen.add(source)
    return tuple(routes)


@dataclass(frozen=True)
class Settings:
    transport_class: str
    parameters: dict[str, Any]
    command_timeout: float = 5.0
    test_timeout: float = 15.0
    max_events: int = 256

    log_routes: tuple[LogRoute, ...] = ()

    @classmethod
    def load(cls, path: Path) -> Settings:
        try:
            with path.open("rb") as stream:
                document = tomllib.load(stream)
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"Cannot read {path}: {exc}") from exc
        table = document.get("tzen")
        if not isinstance(table, dict):
            raise ConfigurationError("Configuration requires a [tzen] table")
        if "companion_paths" in table:
            raise ConfigurationError("companion_paths is no longer supported; pass test paths to pytest")
        unknown = table.keys() - {"transport", "command_timeout", "test_timeout", "max_events", "logging"}
        if unknown:
            raise ConfigurationError(f"Unknown tzen settings: {', '.join(sorted(unknown))}")
        transport = table.get("transport")
        if not isinstance(transport, dict) or transport.keys() - {"class", "parameters"}:
            raise ConfigurationError("[tzen.transport] accepts class and parameters")
        class_path = transport.get("class")
        if not isinstance(class_path, str) or class_path.count(":") != 1 or not all(class_path.split(":")):
            raise ConfigurationError("transport.class must be 'importable.module:ClassName'")
        parameters = transport.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ConfigurationError("transport.parameters must be a TOML table")
        max_events = table.get("max_events", 256)
        if type(max_events) is not int or max_events <= 0:
            raise ConfigurationError("max_events must be a positive integer")
        return cls(
            class_path, parameters,
            _positive_number(table.get("command_timeout", 5.0), "command_timeout"),
            _positive_number(table.get("test_timeout", 15.0), "test_timeout"),
            max_events, _log_routes(table.get("logging", {}), path.resolve().parent),
        )

    def open_client(self, transport=None):
        client = Client(self.open_transport() if transport is None else transport,
                        self.command_timeout, self.max_events)
        try:
            for route in self.log_routes:
                handler = route.handler
                if route.sink is not None:
                    sink = route.sink.factory(**route.sink.parameters)
                    close = getattr(sink, "close", None)
                    if callable(close):
                        client._resources.callback(close)
                    handler = partial(_log_then_write, handler, sink)
                client.events.subscribe_logs(handler, source=route.source)
        except BaseException:
            client.close()
            raise
        return client

    def receive_after_test(self, client, result):
        """Receive one correlated message per explicitly requested source."""
        identity = ExecutionRef(result.run_id, result.test.index)
        pending = {r.source: time.monotonic() + r.after_test_timeout for r in self.log_routes
                   if r.after_test_timeout is not None}
        if not pending:
            return
        def received(record):
            pending.pop(record.source, None)
        with client.events.subscribe_logs(received, execution=identity):
            while pending:
                remaining = min(pending.values()) - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Missing post-test logs for {identity}, sources {sorted(pending)}")
                client.receive(timeout=remaining)

    def open_transport(self) -> TzenTransport:
        module_name, class_name = self.transport_class.split(":")
        try:
            transport_type = getattr(import_module(module_name), class_name)
        except (ImportError, AttributeError) as exc:
            raise ConfigurationError(f"Cannot import transport {self.transport_class}") from exc
        if not isinstance(transport_type, type):
            raise ConfigurationError("transport.class must identify a class")
        if not all(callable(getattr(transport_type, name, None)) for name in ("read", "write", "close")):
            raise ConfigurationError("Transport must implement read(size), write(data), and close()")
        return transport_type(**self.parameters)
