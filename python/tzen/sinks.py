"""Post-log destinations for configured target sources."""
import base64
from pathlib import Path
from typing import Protocol

from .events import TargetLog


class LogSink(Protocol):
    """One instance per configured route and client. Called in receive order."""

    def write(self, record: TargetLog) -> None: ...


class FileLogSink:
    """Append UTF-8 lines or independently base64-encoded binary chunks."""

    def __init__(self, path: str, format: str = "text"):
        if format not in ("text", "binary"):
            raise ValueError("format must be text or binary")
        if not isinstance(path, str) or not path:
            raise ValueError("path must be a nonempty string")
        self.path = Path(path)
        self.format = format

    def write(self, record: TargetLog) -> None:
        if self.format == "binary":
            data = base64.b64decode(record.message, validate=True)
        else:
            data = (record.message + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.write(data)
