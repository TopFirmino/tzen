# C test harness

`src/tzen.c` implements bounded RX/TX, discovery, test execution, synchronization,
and run-specific logs/results. The application includes only `tzen.h`; protobuf,
COBS and CRC stay internal. TTP itself handles protobuf only.

```c
TzenConfig_t config = {
    .send_bytes = uart_send_frame,
    .user_data = uart_context,
    .tests = test_table,
    .num_tests = test_count
};
if (!tzen_th_init(&config)) { /* Handle invalid configuration. */ }

/* One producer: receive bytes in order. */
tzen_th_feed_b(received_byte);

/* One main task: receive commands, send replies, drain worker results. */
tzen_th_main_function();

/* Worker task 0 (or core 0), polled repeatedly: */
tzen_th_worker_main_function(0);
/* Optional independent worker task 1 (or core 1): */
tzen_th_worker_main_function(1);
```

For a single-threaded application, call main then each configured worker from a
superloop. For concurrent workers, assign each task its own stable worker ID.
Calls on different IDs can execute user code concurrently. Overlapping calls on
the same ID return without doing work. Invalid IDs are ignored. No thread or
core is created by the library. Schedule main and workers repeatedly: there are
no wakeup callbacks. Each worker executes at most one step callback per poll.

All queues and worker state use fixed storage:

- RX: `TZEN_TH_RX_SLOTS` (default 4), with one producer-owned slot and 3 usable
  queued frames. Feed decodes COBS directly into that slot. Invalid/oversized
  frames and new arrivals when full are dropped. Main validates CRC before
  public TTP decoding, dispatches at most one RX queue capacity per call, and
  retains the RX slot until dispatch finishes.
- Execution requests: a FIFO of `TZEN_TH_WORKER_QUEUE_DEPTH` (default 4), in
  addition to up to `TZEN_TH_MAX_WORKERS` active executions (default 2). Entries
  contain run ID, test index, publication and cancellation flags. A worker cannot
  take a new request until main has attempted its acceptance reply; a failed
  acceptance cancels it. Workers take ready requests in FIFO order.
- Return events: a FIFO of `TZEN_TH_RESULT_QUEUE_DEPTH` (default 16). Workers
  copy log, step, sync and terminal messages into it. Main alone drains protocol
  events through the transport, at most one result queue capacity per poll.
  Workers never call the transport. Each worker reserves two result slots before
  calling setup/step/teardown, guaranteeing space for step and terminal results.
  With insufficient capacity, the worker returns without starting user code.
  Logs can only consume unreserved slots and return false when full.

Configure paired custom macros for concurrent callers:

| Hook suffix after TZEN_TH_ENTER/EXIT_CRITICAL_SECTION | Protects |
| --- | --- |
| `_RX_QUEUE()` | RX publication and consumption |
| `_WORKER_QUEUE()` | Request/result rings, worker ownership/control, status |
| `_TX()` | One complete transport callback invocation |

All pairs default to the general `TZEN_TH_ENTER_CRITICAL_SECTION()` and
`TZEN_TH_EXIT_CRITICAL_SECTION()` hooks, which default to no-ops for serialized
calls only. Both members of any custom pair must be provided. Hook pairs are
never nested, so they may share one nonrecursive mutex. Test callbacks run outside
all locks; protobuf and CRC run outside queue locks. The TX lock covers the
transport callback; that callback must not reenter harness APIs.

For different cores, use a cross-core mutex/spinlock with acquire/release memory
visibility and coherent shared storage. Disabling interrupts only on the current
core is insufficient. ISR feed callers require ISR-safe RX hooks that preserve
prior interrupt state; worker/main/TX hooks run in task context. The host example
uses a shared pthread mutex. Target ISR timing and multicore port behavior still
require target validation.

Execute accepts valid nonempty tests and returns OK before any run event is
transmitted. Duplicate queued/active run IDs and full request queues return BUSY;
invalid indices return INDEX. Run ID zero is valid. A run ID remains reserved
through the terminal transport attempt, including queued cancellations. New
requests are rejected as INVALID after a transport failure or without a transport.
There is no command retry cache.

Abort marks the matching queued/active execution. A queued cancellation remains
in FIFO order until a worker returns ABORTED, with no setup or teardown. Active
abort is cooperative: it takes effect after a callback returns or on the next
poll. Abort is rejected once finishing has begun, or if already requested.
Other runs remain independent.

