<!--
Tzen
Author: L. Furcas
SPDX-License-Identifier: MPL-2.0
-->

# Tzen Ada host

This example initializes and polls the C harness from Ada through
[`Tzen_Bindings`](../../../testharness-c/ada/README.md). It uses binary
stdin/stdout pipes and emits a startup log. The pipe I/O implementation is
shared with the C host. Its registry contains three Ada examples.

- **Yield and pass** counts polls in the run's scratchpad and logs completion.
- **Synchronize and pass** waits for the Python host to release sync point 42,
  then runs the same yielding step.
- **Expected failure** logs an error and returns a failed step.

This project selects its local `tzen_host_cfg.h` for both the C harness and
the Ada binding shim. The Ada main procedure supplies the runtime configuration.

From the repository root, with GNAT and GPRbuild installed and the C compiler
from the same toolchain on `PATH`:

```powershell
git submodule update --init
gprbuild -p -P examples/Host/ADA/tzen_host_ada.gpr
uv run --locked python examples/Host/python/run.py --slave ada
```

The launcher checks all three results and also aborts a separate run at sync
point 42. It uses `examples/Host/ADA/tzen_host_ada.exe` unless you pass
`--executable`. Running it without `--slave` uses the C host by default.

The Ada registry uses the same names as the C host, so the existing pytest
declarations can exercise either one. Run the two positive Ada cases with:

```powershell
uv run --locked pytest examples/Host/tests --tzen-config examples/Host/ADA/tzen-host.toml -k "not TestExpectedFailure"
```

Include `TestExpectedFailure` to see the Ada diagnostic reported as a pytest
failure.
