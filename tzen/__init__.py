"""Source-checkout compatibility; the installed package lives in python/tzen."""
from pathlib import Path

__path__.append(str(Path(__file__).resolve().parents[1] / "python" / "tzen"))
from .client import Client, CommandError, TestInfo, TestResult
from .transport import SerialTransport, TzenTransport
from .declarations import testcase, Documentation
from .execution import TzenCase

__all__ = ["Client", "CommandError", "TestInfo", "TestResult", "SerialTransport", "TzenTransport", "testcase", "Documentation", "TzenCase"]
