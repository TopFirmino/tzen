# Arduino Mega 2560 example

The board adapter runs C tests through the portable harness. It uses only the
built-in LED and USB serial at 115200 baud. No external power rail, ADC, relay,
or extra wiring is used. LED readback checks the output register, not light
output or an external electrical measurement.

The C test file follows the proposed scratchpad/step/setup/teardown pattern:

- `LED cycle`: enable LED, yield cooperatively for 100 ms, verify readback, clean up.
- `LED host sync`: enable LED and wait at sync ID 42, then verify after release.
- `Expected failure`: intentionally emit a failed step and FAIL result.

All exits call teardown, turning the LED off. `ArduinoHarness/ArduinoHarness.ino`
is the board adapter. `C/test_example.c` contains the registry and steps.
`prepare.py` stages those plus the canonical harness/TTP/nanopb sources under
`build/ArduinoHarness`; do not edit generated copies. `build.py` stages, compiles,
and optionally uploads. The include flag is needed for nanopb during Arduino's
header dependency discovery.

From the repository root:

```powershell
python -m pip install -e .
$cli = "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
$config = "$env:USERPROFILE\.arduinoIDE\arduino-cli.yaml"
python examples/Arduino/build.py --cli $cli --config $config --port COM5
python -m examples.Arduino.run --port COM5
python -m examples.Arduino.run --port COM5 --verify
```

Without `--port`, build.py only compiles. Default board is `arduino:avr:mega`;
use `--fqbn` for another board. COM5 is the Mega detected on this workstation;
check your port before uploading elsewhere. Close IDE Serial Monitor before
using the Python client or uploading. Port opening resets this Mega; the client
waits for boot before requesting discovery.

`--verify` also checks intentional FAIL, abort while waiting, BUSY, wrong sync ID,
CRC rejection, and abort during a yielded step. The intentional failure is an
expected verification result. Protobuf omits zero/default fields in printed
messages: an empty `finished {}` means SUCCESS, not a missing result.

See [verification.md](verification.md) for the connected-board verification.
