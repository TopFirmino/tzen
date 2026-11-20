<!--
Tzen
Author: L. Furcas
SPDX-License-Identifier: MPL-2.0
-->

# Tzen

A cooperative C test harness, controlled from Python over CRC-protected TTP.

- `ttp/`: protocol schema, generated C/Python bindings and protobuf-only codecs.
- `testharness-c/`: C11 harness with COBS/CRC16 framing, protected execution queues and cooperative workers.
- `python/tzen/`: Python master, pytest plugin, wire framing and transport protocol.
- `examples/Arduino/`: Mega 2560 firmware and Python example using the package.

From the repository root, use uv to install the package and its development tools:

```powershell
uv sync --locked
```

To install into an existing Python environment with pip:

```powershell
python -m pip install -e .
```

See the [pytest plugin guide](python/tzen/README.md) for TOML configuration and
custom `TzenTransport` implementations. Discover and execute slave tests with
`python -m pytest tests/ --tzen-config path/to/board.toml -v`.

For the C host example, build with `make -C examples/Host/C`, then run
`python -m pytest examples/Host/tests --tzen-config examples/Host/tzen-host.toml -v` from the repository
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

## Checks before pushing

Run these commands from the repository root. The TTP interoperability tests
need GCC and the `nanopb` submodule (`git submodule update --init`).

```powershell
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest -q python/tests ttp/tests
```

Ruff lints first-party Python files, including tests and examples. Mypy checks
the `tzen` package and the Python TTP codec. GitHub Actions runs these checks on
pushes and pull requests with Python 3.10 and 3.13.

To run the native C harness tests locally, use
`uv run --locked pytest -q testharness-c/tests`.

`uv.lock` pins the project and development dependencies. When updating them,
run `uv lock` and commit the lockfile with the dependency changes. For a
runtime-only uv environment, use `uv sync --locked --no-dev`.

After a TTP schema change, run `ttp\generate_pb_files.bat` to regenerate the C
and Python bindings and the Python type stub with their license notices.

## License

Tzen by L. Furcas is licensed under the [Mozilla Public License 2.0](LICENSE).
The nanopb submodule retains its own [license](https://github.com/nanopb/nanopb/blob/bf966422f6bb48fec975520e396f50f6db2049e5/LICENSE.txt).
