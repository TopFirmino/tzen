<!--
Tzen
Author: L. Furcas
SPDX-License-Identifier: MPL-2.0
-->

# Ada bindings for the C test harness

Use `Tzen_Bindings` from a GNAT Ada 2012 application. Compile
`tzen_bindings.ads`, `tzen_bindings.adb` and `tzen_ada.c` alongside the C harness
and its TTP and nanopb dependencies. Compile the C shim and harness with the
same configuration headers and compiler ABI. The bindings assume standard
C enum sizes, so build the C sources without `-fshort-enums`. The
[Ada host project](../../examples/Host/ADA/tzen_host_ada.gpr) shows the source
and include paths.

## Port an application

1. Fill an aliased `Configuration` and call `Init` before feeding bytes or
   starting the pollers. Supply a library-level `Send_Callback` with
   `Convention => C` to write or copy the full frame before returning.
   `User_Data` is passed through to the callback. `Get_Us` is reserved by
   the current harness.
2. Feed received bytes in order with `Feed_Byte`. Schedule `Poll` and
   `Poll_Worker` regularly, including while the transport is idle. Worker
   IDs start at zero and end at `Worker_Count - 1`. The default C
   configuration assumes serialized calls. For concurrent callers, use the
   hooks described in [the C harness guide](../README.md).
3. Register Ada callbacks by filling a `Test_Array` and setting `Tests`
   to the first descriptor's `'Access` and `Num_Tests` to the array length.
   Each descriptor similarly points to the first element of its `Step_Array`,
   sets `Num_Steps`, and gives the harness a NUL-terminated name of up to
   31 bytes. Declare steps and any optional setup and teardown subprograms
   at library level with `Convention => C`. Keep descriptor arrays, step
   arrays, callback code, and name storage alive while the configuration is
   active. Handle exceptions inside callbacks before returning to C.

Within a callback, use `Info_For` to copy the execution identity and inspect
step progress. `Scratchpad` returns storage cleared at the start of each run.
Pass the size and alignment of your state in C bytes and check for
`System.Null_Address` before interpreting it. Use the context and scratchpad
only during callbacks that own them. Use `Sync` with a `Wait_Sync` step result.

`Log` and `Emit_Log` take Ada strings of up to 63 bytes. Build formatted
messages in Ada using string concatenation or `'Image`. A null execution
pointer passed to `Emit_Log` emits a global log on an application-defined
source.
