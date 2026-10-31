import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

class NativeEngineTests(unittest.TestCase):
    def test_engine(self):
        with tempfile.TemporaryDirectory(prefix="tzen_native_") as temp:
            exe = Path(temp) / "engine.exe"
            includes = ["testharness-c/inc", "testharness-c/cfg", "ttp/C/inc", "ttp/C/generated", "nanopb"]
            sources = ["testharness-c/tests/test_engine.c", "testharness-c/src/tzen.c", "ttp/C/src/ttp.c", "ttp/C/generated/ttp.pb.c", "nanopb/pb_common.c", "nanopb/pb_decode.c", "nanopb/pb_encode.c"]
            command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror"]
            for folder in includes:
                command.extend(["-I", str(ROOT / folder)])
            subprocess.run(command + [str(ROOT / s) for s in sources] + ["-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=10)
