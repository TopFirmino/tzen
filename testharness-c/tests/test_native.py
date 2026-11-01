import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

class NativeEngineTests(unittest.TestCase):
    def test_engine(self):
        self.build_and_run("test_engine.c")

    def test_queues(self):
        self.build_and_run("test_queues.c", ["-DTZEN_TH_MAX_PACKET_SIZE=600"])

    def test_concurrent(self):
        self.build_and_run("test_concurrent.c", ["-pthread"])

    def build_and_run(self, source, flags=()):
        with tempfile.TemporaryDirectory(prefix="tzen_native_") as temp:
            exe = Path(temp) / "engine.exe"
            includes = ["testharness-c/inc", "testharness-c/cfg", "ttp/C/inc", "ttp/C/generated", "nanopb"]
            sources = ["testharness-c/tests/" + source, "testharness-c/src/tzen.c", "ttp/C/src/ttp.c", "ttp/C/generated/ttp.pb.c", "nanopb/pb_common.c", "nanopb/pb_decode.c", "nanopb/pb_encode.c"]
            command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror"]
            for folder in includes:
                command.extend(["-I", str(ROOT / folder)])
            subprocess.run(command + list(flags) + [str(ROOT / s) for s in sources] + ["-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=10)
