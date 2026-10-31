# C test harness

`inc/tzen.h` retains the proposed descriptor/context API. `src/tzen.c` implements
one cooperative engine; `cfg/tzen_cfg.h` configures its static storage. Build with
C11 and include the harness `inc`/`cfg`, TTP `C/inc`/`C/generated`, and nanopb paths.
Link the harness, TTP codec, generated protobuf source, and nanopb encode/decode/common.

Declare static step arrays with `TH_TEST_ENTRY`, provide transport callbacks and
a registry to `th_init`, feed COBS bodies without either zero delimiter to
`th_on_rx_frame`, and call `th_poll` continuously. The transport callback must
consume or copy outgoing bytes before returning: its frame pointer is temporary.

Execution contract:

- Commands are decoded and CRC-checked before insertion into a fixed queue (default depth 4). Invalid frames, zero sequence IDs and full queues return false without a response. The adapter owns stream delimiters and overflow recovery.
- Poll processes at most one queue-depth worth of commands, then invokes at most one step. A step must return promptly; this engine cannot preempt blocking code.
- Execute validates busy state before index, clears the context/scratchpad, replies with acceptance, then calls setup. A setup failure runs teardown and reports FAIL.
- PASS_NEXT advances; YIELD repeats the same step on the next poll and increments `step_Iterations`; DONE_PASS exits early; FAIL terminates immediately.
- WAIT_SYNC requires a preceding `th_request_sync`. The matching release advances to the next step, including success if the wait was the last step. Zero run IDs and sync IDs are allowed. A mismatched release/abort returns NOT_FOUND. Emitting sync and returning another result is an invalid step contract and ends with FAIL.
- `th_report_step` emits an explicit report with the current 1-based step number. Reports are not automatically duplicated by the engine. `th_log` and `th_logf` produce protocol log events. Logs have no run identity in the schema.
- Teardown runs exactly once for success, fail (including setup failure), or accepted abort, before the terminal event. It must restore hardware on every exit; the Arduino example always turns the LED off.
- TX failure is sticky (`th_transport_ok()` becomes false). The worker aborts an active run with teardown, attempts its terminal event, and rejects further executions until reinitialized. Delivery cannot be guaranteed after transport failure.
- Discovery is available during execution and sync waits. Reinitializing during an active run is rejected. EOF/disconnection is not an automatic target abort: a standalone target waiting for sync remains waiting until released, aborted, or reset.

The scratchpad is zeroed per run and aligned to 8 bytes. `TH_GET_STATE` checks
both size and requested alignment at compile time. Step state belongs in this
context, not function statics. Test descriptors and names must remain valid for
the engine lifetime; names exceeding 31 UTF-8 bytes are rejected during init.

There is one owner for init/poll/step utilities. RX may run in a separate task
with paired mutex callbacks protecting the command queue; notify_worker runs
after unlocking. RX is not directly ISR-safe. RTOS behavior has not been tested.
Setup/teardown and TX callbacks must also be bounded for responsive scheduling.
The implementation has fixed storage and no explicit heap calls; this is not
proof that an application, transport, or linked platform is allocation-free.

Run `python -m unittest discover -s testharness-c/tests -v` for native lifecycle,
queue, failure and teardown checks. Arduino integration is under `examples/Arduino`.
