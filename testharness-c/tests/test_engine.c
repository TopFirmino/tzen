#include "tzen.h"
#include "ttp.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

static TargetToHost output[128];
static size_t used;
static unsigned int setup_calls, teardown_calls, step_calls;
static TzenTestStatus_t cleanup_status;
static bool send_ok = true, setup_ok = true;
static TzenStepResult_t mode = TZEN_STEP_PASS_NEXT;
static bool send_frame(const uint8_t *frame, size_t len, void *user)
{
    (void)user;
    if (!send_ok) return false;
    assert(used < 128);
    assert(Ttp_DecodeTargetToHostFrame(&output[used++], frame + 1, len - 2) == TTP_STATUS_OK);
    return true;
}
static bool setup(TzenContext_t *ctx)
{
    size_t i;
    ++setup_calls;
    assert(ctx->current_step == 0 && ctx->step_Iterations == 0 && ctx->ext_vm_ctx == NULL);
    for (i=0; i < sizeof(ctx->scratchpad); ++i) assert(ctx->scratchpad[i] == 0);
    ctx->scratchpad[0] = 77;
    return setup_ok;
}
static void cleanup(TzenContext_t *ctx, TzenTestStatus_t status)
{
    assert(ctx->scratchpad[0] == 77); ++teardown_calls; cleanup_status = status;
}
static TzenStepResult_t step(TzenContext_t *ctx)
{
    ++step_calls;
    assert(ctx->scratchpad[0] == 77);
    if (mode == TZEN_STEP_WAIT_SYNC) tzen_sync(ctx, 0); /* zero is a valid sync ID */
    return mode;
}
static const TzenStepFn_t steps[] = {step, step};
static const TzenTestDescriptor_t table[] = {TZEN_TEST_ENTRY("native", steps, setup, cleanup)};
static TzenConfig_t config;
static uint32_t seq = 1;
static void init(void)
{
    config.transport_send = send_frame;
    assert(tzen_th_init(&config, table, 1));
    used = setup_calls = teardown_calls = step_calls = 0;
}
static void poll(void) { tzen_th_main_function(); tzen_th_worker_main_function(0); }
static void enqueue(HostToTarget *command)
{
    uint8_t frame[TTP_MAX_FRAME_SIZE]; size_t size;
    command->seq_id = seq++;
    assert(Ttp_EncodeHostToTargetFrame(command, frame, sizeof(frame), &size) == TTP_STATUS_OK);
    for (size_t i = 0; i < size; ++i) tzen_th_feed_b(frame[i]);
}
static void start(void)
{
    HostToTarget m = HostToTarget_init_zero;
    m.which_cmd = HostToTarget_execute_test_tag; m.cmd.execute_test.run_id = 7;
    enqueue(&m); poll();
}
static void abort_run(void)
{
    HostToTarget m = HostToTarget_init_zero;
    m.which_cmd = HostToTarget_abort_test_tag; m.cmd.abort_test.run_id = 7;
    enqueue(&m); poll();
}
static size_t step_reports(void)
{
    size_t i, n = 0;
    for (i = 0; i < used; ++i)
        if (output[i].which_payload == TargetToHost_test_event_tag &&
            output[i].payload.test_event.which_event == TestEvent_step_tag) ++n;
    return n;
}
int main(void)
{
    HostToTarget m = HostToTarget_init_zero;
    uint8_t frame[TTP_MAX_FRAME_SIZE]; size_t size, i;
    init(); start();
    assert(step_calls == 1 && tzen_get_state() == TZEN_ENGINE_RUNNING_STEP);
    assert(step_reports() == 1 && output[1].payload.test_event.event.step.step_number == 1);
    assert(output[1].payload.test_event.event.step.success);
    poll(); assert(teardown_calls == 1 && cleanup_status == TZEN_TEST_STATUS_SUCCESS);
    poll(); assert(teardown_calls == 1);
    assert(step_reports() == 2 && output[2].payload.test_event.event.step.step_number == 2);
    assert(output[used-1].payload.test_event.event.finished.status == TestFinishedEvent_Status_SUCCESS);
    init(); mode = TZEN_STEP_YIELD; start(); poll(); assert(step_calls == 2);
    assert(step_reports() == 0);
    abort_run(); assert(step_calls == 2 && teardown_calls == 1 && cleanup_status == TZEN_TEST_STATUS_ABORTED);
    assert(step_reports() == 0);
    init(); mode = TZEN_STEP_FAIL; start(); assert(teardown_calls == 1 && cleanup_status == TZEN_TEST_STATUS_FAIL);
    assert(step_reports() == 1 && !output[1].payload.test_event.event.step.success);
    init(); mode = TZEN_STEP_DONE_PASS; start(); assert(step_calls == 1 && cleanup_status == TZEN_TEST_STATUS_SUCCESS);
    assert(step_reports() == 1);
    init(); setup_ok = false; start(); assert(step_calls == 0 && teardown_calls == 1 && cleanup_status == TZEN_TEST_STATUS_FAIL);
    assert(step_reports() == 0);
    setup_ok = true;
    init(); mode = TZEN_STEP_WAIT_SYNC; start(); assert(tzen_get_state() == TZEN_ENGINE_WAITING_SYNC);
    assert(step_reports() == 0);
    assert(!tzen_th_init(&config, table, 1));
    m.which_cmd = HostToTarget_sync_release_tag; m.cmd.sync_release.run_id = 7; m.cmd.sync_release.sync_id = 9;
    enqueue(&m); poll(); assert(output[used-1].status == ResultCode_RESULT_ERR_NOT_FOUND);
    assert(step_reports() == 0);
    mode = TZEN_STEP_PASS_NEXT;
    m.cmd.sync_release.sync_id = 0; enqueue(&m); poll();
    assert(teardown_calls == 1 && cleanup_status == TZEN_TEST_STATUS_SUCCESS);
    assert(step_reports() == 2);
    init(); mode = TZEN_STEP_YIELD; start(); mode = TZEN_STEP_PASS_NEXT; send_ok = false; poll();
    assert(tzen_get_state() == TZEN_ENGINE_IDLE && teardown_calls == 1 && cleanup_status == TZEN_TEST_STATUS_ABORTED);
    assert(!tzen_th_transport_ok()); send_ok = true;
    init(); m.which_cmd = HostToTarget_get_tests_tag;
    for (i=0; i < (TZEN_TH_RX_SLOTS - 1U); ++i) enqueue(&m);
    m.seq_id = seq++;
    assert(Ttp_EncodeHostToTargetFrame(&m, frame, sizeof(frame), &size) == TTP_STATUS_OK);
    for (i=0; i < size; ++i) tzen_th_feed_b(frame[i]);
    poll();
    assert(used == (TZEN_TH_RX_SLOTS - 1U));
    frame[size-2] ^= 1;
    for (i=0; i < size; ++i) tzen_th_feed_b(frame[i]);
    poll(); assert(used == (TZEN_TH_RX_SLOTS - 1U));
    assert(!tzen_th_init(NULL, table, 1));
    config.mutex_lock = (void (*)(void *))1;
    assert(!tzen_th_init(&config, table, 1)); config.mutex_lock = NULL;
    puts("PASS: setup, teardown, scratchpad, one-step polling, yield, fail, early success, sync, abort, TX failure, queue, CRC");
    return 0;
}
