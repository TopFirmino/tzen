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

Tests run sequentially; C-only tests automatically release sync requests, while
Python companions release them explicitly. Command timeout
limits each command response; test timeout bounds waiting for execution events.
Transport calls and best-effort abort can add their own bounded latency. On a
protocol/transport error or timeout, subsequent tests on that connection are
skipped because the target state is uncertain. The transport closes at pytest
cleanup, including collection errors and collect-only. pytest-xdist parallel
execution is rejected to avoid concurrent access to the same slave.

## Testcase documentation and Python companions

Configure declaration files or directories, relative to the TOML file:

```toml
[tzen]
companion_paths = ["companions"]
```

Directories load `case_*.py` recursively; an explicit `.py` file can have any
name. Only decorated functions become declarations. A declaration matches the
exact name in the C registry; matching by index is deliberately avoided.
Missing targets, ambiguous C names, and duplicate declarations are collection
errors. Without a declaration, a C test still executes normally.

```python
from tzen import testcase

@testcase(target="C-only test", requirements=["REQ-001"], tags=["startup"])
def description():
    """Verify successful startup.

    Preconditions: board powered.
    Procedure: execute the C startup checks.
    Expected result: every C step succeeds.
    """

@testcase(target="GPIO test", companion=True, requirements=["REQ-002"])
def check_gpio(tzen_case, multimeter):
    """Verify the output voltage while C waits at sync 10."""
    multimeter.configure_voltage()
    with tzen_case.run() as run:
        run.wait_sync(10)
        assert multimeter.voltage() > 3.0
        run.release(10)
    assert run.result.passed
```

`multimeter` is a user-defined pytest fixture. Documentation-only is the
default: that function's body is never called. `companion=True` explicitly
enables Python execution and requires the `tzen_case` argument. Each pair is
one pytest item under the slave and executes the C counterpart exactly once.
Normal return requires C SUCCESS as well as successful Python assertions.
An absent C execution cannot silently pass. Non-successful C completion fails
the item, even if Python attempts to ignore it.

Python companions control synchronization explicitly: unexpected, missing, or
unreleased sync points fail the test. C-only tests retain automatic release.
On a Python failure, Tzen attempts abort and consumes the terminal event before
another test starts; an uncertain connection disables further execution.
The test timeout bounds protocol waits. It cannot interrupt arbitrary blocking
Python/instrument code, so instrument fixtures must configure their own I/O
timeouts. Do not launch a background thread that reads the TTP transport.

Define fixtures in the declaration files or in pytest's root `conftest.py`.
Declaration modules share one synthetic slave module scope; conflicting module
symbols are rejected, so put shared fixtures/helpers in an importable module.
Nested `conftest.py` files in companion directories are not auto-discovered.
Use absolute imports for helpers. Python test parametrization and parametrized
fixtures are not supported for companions yet. Explicit local collection does
not collect decorated declarations a second time.

Descriptions come from docstrings. Requirements, tags, execution type, target
name, source path, and (online) C index/step count are exported as JSON.
Each collected item exposes a `documentation` dictionary to other plugins.
JUnit includes the description along with execution identity.

```sh
# Offline: imports declarations, never opens the target connection.
python -m tzen docs --config board.toml --output docs/offline.json

# Online: validates against firmware, without executing tests or fixtures.
python -m pytest --tzen-config board.toml --collect-only -vv --tzen-docs docs/live.json --tzen-strict-docs
```

Offline exports are explicitly marked `verified_against_slave: false`; they
contain only declared tests and cannot detect undocumented firmware tests.
Online exports include selected tests after pytest filtering and are produced
only after successful collection. `--tzen-strict-docs` rejects missing or empty
descriptions; otherwise these produce a warning. Collection verification means
name matching against the current registry, not firmware-version certification.
The current wire protocol does not advertise mandatory companions, so it cannot
detect a missing required companion file from C metadata alone.

See the [host example](../../examples/Host/C/README.md) for a runnable companion.

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
