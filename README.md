# Tzen

A cooperative C test harness, controlled from Python over CRC-protected TTP.

- `ttp/`: protocol schema, generated C/Python bindings and protobuf-only codecs.
- `testharness-c/`: C11 harness with COBS/CRC16 framing, protected execution queues and cooperative workers.
- `python/tzen/`: Python master, pytest plugin, wire framing and transport protocol.
- `examples/Arduino/`: Mega 2560 firmware and Python example using the package.

Install into your Python environment:

```powershell
python -m pip install -e .
```

See the [pytest plugin guide](python/tzen/README.md) for TOML configuration and
custom `TzenTransport` implementations. Discover and execute slave tests with
`python -m pytest --tzen-config path/to/board.toml -v`.

For the C host example, build with `make -C examples/Host/C`, then run
`python -m pytest --tzen-config examples/Host/tzen-host.toml -m tzen -v` from the repository
root. Its intentional failure is reported as a failed pytest test.

The host example includes Python-owned documentation for all three tests and a
Python companion coordinating with C at sync 42. See the
[host guide](examples/Host/C/README.md) for offline JSON documentation export,
live collection with descriptions, and a passing run of the positive cases.

See [Arduino instructions](examples/Arduino/README.md) to build, flash and run.
The current `tzen.c` implements RX/TX, discovery, execution, synchronization and
run-specific logs/results with independently polled workers. The older Arduino execution example requires migration
before it can run against this implementation. Use the [Host example](examples/Host/C/README.md)
for current command/response checks over binary subprocess pipes.

Local regression checks (gcc required for C tests):

```powershell
python -m unittest discover -s ttp/tests -v
python -m unittest discover -s testharness-c/tests -v
python -m unittest discover -s tzen/tests -v
python -m pytest python/tests -q
```
