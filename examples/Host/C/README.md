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

Two buffered binary `tmpfile()` streams simulate Master-to-Slave and
Slave-to-Master transfers. They are flushed and repositioned before reading,
closed on completion, and automatically removed. Each stream has one owner
at a time; no file is read and written concurrently.

The Master writes the standard CRC vector `123456789` (CRC `0x29B1`), then a
corrupted frame. A producer thread reads the Master-to-Slave stream and feeds
the Slave byte by byte using `tzen_th_feed_b`. The main thread calls
`tzen_th_main_function` concurrently and drains packets after joining.

The Slave then calls `tzen_th_send_packet` with `123456789` and a zero-byte
payload. Its configured `send_bytes` callback writes each complete framed
packet in one `fwrite` call to the Slave-to-Master stream. The Master verifies
the exact expected frame bytes, including COBS, CRC and delimiters, and rejects
trailing data. These initial sends demonstrate the raw framing API.

`protocol_cases.c` then registers two example test descriptors and exchanges
actual TTP requests/replies through a second pair of buffered binary temporary
files. No tests execute: the step callbacks abort if accidentally called.
The Master uses the public `Ttp_EncodeHostToTarget` and
`Ttp_DecodeTargetToHost` APIs and independent framing/CRC code to verify the
Slave's replies. The Slave uses the public TTP decode/encode APIs internally.

Cases cover test count, both names and step counts (including a 31-byte name),
out-of-range indices, maximum sequence ID, missing/unknown commands, rejected
execution/control commands, zero sequence ID, corrupt CRC, malformed protobuf,
recovery after rejection, invalid metadata configuration, and an empty registry.
Every expected response is checked for sequence ID, status and payload; cases
expecting silence reject any output. Protocol cases exchange one request at a
time to avoid intentionally overflowing the bounded RX queue.

```c
TzenConfig_t cfg = {.send_bytes = my_send_frame, .user_data = my_transport};
if (!tzen_th_init(&cfg)) { /* Handle initialization error. */ }
if (!tzen_th_send_packet(payload, payload_len)) { /* Handle send failure. */ }
```

`my_send_frame(const uint8_t *frame, size_t len, void *user_data)` returns
`bool`. It must consume/copy the entire frame before returning, and return
false on any failure, including partial writes. The wire format is
`0x00 | COBS(payload + CRC16-CCITT-FALSE) | 0x00`, with CRC high byte first.
The payload can be empty and is bounded by `TZEN_TH_MAX_PACKET_SIZE - 2`.
The harness copies the transport callback and user pointer at initialization;
the pointed-to transport must remain valid during sends. A NULL callback
permits RX-only use. TX uses bounded stack storage without heap allocation.

Serialize send callers and calls to `tzen_th_transport_ok`; the RX tasks may
continue independently. Since main now sends command replies, serialize main
with other send/status callers too. The callback must not reenter harness APIs.
A failed callback makes `tzen_th_transport_ok()` false until reinitialization;
later sends are still allowed and each returns its own result. Invalid send
arguments or a missing callback return false without invoking the transport
or changing this status.

The queue supports one producer and one consumer using configurable critical
sections. Initialize before starting either task. Full queues drop new frames;
the consumer releases slots only after checking the CRC. Private
`rx_valid_packets` and `rx_invalid_packets` counters in `testharness_state`
can be inspected in a debugger while the tasks are stopped. The `check`
target runs the host transfer and protocol examples, verifies RX CRC outcomes, queue reuse,
malformed frames and concurrent reception, plus a build with default no-op
hooks. TX tests use independent COBS decoding and CRC verification, check a
known wire vector, empty/zero payloads, all permitted lengths, and all two-byte
payload values (including zero CRC bytes). They verify one callback per frame,
argument rejection, callback failures, sticky status and reinitialization.
Both default 256-byte and 600-byte decoded capacities are tested to cover
254-byte COBS block boundaries and multiple full blocks.

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