Each started execution receives a zeroed, 8-byte-aligned scratchpad, NULL
`ext_vm_ctx`, and its own context. Setup runs once and teardown runs exactly once,
including setup failure and active abort. Lifecycle callbacks are bounded and
must coordinate any shared external resources. Never retain a context after its
callback or modify the run/step bookkeeping fields. Use scratchpad/ext_vm_ctx
for application-owned state; clean up owned resources in teardown.

Step behavior:

| Return value | Behavior |
| --- | --- |
| PASS_NEXT | Report step success, advance, finish after last step |
| DONE_PASS | Report step success and finish immediately |
| FAIL or invalid value | Report step failure and finish FAIL |
| YIELD | No step report; repeat this step next poll, increment step_Iterations |
| WAIT_SYNC | Require exactly one tzen_sync(ctx, id) call; queue SyncWait and wait |

`step_Iterations` resets on advance and saturates at UINT32_MAX. Reports use
1-based step numbers. Synchronization IDs may be zero. SyncRelease must match
both run ID and current sync ID and is accepted once. A release completes the
waiting step; the next step runs on another poll. Missing/wrong/repeated releases
return NOT_FOUND. Contract violations (missing sync call, multiple calls, or
calling sync then returning another result) fail the step without a SyncWait.
Aborting an unfinished step produces no step report. There is no sync timeout.

`tzen_log` and `tzen_logf` return bool and enqueue a copied message containing
`run_id` and `test_index` from the supplied context. Call them from that context's
own setup/step/teardown callback. They return false for invalid context/level/text,
text longer than 63 bytes, a formatting failure, transport failure or queue
backpressure. There is no blocking or truncation. A rejected log does not affect
the transport status or consume reserved completion capacity. Logs for each run
precede its terminal event. Both generated bindings include the new identity
fields, and Python framing now allows 94-byte frames.

`send_bytes(frame, len, user_data)` returns bool and must consume/copy the complete
frame before returning; its pointer expires on return. Report partial writes as
failure. Framing is `0x00 | COBS(protobuf + CRC16-CCITT-FALSE) | 0x00`, with CRC
high byte first. `TZEN_TH_MAX_PACKET_SIZE` bounds decoded payload including CRC
(default 256); reserve at least 91 bytes for the current maximum TTP message
plus CRC. Framing is handled internally using bounded stack storage. There are no explicit heap allocations in the harness.

A failed transport callback makes `tzen_th_transport_ok()` false until reinit;
internal protocol encoding/capacity failure also marks failure. Invalid raw-send
arguments or a missing callback do not change it. Later raw sends remain allowed,
but workers abort/clean up on subsequent polls and queued runs never start.
Main drains/discards undeliverable worker events, releasing capacity and IDs;
delivery after a transport failure is not guaranteed. Keep polling main/workers
until cleanup is complete. The status queries are synchronized snapshots;
RUNNING_STEP also covers pending jobs/results/cleanup, WAITING_SYNC means only
waiting workers remain, and IDLE means no jobs/results/active work remains.

Initialization copies callback/user data and the table pointer/count. Keep the
table, its names and step arrays valid and unchanged until reinit. Empty tables
and names are valid; names must be non-NULL and at most 31 bytes. Nonzero step
counts require valid arrays and callbacks. Zero-step entries are discoverable
but execute returns INVALID. Failed init preserves the previous configuration.
Reinit is rejected with pending jobs/results or active/polling workers. Init and
reinit require all callers stopped. `get_us` remains reserved.

Build as C11 with harness `inc`/`cfg`, TTP `C/inc`/`C/generated` and nanopb include
paths. Link `tzen.c`, `ttp.c`, `ttp.pb.c` and nanopb common/encode/decode sources.
The C++ public header exposes no TTP types. `tzen_codex.c` and older
`test_engine.c`, `test_queues.c`, `test_concurrent.c` remain historical references
for an earlier API, excluded from builds. Current worker tests are in
`tests/test_workers.c`.

Run `make -C examples/Host/C check` or
`python -m unittest discover -s testharness-c/tests -v`. Checks include buffered
binary Master/Slave transfers, one/two live worker threads, overlapping same-ID
calls, 1,000 executions, queue saturation, cleanup and minimal result capacity.
These are host checks, without flashing or target multicore/ISR validation.
