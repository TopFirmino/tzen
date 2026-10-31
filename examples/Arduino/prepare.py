"""Stage canonical C sources as a self-contained Arduino sketch, without symlinks."""
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).resolve().parent / "build" / "ArduinoHarness"
DEST.mkdir(parents=True, exist_ok=True)
# Arduino adds the sketch root to header search paths, including nanopb <pb.h>.
legacy = DEST / "src"
if legacy.exists():
    assert legacy.resolve().is_relative_to((ROOT / "examples/Arduino/build").resolve())
    shutil.rmtree(legacy)
src = DEST
files = [ROOT / p for p in (
    "testharness-c/inc/tzen.h", "testharness-c/src/tzen.c", "testharness-c/cfg/tzen_cfg.h",
    "ttp/C/inc/ttp.h", "ttp/C/src/ttp.c", "ttp/C/generated/ttp.pb.h", "ttp/C/generated/ttp.pb.c",
    "nanopb/pb.h", "nanopb/pb_common.h", "nanopb/pb_common.c",
    "nanopb/pb_encode.h", "nanopb/pb_encode.c", "nanopb/pb_decode.h", "nanopb/pb_decode.c",
    "examples/Arduino/C/board.h", "examples/Arduino/C/test_example.c")]
for source in files:
    shutil.copy2(source, src / source.name)
shutil.copy2(Path(__file__).parent / "ArduinoHarness/ArduinoHarness.ino", DEST / "ArduinoHarness.ino")
print(DEST)
