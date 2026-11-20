/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

/* Focused execution-channel tests. RX and wire framing have separate suites. */
#include "../src/tzen.c"
#include <assert.h>
#include <stdio.h>
#ifdef TZEN_TH_TEST_WORKERS_CONCURRENT
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <time.h>
#endif

#define RUNS 2048U
static TargetToHost output[16384];
static size_t used;
static unsigned setups[RUNS], cleanups[RUNS], calls[RUNS], terminals[RUNS];
static TzenTestStatus_t cleanup_status[RUNS];
static uint32_t order[RUNS];
static size_t order_count;
static bool send_ok = true, setup_ok = true;
static size_t logs_accepted, logs_rejected;
static TzenStepResult_t mode = TZEN_STEP_PASS_NEXT;
static unsigned special;
#ifdef TZEN_TH_TEST_WORKERS_CONCURRENT
static pthread_t main_thread;
static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_changed = PTHREAD_COND_INITIALIZER;
static unsigned entered;
static bool open_gate;
#endif

static bool capture(const uint8_t *frame, size_t len, void *unused)
{
    (void)unused;
#ifdef TZEN_TH_TEST_WORKERS_CONCURRENT
    assert(pthread_equal(main_thread, pthread_self())); /* Workers never transmit. */
#endif
    if (!send_ok) return false;
    uint8_t raw[TZEN_TH_MAX_PACKET_SIZE];
    size_t count = 0U;
    assert(len >= 4U && frame[0] == 0U && frame[len - 1U] == 0U);
    for (size_t pos = 1U; pos < len - 1U;) {
        uint8_t code = frame[pos++];
        assert(code != 0U);
        for (unsigned i = 1U; i < code; ++i) {
            assert(pos < len - 1U && count < sizeof(raw) && frame[pos] != 0U);
            raw[count++] = frame[pos++];
        }
        if (code < 255U && pos < len - 1U) raw[count++] = 0U;
    }
    assert(count >= 2U && used < sizeof(output) / sizeof(output[0]));
    assert(tzen_th_crc16(raw, count - 2U) == (uint16_t)((uint16_t)raw[count - 2U] << 8U | raw[count - 1U]));
    assert(Ttp_DecodeTargetToHost(&output[used], raw, count - 2U) == TTP_STATUS_OK);
    if (output[used].which_payload == TargetToHost_test_event_tag &&
        output[used].payload.test_event.which_event == TestEvent_finished_tag) {
        uint32_t id = output[used].payload.test_event.run_id;
        assert(id < RUNS);
        ++terminals[id];
    }
    ++used;
    return true;
}

static bool setup(TzenContext_t *ctx)
{
    assert(ctx->run_id < RUNS && ctx->current_step == 0U && ctx->step_Iterations == 0U);
    assert(ctx->ext_vm_ctx == NULL && ((uintptr_t)ctx->scratchpad % 8U) == 0U);
    for (size_t i = 0U; i < sizeof(ctx->scratchpad); ++i) assert(ctx->scratchpad[i] == 0U);
    ctx->scratchpad[0] = 77U;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    ++setups[ctx->run_id];
    assert(order_count < RUNS);
    order[order_count++] = ctx->run_id;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return setup_ok;
}

static void cleanup(TzenContext_t *ctx, TzenTestStatus_t status)
{
    assert(ctx->scratchpad[0] == 77U);
    ++cleanups[ctx->run_id];
    cleanup_status[ctx->run_id] = status;
}

