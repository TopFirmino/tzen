from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional

import ttp.python.ttp as ttp


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SLAVE_EXE = ROOT / "ttp" / "C" / "ttp_slave.exe"
DEFAULT_BUILD_SCRIPT = ROOT / "ttp" / "C" / "build_slave.bat"


class TtpProcessMaster:
    def __init__(
        self,
        slave_exe: Path = DEFAULT_SLAVE_EXE,
        debug_log: Optional[Path] = None,
        debug_shell: bool = False,
    ) -> None:
        self.slave_exe = slave_exe
        self.debug_log = debug_log
        self.debug_shell = debug_shell
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.debug_process: Optional[subprocess.Popen[bytes]] = None

    def start(self) -> None:
        command = [str(self.slave_exe)]
        if self.debug_log is not None:
            command.extend(["--debug-log", str(self.debug_log)])

        if self.debug_shell and self.debug_log is not None:
            self._start_debug_shell(self.debug_log)

        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None if self.debug_log is None else subprocess.DEVNULL,
            cwd=str(self.slave_exe.parent),
        )

    def close(self) -> None:
        if self.process is None:
            return

        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=2.0)

    def request(self, message: ttp.HostTargetMessage) -> ttp.HostTargetMessage:
        self.send(message)
        return self.receive()

    def send(self, message: ttp.HostTargetMessage) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("slave process is not started")

        self.process.stdin.write(ttp.encode_frame(message))
        self.process.stdin.flush()

    def receive(self) -> ttp.HostTargetMessage:
        frame = self._read_frame()
        return ttp.decode_frame(frame)

    def get_manifest(self) -> list[str]:
        response = self.request(ttp.make_get_tests())
        if response.WhichOneof("payload") != "get_tests_response":
            raise RuntimeError(f"unexpected response: {response}")

        names: list[str] = []
        for index in range(response.get_tests_response.total_tests):
            test_response = self.request(ttp.make_get_test(index))
            if test_response.WhichOneof("payload") != "get_test_response":
                raise RuntimeError(f"unexpected response for test {index}: {test_response}")
            names.append(test_response.get_test_response.name)

        return names

    def execute_test(self, index: int) -> Iterable[ttp.HostTargetMessage]:
        ack = self.request(ttp.make_execute_test(index))
        yield ack
        if ack.WhichOneof("payload") != "ack" or not ack.ack.success:
            return

        while True:
            event = self.receive()
            yield event
            if event.WhichOneof("payload") == "test_finished":
                return

    def _read_frame(self) -> bytes:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("slave process is not started")

        frame = bytearray()
        in_frame = False

        while True:
            chunk = self.process.stdout.read(1)
            if chunk == b"":
                raise EOFError("slave stdout closed")

            value = chunk[0]
            if value == ttp.FRAME_DELIMITER:
                if in_frame and frame:
                    return bytes(frame)
                in_frame = True
                frame.clear()
                continue

            if in_frame:
                frame.append(value)

    def _start_debug_shell(self, debug_log: Path) -> None:
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        debug_log.write_text("", encoding="utf-8")

        if os.name == "nt":
            command = [
                "powershell",
                "-NoExit",
                "-Command",
                f"Get-Content -LiteralPath '{debug_log}' -Wait",
            ]
            self.debug_process = subprocess.Popen(
                command,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )


def build_slave() -> None:
    result = subprocess.run([str(DEFAULT_BUILD_SCRIPT)], cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def print_message(message: ttp.HostTargetMessage) -> None:
    payload = message.WhichOneof("payload")
    if payload == "ack":
        print(f"ack success={message.ack.success} error={message.ack.error_message!r}")
    elif payload == "log":
        print(f"log level={message.log.level} message={message.log.message!r}")
    elif payload == "test_step":
        print(
            "test_step "
            f"step={message.test_step.step_number} "
            f"success={message.test_step.success} "
            f"description={message.test_step.description!r}"
        )
    elif payload == "test_finished":
        print(f"test_finished status={message.test_finished.status}")
    else:
        print(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local TTP master against the C stdin/stdout slave.")
    parser.add_argument("--build", action="store_true", help="Build the C slave before starting it.")
    parser.add_argument("--slave-exe", type=Path, default=DEFAULT_SLAVE_EXE)
    parser.add_argument("--debug-shell", action="store_true", help="Open a separate shell tailing slave debug prints.")
    parser.add_argument(
        "--debug-log",
        type=Path,
        default=Path(tempfile.gettempdir()) / "ttp_slave_debug.log",
        help="Path used by the slave for debug prints.",
    )
    parser.add_argument("--execute", type=int, default=0, help="Test index to execute after reading the manifest.")
    args = parser.parse_args()

    if args.build:
        build_slave()

    master = TtpProcessMaster(
        slave_exe=args.slave_exe,
        debug_log=args.debug_log if args.debug_shell else None,
        debug_shell=args.debug_shell,
    )

    master.start()
    try:
        manifest = master.get_manifest()
        print(f"manifest: {manifest}")
        for event in master.execute_test(args.execute):
            print_message(event)
    finally:
        master.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
