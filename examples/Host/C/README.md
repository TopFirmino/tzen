# Host C example

Requires GNU Make and a C11 compiler. From the repository root:

```powershell
make -C examples/Host
make -C examples/Host run
```

The Makefile compiles `main.c` and the existing `testharness-c/src/tzen.c`
directly, using the project's headers. No harness sources are copied.
`tzen_codex.c` is the old implementation and is excluded.

The example calls `tzen_th_init` and passes a sample COBS frame one byte at
a time to `tzen_th_feed_b`. The sample has no protocol command or valid CRC.
It demonstrates the current RX API; command processing and test execution
are not implemented yet. Configuration callbacks are unused at this stage.

Use `make -C examples/Host clean` to remove the executable.
