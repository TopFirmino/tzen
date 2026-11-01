/* Master-side framing is independent of the Slave harness. TTP only handles
 * protobuf on both peers. Each request/reply crosses a buffered binary file. */
#include "tzen.h"
#include "ttp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sched.h>
#include <time.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "Protocol check failed at line %d: %s\n", __LINE__, #expr); \
    return false; } } while (0)

#define WIRE_CAPACITY (TZEN_TH_MAX_PACKET_SIZE + TZEN_TH_MAX_PACKET_SIZE / 254U + 3U)

static bool test_setup(TzenContext_t *ctx)
{
    ctx->scratchpad[0] = 0xA5U;
    (void)tzen_log(ctx, TZEN_LOG_INFO, "Setup");
    return true;
}

static void test_teardown(TzenContext_t *ctx, TzenTestStatus_t status)
{
    (void)tzen_logf(ctx, TZEN_LOG_INFO, "Teardown: status=%u", (unsigned)status);
}

static TzenStepResult_t yielding_step(TzenContext_t *ctx)
{
    if (ctx->scratchpad[0] != 0xA5U) return TZEN_STEP_FAIL;
    (void)tzen_logf(ctx, TZEN_LOG_INFO, "Run %lu iteration %lu",
                   (unsigned long)ctx->run_id, (unsigned long)ctx->step_Iterations);
    return ctx->step_Iterations < 2U ? TZEN_STEP_YIELD : TZEN_STEP_PASS_NEXT;
}

static TzenStepResult_t sync_step(TzenContext_t *ctx)
{
    tzen_sync(ctx, 42U);
    return TZEN_STEP_WAIT_SYNC;
}

static TzenStepResult_t failing_step(TzenContext_t *ctx)
{
    (void)tzen_log(ctx, TZEN_LOG_ERROR, "Intentional example failure");
    return TZEN_STEP_FAIL;
}

static const TzenStepFn_t first_steps[] = {yielding_step, sync_step};
static const TzenStepFn_t second_steps[] = {failing_step};
static const TzenTestDescriptor_t tests[] = {
    TZEN_TEST_ENTRY("Power rail", first_steps, test_setup, test_teardown),
    TZEN_TEST_ENTRY("Expected failure (host example)", second_steps, test_setup, test_teardown)
};

static struct { unsigned logs, steps, syncs, finished; } observed[3];

static bool observe(const TargetToHost *message)
{
    CHECK(message->seq_id == 0U && message->status == ResultCode_RESULT_OK);
    uint32_t run_id, index;
    if (message->which_payload == TargetToHost_log_tag) {
        run_id = message->payload.log.run_id;
        index = message->payload.log.test_index;
    } else {
        CHECK(message->which_payload == TargetToHost_test_event_tag);
        run_id = message->payload.test_event.run_id;
        index = message->payload.test_event.test_index;
    }
    unsigned slot = run_id == 101U ? 0U : (run_id == 202U ? 1U : 2U);
    CHECK(run_id == 101U || run_id == 202U || run_id == 303U);
    CHECK(index == (slot == 1U ? 1U : 0U) && observed[slot].finished == 0U);
    if (message->which_payload == TargetToHost_log_tag) {
        ++observed[slot].logs;
    } else {
        const TestEvent *event = &message->payload.test_event;
        if (event->which_event == TestEvent_step_tag) {
            ++observed[slot].steps;
            CHECK(event->event.step.step_number == observed[slot].steps);
            CHECK(event->event.step.success == (slot != 1U));
        } else if (event->which_event == TestEvent_sync_tag) {
            CHECK(slot != 1U && event->event.sync.sync_id == 42U);
            ++observed[slot].syncs;
        } else {
            CHECK(event->which_event == TestEvent_finished_tag);
            CHECK(event->event.finished.status == (slot == 0U ? TestFinishedEvent_Status_SUCCESS :
                (slot == 1U ? TestFinishedEvent_Status_FAIL : TestFinishedEvent_Status_ABORTED)));
            ++observed[slot].finished;
        }
    }
    return true;
}

static uint16_t master_crc(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFU;
    for (size_t i = 0U; i < len; ++i) {
        for (unsigned bit = 0U; bit < 8U; ++bit) {
            bool feedback = ((crc & 0x8000U) != 0U) != ((data[i] & (0x80U >> bit)) != 0U);
            crc = (uint16_t)(crc << 1U);
            if (feedback) crc ^= 0x1021U;
        }
    }
    return crc;
}

static bool slave_write(const uint8_t *frame, size_t len, void *user_data)
{
    return fwrite(frame, 1U, len, (FILE *)user_data) == len;
}

