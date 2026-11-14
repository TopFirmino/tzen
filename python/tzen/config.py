"""Validated TOML configuration and user transport construction."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import math
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class Settings:
    transport_class: str
    parameters: dict[str, Any]
    command_timeout: float = 5.0
    test_timeout: float = 15.0
    max_events: int = 256

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
        unknown = table.keys() - {"transport", "command_timeout", "test_timeout", "max_events"}
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
            max_events,
        )

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