static TzenStepResult_t step(TzenContext_t *ctx)
{
    assert(ctx->scratchpad[0] == 77U && ctx->run_id < RUNS);
    ++calls[ctx->run_id];
    if (special == 1U) { /* Log flood must leave room for step + terminal. */
        for (unsigned i = 0U; i < TZEN_TH_RESULT_QUEUE_DEPTH + 4U; ++i) {
            if (tzen_logf(ctx, TZEN_LOG_INFO, "message %u", i)) ++logs_accepted;
            else ++logs_rejected;
        }
        assert(!tzen_log(NULL, TZEN_LOG_INFO, "invalid"));
        assert(!tzen_log(ctx, (TzenLogLevel_t)99, "invalid"));
        assert(!tzen_log(ctx, TZEN_LOG_INFO, NULL));
        assert(!tzen_log(ctx, TZEN_LOG_INFO, "1234567890123456789012345678901234567890123456789012345678901234"));
        assert(!tzen_logf(ctx, TZEN_LOG_INFO, "%064d", 1));
        return TZEN_STEP_DONE_PASS;
    }
    if (special == 2U) return TZEN_STEP_WAIT_SYNC; /* Missing tzen_sync. */
    if (special == 3U) { tzen_sync(ctx, 0U); return TZEN_STEP_PASS_NEXT; }
    if (special == 4U) { tzen_sync(ctx, 0U); tzen_sync(ctx, 0U); return TZEN_STEP_WAIT_SYNC; }
#ifdef TZEN_TH_TEST_WORKERS_CONCURRENT
    if (special == 5U) {
        (void)tzen_logf(ctx, TZEN_LOG_WARNING, "concurrent %lu", (unsigned long)ctx->run_id);
        assert(pthread_mutex_lock(&gate) == 0);
        ++entered;
        assert(pthread_cond_broadcast(&gate_changed) == 0);
        while (!open_gate) assert(pthread_cond_wait(&gate_changed, &gate) == 0);
        assert(pthread_mutex_unlock(&gate) == 0);
        return TZEN_STEP_DONE_PASS;
    }
    if (special == 6U) {
        (void)tzen_logf(ctx, TZEN_LOG_INFO, "stress %lu", (unsigned long)ctx->run_id);
        return ctx->step_Iterations < 2U ? TZEN_STEP_YIELD : TZEN_STEP_DONE_PASS;
    }
#endif
    if (mode == TZEN_STEP_WAIT_SYNC) tzen_sync(ctx, 0U);
    return mode;
}

static const TzenStepFn_t steps[] = {step, step};
static const TzenTestDescriptor_t table[] = {TZEN_TEST_ENTRY("worker", steps, setup, cleanup)};
static const TzenConfig_t config = {.send_bytes = capture, .tests = table, .num_tests = 1U};
static uint32_t sequence = 1U;

static void reset(void)
{
    assert(tzen_get_state() == TZEN_ENGINE_IDLE);
    assert(tzen_th_init(&config));
    memset(setups, 0, sizeof(setups)); memset(cleanups, 0, sizeof(cleanups));
    memset(calls, 0, sizeof(calls)); memset(terminals, 0, sizeof(terminals));
    used = order_count = logs_accepted = logs_rejected = 0U;
    send_ok = setup_ok = true;
    mode = TZEN_STEP_PASS_NEXT; special = 0U;
}

static ResultCode command(pb_size_t tag, uint32_t run, uint32_t arg)
{
    HostToTarget message = HostToTarget_init_zero;
    message.seq_id = sequence++;
    message.which_cmd = tag;
    if (tag == HostToTarget_execute_test_tag) {
        message.cmd.execute_test.run_id = run;
        message.cmd.execute_test.index = arg;
    } else if (tag == HostToTarget_abort_test_tag) message.cmd.abort_test.run_id = run;
    else if (tag == HostToTarget_sync_release_tag) {
        message.cmd.sync_release.run_id = run;
        message.cmd.sync_release.sync_id = arg;
    }
    uint8_t payload[TTP_MAX_MESSAGE_SIZE]; size_t len;
    assert(Ttp_EncodeHostToTarget(&message, payload, sizeof(payload), &len) == TTP_STATUS_OK);
    size_t before = used;
    tzen_th_dispatch(payload, len);
    if (!send_ok) { assert(used == before); return ResultCode_RESULT_ERR_INVALID; }
    assert(used == before + 1U && output[before].seq_id == message.seq_id);
    return output[before].status;
}
#define START(run) command(HostToTarget_execute_test_tag, run, 0U)
#define ABORT(run) command(HostToTarget_abort_test_tag, run, 0U)
#define RELEASE(run, sync) command(HostToTarget_sync_release_tag, run, sync)

