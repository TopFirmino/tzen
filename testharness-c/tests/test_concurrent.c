#include "tzen.h"
#include "ttp.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <sched.h>
#include <stdio.h>

static pthread_mutex_t api_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static unsigned entered, finished;
static bool release_steps;
static atomic_uint received, published, aborted, succeeded;
static _Thread_local unsigned lock_depth;
static void lock_api(void *user)
{
    (void)user; assert(lock_depth == 0);
    assert(!pthread_mutex_lock(&api_mutex)); ++lock_depth;
}
static void unlock_api(void *user)
{
    (void)user; assert(lock_depth == 1); --lock_depth;
    assert(!pthread_mutex_unlock(&api_mutex));
}
static void notify_rx(void *user) { (void)user; assert(lock_depth == 0); atomic_fetch_add(&published, 1); }
static void notify_workers(void *user) { (void)user; assert(lock_depth == 0); }
static bool send_frame(const uint8_t *frame, size_t len, void *user)
{
    TargetToHost m = TargetToHost_init_zero;
    (void)user; assert(lock_depth == 1);
    assert(Ttp_DecodeTargetToHostFrame(&m, frame+1, len-2) == TTP_STATUS_OK);
    if (m.which_payload == TargetToHost_tests_count_tag) atomic_fetch_add(&received, 1);
    if (m.which_payload == TargetToHost_test_event_tag && m.payload.test_event.which_event == TestEvent_finished_tag) {
        if (m.payload.test_event.event.finished.status == TestFinishedEvent_Status_ABORTED) atomic_fetch_add(&aborted, 1);
        else atomic_fetch_add(&succeeded, 1);
    }
    return true;
}
static bool setup(TzenContext_t *ctx)
{
    assert(lock_depth == 0); ctx->scratchpad[0] = (uint8_t)ctx->run_id;
    return true;
}
static void cleanup(TzenContext_t *ctx, TzenTestStatus_t result)
{
    (void)result;
    assert(lock_depth == 0 && ctx->scratchpad[0] == ctx->run_id);
    assert(!pthread_mutex_lock(&gate)); ++finished; assert(!pthread_mutex_unlock(&gate));
}
static TzenStepResult_t blocking_step(TzenContext_t *ctx)
{
    assert(lock_depth == 0);
    tzen_log(ctx, TZEN_LOG_INFO, "threaded step");
    assert(!pthread_mutex_lock(&gate));
    ++entered; assert(!pthread_cond_broadcast(&changed));
    while (!release_steps) assert(!pthread_cond_wait(&changed, &gate));
    assert(!pthread_mutex_unlock(&gate));
    return TZEN_STEP_DONE_PASS;
}
static const TzenStepFn_t steps[] = {blocking_step};
static const TzenTestDescriptor_t table[] = {TZEN_TEST_ENTRY("concurrent", steps, setup, cleanup)};
static void *worker(void *arg)
{
    tzen_th_worker_main_function((uint8_t)(uintptr_t)arg); return NULL;
}
static void send_command(pb_size_t tag, uint32_t run)
{
    HostToTarget m = HostToTarget_init_zero;
    uint8_t frame[TTP_MAX_FRAME_SIZE]; size_t len;
    m.seq_id = 1; m.which_cmd = tag;
    if (tag == HostToTarget_execute_test_tag) m.cmd.execute_test.run_id = run;
    if (tag == HostToTarget_abort_test_tag) m.cmd.abort_test.run_id = run;
    assert(Ttp_EncodeHostToTargetFrame(&m, frame, sizeof(frame), &len) == TTP_STATUS_OK);
    for (size_t i = 0; i < len; ++i) tzen_th_feed_b(frame[i]);
}
static void *producer(void *arg)
{
    (void)arg;
    /* One ISR producer overlaps main consumption; wait for each response to avoid drops. */
    for (unsigned i = 1; i <= 5000; ++i) {
        send_command(HostToTarget_get_tests_tag, 0);
        while (atomic_load(&received) < i) sched_yield();
    }
    return NULL;
}
int main(void)
{
    pthread_t a, b;
    TzenConfig_t config = {0};
    config.transport_send = send_frame;
    config.mutex_lock = lock_api; config.mutex_unlock = unlock_api;
    config.notify_worker = notify_workers; config.notify_main_from_isr = notify_rx;
    assert(tzen_th_init(&config, table, 1));
    send_command(HostToTarget_execute_test_tag, 11); tzen_th_main_function();
    send_command(HostToTarget_execute_test_tag, 22); tzen_th_main_function();
    assert(!pthread_create(&a, NULL, worker, (void *)(uintptr_t)0));
    assert(!pthread_create(&b, NULL, worker, (void *)(uintptr_t)1));
    assert(!pthread_mutex_lock(&gate));
    while (entered != 2) assert(!pthread_cond_wait(&changed, &gate));
    assert(!pthread_mutex_unlock(&gate));
    /* Both callbacks are simultaneously active; main must remain responsive. */
    send_command(HostToTarget_get_tests_tag, 0); tzen_th_main_function();
    assert(atomic_load(&received) == 1);
    send_command(HostToTarget_abort_test_tag, 11); tzen_th_main_function();
    assert(finished == 0);
    assert(!pthread_mutex_lock(&gate)); release_steps = true;
    assert(!pthread_cond_broadcast(&changed)); assert(!pthread_mutex_unlock(&gate));
    assert(!pthread_join(a, NULL)); assert(!pthread_join(b, NULL));
    assert(finished == 2 && atomic_load(&aborted) == 1 && atomic_load(&succeeded) == 1);
    assert(tzen_get_state() == TZEN_ENGINE_IDLE);
    atomic_store(&received, 0); atomic_store(&published, 0);
    assert(!pthread_create(&a, NULL, producer, NULL));
    while (atomic_load(&received) < 5000) { tzen_th_main_function(); sched_yield(); }
    assert(!pthread_join(a, NULL));
    assert(atomic_load(&published) == 5000);
    puts("PASS: two simultaneous worker callbacks, main progress, in-step abort, unlocked callbacks, serialized TX, 5000 concurrent SPSC frames");
    return 0;
}
