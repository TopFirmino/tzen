import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class NativeEngineTests(unittest.TestCase):
    # The legacy engine/queue/concurrent sources describe the earlier worker
    # implementation. This runner covers the current API and execution queues.
    def test_rx(self):
        self.build_and_run("test_rx.c")

    def test_tx(self):
        self.build_and_run("test_tx.c")

    def test_tx_large(self):
        self.build_and_run("test_tx.c", ["-DTZEN_TH_MAX_PACKET_SIZE=600"])

    def test_rx_concurrent(self):
        self.build_and_run("test_rx.c", ["-pthread", "-DTZEN_TH_TEST_CONCURRENT",
            "-include", "examples/Host/C/host_critical_section.h"],
            ["examples/Host/C/host_critical_section.c"])

    def test_host_protocol(self):
        self.build_and_run(None, ["-pthread", "-include",
            "examples/Host/C/host_critical_section.h"],
            ["examples/Host/C/main.c", "examples/Host/C/protocol_cases.c",
             "examples/Host/C/host_critical_section.c", "testharness-c/src/tzen.c"])

    def test_workers(self):
        self.build_and_run("test_workers.c", ["-pthread", "-DTZEN_TH_TEST_WORKERS_CONCURRENT",
            "-include", "examples/Host/C/host_critical_section.h"],
            ["examples/Host/C/host_critical_section.c"])

    def test_workers_small(self):
        self.build_and_run("test_workers.c", ["-DTZEN_TH_MAX_WORKERS=1", "-DTZEN_TH_RESULT_QUEUE_DEPTH=2"])

    def build_and_run(self, source, flags=(), extra_sources=()):
        with tempfile.TemporaryDirectory(prefix="tzen_native_") as temp:
            exe = Path(temp) / "engine.exe"
            includes = ["testharness-c/inc", "testharness-c/cfg", "ttp/C/inc", "ttp/C/generated", "nanopb"]
            sources = (["testharness-c/tests/" + source] if source else []) + list(extra_sources)
            sources += ["ttp/C/src/ttp.c", "ttp/C/generated/ttp.pb.c", "nanopb/pb_common.c", "nanopb/pb_decode.c", "nanopb/pb_encode.c"]
            command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror"]
            for folder in includes:
                command.extend(["-I", folder])
            subprocess.run(command + list(flags) + sources + ["-o", str(exe)], check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, timeout=10)
