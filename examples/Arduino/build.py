"""Stage, compile, and optionally upload with your installed Arduino CLI."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default=shutil.which("arduino-cli"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--fqbn", default="arduino:avr:mega")
    parser.add_argument("--port", help="Upload to this port after compilation")
    args = parser.parse_args()
    if not args.cli:
        parser.error("supply --cli pointing to Arduino IDE's resources/app/lib/backend/resources/arduino-cli.exe")
    here = Path(__file__).resolve().parent
    subprocess.run([sys.executable, str(here / "prepare.py")], check=True)
    sketch = here / "build/ArduinoHarness"
    output = here / "build/compile"
    base = [args.cli]
    if args.config:
        base.extend(["--config-file", str(args.config)])
    # Nanopb's generated header uses <pb.h>; add the staged source directory
    # during Arduino's dependency-discovery pass and compilation.
    include = '-I' + sketch.as_posix()
    subprocess.run(base + ["compile", "--fqbn", args.fqbn,
        "--build-property", "compiler.c.extra_flags=" + include,
        "--build-property", "compiler.cpp.extra_flags=" + include,
        "--build-path", str(output), str(sketch)], check=True)
    if args.port:
        subprocess.run(base + ["upload", "--fqbn", args.fqbn, "--port", args.port,
            "--input-dir", str(output), str(sketch)], check=True)


if __name__ == "__main__":
    main()
