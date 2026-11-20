<!--
Tzen
Author: L. Furcas
SPDX-License-Identifier: MPL-2.0
-->

# C/Python pipe example

## Pytest documentation and Python counterpart

From the repository root, build the host with `make -C examples/Host/C`, then run
`pytest examples/Host/tests -v -rP --log-level=INFO`. The example selects its own transport
configuration by default. The full run includes one intentional failure.

Additional commands from the repository root:

```sh
python -m pip install -e .
make -C examples/Host/C
python -m tzen docs examples/Host/tests --output examples/Host/results/offline.json
python -m pytest examples/Host/tests --tzen-config examples/Host/tzen-host.toml --collect-only -vv --tzen-strict-docs --tzen-docs examples/Host/results/collected.json
python -m pytest examples/Host/tests --tzen-config examples/Host/tzen-host.toml -k "not Expected" -v --tzen-strict-docs --junitxml=examples/Host/results/passing.xml
```

Pytest discovers the declarations in `../tests/test_host.py` normally.
`TestYield` and `TestExpectedFailure` inherit `TzenRemoteTestCase` and supply
only documentation. `TestSynchronization` inherits `TzenCompanionTestCase`
and has three ordered `@step` methods: wait
for sync 42, write/check a host-side probe, and release C. It obtains its probe
from a pytest fixture in `__init__`; its finalizer checks C's completion log.
The host-action step also requests `temporary_probe`, which is removed when
the step ends. The release step checks that it is already gone. There are no
testcase setup/teardown hooks.
Tzen automatically starts and finishes the single C run around the steps.
All three synchronization steps are critical, so failures stop the sequence.
The probe is a temporary file demonstrating host participation, not a physical
voltage measurement. Fixture teardown checks that the host action occurred.

The TOML file configures only transport and execution limits. It has no test
paths. Use the explicit `examples/Host/tests` path to select this example;
running pytest from the repository root without paths collects development
tests according to the repository's normal pytest configuration.
Exact selection also works, for example
`python -m pytest examples/Host/tests/test_host.py::TestSynchronization --tzen-config examples/Host/tzen-host.toml -v`.

The offline command imports declarations but never imports or opens the
configured transport. Its JSON is marked unverified. Live collection validates
the target names against the C registry, exports metadata and descriptions,
and executes neither test bodies nor fixtures. `-vv` shows the descriptions
and ordered Python steps. JUnit includes per-step results in `tzen_steps`;
add `-rP --log-level=INFO` to see Python and C log records for passing cases in host observation order.
The passing execution command selects the two positive cases. Remove
`-k "not Expected"` to include the intentional negative example: pytest then
reports two passes and one failure, returning exit code 1 by design.

## Direct client example

From the repository root, install the Python dependencies and run:

```sh
python -m pip install -r requirements.txt
make -C examples/Host/C check
```

Requires GNU Make, a C11 compiler and Python. On Windows, Cygwin GCC is
supported; native Windows builds use binary CRT descriptors and PeekNamedPipe.
Linux builds use select/read. The executable keeps the `.exe` suffix on both
platforms so the commands are identical.

To run an already built executable:

```sh
python examples/Host/python/run.py
```

Pass `--executable PATH` to use another build. `make run` also runs the Python
example. The C executable expects piped stdin, not interactive keyboard input.

- `testcases.c/.h`: public TZEN callbacks and the static test registry.
- `tzen_host_cfg.h`: host compile-time limits/hooks and runtime declarations.
- `tzen_host_cfg.c`: configuration instance, stdout callback and platform I/O.
- `main.c`: initialization, input byte feeding, main polling and worker polling.
- `../python/pipe_transport.py`: subprocess ownership and timed pipe reads.
- `../python/run.py`: discovery, execution, automatic synchronization release,
  expected failure and synchronization abort through the existing `tzen.Client`.

The Makefile compiles the existing harness and protocol sources directly.
All C engine calls run in one thread, using the default no-op critical-section
hooks. Input polling times out every millisecond, allowing yielded steps and
queued output to progress without another incoming command. Test callbacks
must return promptly. Stdout contains only binary protocol frames; application
diagnostics belong on stderr. The transport callback flushes each frame.
Python drains stdout on a reader thread so client receive deadlines work on
Windows and Linux. Stderr is inherited, avoiding an undrained error pipe.

The three tests demonstrate yielding then passing, waiting for sync ID 42 then
passing, and intentional failure. `check` succeeds only when all expected
results and synchronization abort match. On stdin EOF the C process exits;
Python closes stdin and waits, killing the child if it fails to exit within
two seconds. EOF is process shutdown, not a graceful abort of active tests.

Run `make -C examples/Host/C clean` to remove the executable.

The Makefile selects `tzen_host_cfg.h` with `TZEN_CONFIG_HEADER` for all C
sources. The host build does not use the default `testharness-c/cfg/tzen_cfg.h`.
Other builds can omit the selector to use that default configuration.
`tzen_types.h` contains configuration-independent types and a forward declaration
of the context. `tzen_context.h` includes the selected configuration and defines
the complete context and scratchpad helper; `tzen.h` includes it for testcases.
Keep the configuration identical across all translation units because scratchpad
size affects the context layout. Configuration headers may include
`tzen_types.h`, but should not include `tzen.h` or `tzen_context.h`.


## Source-aware logs, including after TestFinished

`make -C examples/Host/C check` now prints the messages as Python receives them:

- Source `1` (`system`): a global startup message without an execution identity.
- Source `0` (`test`): the existing automatic testcase diagnostics.
- Source `7` (`coverage`): a **synthetic** summary emitted after each started
  testcase's terminal event, including failure and synchronization abort.

The teardown callback copies `(run_id, test_index)` into a bounded application
buffer. On the next main-loop iteration, after the harness has transmitted the
terminal result, `host_emit_deferred_logs()` queues the summary independently of
the released worker. No context pointer is retained. This example is single
threaded and treats enqueue failure as an explicit process error.

The framework reads the system and coverage routes from `../tzen-host.toml`.
The coverage route requests one correlated message after each testcase with a
two-second timeout. These demo messages contain synthetic data.

For visible logs from the pytest cases, run from the repository root:

```sh
python -m pytest examples/Host/tests --tzen-config examples/Host/tzen-host.toml -k "not Expected" -v -rP --log-level=INFO
```

Remove `-k "not Expected"` to also see the intentional failure (pytest exits 1).
The direct `make check` runner verifies that failure as an expected outcome and
also exercises abort, so it exits successfully when all four runs behave correctly.

Pytest captures target messages through Python logging. Use `--log-level=ERROR` for errors only. With `-rP`, pytest displays captured output for passing tests as well. The direct runner prints its own standalone trace.

Source 7 uses the built-in file sink. Source 8 uses the application class
`examples.Host.python.coverage2:Coverage2Sink` in `../python/coverage2.py`.
Its `write(record)` method appends a JSON object with the execution identity
and synthetic sample to `../results/coverage2.jsonl` after normal logging.
