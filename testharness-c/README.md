# C test harness

The application includes only `tzen.h`, supplies a transport callback and static
test registry, and feeds received bytes. COBS, CRC16 and protobuf stay inside the
harness; no TTP types or framing code are needed in the integrating application.

```c
TzenConfig_t config = {0};
config.transport_send = uart_send; /* Copy/consume the entire frame before returning. */
if (!tzen_th_init(&config, test_table, test_count)) {
    /* Handle invalid configuration. */
}

/* UART RX ISR, or one serial receive task: */
tzen_th_feed_b(received_byte);

/* Bare-metal superloop: */
tzen_th_main_function();
for (unsigned int id = 0; id < TZEN_TH_MAX_WORKERS; ++id)
    tzen_th_worker_main_function((uint8_t)id);
```

Build the C implementation as C11, including harness `inc`/`cfg`, TTP
`C/inc`/`C/generated`, and nanopb directories. Link `tzen.c`, the TTP codec,
generated protobuf source, and nanopb common/encode/decode sources. The public
header also supports C++ callers. The configuration macros in `cfg/tzen_cfg.h`
can be overridden with compiler `-D` flags.

Two fixed queues separate reception, command handling and test execution:

- RX uses `TZEN_TH_RX_SLOTS` slots (default 4). One slot belongs to the producer,
  so 3 complete frames can wait by default. `tzen_th_feed_b` decodes COBS directly
  into that slot and publishes only complete frames. It performs bounded work
  per byte, uses no mutex, and performs no CRC/protobuf processing. Invalid or
  oversized COBS frames are discarded until the next zero delimiter; a full RX
  queue drops the incoming frame without altering queued frames. Such drops
  have no protocol reply: the host observes a timeout. `TZEN_TH_MAX_PACKET_SIZE`
  (default 256) bounds decoded bytes including CRC. Main validates CRC and
  protobuf and ignores invalid packets or zero command sequence IDs.
- Execute requests enter a FIFO of `TZEN_TH_WORKER_QUEUE_DEPTH` pending jobs
  (default 4), containing only run ID and test index. Queue-full or duplicate
  queued/active run IDs return BUSY; an invalid index returns INDEX. Accepted
  requests receive OK before workers can start them. There can be up to
  `TZEN_TH_MAX_WORKERS` active runs (default 2), plus the queued jobs. Run ID 0
  is valid. Workers take jobs FIFO, with one context and scratchpad per worker.

`tzen_th_main_function` processes at most one RX queue capacity per call. It
handles discovery immediately and routes control requests by run ID. It never
calls test setup, steps or teardown. Each worker poll starts at most one job and
calls at most one step. In bare metal this is cooperative interleaving. In an
RTOS, separate worker tasks can execute callbacks concurrently; steps must still
return promptly for responsive aborts. Tests sharing hardware must coordinate
access or be run sequentially.

For concurrent tasks, supply paired `mutex_lock`/`mutex_unlock` callbacks using
one shared task mutex. They protect the pending queue, worker control state and
whole outgoing frames. Setup, steps and teardown run outside that mutex.
Callbacks must not reenter harness APIs. Use one producer for feed, one owner
for main, and one task per worker ID; invalid worker IDs are ignored. Each task
must retain its worker ID. Descriptor arrays and names must remain valid for
the harness lifetime. Names longer than 31 UTF-8 bytes are rejected at init.

`notify_main_from_isr` is an optional ISR-safe notification after a frame is
published. `notify_worker` is called from task context, outside the mutex, for
queued/control work and transport errors; it must wake all potentially waiting
workers. Use retained notifications or a checked wait protocol to avoid lost
wakeups. Main also needs scheduling when RX has work. State getters are snapshots:
`tzen_th_worker_get_state(id)` describes one worker's runnable/waiting state;
`tzen_get_state()` returns RUNNING if there is ready work, else WAITING_SYNC if
any worker waits, else IDLE.

RX publication uses C11 acquire/release byte atomics, requiring always lock-free
byte atomics on the target. AVR uses native atomic byte accesses and compiler
barriers for its single-core ISR/main ordering. Init/reinit must run with RX and
all task callers stopped; queued or active runs prevent reinitialization.

Execution contract:

- Setup runs once after a worker takes the job, with a zeroed, 8-byte-aligned
  scratchpad and NULL `ext_vm_ctx`. `TZEN_GET_STATE` checks size/alignment.
- PASS_NEXT completes the step and advances; YIELD repeats it next poll and
  increments `step_Iterations`; DONE_PASS exits early; FAIL terminates.
- WAIT_SYNC requires `tzen_sync(ctx, sync_id)` in that step. A matching release
  is acknowledged immediately and applied by the owning worker on its next
  poll. It completes the waiting step and advances. Zero sync IDs are valid.
  A mismatched or repeated release returns NOT_FOUND. Requesting sync and
  returning any other result fails the step.
- Abort is acknowledged in main and applied by the owning worker when its
  callback returns or at its next poll. Teardown runs exactly once for each
  started run, including setup failure, and precedes the terminal event.
  A job cancelled while still queued emits ABORTED without setup or teardown.
- Step success/failure reports use 1-based step numbers. YIELD and abort of an
  unfinished step emit no step report. WAIT_SYNC reports success upon release.
  Setup failure emits no step report. Invalid step contracts report failure.
- TX failure is sticky (`tzen_th_transport_ok()` becomes false). Active workers
  abort with teardown; pending jobs are drained with ABORTED without starting
  them. Further execute requests fail until reinit. Transport delivery after a
  failure cannot be guaranteed. Call workers to let them perform cleanup.
- `tzen_log` / `tzen_logf` emit diagnostic messages. The wire schema does not
  attach run IDs to logs. Disconnection alone does not trigger target abort.

There are no explicit heap calls in the harness. Allocation behavior and stack
requirements of the application, C library and transport remain platform-specific.
The TX callback receives temporary stack storage and must consume/copy it before
returning. All transport and lifecycle callbacks must be bounded.

Run `python -m unittest discover -s testharness-c/tests -v` with GCC and pthread
support. Native tests cover lifecycle, two simultaneously executing workers,
control routing, FIFO/full/cancel behavior, streaming COBS boundaries, RX
recovery, CRC/protobuf rejection and concurrent SPSC traffic. Target ISR timing,
RTOS integration and hardware behavior require target validation.
