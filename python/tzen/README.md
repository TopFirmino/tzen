<!--
Tzen
Author: L. Furcas
SPDX-License-Identifier: MPL-2.0
-->

# Tzen pytest plugin

Tzen by L. Furcas is licensed under MPL-2.0, including the `py.typed` marker
distributed with the package. See the repository's `LICENSE` for the full text.

Install from the repository root with `uv sync --locked --no-dev` or
`python -m pip install -e .`. With uv, run the examples below in the uv
environment by replacing `python` with `uv run --locked --no-dev python`.
The plugin registers automatically. Python 3.10+ and pytest 8 or 9 are supported.

## Declare tests in normal pytest files

Create a file such as tests/test_board.py and select an explicit testcase type:

    from tzen import TzenRemoteTestCase, TzenCompanionTestCase, step

    class TestStartup(TzenRemoteTestCase):
        """Verify successful startup using only the C testcase."""
        # Matches the C registry name "TestStartup".

    class TestAdcCalibration(TzenCompanionTestCase):
        """Check ADC samples while C waits for the host."""
        target = "adc.calibration"  # Optional class-name override.

        def __init__(self, adc):
            self.adc = adc

        @step("Wait for ADC readiness", critical=True)
        def wait_ready(self):
            self.run.wait_sync(10)

        @step("Read and validate a sample")
        def check_sample(self, measurement):
            self.raw = measurement.read(self.adc)
            assert 0 < self.raw < 4096

        @step("Release the embedded testcase", critical=True)
        def release(self):
            self.run.release(10)

The adc and measurement fixtures are application-specific. Define them in the
test module or a normal conftest.py. See the runnable
[host example](../../examples/Host/tests/test_host.py).

- **TzenRemoteTestCase:** C-only execution, without constructors or Python steps.
- **TzenCompanionTestCase:** at least one decorated step and an optional
  fixture-injecting constructor.
- **TzenTestCase:** shared base, not a concrete declaration. Its descendants
  must select one of the two execution types before collection.
- Both types default to the concrete class name as their C target. Set target
  only when the C name differs. There is no companion flag or requirements/tags
  field.

## Configuration and invocation

TOML configures only transport and execution limits:

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

Use --tzen-config or a tzen.toml file in pytest's root directory:

    python -m pytest tests/ --tzen-config board.toml --collect-only -vv
    python -m pytest tests/ --tzen-config board.toml -v -rA
    python -m pytest tests/test_board.py::TestAdcCalibration --tzen-config board.toml -v
    python -m pytest tests/ --tzen-config board.toml -m tzen -k Calibration

The removed companion_paths setting produces a configuration error. Test
selection belongs to pytest.

## Collection

Pytest uses its normal file rules (test_*.py, *_test.py, python_files),
positional paths, testpaths, ignore rules, packages and conftest.py. Within
these modules, Tzen recognizes classes by inheritance, not a Test name prefix.
Abstract classes, imported helper classes, and classes explicitly declaring
__test__ = False are ignored.

Each concrete declaration becomes one item in its actual Python module:

    <Module test_board.py>
      <TzenItem TestStartup>
      <TzenItem TestAdcCalibration>

The first live Tzen declaration opens the configured transport. The C registry
is queried once per session and shared across modules. Classes match exact C
names, never indices. Missing/ambiguous matches or duplicate target bindings are
collection errors. Undeclared C tests are not appended. Without any Tzen
declarations, no transport is opened.

Ordinary Python tests are collected alongside Tzen tests. --tzen-config never
replaces or expands collection paths. From this repository root, pass
examples/Host/tests to run the host example instead of development tests.
Exact positional node IDs, -k and -m tzen work normally. Name/marker filtering
happens after collection, so live discovery still needs the slave even if
all Tzen items are subsequently deselected.

Fixtures stay in their source modules and directory scopes. Two modules may
define different fixtures with the same name. Package-relative imports and
pytest assertion rewriting follow normal pytest behavior. Testcase and fixture
parametrization are not supported yet. Live pytest-xdist execution is rejected
to prevent multiple workers from accessing one slave.

## Execution and fixture lifetimes

Every companion has a fresh instance. Steps execute in definition order and
retain state on self. Execution is:

1. Prepare constructor fixtures and call __init__, if defined.
2. Start one C execution and expose it as self.run.
3. Execute the decorated steps.
4. Require successful C completion.
5. Finalize testcase-lifetime fixtures.

