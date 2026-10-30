#include "ttp.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

/* Cooperative demonstration: test 0 completes immediately; test 1 waits at
 * sync point 1, allowing discovery, busy rejection, release, and abort. */
static const char *test_names[] = {"sample_test_1", "sample_test_2"};
static FILE *debug_stream;
static bool active;
static uint32_t run_id, test_index, waiting_sync;

static void debug_log(const char *format, ...)
{
    va_list args;
    if (debug_stream == NULL) return;
    va_start(args, format);
    (void)vfprintf(debug_stream, format, args);
    va_end(args);
    (void)fprintf(debug_stream, "\n");
    (void)fflush(debug_stream);
}

static void send_message(const TargetToHost *message)
{
    uint8_t frame[TTP_MAX_FRAME_SIZE];
    size_t size = 0U;
    if (Ttp_EncodeTargetToHostFrame(message, frame, sizeof(frame), &size) != TTP_STATUS_OK ||
        fwrite(frame, 1U, size, stdout) != size || fflush(stdout) != 0)
        debug_log("protocol output failed");
}

static void reply(uint32_t seq, ResultCode code)
{
    TargetToHost response = TargetToHost_init_zero;
    response.seq_id = seq;
    response.status = code;
    send_message(&response);
}

static TargetToHost test_event(pb_size_t tag)
{
    TargetToHost response = TargetToHost_init_zero;
    response.which_payload = TargetToHost_test_event_tag;
    response.payload.test_event.run_id = run_id;
    response.payload.test_event.test_index = test_index;
    response.payload.test_event.which_event = tag;
    return response;
}

static void step(uint32_t number, const char *description)
{
    TargetToHost response = test_event(TestEvent_step_tag);
    response.payload.test_event.event.step.step_number = number;
    response.payload.test_event.event.step.success = true;
    (void)snprintf(response.payload.test_event.event.step.description,
        sizeof(response.payload.test_event.event.step.description), "%s", description);
    send_message(&response);
}

static void finish(TestFinishedEvent_Status status)
{
    TargetToHost response = test_event(TestEvent_finished_tag);
    response.payload.test_event.event.finished.status = status;
    active = false;
    waiting_sync = 0U;
    send_message(&response);
}

static void handle_message(const HostToTarget *message)
{
    TargetToHost response = TargetToHost_init_zero;
    uint32_t seq = message->seq_id;
    response.seq_id = seq;
    /* Zero is reserved for events. Do not emit a reply that could look like one. */
    if (seq == 0U) { debug_log("dropping zero sequence ID"); return; }
    switch (message->which_cmd)
    {
        case HostToTarget_get_tests_tag:
            response.which_payload = TargetToHost_tests_count_tag;
            response.payload.tests_count.total_tests = 2U;
            send_message(&response);
            break;
        case HostToTarget_get_test_info_tag:
            if (message->cmd.get_test_info.index >= 2U) {
                reply(seq, ResultCode_RESULT_ERR_INDEX); break;
            }
            response.which_payload = TargetToHost_test_info_tag;
            response.payload.test_info.index = message->cmd.get_test_info.index;
            response.payload.test_info.total_steps = 2U;
            (void)snprintf(response.payload.test_info.name, sizeof(response.payload.test_info.name),
                "%s", test_names[message->cmd.get_test_info.index]);
            send_message(&response);
            break;
        case HostToTarget_execute_test_tag:
            if (active) { reply(seq, ResultCode_RESULT_ERR_BUSY); break; }
            if (message->cmd.execute_test.index >= 2U) {
                reply(seq, ResultCode_RESULT_ERR_INDEX); break;
            }
            active = true;
            run_id = message->cmd.execute_test.run_id;
            test_index = message->cmd.execute_test.index;
            reply(seq, ResultCode_RESULT_OK);
            response.seq_id = 0U;
            response.which_payload = TargetToHost_log_tag;
            response.payload.log.level = LogEvent_Level_INFO;
            (void)snprintf(response.payload.log.message, sizeof(response.payload.log.message), "test started");
            send_message(&response);
            step(1U, "test started");
            if (test_index == 1U) {
                waiting_sync = 1U;
                response = test_event(TestEvent_sync_tag);
                response.payload.test_event.event.sync.sync_id = waiting_sync;
                send_message(&response);
            } else {
                step(2U, "test completed");
                finish(TestFinishedEvent_Status_SUCCESS);
            }
            break;
        case HostToTarget_abort_test_tag:
            if (!active || message->cmd.abort_test.run_id != run_id) {
                reply(seq, ResultCode_RESULT_ERR_NOT_FOUND); break;
            }
            reply(seq, ResultCode_RESULT_OK);
            finish(TestFinishedEvent_Status_ABORTED);
            break;
        case HostToTarget_sync_release_tag:
            if (!active || message->cmd.sync_release.run_id != run_id ||
                waiting_sync == 0U || message->cmd.sync_release.sync_id != waiting_sync) {
                reply(seq, ResultCode_RESULT_ERR_NOT_FOUND); break;
            }
            reply(seq, ResultCode_RESULT_OK);
            waiting_sync = 0U;
            step(2U, "sync released; test completed");
            finish(TestFinishedEvent_Status_SUCCESS);
            break;
        default:
            reply(seq, ResultCode_RESULT_ERR_INVALID);
            break;
    }
}

static bool read_next_frame(uint8_t *frame, size_t frame_capacity, size_t *frame_size)
{
    size_t length = 0U;
    bool in_frame = false;
    bool dropping = false;

    for (;;)
    {
        int value = fgetc(stdin);
        if (value == EOF)
        {
            return false;
        }

        if ((uint8_t)value == 0U)
        {
            if (in_frame && !dropping && (length > 0U))
            {
                *frame_size = length;
                return true;
            }

            in_frame = true;
            dropping = false;
            length = 0U;
            continue;
        }

        if (!in_frame || dropping)
        {
            continue;
        }

        if (length >= frame_capacity)
        {
            debug_log("dropping oversized frame");
            dropping = true;
            length = 0U;
            continue;
        }

        frame[length] = (uint8_t)value;
        length++;
    }
}

static void configure_stdio_binary(void)
{
#ifdef _WIN32
    (void)_setmode(_fileno(stdin), _O_BINARY);
    (void)_setmode(_fileno(stdout), _O_BINARY);
#endif
}

static bool configure_debug_log(int argc, char **argv)
{
    int i;

    debug_stream = stderr;
    for (i = 1; i < argc; i++)
    {
        if ((strcmp(argv[i], "--debug-log") == 0) && ((i + 1) < argc))
        {
            debug_stream = fopen(argv[i + 1], "w");
            if (debug_stream == NULL)
            {
                return false;
            }
            i++;
        }
    }

    return true;
}

int main(int argc, char **argv)
{
    uint8_t frame[TTP_MAX_FRAME_SIZE - 2U];
    size_t size = 0U;
    configure_stdio_binary();
    if (!configure_debug_log(argc, argv)) return 2;
    while (read_next_frame(frame, sizeof(frame), &size)) {
        HostToTarget message = HostToTarget_init_zero;
        Ttp_Status_t status = Ttp_DecodeHostToTargetFrame(&message, frame, size);
        if (status != TTP_STATUS_OK) {
            /* A damaged seq_id is untrusted: discard without a correlated reply. */
            debug_log("discarding invalid frame: status=%d", (int)status);
            continue;
        }
        handle_message(&message);
    }
    if (debug_stream != NULL && debug_stream != stderr) (void)fclose(debug_stream);
    return 0;
}
