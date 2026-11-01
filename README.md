# Tzen

A cooperative C test harness, controlled from Python over CRC-protected TTP.

- `ttp/`: protocol schema, generated C/Python bindings and protobuf-only codecs.
- `testharness-c/`: C11 harness with COBS/CRC16 framing and discovery commands.
- `tzen/`: Python client, wire framing and USB serial communication.
- `examples/Arduino/`: Mega 2560 firmware and Python example using the package.

Install into your Python environment:

```powershell
python -m pip install -e .
```

See [Arduino instructions](examples/Arduino/README.md) to build, flash and run.
The current `tzen.c` implements RX/TX and test discovery; execution and workers
will be added later. The older Arduino execution example requires migration
before it can run against this implementation. Use the [Host example](examples/Host/C/README.md)
for current command/response checks with buffered temporary files.

Local regression checks (gcc required for C tests):

```powershell
python -m unittest discover -s ttp/tests -v
python -m unittest discover -s testharness-c/tests -v
python -m unittest discover -s tzen/tests -v
```