static bool master_write(FILE *file, const uint8_t *payload, size_t len, bool corrupt)
{
    uint8_t raw[TZEN_TH_MAX_PACKET_SIZE];
    CHECK(len <= sizeof(raw) - 2U);
    memcpy(raw, payload, len);
    uint16_t crc = master_crc(payload, len);
    if (corrupt) crc ^= 1U;
    raw[len++] = (uint8_t)(crc >> 8U);
    raw[len++] = (uint8_t)crc;

    /* Block-oriented encoder, independent from tzen_th_send_packet. */
    CHECK(fputc(0, file) != EOF);
    size_t pos = 0U;
    do {
        size_t start = pos;
        while (pos < len && raw[pos] != 0U && pos - start < 254U) ++pos;
        size_t count = pos - start;
        CHECK(fputc((int)(count + 1U), file) != EOF);
        CHECK(fwrite(raw + start, 1U, count, file) == count);
        if (count == 254U) continue;
        if (pos == len) break;
        ++pos; /* Skip the implicit zero; a trailing zero needs a final code. */
        if (pos == len) CHECK(fputc(1, file) != EOF);
    } while (pos < len);
    /* An exact 254-byte final block may omit a redundant final code. */
    CHECK(fputc(0, file) != EOF);
    return true;
}

static bool master_read(FILE *file, TargetToHost *reply)
{
    uint8_t body[WIRE_CAPACITY];
    uint8_t raw[TZEN_TH_MAX_PACKET_SIZE];
    size_t len = 0U, count = 0U;
    CHECK(fgetc(file) == 0);
    int byte;
    while ((byte = fgetc(file)) != 0) {
        CHECK(byte != EOF && len < sizeof(body));
        body[len++] = (uint8_t)byte;
    }
    for (size_t pos = 0U; pos < len;) {
        uint8_t code = body[pos++];
        CHECK(code != 0U);
        for (unsigned i = 1U; i < code; ++i) {
            CHECK(pos < len && count < sizeof(raw));
            raw[count++] = body[pos++];
        }
        if (code < 255U && pos < len) {
            CHECK(count < sizeof(raw));
            raw[count++] = 0U;
        }
    }
    CHECK(count >= 2U);
    uint16_t crc = master_crc(raw, count - 2U);
    CHECK(raw[count - 2U] == (uint8_t)(crc >> 8U) && raw[count - 1U] == (uint8_t)crc);
    CHECK(Ttp_DecodeTargetToHost(reply, raw, count - 2U) == TTP_STATUS_OK);
    return true;
}

static bool exchange(FILE *request_file, FILE *reply_file, const uint8_t *payload,
                     size_t len, bool corrupt, bool expect_reply, TargetToHost *reply)
{
    CHECK(fseek(request_file, 0L, SEEK_END) == 0);
    long request_start = ftell(request_file);
    CHECK(request_start >= 0L);
    CHECK(master_write(request_file, payload, len, corrupt));
    CHECK(fflush(request_file) == 0 && fseek(request_file, request_start, SEEK_SET) == 0);
    CHECK(fseek(reply_file, 0L, SEEK_END) == 0);
    long reply_start = ftell(reply_file);
    CHECK(reply_start >= 0L);
    int byte;
    while ((byte = fgetc(request_file)) != EOF) tzen_th_feed_b((uint8_t)byte);
    CHECK(!ferror(request_file));
    tzen_th_main_function();
    CHECK(tzen_th_transport_ok());
    CHECK(fflush(reply_file) == 0 && fseek(reply_file, reply_start, SEEK_SET) == 0);
    bool got_reply = false;
    while ((byte = fgetc(reply_file)) != EOF) {
        CHECK(ungetc(byte, reply_file) != EOF);
        TargetToHost message = TargetToHost_init_zero;
        CHECK(master_read(reply_file, &message));
        if (message.seq_id != 0U) {
            CHECK(expect_reply && !got_reply);
            *reply = message;
            got_reply = true;
        } else CHECK(observe(&message));
    }
    CHECK(got_reply == expect_reply && !ferror(reply_file));
    return true;
}

static bool request(FILE *tx, FILE *rx, const HostToTarget *command,
                    ResultCode status, pb_size_t payload_tag, TargetToHost *reply)
{
    uint8_t payload[TTP_MAX_MESSAGE_SIZE];
    size_t len;
    CHECK(Ttp_EncodeHostToTarget(command, payload, sizeof(payload), &len) == TTP_STATUS_OK);
    CHECK(exchange(tx, rx, payload, len, false, command->seq_id != 0U, reply));
    if (command->seq_id != 0U) {
        CHECK(reply->seq_id == command->seq_id);
        CHECK(reply->status == status && reply->which_payload == payload_tag);
    }
    return true;
}

static bool stop_workers;

