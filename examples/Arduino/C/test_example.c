#include "tzen.h"
#include "board.h"

typedef struct { uint32_t started; } led_state_t;

static bool setup_led(th_context_t *ctx)
{
    (void)ctx; example_led(false); return true;
}
static void cleanup_led(th_context_t *ctx, th_test_status_t result)
{
    (void)ctx; (void)result; example_led(false);
}
static th_step_result_t led_on(th_context_t *ctx)
{
    led_state_t *st = TH_GET_STATE(ctx, led_state_t);
    st->started = example_millis();
    example_led(true);
    th_log(ctx, TH_LOG_INFO, "LED on; cooperative 100 ms wait");
    th_report_step(ctx, true, "LED enabled");
    return TH_STEP_PASS_NEXT;
}
static th_step_result_t verify_led(th_context_t *ctx)
{
    led_state_t *st = TH_GET_STATE(ctx, led_state_t);
    bool passed;
    if ((uint32_t)(example_millis() - st->started) < 100U) return TH_STEP_YIELD;
    passed = example_led_read();
    th_report_step(ctx, passed, "LED output register readback");
    return passed ? TH_STEP_PASS_NEXT : TH_STEP_FAIL;
}
static th_step_result_t wait_for_host(th_context_t *ctx)
{
    example_led(true);
    th_report_step(ctx, true, "LED on; waiting for host");
    th_request_sync(ctx, 42U);
    return TH_STEP_WAIT_SYNC;
}
static th_step_result_t verify_sync(th_context_t *ctx)
{
    bool passed = example_led_read();
    th_report_step(ctx, passed, "Host released sync 42");
    return passed ? TH_STEP_PASS_NEXT : TH_STEP_FAIL;
}
static th_step_result_t expected_failure(th_context_t *ctx)
{
    th_report_step(ctx, false, "Intentional failure to verify FAIL reporting");
    return TH_STEP_FAIL;
}
static const th_step_fn_t cycle_steps[] = {led_on, verify_led};
static const th_step_fn_t sync_steps[] = {wait_for_host, verify_sync};
static const th_step_fn_t fail_steps[] = {expected_failure};
const th_test_descriptor_t g_test_table[] = {
    TH_TEST_ENTRY("LED cycle", cycle_steps, setup_led, cleanup_led),
    TH_TEST_ENTRY("LED host sync", sync_steps, setup_led, cleanup_led),
    TH_TEST_ENTRY("Expected failure", fail_steps, setup_led, cleanup_led)
};
const size_t g_test_count = sizeof(g_test_table) / sizeof(g_test_table[0]);
