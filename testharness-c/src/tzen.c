#include "tzen.h"
#include "ttp.h"
#include <string.h>
#include <stdarg.h>
#include <stdio.h>

_Static_assert(TH_COMMAND_QUEUE_DEPTH > 0, "queue must not be empty");
static th_config_t cfg;
static const th_test_descriptor_t *tests;
static size_t test_count;
static th_context_t ctx;
static th_engine_state_t state;
static bool initialized, tx_ok, sync_requested;
static HostToTarget commands[TH_COMMAND_QUEUE_DEPTH];
static size_t head, tail, count;

static void lock(void) { if (cfg.mutex_lock) cfg.mutex_lock(cfg.user_data); }
static void unlock(void) { if (cfg.mutex_unlock) cfg.mutex_unlock(cfg.user_data); }
static void send_message(const TargetToHost *m)
{
    uint8_t frame[TTP_MAX_FRAME_SIZE];
    size_t size = 0;
    if (Ttp_EncodeTargetToHostFrame(m, frame, sizeof(frame), &size) != TTP_STATUS_OK ||
        !cfg.transport_send(frame, size, cfg.user_data)) tx_ok = false;
}
static void reply(uint32_t seq, ResultCode status)
{
    TargetToHost m = TargetToHost_init_zero;
    m.seq_id = seq; m.status = status; send_message(&m);
}
static TargetToHost event(pb_size_t tag)
{
    TargetToHost m = TargetToHost_init_zero;
    m.which_payload = TargetToHost_test_event_tag;
    m.payload.test_event.run_id = ctx.run_id;
    m.payload.test_event.test_index = ctx.test_index;
    m.payload.test_event.which_event = tag;
    return m;
}
static void finish(th_test_status_t result)
{
    TargetToHost m = event(TestEvent_finished_tag);
    if (tests[ctx.test_index].on_teardown)
        tests[ctx.test_index].on_teardown(&ctx, result);
    state = TH_ENGINE_IDLE;
    sync_requested = false;
    m.payload.test_event.event.finished.status = (TestFinishedEvent_Status)result;
    send_message(&m);
}
bool th_init(const th_config_t *config, const th_test_descriptor_t *table, size_t n)
{
    size_t i, j;
    if (initialized && state != TH_ENGINE_IDLE) return false;
    if (!config || !config->transport_send || (!table && n) || n > UINT32_MAX ||
        (!!config->mutex_lock != !!config->mutex_unlock)) return false;
    for (i = 0; i < n; ++i) {
        if (!table[i].name || strlen(table[i].name) > 31 || !table[i].steps || !table[i].num_steps) return false;
        for (j = 0; j < table[i].num_steps; ++j) if (!table[i].steps[j]) return false;
    }
    cfg = *config; tests = table; test_count = n;
    head = tail = count = 0;
    memset(&ctx, 0, sizeof(ctx)); state = TH_ENGINE_IDLE;
    tx_ok = initialized = true; sync_requested = false;
    return true;
}
bool th_on_rx_frame(const uint8_t *body, size_t len)
{
    HostToTarget command = HostToTarget_init_zero;
    bool accepted = false;
    if (!initialized || len > TTP_MAX_FRAME_SIZE - 2 ||
        Ttp_DecodeHostToTargetFrame(&command, body, len) != TTP_STATUS_OK || !command.seq_id) return false;
    lock();
    if (count < TH_COMMAND_QUEUE_DEPTH) {
        commands[tail] = command; tail = (tail + 1) % TH_COMMAND_QUEUE_DEPTH; ++count;
        accepted = true;
    }
    unlock();
    if (accepted && cfg.notify_worker) cfg.notify_worker(cfg.user_data);
    return accepted;
}
static bool pop(HostToTarget *command)
{
    bool available = false;
    lock();
    if (count) {
        *command = commands[head]; head = (head + 1) % TH_COMMAND_QUEUE_DEPTH; --count;
        available = true;
    }
    unlock(); return available;
}
static void advance(void)
{
    ++ctx.current_step; ctx.step_Iterations = 0; sync_requested = false;
    if (ctx.current_step >= tests[ctx.test_index].num_steps) finish(TH_TEST_STATUS_SUCCESS);
    else state = TH_ENGINE_RUNNING_STEP;
}
static void handle(const HostToTarget *command)
{
    TargetToHost m = TargetToHost_init_zero;
    uint32_t seq = command->seq_id, index;
    m.seq_id = seq;
    switch (command->which_cmd) {
    case HostToTarget_get_tests_tag:
        m.which_payload = TargetToHost_tests_count_tag;
        m.payload.tests_count.total_tests = (uint32_t)test_count; send_message(&m); break;
    case HostToTarget_get_test_info_tag:
        index = command->cmd.get_test_info.index;
        if (index >= test_count) { reply(seq, ResultCode_RESULT_ERR_INDEX); break; }
        m.which_payload = TargetToHost_test_info_tag;
        m.payload.test_info.index = index;
        m.payload.test_info.total_steps = tests[index].num_steps;
        memcpy(m.payload.test_info.name, tests[index].name, strlen(tests[index].name) + 1);
        send_message(&m); break;
    case HostToTarget_execute_test_tag:
        if (state != TH_ENGINE_IDLE) { reply(seq, ResultCode_RESULT_ERR_BUSY); break; }
        index = command->cmd.execute_test.index;
        if (index >= test_count) { reply(seq, ResultCode_RESULT_ERR_INDEX); break; }
        if (!tx_ok) { reply(seq, ResultCode_RESULT_ERR_INVALID); break; }
        memset(&ctx, 0, sizeof(ctx)); ctx.run_id = command->cmd.execute_test.run_id;
        ctx.test_index = index; sync_requested = false; state = TH_ENGINE_RUNNING_STEP;
        reply(seq, ResultCode_RESULT_OK);
        if (!tx_ok) finish(TH_TEST_STATUS_ABORTED);
        else if (tests[index].on_setup && !tests[index].on_setup(&ctx)) finish(TH_TEST_STATUS_FAIL);
        break;
    case HostToTarget_abort_test_tag:
        if (state == TH_ENGINE_IDLE || command->cmd.abort_test.run_id != ctx.run_id) {
            reply(seq, ResultCode_RESULT_ERR_NOT_FOUND); break;
        }
        reply(seq, ResultCode_RESULT_OK); finish(TH_TEST_STATUS_ABORTED); break;
    case HostToTarget_sync_release_tag:
        if (state != TH_ENGINE_WAITING_SYNC || command->cmd.sync_release.run_id != ctx.run_id ||
            command->cmd.sync_release.sync_id != ctx.pending_sync_id) {
            reply(seq, ResultCode_RESULT_ERR_NOT_FOUND); break;
        }
        reply(seq, ResultCode_RESULT_OK);
        if (!tx_ok) finish(TH_TEST_STATUS_ABORTED); else advance();
        break;
    default: reply(seq, ResultCode_RESULT_ERR_INVALID); break;
    }
}
void th_poll(void)
{
    HostToTarget command;
    size_t budget = TH_COMMAND_QUEUE_DEPTH;
    th_step_result_t result;
    if (!initialized) return;
    while (budget-- && pop(&command)) handle(&command);
    if (state != TH_ENGINE_IDLE && !tx_ok) { finish(TH_TEST_STATUS_ABORTED); return; }
    if (state != TH_ENGINE_RUNNING_STEP) return;
    result = tests[ctx.test_index].steps[ctx.current_step](&ctx);
    if (!tx_ok) { finish(TH_TEST_STATUS_ABORTED); return; }
    if (sync_requested && result != TH_STEP_WAIT_SYNC) {
        finish(TH_TEST_STATUS_FAIL); return;
    }
    switch (result) {
    case TH_STEP_PASS_NEXT: advance(); break;
    case TH_STEP_WAIT_SYNC:
        if (sync_requested) state = TH_ENGINE_WAITING_SYNC;
        else finish(TH_TEST_STATUS_FAIL);
        break;
    case TH_STEP_YIELD:
        if (sync_requested) finish(TH_TEST_STATUS_FAIL);
        else if (ctx.step_Iterations != UINT32_MAX) ++ctx.step_Iterations;
        break;
    case TH_STEP_DONE_PASS: finish(TH_TEST_STATUS_SUCCESS); break;
    default: finish(TH_TEST_STATUS_FAIL); break;
    }
}
th_engine_state_t th_get_state(void) { return state; }
bool th_transport_ok(void) { return initialized && tx_ok; }
void th_report_step(th_context_t *context, bool success, const char *description)
{
    TargetToHost m;
    if (!initialized || context != &ctx || state == TH_ENGINE_IDLE) return;
    m = event(TestEvent_step_tag);
    m.payload.test_event.event.step.step_number = ctx.current_step + 1;
    m.payload.test_event.event.step.success = success;
    snprintf(m.payload.test_event.event.step.description,
        sizeof(m.payload.test_event.event.step.description), "%s", description ? description : "");
    send_message(&m);
}
void th_request_sync(th_context_t *context, uint32_t sync_id)
{
    TargetToHost m;
    if (!initialized || context != &ctx || state != TH_ENGINE_RUNNING_STEP || sync_requested) return;
    ctx.pending_sync_id = sync_id; sync_requested = true;
    m = event(TestEvent_sync_tag); m.payload.test_event.event.sync.sync_id = sync_id; send_message(&m);
}
void th_log(th_context_t *context, th_log_level_t level, const char *text)
{
    TargetToHost m = TargetToHost_init_zero;
    (void)context;
    if (!initialized) return;
    m.which_payload = TargetToHost_log_tag; m.payload.log.level = (LogEvent_Level)level;
    snprintf(m.payload.log.message, sizeof(m.payload.log.message), "%s", text ? text : "");
    send_message(&m);
}
void th_logf(th_context_t *context, th_log_level_t level, const char *fmt, ...)
{
    char text[64]; va_list args;
    if (!fmt) return;
    va_start(args, fmt); vsnprintf(text, sizeof(text), fmt, args); va_end(args);
    th_log(context, level, text);
}
