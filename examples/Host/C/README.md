# Host C example

Requires GNU Make, a C11 compiler, and POSIX threads (Cygwin on
Windows, or Linux). From the repository root:

```powershell
make -C examples/Host/C
make -C examples/Host/C run
make -C examples/Host/C check
```

The Makefile compiles `main.c` and the existing `testharness-c/src/tzen.c`
directly, using the project's headers. No harness sources are copied.
`tzen_codex.c` is the old implementation and is excluded.

After `tzen_th_init`, a producer thread feeds COBS frames byte by byte using
`tzen_th_feed_b`. The main thread calls `tzen_th_main_function` concurrently
and drains remaining packets after joining the producer. The frames contain
the standard CRC vector `123456789` with CRC `0x29B1`, then a corrupt CRC.
Command decoding and test execution are not implemented yet.

The queue supports one producer and one consumer using configurable critical
sections. Initialize before starting either task. Full queues drop new frames;
the consumer releases slots only after checking the CRC. Private
`rx_valid_packets` and `rx_invalid_packets` counters in `testharness_state`
can be inspected in a debugger while the tasks are stopped. The `check`
target verifies CRC outcomes, queue reuse, malformed frames, and concurrent
reception, plus a separate build with the default no-op hooks. Configuration
callbacks are unused at this stage.

`TZEN_TH_ENTER_CRITICAL_SECTION()` and `TZEN_TH_EXIT_CRITICAL_SECTION()`
default to no-ops in `tzen_cfg.h` for serialized calls from one task.
For concurrent calls, override both hooks with the same synchronization
mechanism. The host Makefile force-includes `host_critical_section.h` when
compiling the application and harness; `host_critical_section.c` implements
the hooks with a shared pthread mutex. CRC computation stays outside the
critical sections, while the consumer retains ownership of its slot.
For an interrupt-based port, preserve and restore the prior interrupt state
and use hooks appropriate for every calling context.

Use `make -C examples/Host/C clean` to remove the executables.
