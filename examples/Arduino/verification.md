# Connected-board verification

Date: 2026-10-31 (Europe/Rome).

- Board: Arduino Mega 2560, FQBN `arduino:avr:mega`.
- USB port: COM5, VID 2341 / PID 0042, serial 558383430343517121B1.
- Toolchain: Arduino IDE bundled Arduino CLI and installed Arduino AVR core 1.8.7.
- Final firmware: 20,682 bytes flash (8%); 1,600 bytes static RAM (19%), leaving 6,592 bytes for stack/local variables. This is build output, not measured peak stack usage.
- Upload completed successfully through the installed Arduino uploader.
- Firmware HEX SHA256: `6d484765189dcbe1c563e7aa98f97b8e92f363faf502b18a0e7bb4b4a697f7b0`.

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
| LED cycle | SUCCESS with step 1 and step 2 reports |
| Host synchronization | Sync ID 42 received, released, SUCCESS |
| Intentional failure | FAIL, as expected |
| Abort during sync wait | ABORTED |
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
