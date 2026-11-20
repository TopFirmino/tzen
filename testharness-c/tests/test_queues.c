/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

#include "tzen.h"
#include "ttp.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static TargetToHost output[256];
static size_t used;
static unsigned setups, teardowns;
static bool send_ok = true;
static TzenStepResult_t modes[32];
static TzenTestStatus_t results[32];
static TzenContext_t *contexts[32];
static bool send_frame(const uint8_t *frame, size_t len, void *user)
{
    (void)user;
    if (!send_ok) return false;
    assert(used < 256);
    assert(Ttp_DecodeTargetToHostFrame(&output[used++], frame + 1, len - 2) == TTP_STATUS_OK);
    return true;
}
static bool setup(TzenContext_t *ctx)
{
    size_t i;
    assert(ctx->run_id < 32);
    for (i = 0; i < sizeof(ctx->scratchpad); ++i) assert(!ctx->scratchpad[i]);
    contexts[ctx->run_id] = ctx;
    ctx->scratchpad[0] = (uint8_t)(ctx->run_id + 1);
    ++setups; return true;
}
static void cleanup(TzenContext_t *ctx, TzenTestStatus_t result)
{
    assert(ctx->scratchpad[0] == ctx->run_id + 1);
    results[ctx->run_id] = result; ++teardowns;
}
static TzenStepResult_t step(TzenContext_t *ctx)
{
    assert(contexts[ctx->run_id] == ctx && ctx->scratchpad[0] == ctx->run_id + 1);
    if (modes[ctx->run_id] == TZEN_STEP_WAIT_SYNC) tzen_sync(ctx, 0);
    return modes[ctx->run_id];
}
static const TzenStepFn_t steps[] = {step};
static const TzenTestDescriptor_t table[] = {TZEN_TEST_ENTRY("queues", steps, setup, cleanup)};
static void init(void)
{
    TzenConfig_t cfg = {0};
    cfg.transport_send = send_frame;
    assert(tzen_th_init(&cfg, table, 1));
    used = setups = teardowns = 0;
    for (size_t i = 0; i < 32; ++i) modes[i] = TZEN_STEP_YIELD;
}
static void feed(const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; ++i) tzen_th_feed_b(data[i]);
}
static void command(pb_size_t tag, uint32_t run, uint32_t index)
{
    HostToTarget m = HostToTarget_init_zero;
    uint8_t frame[TTP_MAX_FRAME_SIZE]; size_t size;
    m.seq_id = 1; m.which_cmd = tag;
    if (tag == HostToTarget_execute_test_tag) { m.cmd.execute_test.run_id = run; m.cmd.execute_test.index = index; }
    if (tag == HostToTarget_abort_test_tag) m.cmd.abort_test.run_id = run;
    if (tag == HostToTarget_sync_release_tag) { m.cmd.sync_release.run_id = run; m.cmd.sync_release.sync_id = index; }
    assert(Ttp_EncodeHostToTargetFrame(&m, frame, sizeof(frame), &size) == TTP_STATUS_OK);
    feed(frame, size); tzen_th_main_function();
}
static void status(ResultCode code) { assert(used && output[used-1].status == code && output[used-1].seq_id); }
static uint16_t crc(const uint8_t *p, size_t len)
{
    uint16_t c = 0xffff;
    for (size_t i = 0; i < len; ++i) {
        c ^= (uint16_t)p[i] << 8;
        for (unsigned b = 0; b < 8; ++b) c = (uint16_t)((c & 0x8000) ? (c << 1) ^ 0x1021 : c << 1);
    }
    return c;
}
static void raw_payload(uint8_t *p, size_t len, bool damage_crc)
{
    uint8_t body[2 * TZEN_TH_MAX_PACKET_SIZE + 32];
    size_t code_pos = 0, out = 1;
    uint8_t code = 1;
    uint16_t c = crc(p, len - 2);
    p[len-2] = (uint8_t)(c >> 8); p[len-1] = (uint8_t)c ^ (damage_crc ? 1 : 0);
    for (size_t i = 0; i < len; ++i) {
        if (!p[i]) { body[code_pos] = code; code_pos = out++; code = 1; }
        else {
            body[out++] = p[i]; ++code;
            if (code == 255) { body[code_pos] = code; code_pos = out++; code = 1; }
        }
    }
    body[code_pos] = code;
    tzen_th_feed_b(0); feed(body, out); tzen_th_feed_b(0); tzen_th_main_function();
}
static void padded_discovery(size_t len)
{
    uint8_t payload[TZEN_TH_MAX_PACKET_SIZE + 8];
    /* seq=1, get_tests={}, unknown bytes field 100, two-byte length. */
    size_t padding = len - 10;
    uint8_t header[] = {8, 1, 0x52, 0, 0xa2, 6, (uint8_t)((padding & 127) | 128), (uint8_t)(padding >> 7)};
    memcpy(payload, header, sizeof(header));
    memset(payload + sizeof(header), 0x55, padding);
    raw_payload(payload, len, false);
}
int main(void)
{
    size_t before;
    setbuf(stdout, NULL);
    init();
    command(HostToTarget_execute_test_tag, 0, 0); status(ResultCode_RESULT_OK);
    command(HostToTarget_execute_test_tag, 1, 0); status(ResultCode_RESULT_OK);
    assert(!setups); /* Main never executes application code. */
    tzen_th_worker_main_function(0); tzen_th_worker_main_function(1);
    assert(setups == 2 && contexts[0] != contexts[1]);
    assert(contexts[0]->step_Iterations == 1 && contexts[1]->step_Iterations == 1);
    command(HostToTarget_execute_test_tag, 0, 0); status(ResultCode_RESULT_ERR_BUSY);
    modes[0] = TZEN_STEP_WAIT_SYNC;
    tzen_th_worker_main_function(0);
    assert(tzen_th_worker_get_state(0) == TZEN_ENGINE_WAITING_SYNC);
    command(HostToTarget_sync_release_tag, 1, 0); status(ResultCode_RESULT_ERR_NOT_FOUND);
    command(HostToTarget_sync_release_tag, 0, 9); status(ResultCode_RESULT_ERR_NOT_FOUND);
    command(HostToTarget_get_tests_tag, 0, 0); assert(output[used-1].payload.tests_count.total_tests == 1);
    command(HostToTarget_abort_test_tag, 1, 0); status(ResultCode_RESULT_OK);
    assert(teardowns == 0); /* Abort cleanup belongs to the worker. */
    tzen_th_worker_main_function(1);
    assert(teardowns == 1 && results[1] == TZEN_TEST_STATUS_ABORTED);
    assert(tzen_th_worker_get_state(0) == TZEN_ENGINE_WAITING_SYNC);
    command(HostToTarget_sync_release_tag, 0, 0); status(ResultCode_RESULT_OK);
    command(HostToTarget_sync_release_tag, 0, 0); status(ResultCode_RESULT_ERR_NOT_FOUND);
    tzen_th_worker_main_function(0);
    assert(teardowns == 2 && results[0] == TZEN_TEST_STATUS_SUCCESS);
    tzen_th_worker_main_function(255);
    init();
    for (size_t i = 0; i < TZEN_TH_WORKER_QUEUE_DEPTH; ++i) {
        command(HostToTarget_execute_test_tag, (uint32_t)i, 0); status(ResultCode_RESULT_OK);
    }
    command(HostToTarget_execute_test_tag, 10, 0); status(ResultCode_RESULT_ERR_BUSY);
    command(HostToTarget_execute_test_tag, 0, 0); status(ResultCode_RESULT_ERR_BUSY);
    command(HostToTarget_abort_test_tag, 1, 0);
    assert(output[used-1].payload.test_event.event.finished.status == TestFinishedEvent_Status_ABORTED);
    assert(!setups && !teardowns);
    tzen_th_worker_main_function(0); tzen_th_worker_main_function(1);
    assert(contexts[0]->run_id == 0 && contexts[2]->run_id == 2); /* FIFO after cancellation. */
    send_ok = false;
    tzen_log(NULL, TZEN_LOG_INFO, "trigger TX failure");
    tzen_th_worker_main_function(0); tzen_th_worker_main_function(1);
    while (tzen_get_state() != TZEN_ENGINE_IDLE) tzen_th_worker_main_function(0);
    assert(!tzen_th_transport_ok() && teardowns == setups);
    send_ok = true; init();
    /* Multiple 0xff blocks and exact decoded buffer limit, including CRC. */
    padded_discovery(TZEN_TH_MAX_PACKET_SIZE); assert(used == 1);
    padded_discovery(TZEN_TH_MAX_PACKET_SIZE + 1); assert(used == 1);
    before = used;
    { uint8_t bad[] = {0, 5, 9, 0, 1, 0, 0}; feed(bad, sizeof(bad)); tzen_th_main_function(); }
    assert(used == before);
    { uint8_t invalid[] = {0xff, 0xff, 0, 0}; raw_payload(invalid, sizeof(invalid), false); }
    assert(used == before); /* Valid CRC, invalid protobuf. */
    { uint8_t noseq[] = {0x52, 0, 0, 0}; raw_payload(noseq, sizeof(noseq), false); }
    assert(used == before);
    { uint8_t badcrc[] = {8, 1, 0x52, 0, 0, 0}; raw_payload(badcrc, sizeof(badcrc), true); }
    assert(used == before);
    /* Leave a partial frame, then resynchronize and receive a good one. */
    tzen_th_feed_b(255); tzen_th_feed_b(11); tzen_th_feed_b(0);
    command(HostToTarget_get_tests_tag, 0, 0); assert(used == before + 1);
    /* Fill RX, drop a new arrival, consume while another frame is partial. */
    {
        HostToTarget m = HostToTarget_init_zero;
        uint8_t frame[TTP_MAX_FRAME_SIZE]; size_t len;
        m.seq_id = 7; m.which_cmd = HostToTarget_get_tests_tag;
        assert(Ttp_EncodeHostToTargetFrame(&m, frame, sizeof(frame), &len) == TTP_STATUS_OK);
        before = used;
        for (size_t i = 0; i < TZEN_TH_RX_SLOTS; ++i) feed(frame, len);
        feed(frame, len - 1);
        tzen_th_main_function(); assert(used == before + TZEN_TH_RX_SLOTS - 1);
        tzen_th_feed_b(0); tzen_th_main_function();
        assert(used == before + TZEN_TH_RX_SLOTS); /* Safe to publish when space becomes available. */
        for (size_t i = 0; i < 10 * TZEN_TH_RX_SLOTS; ++i) { feed(frame, len); tzen_th_main_function(); }
    }
    puts("PASS: streaming boundaries/recovery, CRC/protobuf rejection, RX full/wrap, worker FIFO/full/cancel, overlapping contexts, run routing, all-worker TX cleanup");
    return 0;
}
