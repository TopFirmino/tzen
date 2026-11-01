/* Master-side framing is independent of the Slave harness. TTP only handles
 * protobuf on both peers. Each request/reply crosses a buffered binary file. */
#include "tzen.h"
#include "ttp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "Protocol check failed at line %d: %s\n", __LINE__, #expr); \
    return false; } } while (0)

#define WIRE_CAPACITY (TZEN_TH_MAX_PACKET_SIZE + TZEN_TH_MAX_PACKET_SIZE / 254U + 3U)

static TzenStepResult_t never_execute(TzenContext_t *ctx)
{
    (void)ctx;
    fputs("Discovery must not execute a test.\n", stderr);
    abort();
}

static const TzenStepFn_t first_steps[] = {never_execute, never_execute};
static const TzenStepFn_t second_steps[] = {never_execute};
static const TzenTestDescriptor_t tests[] = {
    TZEN_TEST_ENTRY("Power rail", first_steps, NULL, NULL),
    TZEN_TEST_ENTRY("1234567890123456789012345678901", second_steps, NULL, NULL)
};

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
    if (expect_reply) CHECK(master_read(reply_file, reply));
    CHECK(fgetc(reply_file) == EOF && !ferror(reply_file));
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
    for (size_t i = 0U; i < sizeof(unsupported) / sizeof(unsupported[0]); ++i) {
        command = (HostToTarget)HostToTarget_init_zero;
        command.seq_id = 10U + (uint32_t)i;
        command.which_cmd = unsupported[i];
        CHECK(request(tx, rx, &command, ResultCode_RESULT_ERR_INVALID, 0U, &reply));
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

    cfg.tests = NULL;
    cfg.num_tests = 0U;
    CHECK(tzen_th_init(&cfg));
    CHECK(request(tx, rx, &command, ResultCode_RESULT_OK, TargetToHost_tests_count_tag, &reply));
    CHECK(reply.payload.tests_count.total_tests == 0U);
    command.seq_id++;
    command.which_cmd = HostToTarget_get_test_info_tag;
    command.cmd.get_test_info.index = 0U;
    CHECK(request(tx, rx, &command, ResultCode_RESULT_ERR_INDEX, 0U, &reply));
    puts("TTP checks passed: discovery, metadata, errors, silent rejection and recovery; no tests executed.");
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