static void poll(void) { tzen_th_worker_main_function(0U); tzen_th_main_function(); }
static void drain(void)
{
    for (unsigned i = 0U; tzen_get_state() != TZEN_ENGINE_IDLE && i < 100U; ++i) poll();
    assert(tzen_get_state() == TZEN_ENGINE_IDLE);
}

static void lifecycle(void)
{
    reset();
    assert(START(0U) == ResultCode_RESULT_OK); /* Run ID zero is valid. */
    assert(START(0U) == ResultCode_RESULT_ERR_BUSY);
    assert(!tzen_th_init(&config));
    tzen_th_worker_main_function(0U);
    assert(calls[0] == 1U && used == 2U); /* Worker only enqueues returns. */
    tzen_th_main_function();
    assert(output[2].payload.test_event.event.step.step_number == 1U);
    tzen_th_worker_main_function(0U);
    assert(cleanups[0] == 1U && cleanup_status[0] == TZEN_TEST_STATUS_SUCCESS);
    tzen_th_worker_main_function(0U);
    assert(calls[0] == 2U);
    assert(START(0U) == ResultCode_RESULT_ERR_BUSY); /* Terminal not delivered yet. */
    tzen_th_main_function();
    assert(terminals[0] == 1U && tzen_get_state() == TZEN_ENGINE_IDLE);
    assert(START(0U) == ResultCode_RESULT_OK); /* ID reusable after delivery. */
    drain(); assert(setups[0] == 2U && cleanups[0] == 2U && terminals[0] == 2U);

    reset(); mode = TZEN_STEP_YIELD;
    assert(START(1U) == ResultCode_RESULT_OK); poll(); poll();
    assert(calls[1] == 2U && testharness_state.workers[0].ctx.step_Iterations == 2U);
    assert(ABORT(1U) == ResultCode_RESULT_OK);
    assert(ABORT(1U) == ResultCode_RESULT_ERR_NOT_FOUND);
    drain(); assert(calls[1] == 2U && cleanups[1] == 1U && cleanup_status[1] == TZEN_TEST_STATUS_ABORTED);

    reset(); setup_ok = false;
    assert(START(2U) == ResultCode_RESULT_OK); drain();
    assert(calls[2] == 0U && cleanups[2] == 1U && cleanup_status[2] == TZEN_TEST_STATUS_FAIL);
    reset(); mode = TZEN_STEP_DONE_PASS;
    assert(START(3U) == ResultCode_RESULT_OK); drain(); assert(calls[3] == 1U && cleanups[3] == 1U);
    reset(); mode = TZEN_STEP_FAIL;
    assert(START(4U) == ResultCode_RESULT_OK); drain();
    assert(calls[4] == 1U && cleanups[4] == 1U && cleanup_status[4] == TZEN_TEST_STATUS_FAIL);
    for (unsigned violation = 2U; violation <= 4U; ++violation) {
        reset(); special = violation;
        assert(START(5U) == ResultCode_RESULT_OK); drain();
        assert(cleanup_status[5] == TZEN_TEST_STATUS_FAIL);
        for (size_t i = 0U; i < used; ++i)
            assert(output[i].which_payload != TargetToHost_test_event_tag || output[i].payload.test_event.which_event != TestEvent_sync_tag);
    }
    reset(); mode = (TzenStepResult_t)99;
    assert(START(5U) == ResultCode_RESULT_OK); drain(); assert(cleanup_status[5] == TZEN_TEST_STATUS_FAIL);
}

static void synchronization(void)
{
    reset(); mode = TZEN_STEP_WAIT_SYNC;
    assert(START(6U) == ResultCode_RESULT_OK); poll();
    assert(tzen_get_state() == TZEN_ENGINE_WAITING_SYNC);
    assert(RELEASE(7U, 0U) == ResultCode_RESULT_ERR_NOT_FOUND);
    assert(RELEASE(6U, 99U) == ResultCode_RESULT_ERR_NOT_FOUND);
    assert(RELEASE(6U, 0U) == ResultCode_RESULT_OK);
    assert(RELEASE(6U, 0U) == ResultCode_RESULT_ERR_NOT_FOUND);
    mode = TZEN_STEP_PASS_NEXT;
    poll(); assert(calls[6] == 1U && cleanups[6] == 0U);
    assert(RELEASE(6U, 0U) == ResultCode_RESULT_ERR_NOT_FOUND);
    drain(); assert(calls[6] == 2U && cleanup_status[6] == TZEN_TEST_STATUS_SUCCESS);
    reset(); mode = TZEN_STEP_WAIT_SYNC;
    assert(START(7U) == ResultCode_RESULT_OK); poll();
    assert(ABORT(7U) == ResultCode_RESULT_OK); drain(); assert(cleanup_status[7] == TZEN_TEST_STATUS_ABORTED);
}

