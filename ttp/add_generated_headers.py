# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Add the project license notice to generated TTP bindings."""

from pathlib import Path

TTP_DIR = Path(__file__).resolve().parent


def add_generated_headers() -> None:
    lines = Path(__file__).read_bytes().splitlines()
    notice = lines[:lines.index(b"")]
    for path in (
        TTP_DIR / "C/generated/ttp.pb.c",
        TTP_DIR / "C/generated/ttp.pb.h",
        TTP_DIR / "python/generated/__init__.py",
        TTP_DIR / "python/generated/ttp_pb2.py",
        TTP_DIR / "python/generated/ttp_pb2.pyi",
    ):
        content = path.read_bytes()
        if any(b"SPDX-License-Identifier: MPL-2.0" in line for line in content.splitlines()[:6]):
            continue
        newline = b"\r\n" if b"\r\n" in content else b"\n"
        if path.suffix in {".c", ".h"}:
            header = [b"/*", *(b" *" + line[1:] for line in notice), b" */"]
        else:
            header = notice
        prefix = b""
        first_line, separator, rest = content.partition(newline)
        if path.suffix == ".py" and first_line.startswith(b"# -*- coding:"):
            prefix, content = first_line + separator, rest
        notice_bytes = newline.join(header) + newline
        separator = newline if content else b""
        path.write_bytes(prefix + notice_bytes + separator + content)


if __name__ == "__main__":
    add_generated_headers()
