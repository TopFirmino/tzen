# Previous single-worker connected-board verification

These measurements describe the earlier firmware. The two-queue, multi-worker
implementation has not been uploaded or verified on the connected board.
The BUSY expectation below belonged to the previous single-worker engine.

Date: 2026-10-31 (Europe/Rome).

- Board: Arduino Mega 2560, FQBN `arduino:avr:mega`.
- USB port: COM5, VID 2341 / PID 0042, serial 558383430343517121B1.
- Toolchain: Arduino IDE bundled Arduino CLI and installed Arduino AVR core 1.8.7.
- Final firmware: 20,480 bytes flash (8%); 1,512 bytes static RAM (18%), leaving 6,680 bytes for stack/local variables. This is build output, not measured peak stack usage.
- Upload completed successfully through the installed Arduino uploader.
- Firmware HEX SHA256: `b32d9fae9b189e5945f4be17a4fa6d697434241c7a94bbbdc733f6e71f105627`.

The final build/upload was run with `examples/Arduino/build.py --port COM5`
and the explicit IDE CLI/config paths shown in README.md.
The real USB session was run with:

```powershell
python -m examples.Arduino.run --port COM5 --verify
```

Verified on the flashed board:

| Check | Observed result |
| --- | --- |
| Discovery | LED cycle (2 steps), LED host sync (2), Expected failure (1) |
| LED cycle | SUCCESS with exactly one automatic report each for steps 1 and 2; yielded polls emit no reports |
| Host synchronization | Sync ID 42 received, released, then automatic reports for steps 1 and 2 and SUCCESS |
| Intentional failure | FAIL, as expected |
| Abort during sync wait | ABORTED with no completed-step report |
| Concurrent execute while waiting | RESULT_ERR_BUSY |
| Incorrect sync ID | RESULT_ERR_NOT_FOUND; waiting run remained active |
| CRC-damaged execute | Rejected; subsequent normal execution accepted |
| Abort during cooperative yielded step | ABORTED |

Local protocol, native C engine, and Python client regression suites also pass.
C test executables are built with `-std=c11` (engine) or `-std=c99` (codec),
`-Wall -Wextra -Werror`.

The LED check reads the configured digital output register; optical output and
external electrical behavior were not measured. Native tests verify teardown
invocation and context lifecycle; RTOS callback synchronization and real sensor/
power-rail tests are not covered by this Arduino demonstration. Hardware cleanup
on physical USB loss is not automatically enforced by the current protocol.

That firmware public C API used `Tzen_*` functions/types and `TZEN_*` constants.
The engine owned step reporting. Those testcases used `Tzen_Log` / `Tzen_Logf` for text;
`TestStepEvent` contains only step_number and success (former tag 3 is reserved).
The C and Python protobuf bindings were regenerated together for this verification.

## Two-queue implementation build check

On 2026-10-31 the updated byte-feed/main/multi-worker sketch compiled for
`arduino:avr:mega` using the installed AVR core 1.8.7: 21,962 bytes flash and
2,632 bytes static RAM, leaving 5,560 bytes for locals/stack. This is compiler
output, not measured peak stack usage. Staged sketch and compile outputs were
rebuilt by `examples/Arduino/build.py` without `--port`. No upload or connected
board session was performed for this revision.

Native C11 tests also pass for two simultaneous worker callbacks, main progress
while both workers execute, abort routing, serialized TX and 5,000 concurrent
ISR-style producer/main consumer frames. The AVR byte publication path is
compile-validated; real ISR timing and RTOS behavior still require target tests.
