#include "testcases.h"
#include "tzen.h"

static TzenStepResult_t count(TzenContext_t *ctx)
{
    if (ctx->step_Iterations < 3U) return TZEN_STEP_YIELD;
    tzen_log(ctx, TZEN_LOG_INFO, "Yielding test completed");
    return TZEN_STEP_PASS_NEXT;
}
static TzenStepResult_t synchronize(TzenContext_t *ctx)
{
    tzen_sync(ctx, 42U);
    return TZEN_STEP_WAIT_SYNC;
}
static TzenStepResult_t fail(TzenContext_t *ctx)
{
    tzen_log(ctx, TZEN_LOG_ERROR, "Intentional example failure");
    return TZEN_STEP_FAIL;
}
static const TzenStepFn_t count_steps[] = {count};
static const TzenStepFn_t sync_steps[] = {synchronize, count};
static const TzenStepFn_t fail_steps[] = {fail};
const TzenTestDescriptor_t host_tests[HOST_TEST_COUNT] = {
    TZEN_TEST_ENTRY("Yield and pass", count_steps, NULL, NULL),
    TZEN_TEST_ENTRY("Synchronize and pass", sync_steps, NULL, NULL),
    TZEN_TEST_ENTRY("Expected failure", fail_steps, NULL, NULL)
};
