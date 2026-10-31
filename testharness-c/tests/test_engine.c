#include "tzen.h"
#include "ttp.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

static TargetToHost output[128];
static size_t used;
static unsigned int setup_calls, teardown_calls, step_calls;
static th_test_status_t cleanup_status;
static bool send_ok = true, setup_ok = true;
static th_step_result_t mode = TH_STEP_PASS_NEXT;
static bool send_frame(const uint8_t *frame, size_t len, void *user)
{
    (void)user;
    if (!send_ok) return false;
    assert(used < 128);
    assert(Ttp_DecodeTargetToHostFrame(&output[used++], frame + 1, len - 2) == TTP_STATUS_OK);
    return true;
}
static bool setup(th_context_t *ctx)
{
    size_t i;
    ++setup_calls;
    assert(ctx->current_step == 0 && ctx->step_Iterations == 0 && ctx->ext_vm_ctx == NULL);
    for (i=0; i < sizeof(ctx->scratchpad); ++i) assert(ctx->scratchpad[i] == 0);
    ctx->scratchpad[0] = 77;
    return setup_ok;
}
static void cleanup(th_context_t *ctx, th_test_status_t status)
{
    assert(ctx->scratchpad[0] == 77); ++teardown_calls; cleanup_status = status;
}
static th_step_result_t step(th_context_t *ctx)
{
    ++step_calls;
    assert(ctx->scratchpad[0] == 77);
    th_report_step(ctx, mode != TH_STEP_FAIL, "step");
    if (mode == TH_STEP_WAIT_SYNC) th_request_sync(ctx, 0); /* zero is a valid sync ID */
    return mode;
}
static const th_step_fn_t steps[] = {step, step};
static const th_test_descriptor_t table[] = {TH_TEST_ENTRY("native", steps, setup, cleanup)};
static th_config_t config;
static uint32_t seq = 1;
static void init(void)
{
    config.transport_send = send_frame;
    assert(th_init(&config, table, 1));
    used = setup_calls = teardown_calls = step_calls = 0;
}
static void enqueue(HostToTarget *command)
{
    uint8_t frame[TTP_MAX_FRAME_SIZE]; size_t size;
    command->seq_id = seq++;
    assert(Ttp_EncodeHostToTargetFrame(command, frame, sizeof(frame), &size) == TTP_STATUS_OK);
    assert(th_on_rx_frame(frame+1, size-2));
}
static void start(void)
{
    HostToTarget m = HostToTarget_init_zero;
    m.which_cmd = HostToTarget_execute_test_tag; m.cmd.execute_test.run_id = 7;
    enqueue(&m); th_poll();
}
static void abort_run(void)
{
    HostToTarget m = HostToTarget_init_zero;
    m.which_cmd = HostToTarget_abort_test_tag; m.cmd.abort_test.run_id = 7;
    enqueue(&m); th_poll();
}
int main(void)
{
    HostToTarget m = HostToTarget_init_zero;
    uint8_t frame[TTP_MAX_FRAME_SIZE]; size_t size, i;
    init(); start();
    assert(step_calls == 1 && th_get_state() == TH_ENGINE_RUNNING_STEP);
    th_poll(); assert(teardown_calls == 1 && cleanup_status == TH_TEST_STATUS_SUCCESS);
    th_poll(); assert(teardown_calls == 1);
    assert(output[used-1].payload.test_event.event.finished.status == TestFinishedEvent_Status_SUCCESS);
    init(); mode = TH_STEP_YIELD; start(); th_poll(); assert(step_calls == 2);
    abort_run(); assert(step_calls == 2 && teardown_calls == 1 && cleanup_status == TH_TEST_STATUS_ABORTED);
    init(); mode = TH_STEP_FAIL; start(); assert(teardown_calls == 1 && cleanup_status == TH_TEST_STATUS_FAIL);
    init(); mode = TH_STEP_DONE_PASS; start(); assert(step_calls == 1 && cleanup_status == TH_TEST_STATUS_SUCCESS);
    init(); setup_ok = false; start(); assert(step_calls == 0 && teardown_calls == 1 && cleanup_status == TH_TEST_STATUS_FAIL);
    setup_ok = true;
    init(); mode = TH_STEP_WAIT_SYNC; start(); assert(th_get_state() == TH_ENGINE_WAITING_SYNC);
    assert(!th_init(&config, table, 1));
    m.which_cmd = HostToTarget_sync_release_tag; m.cmd.sync_release.run_id = 7; m.cmd.sync_release.sync_id = 9;
    enqueue(&m); th_poll(); assert(output[used-1].status == ResultCode_RESULT_ERR_NOT_FOUND);
    mode = TH_STEP_PASS_NEXT;
    m.cmd.sync_release.sync_id = 0; enqueue(&m); th_poll();
    assert(teardown_calls == 1 && cleanup_status == TH_TEST_STATUS_SUCCESS);
    init(); mode = TH_STEP_YIELD; start(); send_ok = false; th_poll();
    assert(th_get_state() == TH_ENGINE_IDLE && teardown_calls == 1 && cleanup_status == TH_TEST_STATUS_ABORTED);
    assert(!th_transport_ok()); send_ok = true;
    init(); m.which_cmd = HostToTarget_get_tests_tag;
    for (i=0; i < TH_COMMAND_QUEUE_DEPTH; ++i) enqueue(&m);
    m.seq_id = seq++;
    assert(Ttp_EncodeHostToTargetFrame(&m, frame, sizeof(frame), &size) == TTP_STATUS_OK);
    assert(!th_on_rx_frame(frame+1, size-2)); th_poll();
    assert(used == TH_COMMAND_QUEUE_DEPTH);
    frame[size-2] ^= 1;
    assert(!th_on_rx_frame(frame+1, size-2));
    assert(!th_init(NULL, table, 1));
    config.mutex_lock = (void (*)(void *))1;
    assert(!th_init(&config, table, 1)); config.mutex_lock = NULL;
    puts("PASS: setup, teardown, scratchpad, one-step polling, yield, fail, early success, sync, abort, TX failure, queue, CRC");
    return 0;
}