static void *poll_worker(void *arg)
{
    uint8_t id = *(uint8_t *)arg;
    for (;;) {
        TZEN_TH_ENTER_CRITICAL_SECTION();
        bool stop = stop_workers;
        TZEN_TH_EXIT_CRITICAL_SECTION();
        if (stop) break;
        tzen_th_worker_main_function(id);
        sched_yield();
    }
    return NULL;
}

static bool poll_events(FILE *rx)
{
    CHECK(fseek(rx, 0L, SEEK_END) == 0);
    long start = ftell(rx);
    CHECK(start >= 0L);
    tzen_th_main_function();
    CHECK(fflush(rx) == 0 && fseek(rx, start, SEEK_SET) == 0);
    int byte;
    while ((byte = fgetc(rx)) != EOF) {
        CHECK(ungetc(byte, rx) != EOF);
        TargetToHost message = TargetToHost_init_zero;
        CHECK(master_read(rx, &message) && observe(&message));
    }
    CHECK(!ferror(rx) && tzen_th_transport_ok());
    return true;
}

static double monotonic_seconds(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) abort();
    return (double)now.tv_sec + (double)now.tv_nsec / 1000000000.0;
}

static bool execution_loop(FILE *tx, FILE *rx)
{
    double deadline = monotonic_seconds() + 5.0;
    bool released = false;
    TargetToHost reply;
    while (observed[0].finished == 0U || observed[1].finished == 0U) {
        CHECK(monotonic_seconds() < deadline);
        CHECK(poll_events(rx));
        if (observed[0].syncs != 0U && !released) {
            HostToTarget release = HostToTarget_init_zero;
            release.seq_id = 50U;
            release.which_cmd = HostToTarget_sync_release_tag;
            release.cmd.sync_release.run_id = 101U;
            release.cmd.sync_release.sync_id = 99U;
            CHECK(request(tx, rx, &release, ResultCode_RESULT_ERR_NOT_FOUND, 0U, &reply));
            release.seq_id++;
            release.cmd.sync_release.sync_id = 42U;
            CHECK(request(tx, rx, &release, ResultCode_RESULT_OK, 0U, &reply));
            released = true;
        }
        sched_yield();
    }
    CHECK(observed[0].logs != 0U && observed[1].logs != 0U);
    CHECK(observed[0].steps == 2U && observed[1].steps == 1U && observed[0].syncs == 1U);

    HostToTarget command = HostToTarget_init_zero;
    command.seq_id = 60U;
    command.which_cmd = HostToTarget_execute_test_tag;
    command.cmd.execute_test.run_id = 303U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, 0U, &reply));
    command.seq_id++;
    command.which_cmd = HostToTarget_abort_test_tag;
    command.cmd.abort_test.run_id = 303U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, 0U, &reply));
    while (observed[2].finished == 0U) {
        CHECK(monotonic_seconds() < deadline);
        CHECK(poll_events(rx));
        sched_yield();
    }
    command.seq_id++;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_ERR_NOT_FOUND, 0U, &reply));
    CHECK(tzen_get_state() == TZEN_ENGINE_IDLE);
    return true;
}

static bool execution_cases(FILE *tx, FILE *rx, const TzenConfig_t *cfg, unsigned count)
{
    CHECK(tzen_th_init(cfg));
    memset(observed, 0, sizeof(observed));
    HostToTarget command = HostToTarget_init_zero;
    TargetToHost reply;
    command.seq_id = 40U;
    command.which_cmd = HostToTarget_execute_test_tag;
    command.cmd.execute_test.run_id = 101U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, 0U, &reply));
    command.seq_id++;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_ERR_BUSY, 0U, &reply));
    command.seq_id++;
    command.cmd.execute_test.run_id = 202U;
    command.cmd.execute_test.index = 1U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, 0U, &reply));
    CHECK(!tzen_th_init(cfg));

    pthread_t threads[2];
    uint8_t ids[2] = {0U, 1U};
    unsigned launched = 0U;
    stop_workers = false; /* No worker is running yet. */
    while (launched < count && pthread_create(&threads[launched], NULL, poll_worker, &ids[launched]) == 0)
        ++launched;
    bool ok = launched == count && execution_loop(tx, rx);
    TZEN_TH_ENTER_CRITICAL_SECTION();
    stop_workers = true;
    TZEN_TH_EXIT_CRITICAL_SECTION();
    for (unsigned i = 0U; i < launched; ++i) if (pthread_join(threads[i], NULL) != 0) ok = false;
    if (ok) printf("Execution checks passed with %u worker thread(s): yield, sync, logs, success, failure and abort.\n", count);
    return ok;
}

