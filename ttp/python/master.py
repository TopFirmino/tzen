from __future__ import annotations

import argparse
from collections import deque
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
        self._next_seq = 1
        self._next_run = 1
        self._events = deque()
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
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.process = None
        self._events.clear()

    def request(self, message: ttp.HostToTarget) -> ttp.TargetToHost:
        """One outstanding request; retain intervening events for receive()."""
        self.send(message)
        while True:
            response = self._receive_wire()
            if response.seq_id == 0:
                self._events.append(response)
            elif response.seq_id == message.seq_id:
                return response
            else:
                raise RuntimeError(f"unexpected response sequence {response.seq_id}")

    def send(self, message: ttp.HostToTarget) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("slave process is not started")
        if not isinstance(message, ttp.HostToTarget):
            raise TypeError("host can send only HostToTarget")
        # Allocate all wire sequence IDs here, including for low-level send().
        message.seq_id = self._next_seq
        self._next_seq = self._next_seq % 0xFFFFFFFF + 1
        self.process.stdin.write(ttp.encode_frame(message))
        self.process.stdin.flush()

    def _receive_wire(self) -> ttp.TargetToHost:
        return ttp.decode_frame(self._read_frame(), ttp.TargetToHost)

    def receive(self) -> ttp.TargetToHost:
        return self._events.popleft() if self._events else self._receive_wire()

    def get_test_info(self, index: int) -> ttp.GetTestInfoResp:
        response = self.request(ttp.make_get_test_info(index))
        if response.status != ttp.RESULT_OK or response.WhichOneof("payload") != "test_info":
            raise RuntimeError(f"test info rejected: {response}")
        return response.test_info

    def get_manifest(self) -> list[str]:
        response = self.request(ttp.make_get_tests())
        if response.status != ttp.RESULT_OK or response.WhichOneof("payload") != "tests_count":
            raise RuntimeError(f"unexpected response: {response}")
        return [self.get_test_info(i).name for i in range(response.tests_count.total_tests)]

    def abort_test(self, run_id: int) -> ttp.TargetToHost:
        return self.request(ttp.make_abort_test(run_id))

    def release_sync(self, run_id: int, sync_id: int) -> ttp.TargetToHost:
        return self.request(ttp.make_sync_release(run_id, sync_id))

    def execute_test(self, index: int, run_id: Optional[int] = None,
                     auto_release: bool = True) -> Iterable[ttp.TargetToHost]:
        if run_id is None:
            run_id = self._next_run
            self._next_run = self._next_run % 0xFFFFFFFF + 1
        response = self.request(ttp.make_execute_test(index, run_id))
        yield response
        if response.status != ttp.RESULT_OK:
            return
        while True:
            event = self.receive()
            yield event
            if event.seq_id != 0:
                raise RuntimeError(f"unexpected command response during run: {event}")
            if event.WhichOneof("payload") != "test_event":
                continue
            test_event = event.test_event
            if test_event.run_id != run_id or test_event.test_index != index:
                raise RuntimeError(f"unexpected execution identity: {event}")
            kind = test_event.WhichOneof("event")
            if kind == "finished":
                return
            if kind == "sync" and auto_release:
                release = self.release_sync(run_id, test_event.sync.sync_id)
                yield release
                if release.status != ttp.RESULT_OK:
                    raise RuntimeError(f"sync release rejected: {release}")

    def _read_frame(self) -> bytes:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("slave process is not started")

        frame = bytearray()
        in_frame = False
        dropping = False

        while True:
            chunk = self.process.stdout.read(1)
            if chunk == b"":
                raise EOFError("slave stdout closed")

            value = chunk[0]
            if value == ttp.FRAME_DELIMITER:
                if in_frame and frame and not dropping:
                    return bytes(frame)
                in_frame = True
                dropping = False
                frame.clear()
                continue

            if in_frame and not dropping:
                if len(frame) >= ttp.MAX_FRAME_SIZE - 2:
                    dropping = True
                    frame.clear()
                else:
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


def print_message(message: ttp.TargetToHost) -> None:
    if message.seq_id:
        print(f"response seq={message.seq_id} status={ttp.ResultCode.Name(message.status)}")
    print(str(message).strip())


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
