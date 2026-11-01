#include "tzen.h"
#include "ttp.h"
#include <string.h>
#include <stdarg.h>
#include <stdio.h>

/* AVR has atomic byte loads/stores but its GCC does not advertise C11
 * lock-free atomics. On this single-core target compiler barriers provide
 * acquire/release ordering between the sole ISR producer and main consumer. */
#if defined(__AVR__)
typedef volatile uint8_t AtomicByte;
static uint8_t load_byte(const AtomicByte *p)
{
    uint8_t value = *p;
    __asm__ __volatile__("" ::: "memory");
    return value;
}
static void store_byte(AtomicByte *p, uint8_t value)
{
    __asm__ __volatile__("" ::: "memory");
    *p = value;
}
#else
#include <stdatomic.h>
_Static_assert(ATOMIC_CHAR_LOCK_FREE == 2, "ISR RX requires lock-free byte atomics");
typedef atomic_uchar AtomicByte;
static uint8_t load_byte(const AtomicByte *p)
{
    return atomic_load_explicit(p, memory_order_acquire);
}
static void store_byte(AtomicByte *p, uint8_t value)
{
    atomic_store_explicit(p, value, memory_order_release);
}
#endif
_Static_assert(TZEN_TH_RX_SLOTS >= 2 && TZEN_TH_RX_SLOTS <= 256, "RX slots: 2..256");
_Static_assert(TZEN_TH_MAX_WORKERS > 0 && TZEN_TH_MAX_WORKERS <= 256, "workers: 1..256");
_Static_assert(TZEN_TH_WORKER_QUEUE_DEPTH > 0, "worker queue must not be empty");
_Static_assert(TZEN_TH_MAX_PACKET_SIZE >= TTP_MAX_FRAME_PAYLOAD_SIZE, "RX packet storage too small");

static TzenConfig_t cfg;
static const TzenTestDescriptor_t *tests;
static size_t test_count;
static bool initialized;
static AtomicByte tx_failed;
static struct {
    struct { uint8_t data[TZEN_TH_MAX_PACKET_SIZE]; size_t len; } slots[TZEN_TH_RX_SLOTS];
    AtomicByte write_idx, read_idx;
    uint8_t code, remaining;
    size_t pos;
    bool drop;
} rx;
typedef struct { uint32_t run_id, test_index; } Job;
static Job jobs[TZEN_TH_WORKER_QUEUE_DEPTH];
static size_t job_count;
typedef struct {
    TzenContext_t ctx;
    TzenEngineState_t state;
    bool active, busy, started, finishing, abort_requested, release_requested, sync_requested;
} Worker;
static Worker workers[TZEN_TH_MAX_WORKERS];

