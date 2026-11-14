# Tzen pytest plugin

Install from the repository root with `python -m pip install -e .`.
The installed package registers its pytest plugin automatically. Python 3.10+
and pytest 8 or 9 are supported.

Create a `tzen.toml` in your test directory:

```toml
[tzen]
command_timeout = 5.0
test_timeout = 30.0
max_events = 256

[tzen.transport]
class = "tzen.transport:SerialTransport"

[tzen.transport.parameters]
port = "COM5"
baudrate = 115200
reset_wait = 2.0
```

```shell
python -m pytest --tzen-config tzen.toml --collect-only -q
python -m pytest --tzen-config tzen.toml -v
python -m pytest --tzen-config path/to/board.toml -v
python -m pytest --tzen-config tzen.toml -k "example" --junitxml=results.xml
```

The TOML file is configuration only. Pass it using `--tzen-config`, or place
a `tzen.toml` in pytest's root directory for automatic configuration.
With a configured slave and no positional test paths, only remote tests are
collected; implicit working-directory and `testpaths` discovery is disabled.
The slave appears as a session-level parent:

```text
<Slave slave>
  <SlaveItem example[0]>
  <SlaveItem another example[1]>
```

To include local tests, provide their paths explicitly, for example
`python -m pytest tests/ --tzen-config board.toml`. Without a configured slave,
pytest discovery is unchanged. Use `-m tzen` or `-m "not tzen"` to filter a
mixed run, and `-k "example[0]"` to select a remote test. Marker filtering happens after
discovery, so a configured slave is still contacted during collection.
Remote IDs such as `slave::example[0]` are report identifiers, not filesystem
paths: select remote tests with `-k` rather than positional node IDs.
Local tests retain normal positional node-ID selection.

Discovery opens the transport, asks the slave for its test count and metadata,
and creates one pytest item per test. Node IDs end in `name[index]`, so duplicate
names remain selectable. `--collect-only` still requires a connected slave but
does not execute tests. `-k`, `-m tzen`, `-x`, and pytest reporting
work normally. SUCCESS passes; FAIL and ABORTED fail. Logs and step results are
attached to the call report, including failure output. JUnit records test index
and run ID for completed runs.

Tests run sequentially, with automatic release of sync requests. Command timeout
limits each command response; test timeout bounds waiting for execution events.
Transport calls and best-effort abort can add their own bounded latency. On a
protocol/transport error or timeout, subsequent tests on that connection are
skipped because the target state is uncertain. The transport closes at pytest
cleanup, including collection errors and collect-only. pytest-xdist parallel
execution is rejected to avoid concurrent access to the same slave.

## Custom transports

`TzenTransport` is a runtime-checkable `typing.Protocol`. Explicit inheritance
is optional; any class with the required methods can be used:

```python
# my_board/transport.py (make this module importable in your environment)
from tzen import TzenTransport

class BoardTransport(TzenTransport):
    def __init__(self, address: str, channel: int = 0):
        # Open your connection here; clean up if construction fails.
        ...

    def read(self, size: int = 1) -> bytes:
        # Return up to size bytes. Return b"" on a short read timeout.
        # Raise on disconnect. Never wait indefinitely.
        ...

    def write(self, data: bytes) -> None:
        # Send all bytes within a bounded time, or raise.
        ...

    def close(self) -> None:
        # Release the connection; repeated close calls should be harmless.
        ...
```

Configure it with:

```toml
[tzen.transport]
class = "my_board.transport:BoardTransport"
[tzen.transport.parameters]
address = "device-address"
channel = 2
```

Parameters are passed unchanged as constructor keyword arguments. Relative
paths in parameters are relative to pytest's working directory. The transport
handles only bytes: Tzen handles protobuf, COBS, CRC16, sequence IDs, and run IDs.
Configuration imports and constructs Python classes, so use trusted TOML files.

For programmatic control, `Client`, `TestInfo`, `TestResult`, and `SerialTransport`
remain public. `Client.run(..., on_sync=callback)` supports custom host-side
synchronization decisions outside the plugin. A client owns a single transport
and is not thread-safe.

Collection uses pytest's public
[collection reporting hook](https://docs.pytest.org/en/stable/reference/reference.html#pytest.hookspec.pytest_make_collect_report)
to add the slave alongside the ordinary session collectors.
