#include "testcases.h"
#include "tzen.h"

/* Synthetic coverage messages, not a coverage measurement implementation.
 * All callbacks and this producer run on the host's single main thread. */
static TzenExecutionRef_t pending[TZEN_TH_MAX_WORKERS];
static size_t pending_count;
static bool pending_overflow;

static void defer_coverage(TzenContext_t *ctx, TzenTestStatus_t status)
{
    (void)status;
    if (pending_count == TZEN_TH_MAX_WORKERS) {
        pending_overflow = true;
        return;
    }
    pending[pending_count++] = (TzenExecutionRef_t){ctx->run_id, ctx->test_index};
}

bool host_emit_deferred_logs(void)
{
    if (pending_overflow) return false;
    for (size_t i = 0U; i < pending_count; ++i) {
        if (!tzen_emit_log(HOST_SOURCE_COVERAGE, &pending[i], TZEN_LOG_INFO,
                           "Demo coverage summary after TestFinished (synthetic)"))
            return false;
        if (!tzen_emit_log(HOST_SOURCE_COVERAGE2, &pending[i], TZEN_LOG_INFO,
                           "Synthetic coverage2 sample"))
            return false;
    }
    pending_count = 0U;
    return true;
}

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
    TZEN_TEST_ENTRY("Yield and pass", count_steps, NULL, defer_coverage),
    TZEN_TEST_ENTRY("Synchronize and pass", sync_steps, NULL, defer_coverage),
    TZEN_TEST_ENTRY("Expected failure", fail_steps, NULL, defer_coverage)
};