static void queues(void)
{
    reset(); mode = TZEN_STEP_DONE_PASS;
    for (uint32_t i = 0U; i < TZEN_TH_WORKER_QUEUE_DEPTH; ++i) assert(START(10U + i) == ResultCode_RESULT_OK);
    assert(START(100U) == ResultCode_RESULT_ERR_BUSY);
    assert(START(10U) == ResultCode_RESULT_ERR_BUSY);
    assert(ABORT(10U) == ResultCode_RESULT_OK);
    assert(START(10U) == ResultCode_RESULT_ERR_BUSY);
    drain();
    assert(setups[10] == 0U && cleanups[10] == 0U && terminals[10] == 1U);
    for (size_t i = 0U; i < order_count; ++i) assert(order[i] == 11U + i);
    assert(order_count == TZEN_TH_WORKER_QUEUE_DEPTH - 1U);
    /* Wrap the request/result rings repeatedly. */
    for (uint32_t i = 0U; i < 20U; ++i) { assert(START(100U + i) == ResultCode_RESULT_OK); drain(); }

    reset(); special = 1U;
    assert(START(20U) == ResultCode_RESULT_OK); tzen_th_worker_main_function(0U);
    assert(logs_accepted == TZEN_TH_RESULT_QUEUE_DEPTH - 2U && logs_rejected != 0U);
    assert(testharness_state.results.count == TZEN_TH_RESULT_QUEUE_DEPTH);
    assert(cleanups[20] == 1U);
    assert(START(21U) == ResultCode_RESULT_OK);
    tzen_th_worker_main_function(0U);
#if TZEN_TH_MAX_WORKERS > 1U
    tzen_th_worker_main_function(1U);
#endif
    assert(calls[21] == 0U); /* No callbacks without reserved return capacity. */
    tzen_th_main_function(); special = 0U; mode = TZEN_STEP_DONE_PASS; drain();
    assert(terminals[20] == 1U && terminals[21] == 1U && calls[21] == 1U);
    for (size_t i = 0U; i < used; ++i) if (output[i].which_payload == TargetToHost_log_tag)
        assert(output[i].payload.log.run_id == 20U && output[i].payload.log.test_index == 0U);
}

static void transport_failure(void)
{
    reset(); mode = TZEN_STEP_YIELD;
    assert(START(30U) == ResultCode_RESULT_OK); poll();
    assert(START(31U) == ResultCode_RESULT_OK);
    send_ok = false;
    (void)command(HostToTarget_get_tests_tag, 0U, 0U);
    assert(!tzen_th_transport_ok());
    drain();
    assert(cleanups[30] == 1U && cleanup_status[30] == TZEN_TEST_STATUS_ABORTED);
    assert(setups[31] == 0U && cleanups[31] == 0U);
    send_ok = true;
    assert(START(32U) == ResultCode_RESULT_ERR_INVALID);
    reset(); assert(tzen_th_transport_ok());
    assert(command(HostToTarget_execute_test_tag, 32U, UINT32_MAX) == ResultCode_RESULT_ERR_INDEX);
    tzen_th_worker_main_function(UINT8_MAX);
    assert(tzen_th_worker_get_state(UINT8_MAX) == TZEN_ENGINE_IDLE);

    reset(); send_ok = false;
    (void)START(33U); /* A failed acceptance must not publish executable work. */
    send_ok = true; drain();
    assert(setups[33] == 0U && cleanups[33] == 0U);
    reset();
    TzenTestDescriptor_t bad = table[0];
    TzenConfig_t invalid = config;
    invalid.tests = &bad;
    bad.steps = NULL;
    assert(!tzen_th_init(&invalid));
    const TzenStepFn_t null_step[] = {NULL};
    bad.steps = null_step; bad.num_steps = 1U;
    assert(!tzen_th_init(&invalid));
    bad.num_steps = 0U;
    assert(tzen_th_init(&invalid));
    assert(START(34U) == ResultCode_RESULT_ERR_INVALID);
    invalid = config; invalid.send_bytes = NULL;
    assert(tzen_th_init(&invalid));
    /* No callback: no execution can be accepted and no request is queued. */
    HostToTarget request = HostToTarget_init_zero;
    request.which_cmd = HostToTarget_execute_test_tag;
    request.cmd.execute_test.run_id = 34U;
    size_t ready_slot = TZEN_TH_WORKER_QUEUE_DEPTH;
    assert(tzen_th_control(&request, &ready_slot) == ResultCode_RESULT_ERR_INVALID);
    assert(testharness_state.jobs.count == 0U);
    reset();
}

