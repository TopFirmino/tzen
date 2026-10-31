# Tzen

A cooperative C test harness, controlled from Python over CRC-protected TTP.

- `ttp/`: transmission schema, generated C/Python bindings, protobuf, COBS and CRC16 codecs.
- `testharness-c/`: portable C11 harness, static test registry, lifecycle and command processing.
- `tzen/`: Python package for discovery, test execution and USB serial communication.
- `examples/Arduino/`: Mega 2560 firmware and Python example using the package.

Install into your Python environment:

```powershell
python -m pip install -e .
```

See [Arduino instructions](examples/Arduino/README.md) to build, flash and run.

Local regression checks (gcc required for C tests):

```powershell
python -m unittest discover -s ttp/tests -v
python -m unittest discover -s testharness-c/tests -v
python -m unittest discover -s tzen/tests -v
```