Use self.run.wait_sync(id) and self.run.release(id) for explicit coordination.
Python steps do not automatically correspond to C step numbers or sync IDs.
C-only tests automatically release sync requests.

Constructor fixtures live until the testcase ends, even if construction fails.
Function-scoped fixtures first requested by a step are acquired just before
that step and finalized immediately afterward, including on failure. Dependencies
close in reverse acquisition order; later steps receive fresh instances.
Constructor-owned/autouse fixtures are reused without premature cleanup.
Explicit module/session scopes retain their normal pytest lifetime.
Unexecuted steps never acquire their step-only fixtures.

Use fixture yield or request.addfinalizer for cleanup. Testcases have no
setup/teardown hooks. Constructors and steps use named required fixture
parameters. Methods must be synchronous instance methods; async/generator,
static and class methods are rejected.

A non-critical assertion failure is recorded and allows subsequent steps to
run, but fails the overall testcase. critical=True stops the sequence immediately.
Unexpected exceptions and fixture setup/finalization errors always stop.
Active C execution is aborted on failure. Only C SUCCESS and successful Python
execution produce a pass. Steps are not separate pytest items and cannot be
selected individually; -x takes effect after the whole testcase.

Logs and results belong to the combined item. -rA shows successful report
sections. JUnit includes tzen_steps, the description and execution identity.
Single inheritance preserves base step order: decorated overrides keep their
position, undecorated overrides remove inherited steps, and new steps append.
Use imported or abstract base classes for reuse; multiple testcase bases are
rejected.

## Documentation

Docstrings describe testcases; @step supplies procedure descriptions and
criticality. Each item exposes a documentation dictionary. Live JSON also
includes the matched C index and step count.

    # Live registry validation, without test or fixture execution:
    python -m pytest tests/ --tzen-config board.toml --collect-only -vv --tzen-docs docs/live.json --tzen-strict-docs

    # Offline, using the same pytest collector, without a transport:
    python -m tzen docs tests/ --output docs/offline.json -q

    # Equivalent direct pytest invocation:
    python -m pytest tests/ --collect-only --tzen-offline --tzen-docs docs/offline.json

The offline CLI accepts additional pytest options such as -k or
--tzen-strict-docs. Offline mode requires collect-only and marks exports
verified_against_slave: false. It cannot verify registry matches. Successful
live collection marks registry validation true; this means name matching, not
firmware-version certification. Exports include selected Tzen items after
filtering and are written only after successful collection. Missing descriptions
warn by default or fail collection with --tzen-strict-docs.

Collection imports test modules and conftests, so module-level code executes.
It does not instantiate testcase classes, execute steps, or set up fixtures.
Keep hardware I/O in fixtures/steps. The protocol currently has no C metadata
advertising a mandatory Python companion.

## Custom transports

TzenTransport is a runtime-checkable typing.Protocol. Explicit inheritance
is optional; implement bounded byte operations:

    class BoardTransport:
        def __init__(self, address: str):
            # Open the connection; clean up if construction fails.
            ...

        def read(self, size: int = 1) -> bytes:
            # Return at most size bytes; b"" means a bounded read timeout.
            # Raise on disconnect. Never wait indefinitely.
            ...

        def write(self, data: bytes) -> None:
            # Send all bytes within a bounded time, or raise.
            ...

        def close(self) -> None:
            # Release resources; repeated calls should be harmless.
            ...

Select class = "my_board.transport:BoardTransport" and supply constructor
keyword arguments in [tzen.transport.parameters]. Arguments pass through
unchanged; relative paths in them are relative to pytest's working directory.
Tzen handles protobuf, COBS, CRC16, sequence IDs and run IDs. Use trusted
configuration and Python files.

The transport closes at pytest cleanup, including collection failures. Tests
execute sequentially. Protocol/transport errors or uncertain abort cleanup
disable subsequent executions on that connection. Command timeout bounds each
response; test timeout bounds protocol waits, not arbitrary blocking Python or
instrument code. Instrument fixtures must set their own I/O timeouts.
Client remains available for programmatic control and is not thread-safe.

## Migration

Move declarations into normal pytest files, typically tests/test_*.py.
Replace C-only classes with TzenRemoteTestCase and Python-step classes with
TzenCompanionTestCase. Remove companion = ... and companion_paths.
Function-based @testcase declarations are replaced by the explicit class types.
Pass test paths to pytest. Offline documentation takes test paths instead of a
TOML configuration.


## Message sources and subscriptions