#ifdef TZEN_TH_TEST_WORKERS_CONCURRENT
static atomic_bool stop;
static void *worker_task(void *arg)
{
    uint8_t id = *(uint8_t *)arg;
    do { tzen_th_worker_main_function(id); sched_yield(); } while (!atomic_load(&stop));
    return NULL;
}

static void concurrent(void)
{
#if TZEN_TH_MAX_WORKERS >= 2U && TZEN_TH_RESULT_QUEUE_DEPTH >= 4U
    reset(); special = 5U; entered = 0U; open_gate = false;
    assert(START(40U) == ResultCode_RESULT_OK && START(41U) == ResultCode_RESULT_OK);
    pthread_t threads[2]; uint8_t ids[2] = {0U, 1U};
    atomic_store(&stop, false);
    assert(pthread_create(&threads[0], NULL, worker_task, &ids[0]) == 0);
    assert(pthread_create(&threads[1], NULL, worker_task, &ids[1]) == 0);
    assert(pthread_mutex_lock(&gate) == 0);
    struct timespec until; assert(clock_gettime(CLOCK_REALTIME, &until) == 0); until.tv_sec += 5;
    while (entered != 2U) assert(pthread_cond_timedwait(&gate_changed, &gate, &until) == 0);
    assert(pthread_mutex_unlock(&gate) == 0);
    /* Both callbacks are simultaneously inside user code, outside queue locks. */
    tzen_th_worker_main_function(0U); /* Overlap on the same ID is ignored. */
    assert(ABORT(40U) == ResultCode_RESULT_OK);
    assert(RELEASE(41U, 0U) == ResultCode_RESULT_ERR_NOT_FOUND);
    assert(command(HostToTarget_get_tests_tag, 0U, 0U) == ResultCode_RESULT_OK);
    assert(pthread_mutex_lock(&gate) == 0);
    open_gate = true;
    assert(pthread_cond_broadcast(&gate_changed) == 0);
    assert(pthread_mutex_unlock(&gate) == 0);
    atomic_store(&stop, true);
    assert(pthread_join(threads[0], NULL) == 0 && pthread_join(threads[1], NULL) == 0);
    tzen_th_main_function();
    assert(calls[40] == 1U && calls[41] == 1U);
    assert(cleanup_status[40] == TZEN_TEST_STATUS_ABORTED && cleanup_status[41] == TZEN_TEST_STATUS_SUCCESS);
    assert(terminals[40] == 1U && terminals[41] == 1U);

    reset(); special = 6U; atomic_store(&stop, false);
    assert(pthread_create(&threads[0], NULL, worker_task, &ids[0]) == 0);
    assert(pthread_create(&threads[1], NULL, worker_task, &ids[1]) == 0);
    uint32_t next = 1U; unsigned finished = 0U;
    time_t deadline = time(NULL) + 10;
    while (finished < 1000U) {
        assert(time(NULL) < deadline);
        if (next <= 1000U) {
            ResultCode status = START(next);
            assert(status == ResultCode_RESULT_OK || status == ResultCode_RESULT_ERR_BUSY);
            if (status == ResultCode_RESULT_OK) ++next;
        }
        tzen_th_main_function();
        finished = 0U;
        for (uint32_t i = 1U; i < next; ++i) finished += terminals[i];
        /* Keep response retries bounded in the capture buffer. */
        used = 0U;
        sched_yield();
    }
    atomic_store(&stop, true);
    assert(pthread_join(threads[0], NULL) == 0 && pthread_join(threads[1], NULL) == 0);
    tzen_th_main_function();
    for (unsigned i = 1U; i <= 1000U; ++i)
        assert(setups[i] == 1U && cleanups[i] == 1U && calls[i] == 3U && terminals[i] == 1U);
    assert(tzen_get_state() == TZEN_ENGINE_IDLE);
#endif
}
#endif

