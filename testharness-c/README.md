# C test harness

The current `src/tzen.c` implements bounded RX, TX, and test discovery. Test
execution, worker scheduling, logs and synchronization will be added later.
`src/tzen_codex.c` and the older `test_engine.c`, `test_queues.c`, and
`test_concurrent.c` are historical implementation/reference files; they target
an earlier API and are excluded from the current builds and test runner.

The application includes only `tzen.h` and configures its transport and metadata:

```c
TzenConfig_t config = {
    .send_bytes = uart_send_frame,
    .user_data = uart_context,
    .tests = test_table,
    .num_tests = test_count
};
if (!tzen_th_init(&config)) {
    /* Handle invalid configuration. */
}

/* One receive producer task or ISR with suitable critical-section hooks: */
tzen_th_feed_b(received_byte);

/* One main task: validate CRC, decode commands, send replies. */
tzen_th_main_function();
```

`send_bytes(frame, len, user_data)` returns bool and receives exactly one complete
frame per call. It must consume/copy the whole frame before returning and report
partial writes as failure. The frame pointer expires on return. A NULL callback
allows RX-only use. The table and names must remain valid and unchanged until
reinitialization; initialization copies the callback, user pointer and table
pointer/count, so the config structure itself may expire. Empty tables and names
are permitted; nonempty tables require a pointer, names must be non-NULL and at
most 31 bytes, and the count must fit uint32. Failed init leaves the previous
configuration intact. Initialization/reinitialization requires all callers stopped.

Framing belongs to the harness: `0x00 | COBS(protobuf + CRC16) | 0x00`, using
CRC-16/CCITT-FALSE and a high-byte-first trailer. `ttp` provides only public
protobuf encoding/decoding. Main verifies CRC before calling
`Ttp_DecodeHostToTarget`, creates a reply with `Ttp_EncodeTargetToHost`, and sends
it through `tzen_th_send_packet` and the configured callback.

Current command behavior:

- GetTests returns the configured table count.
- GetTestInfo returns index, name and number of steps; invalid indices return
  RESULT_ERR_INDEX without a payload.
- Other commands, including ExecuteTest, AbortTest and SyncRelease, return
  RESULT_ERR_INVALID without a payload. No lifecycle callbacks execute.
- Missing/unknown commands return RESULT_ERR_INVALID when the sequence is nonzero.
- Sequence ID zero, malformed protobuf, invalid CRC and malformed COBS receive
  no response. Responses retain the request sequence ID; there is no retry cache.

RX is a single-producer/single-consumer queue with `TZEN_TH_RX_SLOTS` slots;
usable queued capacity is slots minus one. Feed decodes COBS directly into the
producer-owned slot. Full queues drop new frames, and oversized/incomplete frames
are discarded. Main retains each slot until CRC checking and dispatch finish,
then releases it. Main processes at most one queue capacity per call. Private
`rx_valid_packets`/`rx_invalid_packets` count CRC outcomes, not protobuf validity.

`TZEN_TH_MAX_PACKET_SIZE` bounds decoded payload plus its two CRC bytes. Raw
`tzen_th_send_packet(payload, len)` accepts up to this size minus two, including
empty payloads. Ensure the configured capacity can hold the protocol messages
and replies your application needs. Send failures return false; a callback
failure also makes `tzen_th_transport_ok()` false until reinit. Later sends remain
allowed. Invalid arguments or an absent callback do not change sticky status.

For concurrent RX/main callers, configure paired critical-section hooks in
`tzen_cfg.h` or a forced-include port header. The default hooks are no-ops for
serialized calls. RX-specific hooks default to the general hooks. An ISR port
must preserve prior interrupt state and use ISR-safe hooks. Serialize main with
other TX callers and transport-status queries, since main now sends replies.
Callbacks must not reenter harness APIs. CRC, protobuf and transport callbacks
run outside the RX critical sections. There are no explicit heap calls; TX uses
bounded stack storage and transport allocation remains application-specific.

Build as C11 and include harness `inc`/`cfg`, TTP `C/inc`/`C/generated` and nanopb.
Link `tzen.c`, `ttp.c`, generated `ttp.pb.c`, and nanopb common/encode/decode sources.
The public harness header supports C++ callers without exposing TTP types.

Run `make -C examples/Host/C check` for buffered-file Master/Slave exchanges,
discovery/error cases, concurrent RX, and TX framing regressions. Alternatively,
run `python -m unittest discover -s testharness-c/tests -v` with GCC/pthreads.
The current Python runner covers this implementation stage and leaves historical
execution tests for the later worker implementation. These are host checks;
ISR timing, hardware transport and target integration remain unverified.