Test diagnostics work without configuration: `Client.run()` and pytest companion
runs collect source `0` (`SOURCE_TEST`) logs for their own `(run_id, test_index)`.
Their results stop at `TestFinished`. Other sources and other executions do not
become testcase diagnostics or cause identity-mismatch errors.

Source IDs `1..UINT32_MAX` are application-defined (for example `7` for coverage).
A log's `scope` explicitly distinguishes `EXECUTION` from `GLOBAL`. Execution IDs
including `(0, 0)` are valid; a global log has no execution identity. Source `0`
is reserved for testcase diagnostics and requires execution scope. The testcase
is identified by `test_index`, and its invocation by `run_id`.

Use `client.events.subscribe_logs` with a function, bound method, or callable
object implementing the `LogHandler` protocol. Each immutable `TargetLog`
provides the source ID, message, Python logging level, and optional execution.

```python
import logging
from tzen import TargetLog

def save_coverage(record: TargetLog) -> None:
    logging.getLogger("coverage").log(record.level, "%s", record.message)

with client.events.subscribe_logs(save_coverage, source=7):
    result = client.run("My test")
```

Omit `source` to observe all logs. Pass `execution=ExecutionRef(42, 3)` for
one execution or `global_only=True` for global logs. `result.logs` exposes
the testcase diagnostics as the same record type. Low-level consumers can use
`events.subscribe` for raw protocol envelopes.

Callbacks run synchronously in registration order when the client reads an event,
including while waiting for a command ACK. No background reader, retries, run-open
registry, or collection-completion protocol is introduced. Keep reading with
`receive()` when the application wants messages outside a test. A completed run's
identity remains usable; producers must preserve the original identity instead
of assigning delayed data to whichever testcase is running now.

Callbacks must not mutate the envelope or recursively read/request/close the
client; recursive client operations raise `RuntimeError`. Callback exceptions
propagate, and later callbacks for that event are not called. Subscription changes
apply to the next event. No callback history is retained. During `request()`, events
with matching subscribers are dispatched without retaining an extra raw copy;
unhandled events are buffered up to `max_queued_events` for `receive()`. Such
buffered events have already been dispatched once and are not replayed to new
subscribers. Test inboxes and test result histories are bounded separately by the
same limit. Applications control storage for their own subscribers.

For pytest projects, declare shared routes in the same TOML file as the transport.
The plugin looks up from each collected Tzen test module to the pytest root,
choosing the nearest configuration. Within a directory it tries `tzen-host.toml`
before `tzen.toml`. An explicit `--tzen-config` applies to the whole invocation.
A session uses one target configuration.

```toml
[[tzen.logging.sources]]
source = 7
logger = "tzen.target.coverage"
after_test_timeout = 2.0
```

A logger route forwards the target severity to standard Python logging. For
application-specific processing, replace `logger` with `handler = "mymodule:save"`;
the function receives a `TargetLog`. Routes are active from discovery onwards.
Source zero uses the built-in testcase handling. Normally execution ends at
TestFinished. Specify `after_test_timeout` only when the target guarantees a
subsequent correlated message from that source for every completed execution.

The schema retains the existing field numbers. Absent new fields mean source `0`
and execution scope, so updated readers accept existing testcase logs. Old readers
do not understand global/custom-source routing; update host and target together
before using the new messages. Text remains bounded to 63 bytes in C; binary
coverage chunks and structured measurements are outside this minimal extension.

## Save a source after logging

Add a sink under the source entry in your TOML. For example:

```toml
[[tzen.logging.sources]]
source = 7
logger = "tzen.target.coverage"

[tzen.logging.sources.sink]
class = "tzen:FileLogSink"

[tzen.logging.sources.sink.parameters]
path = "results/coverage.log"
format = "text"
```

The framework calls the route's logger or handler first, then calls the sink
once for that record. Python logging level filters affect display independently
of the sink. FileLogSink appends across runs. Relative paths resolve against the
TOML directory. Text mode writes UTF-8 followed by LF. For binary coverage set
`format = "binary"` and send one complete base64-encoded chunk per log message.
The sink validates each chunk and appends its decoded bytes, in arrival order.
The C harness allows 63 text bytes per message, so up to 45 raw bytes fit per
base64 chunk. File and decode errors propagate to the caller.

For application-specific processing, point `class` to your own importable
`module:ClassName`. Its constructor receives the parameters as keyword arguments.
Implement `write(self, record: TargetLog) -> None` as specified by `tzen.LogSink`.
One instance belongs to each configured source per client. The framework calls
an optional `close()` when the client closes, including on setup failure.