static bool protocol_cases(FILE *tx, FILE *rx)
{
    TzenConfig_t cfg = {.send_bytes = slave_write, .user_data = rx,
                        .tests = tests, .num_tests = sizeof(tests) / sizeof(tests[0])};
    CHECK(tzen_th_init(&cfg));
    HostToTarget command = HostToTarget_init_zero;
    TargetToHost reply = TargetToHost_init_zero;
    command.seq_id = 1U;
    command.which_cmd = HostToTarget_get_tests_tag;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, TargetToHost_tests_count_tag, &reply));
    CHECK(reply.payload.tests_count.total_tests == 2U);

    command.which_cmd = HostToTarget_get_test_info_tag;
    for (uint32_t i = 0U; i < 2U; ++i) {
        command.seq_id++;
        command.cmd.get_test_info.index = i;
        CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, TargetToHost_test_info_tag, &reply));
        CHECK(reply.payload.test_info.index == i);
        CHECK(strcmp(reply.payload.test_info.name, tests[i].name) == 0);
        CHECK(reply.payload.test_info.total_steps == tests[i].num_steps);
    }
    command.seq_id = UINT32_MAX;
    command.cmd.get_test_info.index = 2U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_ERR_INDEX, 0U, &reply));
    command.cmd.get_test_info.index = UINT32_MAX;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_ERR_INDEX, 0U, &reply));

    const pb_size_t unsupported[] = {0U, HostToTarget_execute_test_tag,
        HostToTarget_abort_test_tag, HostToTarget_sync_release_tag};
    const ResultCode errors[] = {ResultCode_RESULT_ERR_INVALID, ResultCode_RESULT_ERR_INDEX,
        ResultCode_RESULT_ERR_NOT_FOUND, ResultCode_RESULT_ERR_NOT_FOUND};
    for (size_t i = 0U; i < sizeof(unsupported) / sizeof(unsupported[0]); ++i) {
        command = (HostToTarget)HostToTarget_init_zero;
        command.seq_id = 10U + (uint32_t)i;
        command.which_cmd = unsupported[i];
        if (command.which_cmd == HostToTarget_execute_test_tag) command.cmd.execute_test.index = UINT32_MAX;
        CHECK(request(tx, rx, &command, errors[i], 0U, &reply));
    }

    command.which_cmd = HostToTarget_get_tests_tag;
    command.seq_id = 0U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, 0U, &reply));
    uint8_t payload[TTP_MAX_MESSAGE_SIZE];
    size_t len;
    command.seq_id = 20U;
    CHECK(Ttp_EncodeHostToTarget(&command, payload, sizeof(payload), &len) == TTP_STATUS_OK);
    CHECK(exchange(tx, rx, payload, len, true, false, &reply));
    /* Correct CRC but truncated protobuf varint: must not dispatch. */
    const uint8_t malformed[] = {0x08U, 0x80U};
    CHECK(exchange(tx, rx, malformed, sizeof(malformed), false, false, &reply));
    /* Unknown protobuf command field is skipped; no known oneof -> INVALID. */
    const uint8_t unknown[] = {0x08U, 21U, 0x3AU, 0x00U};
    CHECK(exchange(tx, rx, unknown, sizeof(unknown), false, true, &reply));
    CHECK(reply.seq_id == 21U && reply.status == ResultCode_RESULT_ERR_INVALID && reply.which_payload == 0U);
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, TargetToHost_tests_count_tag, &reply));

    /* Initialization validation must not destroy the last good configuration. */
    TzenConfig_t invalid = cfg;
    invalid.tests = NULL;
    CHECK(!tzen_th_init(&invalid));
    TzenTestDescriptor_t bad = {.name = "12345678901234567890123456789012"};
    invalid.tests = &bad;
    invalid.num_tests = 1U;
    CHECK(!tzen_th_init(&invalid));
    bad.name = NULL;
    CHECK(!tzen_th_init(&invalid));
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, TargetToHost_tests_count_tag, &reply));
    CHECK(reply.payload.tests_count.total_tests == 2U);

    CHECK(execution_cases(tx, rx, &cfg, 1U));
#if TZEN_TH_MAX_WORKERS >= 2U
    CHECK(execution_cases(tx, rx, &cfg, 2U));
#endif
    cfg.tests = NULL;
    cfg.num_tests = 0U;
    CHECK(tzen_th_init(&cfg));
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, TargetToHost_tests_count_tag, &reply));
    CHECK(reply.payload.tests_count.total_tests == 0U);
    command.seq_id++;
    command.which_cmd = HostToTarget_get_test_info_tag;
    command.cmd.get_test_info.index = 0U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_ERR_INDEX, 0U, &reply));
    puts("TTP checks passed: discovery, metadata, execution, errors, silent rejection and recovery.");
    return true;
}

bool host_protocol_cases(void)
{
    FILE *tx = tmpfile();
    FILE *rx = tmpfile();
    bool ok = tx != NULL && rx != NULL && protocol_cases(tx, rx);
    if (tx != NULL && fclose(tx) != 0) ok = false;
    if (rx != NULL && fclose(rx) != 0) ok = false;
    return ok;
}
