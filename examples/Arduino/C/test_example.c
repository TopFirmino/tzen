#include "tzen.h"
#include "board.h"

typedef struct { uint32_t started; } led_state_t;

static bool setup_led(TzenContext_t *ctx)
{
    (void)ctx; example_led(false); return true;
}
static void cleanup_led(TzenContext_t *ctx, TzenTestStatus_t result)
{
    (void)ctx; (void)result; example_led(false);
}
static TzenStepResult_t led_on(TzenContext_t *ctx)
{
    led_state_t *st = TZEN_GET_STATE(ctx, led_state_t);
    st->started = example_millis();
    example_led(true);
    tzen_log(ctx, TZEN_LOG_INFO, "LED on; cooperative 100 ms wait");
    return TZEN_STEP_PASS_NEXT;
}
static TzenStepResult_t verify_led(TzenContext_t *ctx)
{
    led_state_t *st = TZEN_GET_STATE(ctx, led_state_t);
    bool passed;
    if ((uint32_t)(example_millis() - st->started) < 100U) return TZEN_STEP_YIELD;
    passed = example_led_read();
    return passed ? TZEN_STEP_PASS_NEXT : TZEN_STEP_FAIL;
}
static TzenStepResult_t wait_for_host(TzenContext_t *ctx)
{
    example_led(true);
    tzen_log(ctx, TZEN_LOG_INFO, "LED on; waiting for host");
    tzen_sync(ctx, 42U);
    return TZEN_STEP_WAIT_SYNC;
}
static TzenStepResult_t verify_sync(TzenContext_t *ctx)
{
    bool passed = example_led_read();
    (void)ctx;
    return passed ? TZEN_STEP_PASS_NEXT : TZEN_STEP_FAIL;
}
static TzenStepResult_t expected_failure(TzenContext_t *ctx)
{
    tzen_log(ctx, TZEN_LOG_INFO, "Intentional failure to verify FAIL reporting");
    return TZEN_STEP_FAIL;
}
static const TzenStepFn_t cycle_steps[] = {led_on, verify_led};
static const TzenStepFn_t sync_steps[] = {wait_for_host, verify_sync};
static const TzenStepFn_t fail_steps[] = {expected_failure};
const TzenTestDescriptor_t g_test_table[] = {
    TZEN_TEST_ENTRY("LED cycle", cycle_steps, setup_led, cleanup_led),
    TZEN_TEST_ENTRY("LED host sync", sync_steps, setup_led, cleanup_led),
    TZEN_TEST_ENTRY("Expected failure", fail_steps, setup_led, cleanup_led)
};
const size_t g_test_count = sizeof(g_test_table) / sizeof(g_test_table[0]);
