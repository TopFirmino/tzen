# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Byte transports used by the harness client; protobuf codecs live in ttp; framing lives in tzen."""
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class TzenTransport(Protocol):
    """User-defined, synchronous byte transport.

    The constructor opens the connection and must clean up if opening fails.
    Reads return at most size bytes, or b"" on a bounded read timeout; connection
    loss raises an exception. Writes send all bytes or raise. Both operations
    must return in bounded time so the client can enforce its deadlines.
    close() releases resources and should be idempotent. Subclassing is optional.
    """

    def read(self, size: int = 1) -> bytes: ...

    def write(self, data: bytes) -> None: ...

    def close(self) -> None: ...


class SerialTransport:
    def __init__(self, port, baudrate=115200, reset_wait=2.0):
        import serial
        self.serial = serial.Serial(port, baudrate, timeout=0.05, write_timeout=2.0)
        try:
            time.sleep(reset_wait)  # Mega resets when the USB serial port opens.
            self.serial.reset_input_buffer()
        except BaseException:
            self.serial.close()
            raise

    def read(self, size: int = 1) -> bytes:
        return self.serial.read(size)

    def write(self, data: bytes) -> None:
        if self.serial.write(data) != len(data):
            raise OSError("short serial write")

    def close(self) -> None:
        self.serial.close()
