# C/Python pipe example

## Pytest documentation and Python counterpart

From the repository root:

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
add `-rA` to display successful Python step reports in the terminal.
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
