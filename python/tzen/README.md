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

### Class declarations and steps

Use `TzenTestCase` for class-based testcases. The collector binds `target` to
the exact C name; if omitted, the concrete Python class name is used.

```python
from tzen import TzenTestCase, step

class TestAdcCalibration(TzenTestCase):
    """Check ADC initialization, raw readings, and voltage tolerance."""

    target = "adc.calibration"

    def __init__(self, adc):
        self.adc = adc             # User-provided pytest fixture
        self.channel = 0
        self.expected_vref = 3300

    @step("Initialize ADC peripheral and check status register", critical=True)
    def init_peripheral(self):
        assert self.adc.init(self.channel) == 0, "ADC failed to initialize"

    @step("Read raw sample and verify non-zero", critical=True)
    def read_sample(self):
        self.raw = self.adc.read(self.channel)
        assert 0 < self.raw < 4096, f"Out of range: {self.raw}"

    @step("Convert to mV and check tolerance", critical=True)
    def verify_voltage(self):
        mv = self.adc.raw_to_mv(self.raw)
        assert abs(mv - self.expected_vref) < 50, f"Drift too high: {mv} mV"
```

The `adc` fixture and firmware testcase are application-specific; the runnable
host example uses `self.run.wait_sync(42)` and `self.run.release(42)`.

Execution order is constructor fixture setup -> `__init__` -> start C ->
decorated steps in declaration order -> successful C completion -> testcase
fixture teardown. Each pytest testcase has a fresh
instance; `self` retains state between its steps. Tzen opens one C run around
the whole sequence and exposes it as `self.run`, so classes do not need to
manually enter `tzen_case.run()`. Python steps are not automatically mapped to
C step numbers or sync IDs: synchronize explicitly where the application needs
coordination. The C run must also finish successfully for the testcase to pass.

`critical=False` is the default. An assertion failure in a non-critical step is
recorded and subsequent steps continue, but the overall testcase fails.
`critical=True` stops subsequent steps immediately on assertion failure.
Unexpected exceptions stop the sequence regardless of criticality. An active
C run is aborted on failure; unexecuted Python steps are reported as `not_run`.
Mark prerequisite steps critical when subsequent steps depend on their results.
Testcases have no `setup` or `teardown` hooks. Acquisition and cleanup belong
exclusively to fixtures: use `yield` or `request.addfinalizer`. An optional
`__init__` receives fixtures through named required parameters and initializes
instance state. A failed constructor still finalizes its fixtures.

Constructor fixtures remain alive until the testcase ends. Function-scoped
fixtures requested only by a step are created just before that step and finalized
immediately afterward, including on failure. Dependencies close in reverse
acquisition order. Later steps requesting the same fixture get a fresh instance.
A step requesting a constructor-owned or autouse fixture reuses it without
ending its testcase lifetime. Explicit module/session scopes retain their normal
pytest lifetime. Fixture setup/cleanup errors stop the sequence regardless of
the step's critical flag. Fixtures for unexecuted steps are never created.

Both constructors and step methods use named required fixture parameters.
Only constructor fixtures are prepared before class construction. Methods must be
synchronous instance methods; static/class methods, generators and async methods
are rejected. Steps are not separate pytest items and cannot be independently
selected or reordered. `-x` stops after a testcase, not after a non-critical step.

A class with steps is a companion by default. Set `companion = False` for
documentation-only classes: constructors and steps are then never executed. A class
without steps defaults to documentation-only. Explicit `companion = True`
without any steps is a collection error. Class docstrings and ordered step
descriptions/critical flags are included in offline and live
JSON exports. `--collect-only -vv` also displays the steps without constructing
the class or executing fixtures. Requirements/tags fields are not part of the
execution declaration API. Step results appear in the call report and
the JUnit `tzen_steps` property; use `-rA` to display passed-test report sections.

Single inheritance is supported: inherited steps run first, decorated overrides
keep their position, new steps append, and undecorated overrides remove an
inherited step. Abstract classes are not collected; use an abstract base class
or import reusable base classes from a helper module. Multiple testcase-base
inheritance is rejected. Older function declarations remain supported below.

### Function declarations and configuration

Configure declaration files or directories, relative to the TOML file:

```toml
[tzen]
companion_paths = ["companions"]
```

Directories load `case_*.py` recursively; an explicit `.py` file can have any
name. `TzenTestCase` subclasses and decorated functions become declarations. A declaration matches the
exact name in the C registry; matching by index is deliberately avoided.
Missing targets, ambiguous C names, and duplicate declarations are collection
errors. Without a declaration, a C test still executes normally.

```python
from tzen import testcase

@testcase(target="C-only test")
def description():
    """Verify successful startup.

    Preconditions: board powered.
    Procedure: execute the C startup checks.
    Expected result: every C step succeeds.
    """

@testcase(target="GPIO test", companion=True)
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

Descriptions come from docstrings. Execution type, target
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
