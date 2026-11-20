# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Subprocess pipes with periodic reads for the tzen client deadlines."""
import queue
import subprocess
import threading
from pathlib import Path


class PipeTransport:
    def __init__(self, executable=None, *, slave="c"):
        hosts = {"c": ("C", "tzen_host.exe"), "ada": ("ADA", "tzen_host_ada.exe")}
        if slave not in hosts:
            raise ValueError("Host slave must be 'c' or 'ada'")
        if executable is None:
            directory, name = hosts[slave]
            executable = Path(__file__).resolve().parents[1] / directory / name
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, bufsize=0)
        self._bytes = queue.Queue(maxsize=65536)
        self._stop = threading.Event()
        self._eof = threading.Event()
        self._reader = threading.Thread(target=self._receive, daemon=True)
        self._reader.start()

    def _receive(self):
        try:
            while not self._stop.is_set():
                byte = self.process.stdout.read(1)
                if not byte:
                    break
                while not self._stop.is_set():
                    try:
                        self._bytes.put(byte, timeout=0.05)
                        break
                    except queue.Full:
                        pass
        finally:
            self._eof.set()

    def read(self, size=1):
        if size <= 0:
            return b""
        try:
            return self._bytes.get(timeout=0.05)
        except queue.Empty:
            if self._eof.is_set():
                raise EOFError("Host slave closed stdout")
            return b""

    def write(self, data):
        view = memoryview(data)
        while view:
            written = self.process.stdin.write(view)
            if not written:
                raise BrokenPipeError("Host slave pipe write failed")
            view = view[written:]

    def close(self):
        self._stop.set()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self._reader.join(timeout=2)
        self.process.stdout.close()