static void independent_logs(void)
{
    reset();
    TzenConfig_t no_sender = config;
    no_sender.send_bytes = NULL;
    assert(tzen_th_init(&no_sender));
    assert(!tzen_emit_log(7U, NULL, TZEN_LOG_INFO, "no sender"));
    reset();
    assert(!tzen_emit_log(TZEN_SOURCE_TEST, NULL, TZEN_LOG_INFO, "invalid"));
    assert(!tzen_emit_log(7U, NULL, (TzenLogLevel_t)99, "invalid"));
    assert(!tzen_emit_log(7U, NULL, TZEN_LOG_INFO, NULL));
    assert(!tzen_emit_log(7U, NULL, TZEN_LOG_INFO,
        "1234567890123456789012345678901234567890123456789012345678901234"));
    assert(tzen_emit_log(7U, NULL, TZEN_LOG_INFO, "global"));
    tzen_th_main_function();
    assert(used == 1U && output[0].payload.log.source == 7U);
    assert(output[0].payload.log.scope == LogEvent_Scope_GLOBAL);
    assert(output[0].payload.log.run_id == 0U && output[0].payload.log.test_index == 0U);
    mode = TZEN_STEP_DONE_PASS;
    assert(START(0U) == ResultCode_RESULT_OK);
    tzen_th_worker_main_function(0U);
    tzen_th_main_function();
    assert(terminals[0] == 1U && tzen_get_state() == TZEN_ENGINE_IDLE);
    /* Reuse the worker: a delayed producer retains only a copied identity. */
    TzenExecutionRef_t original = {0U, 0U};
    assert(START(1U) == ResultCode_RESULT_OK);
    tzen_th_worker_main_function(0U);
    tzen_th_main_function();
    assert(tzen_emit_log(7U, &original, TZEN_LOG_INFO, "late"));
    original.run_id = 99U;
    tzen_th_main_function();
    const LogEvent *late = &output[used - 1U].payload.log;
    assert(late->scope == LogEvent_Scope_EXECUTION && late->run_id == 0U);
    assert(late->source == 7U && late->test_index == 0U);
    /* External messages also honor reserved control-event slots. */
    testharness_state.results.reserved = 2U;
    size_t accepted = 0U;
    while (tzen_emit_log(7U, NULL, TZEN_LOG_INFO, "flood")) ++accepted;
    assert(accepted == TZEN_TH_RESULT_QUEUE_DEPTH - 2U);
    testharness_state.results.reserved = 0U;
    tzen_th_main_function();
    send_ok = false;
    assert(tzen_emit_log(7U, NULL, TZEN_LOG_INFO, "send failure"));
    tzen_th_main_function();
    assert(!tzen_th_transport_ok());
    assert(!tzen_emit_log(7U, NULL, TZEN_LOG_INFO, "rejected"));
    reset();
}

int main(void)
{
#ifdef TZEN_TH_TEST_WORKERS_CONCURRENT
    main_thread = pthread_self();
#endif
    assert(!tzen_emit_log(7U, NULL, TZEN_LOG_INFO, "before init"));
    lifecycle(); synchronization(); queues(); transport_failure(); independent_logs();
#ifdef TZEN_TH_TEST_WORKERS_CONCURRENT
    concurrent();
#endif
    puts("Worker checks passed: lifecycle, routing, FIFO/full queues, reserved returns, logs, cleanup and concurrency.");
    return 0;
}