static void lock(void) { if (cfg.mutex_lock) cfg.mutex_lock(cfg.user_data); }
static void unlock(void) { if (cfg.mutex_unlock) cfg.mutex_unlock(cfg.user_data); }
bool tzen_th_transport_ok(void) { return initialized && !load_byte(&tx_failed); }
static void send_locked(const TargetToHost *m)
{
    uint8_t frame[TTP_MAX_FRAME_SIZE];
    size_t size = 0;
    if (Ttp_EncodeTargetToHostFrame(m, frame, sizeof(frame), &size) != TTP_STATUS_OK ||
        !cfg.transport_send(frame, size, cfg.user_data))
        store_byte(&tx_failed, 1);
}
static void send_message(const TargetToHost *m)
{
    lock(); send_locked(m); unlock();
    if (!tzen_th_transport_ok() && cfg.notify_worker) cfg.notify_worker(cfg.user_data);
}
static void reply(uint32_t seq, ResultCode status)
{
    TargetToHost m = TargetToHost_init_zero;
    m.seq_id = seq; m.status = status; send_message(&m);
}
static TargetToHost event(const TzenContext_t *ctx, pb_size_t tag)
{
    TargetToHost m = TargetToHost_init_zero;
    m.which_payload = TargetToHost_test_event_tag;
    m.payload.test_event.run_id = ctx->run_id;
    m.payload.test_event.test_index = ctx->test_index;
    m.payload.test_event.which_event = tag;
    return m;
}
static bool report_step(Worker *w, bool success)
{
    TargetToHost m = event(&w->ctx, TestEvent_step_tag);
    m.payload.test_event.event.step.step_number = w->ctx.current_step + 1;
    m.payload.test_event.event.step.success = success;
    send_message(&m);
    return tzen_th_transport_ok();
}
static void finish(Worker *w, TzenTestStatus_t result)
{
    TargetToHost m = event(&w->ctx, TestEvent_finished_tag);
    lock();
    if (w->abort_requested || !tzen_th_transport_ok()) result = TZEN_TEST_STATUS_ABORTED;
    w->finishing = true; unlock();
    if (w->started && tests[w->ctx.test_index].on_teardown)
        tests[w->ctx.test_index].on_teardown(&w->ctx, result);
    m.payload.test_event.event.finished.status = (TestFinishedEvent_Status)result;
    send_message(&m);
    lock();
    w->active = w->started = false;
    w->state = TZEN_ENGINE_IDLE;
    w->sync_requested = w->abort_requested = w->release_requested = false;
    w->finishing = false;
    unlock();
}
static void fail_step(Worker *w)
{
    finish(w, report_step(w, false) ? TZEN_TEST_STATUS_FAIL : TZEN_TEST_STATUS_ABORTED);
}
static void advance(Worker *w)
{
    ++w->ctx.current_step; w->ctx.step_Iterations = 0;
    lock(); w->sync_requested = false; w->state = TZEN_ENGINE_RUNNING_STEP; unlock();
    if (w->ctx.current_step >= tests[w->ctx.test_index].num_steps)
        finish(w, TZEN_TEST_STATUS_SUCCESS);
}
bool tzen_th_init(const TzenConfig_t *config, const TzenTestDescriptor_t *table, size_t n)
{
    size_t i, j;
    /* Init/reinit requires the producer and all task callers to be quiescent. */
    if (initialized) {
        if (job_count) return false;
        for (i = 0; i < TZEN_TH_MAX_WORKERS; ++i)
            if (workers[i].active || workers[i].busy) return false;
    }
    if (!config || !config->transport_send || (!table && n) || n > UINT32_MAX ||
        (!!config->mutex_lock != !!config->mutex_unlock)) return false;
    for (i = 0; i < n; ++i) {
        if (!table[i].name || strlen(table[i].name) > 31 || !table[i].steps || !table[i].num_steps)
            return false;
        for (j = 0; j < table[i].num_steps; ++j) if (!table[i].steps[j]) return false;
    }
    cfg = *config; tests = table; test_count = n; job_count = 0;
    memset(workers, 0, sizeof(workers));
    store_byte(&rx.write_idx, 0); store_byte(&rx.read_idx, 0);
    rx.code = 0xFF; rx.remaining = 0; rx.pos = 0; rx.drop = false;
    store_byte(&tx_failed, 0); initialized = true;
    return true;
}
static void rx_append(uint8_t index, uint8_t byte)
{
    if (rx.pos < TZEN_TH_MAX_PACKET_SIZE) rx.slots[index].data[rx.pos++] = byte;
    else rx.drop = true;
}
void tzen_th_feed_b(uint8_t byte)
{
    uint8_t write, next;
    if (!initialized) return;
    write = load_byte(&rx.write_idx);
    if (!byte) {
        next = (uint8_t)((write + 1U) % TZEN_TH_RX_SLOTS);
        if (!rx.drop && rx.pos && !rx.remaining &&
            next != load_byte(&rx.read_idx)) {
            rx.slots[write].len = rx.pos;
            store_byte(&rx.write_idx, next);
            if (cfg.notify_main_from_isr) cfg.notify_main_from_isr(cfg.user_data);
        }
        rx.code = 0xFF; rx.remaining = 0; rx.pos = 0; rx.drop = false;
        return;
    }
    if (rx.drop) return;
    /* The unpublished slot is always reserved for the producer, even when full. */
    if (rx.remaining) {
        rx_append(write, byte); --rx.remaining;
    } else {
        if (rx.code != 0xFF) rx_append(write, 0);
        rx.code = byte; rx.remaining = (uint8_t)(byte - 1U);
    }
}
/* Caller holds the task mutex. Run IDs remain reserved until terminal events. */
static Worker *find_worker(uint32_t run_id)
{
    size_t i;
    for (i = 0; i < TZEN_TH_MAX_WORKERS; ++i)
        if (workers[i].active && workers[i].ctx.run_id == run_id) return &workers[i];
    return NULL;
}
static void handle(const HostToTarget *c)
{
    TargetToHost m = TargetToHost_init_zero;
    ResultCode status = ResultCode_RESULT_OK;
    Worker *w;
    size_t i;
    bool notify = false, cancelled = false;
    Job job = {0, 0};
    uint32_t index;
    m.seq_id = c->seq_id;
    switch (c->which_cmd) {
    case HostToTarget_get_tests_tag:
        m.which_payload = TargetToHost_tests_count_tag;
        m.payload.tests_count.total_tests = (uint32_t)test_count; send_message(&m); return;
    case HostToTarget_get_test_info_tag:
        index = c->cmd.get_test_info.index;
        if (index >= test_count) { reply(c->seq_id, ResultCode_RESULT_ERR_INDEX); return; }
        m.which_payload = TargetToHost_test_info_tag;
        m.payload.test_info.index = index;
        m.payload.test_info.total_steps = tests[index].num_steps;
        memcpy(m.payload.test_info.name, tests[index].name, strlen(tests[index].name) + 1);
        send_message(&m); return;
    case HostToTarget_execute_test_tag:
        job.run_id = c->cmd.execute_test.run_id; job.test_index = c->cmd.execute_test.index;
        lock();
        if (!tzen_th_transport_ok()) status = ResultCode_RESULT_ERR_INVALID;
        else if (find_worker(job.run_id) || job_count == TZEN_TH_WORKER_QUEUE_DEPTH)
            status = ResultCode_RESULT_ERR_BUSY;
        else if (job.test_index >= test_count) status = ResultCode_RESULT_ERR_INDEX;
        for (i = 0; i < job_count; ++i)
            if (jobs[i].run_id == job.run_id) status = ResultCode_RESULT_ERR_BUSY;
        /* Publish after acceptance reply so a worker cannot emit events first. */
        unlock();
        reply(c->seq_id, status);
        if (status == ResultCode_RESULT_OK) {
            lock(); jobs[job_count++] = job; unlock(); notify = true;
        }
        break;
    case HostToTarget_abort_test_tag:
        lock(); w = find_worker(c->cmd.abort_test.run_id);
        if (w && !w->finishing && !w->abort_requested) { w->abort_requested = true; notify = true; }
        else {
            status = ResultCode_RESULT_ERR_NOT_FOUND;
            for (i = 0; i < job_count; ++i) if (jobs[i].run_id == c->cmd.abort_test.run_id) {
                job = jobs[i];
                memmove(jobs + i, jobs + i + 1, (job_count - i - 1) * sizeof(*jobs));
                --job_count; cancelled = true; status = ResultCode_RESULT_OK; break;
            }
        }
        m.status = status; send_locked(&m); unlock();
        if (cancelled) {
            TzenContext_t context = {0};
            context.run_id = job.run_id; context.test_index = job.test_index;
            m = event(&context, TestEvent_finished_tag);
            m.payload.test_event.event.finished.status = TestFinishedEvent_Status_ABORTED;
            send_message(&m);
        }
        break;
    case HostToTarget_sync_release_tag:
        lock(); w = find_worker(c->cmd.sync_release.run_id);
        if (!w || w->finishing || w->abort_requested || !w->sync_requested || w->release_requested ||
            w->ctx.pending_sync_id != c->cmd.sync_release.sync_id)
            status = ResultCode_RESULT_ERR_NOT_FOUND;
        else { w->release_requested = true; notify = true; }
        m.status = status; send_locked(&m); unlock(); break;
    default: reply(c->seq_id, ResultCode_RESULT_ERR_INVALID); break;
    }
    if ((notify || !tzen_th_transport_ok()) && cfg.notify_worker) cfg.notify_worker(cfg.user_data);
}
void tzen_th_main_function(void)
{
    size_t budget = TZEN_TH_RX_SLOTS - 1U;
    uint8_t read;
    if (!initialized) return;
    while (budget--) {
        HostToTarget command = HostToTarget_init_zero;
        bool valid;
        read = load_byte(&rx.read_idx);
        if (read == load_byte(&rx.write_idx)) break;
        valid = Ttp_DecodeHostToTargetPayload(&command, rx.slots[read].data,
                    rx.slots[read].len) == TTP_STATUS_OK && command.seq_id;
        store_byte(&rx.read_idx, (uint8_t)((read + 1U) % TZEN_TH_RX_SLOTS));
        if (valid) handle(&command);
    }
}
void tzen_th_worker_main_function(uint8_t worker_id)
{
    Worker *w;
    bool starting = false, aborting, released;
    TzenStepResult_t result;
    if (!initialized || worker_id >= TZEN_TH_MAX_WORKERS) return;
    w = &workers[worker_id];
    lock();
    if (w->busy) { unlock(); return; }
    w->busy = true;
    if (!w->active && job_count) {
        memset(&w->ctx, 0, sizeof(w->ctx));
        w->ctx.run_id = jobs[0].run_id; w->ctx.test_index = jobs[0].test_index;
        --job_count; memmove(jobs, jobs + 1, job_count * sizeof(*jobs));
        w->active = true; w->state = TZEN_ENGINE_RUNNING_STEP; starting = true;
    }
    aborting = w->abort_requested;
    released = w->release_requested; w->release_requested = false;
    unlock();
    if (!w->active) goto done;
    if (aborting || !tzen_th_transport_ok()) { finish(w, TZEN_TEST_STATUS_ABORTED); goto done; }
    if (starting) w->started = true;
    if (starting && tests[w->ctx.test_index].on_setup && !tests[w->ctx.test_index].on_setup(&w->ctx)) {
        finish(w, tzen_th_transport_ok() ? TZEN_TEST_STATUS_FAIL : TZEN_TEST_STATUS_ABORTED); goto done;
    }
    lock(); aborting = w->abort_requested; unlock();
    if (aborting || !tzen_th_transport_ok()) { finish(w, TZEN_TEST_STATUS_ABORTED); goto done; }
    if (released) {
        if (report_step(w, true)) advance(w); else finish(w, TZEN_TEST_STATUS_ABORTED);
        if (!w->active) goto done;
    }
    if (w->state != TZEN_ENGINE_RUNNING_STEP) goto done;
    result = tests[w->ctx.test_index].steps[w->ctx.current_step](&w->ctx);
    lock(); aborting = w->abort_requested; unlock();
    if (aborting || !tzen_th_transport_ok()) { finish(w, TZEN_TEST_STATUS_ABORTED); goto done; }
    if (w->sync_requested && result != TZEN_STEP_WAIT_SYNC) { fail_step(w); goto done; }
    switch (result) {
    case TZEN_STEP_PASS_NEXT:
        if (report_step(w, true)) advance(w); else finish(w, TZEN_TEST_STATUS_ABORTED);
        break;
    case TZEN_STEP_WAIT_SYNC:
        if (w->sync_requested) { lock(); w->state = TZEN_ENGINE_WAITING_SYNC; unlock(); }
        else fail_step(w);
        break;
    case TZEN_STEP_YIELD:
        if (w->ctx.step_Iterations != UINT32_MAX) ++w->ctx.step_Iterations;
        break;
    case TZEN_STEP_DONE_PASS:
        finish(w, report_step(w, true) ? TZEN_TEST_STATUS_SUCCESS : TZEN_TEST_STATUS_ABORTED); break;
    default: fail_step(w); break;
    }
done:
    lock(); w->busy = false; unlock();
}
TzenEngineState_t tzen_th_worker_get_state(uint8_t worker_id)
{
    TzenEngineState_t state = TZEN_ENGINE_IDLE;
    if (!initialized || worker_id >= TZEN_TH_MAX_WORKERS) return state;
    lock();
    state = workers[worker_id].state;
    if ((workers[worker_id].active && !tzen_th_transport_ok()) ||
        workers[worker_id].abort_requested || workers[worker_id].release_requested ||
        (!workers[worker_id].active && job_count)) state = TZEN_ENGINE_RUNNING_STEP;
    unlock(); return state;
}
TzenEngineState_t tzen_get_state(void)
{
    size_t i;
    TzenEngineState_t state = TZEN_ENGINE_IDLE;
    if (!initialized) return state;
    lock();
    if (job_count) state = TZEN_ENGINE_RUNNING_STEP;
    for (i = 0; i < TZEN_TH_MAX_WORKERS; ++i) {
        if (workers[i].active && !tzen_th_transport_ok()) { state = TZEN_ENGINE_RUNNING_STEP; break; }
        if (workers[i].state == TZEN_ENGINE_RUNNING_STEP) { state = TZEN_ENGINE_RUNNING_STEP; break; }
        if (workers[i].state == TZEN_ENGINE_WAITING_SYNC && state == TZEN_ENGINE_IDLE)
            state = TZEN_ENGINE_WAITING_SYNC;
        if (workers[i].abort_requested || workers[i].release_requested) { state = TZEN_ENGINE_RUNNING_STEP; break; }
    }
    unlock(); return state;
}
void tzen_sync(TzenContext_t *context, uint32_t sync_id)
{
    TargetToHost m;
    size_t i;
    if (!initialized) return;
    lock();
    for (i = 0; i < TZEN_TH_MAX_WORKERS; ++i) {
        Worker *w = &workers[i];
        if (context == &w->ctx && w->active && w->busy && !w->finishing &&
            w->state == TZEN_ENGINE_RUNNING_STEP && !w->sync_requested) {
            context->pending_sync_id = sync_id; w->sync_requested = true;
            unlock();
            m = event(context, TestEvent_sync_tag);
            m.payload.test_event.event.sync.sync_id = sync_id; send_message(&m); return;
        }
    }
    unlock();
}
void tzen_log(TzenContext_t *context, TzenLogLevel_t level, const char *text)
{
    TargetToHost m = TargetToHost_init_zero;
    (void)context;
    if (!initialized) return;
    m.which_payload = TargetToHost_log_tag;
    m.payload.log.level = (LogEvent_Level)level;
    snprintf(m.payload.log.message, sizeof(m.payload.log.message), "%s", text ? text : "");
    send_message(&m);
}
void tzen_logf(TzenContext_t *context, TzenLogLevel_t level, const char *fmt, ...)
{
    char text[64]; va_list args;
    if (!fmt) return;
    va_start(args, fmt); vsnprintf(text, sizeof(text), fmt, args); va_end(args);
    tzen_log(context, level, text);
}
