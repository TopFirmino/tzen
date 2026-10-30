#include "ttp.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#define RX_QUEUE_DEPTH 4U
#define RX_FRAME_PAYLOAD_MAX (TTP_MAX_FRAME_SIZE - 2U)

typedef bool (*SlaveTestFn)(void);

typedef struct
{
    const char *name;
    SlaveTestFn run;
} SlaveTest_t;

typedef struct
{
    ttp_HostTargetMessage messages[RX_QUEUE_DEPTH];
    size_t head;
    size_t tail;
    size_t count;
} MessageQueue_t;

static FILE *debug_stream;

static void debug_log(const char *format, ...)
{
    va_list args;

    if (debug_stream == NULL)
    {
        return;
    }

    va_start(args, format);
    (void)vfprintf(debug_stream, format, args);
    va_end(args);
    (void)fprintf(debug_stream, "\n");
    (void)fflush(debug_stream);
}

static bool sample_test_1(void)
{
    debug_log("running sample_test_1");
    return true;
}

static bool sample_test_2(void)
{
    debug_log("running sample_test_2");
    return true;
}

static const SlaveTest_t slave_tests[] =
{
    {"sample_test_1", sample_test_1},
    {"sample_test_2", sample_test_2},
};

static const size_t slave_test_count = sizeof(slave_tests) / sizeof(slave_tests[0]);

static bool queue_push(MessageQueue_t *queue, const ttp_HostTargetMessage *message)
{
    if ((queue == NULL) || (message == NULL) || (queue->count >= RX_QUEUE_DEPTH))
    {
        return false;
    }

    queue->messages[queue->tail] = *message;
    queue->tail = (queue->tail + 1U) % RX_QUEUE_DEPTH;
    queue->count++;

    return true;
}

static bool queue_pop(MessageQueue_t *queue, ttp_HostTargetMessage *message)
{
    if ((queue == NULL) || (message == NULL) || (queue->count == 0U))
    {
        return false;
    }

    *message = queue->messages[queue->head];
    queue->head = (queue->head + 1U) % RX_QUEUE_DEPTH;
    queue->count--;

    return true;
}

static void copy_text(char *destination, size_t destination_size, const char *source)
{
    if ((destination == NULL) || (destination_size == 0U))
    {
        return;
    }

    destination[0] = '\0';
    if (source != NULL)
    {
        (void)strncpy(destination, source, destination_size - 1U);
        destination[destination_size - 1U] = '\0';
    }
}

static bool send_message(const ttp_HostTargetMessage *message)
{
    uint8_t frame[TTP_MAX_FRAME_SIZE];
    size_t frame_size = 0U;
    Ttp_Status_t status;

    status = Ttp_EncodeFrame(message, frame, sizeof(frame), &frame_size);
    if (status != TTP_STATUS_OK)
    {
        debug_log("encode failed: status=%d", (int)status);
        return false;
    }

    if (fwrite(frame, 1U, frame_size, stdout) != frame_size)
    {
        debug_log("stdout write failed");
        return false;
    }
    (void)fflush(stdout);

    return true;
}

static void send_ack(bool success, const char *error_message)
{
    ttp_HostTargetMessage response = Ttp_MakeAck(success, error_message);
    (void)send_message(&response);
}

static void send_log(ttp_Log_LogLevel level, const char *text)
{
    ttp_HostTargetMessage response = ttp_HostTargetMessage_init_zero;

    response.which_payload = ttp_HostTargetMessage_log_tag;
    response.payload.log.level = level;
    copy_text(response.payload.log.message, sizeof(response.payload.log.message), text);
    (void)send_message(&response);
}

static void send_test_step(uint32_t step_number, const char *description, bool success)
{
    ttp_HostTargetMessage response = ttp_HostTargetMessage_init_zero;

    response.which_payload = ttp_HostTargetMessage_test_step_tag;
    response.payload.test_step.step_number = step_number;
    response.payload.test_step.success = success;
    copy_text(response.payload.test_step.description,
              sizeof(response.payload.test_step.description),
              description);
    (void)send_message(&response);
}

static void send_test_finished(ttp_TestFinished_Status status)
{
    ttp_HostTargetMessage response = ttp_HostTargetMessage_init_zero;

    response.which_payload = ttp_HostTargetMessage_test_finished_tag;
    response.payload.test_finished.status = status;
    (void)send_message(&response);
}

static void handle_get_tests(void)
{
    ttp_HostTargetMessage response = ttp_HostTargetMessage_init_zero;

    debug_log("handling get_tests");
    response.which_payload = ttp_HostTargetMessage_get_tests_response_tag;
    response.payload.get_tests_response.total_tests = (uint32_t)slave_test_count;
    (void)send_message(&response);
}

static void handle_get_test(uint32_t index)
{
    ttp_HostTargetMessage response = ttp_HostTargetMessage_init_zero;

    debug_log("handling get_test index=%u", (unsigned int)index);
    if (index >= slave_test_count)
    {
        send_ack(false, "test index out of range");
        return;
    }

    response.which_payload = ttp_HostTargetMessage_get_test_response_tag;
    response.payload.get_test_response.index = index;
    copy_text(response.payload.get_test_response.name,
              sizeof(response.payload.get_test_response.name),
              slave_tests[index].name);
    (void)send_message(&response);
}

static void handle_execute_test(uint32_t index)
{
    bool success;

    debug_log("handling execute_test index=%u", (unsigned int)index);
    if (index >= slave_test_count)
    {
        send_ack(false, "test index out of range");
        return;
    }

    send_ack(true, "");
    send_log(ttp_Log_LogLevel_INFO, "test started");
    send_test_step(1U, "calling test function", true);
    success = slave_tests[index].run();
    send_test_step(2U, "test function returned", success);
    send_test_finished(success ? ttp_TestFinished_Status_SUCCESS : ttp_TestFinished_Status_FAIL);
}

static void handle_message(const ttp_HostTargetMessage *message)
{
    switch (message->which_payload)
    {
        case ttp_HostTargetMessage_get_tests_tag:
            handle_get_tests();
            break;

        case ttp_HostTargetMessage_get_test_tag:
            handle_get_test(message->payload.get_test.index);
            break;

        case ttp_HostTargetMessage_execute_test_tag:
            handle_execute_test(message->payload.execute_test.index);
            break;

        case ttp_HostTargetMessage_sync_release_tag:
            debug_log("handling sync_release sync_id=%u",
                      (unsigned int)message->payload.sync_release.sync_id);
            send_ack(true, "");
            break;

        default:
            debug_log("unsupported message tag=%u", (unsigned int)message->which_payload);
            send_ack(false, "unsupported message");
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
    MessageQueue_t queue;
    uint8_t frame[RX_FRAME_PAYLOAD_MAX];
    size_t frame_size = 0U;

    (void)memset(&queue, 0, sizeof(queue));
    configure_stdio_binary();
    if (!configure_debug_log(argc, argv))
    {
        return 2;
    }

    debug_log("TTP slave started");
    while (read_next_frame(frame, sizeof(frame), &frame_size))
    {
        ttp_HostTargetMessage message;
        Ttp_Status_t status = Ttp_DecodeFrame(&message, frame, frame_size);
        if (status != TTP_STATUS_OK)
        {
            debug_log("decode failed: status=%d", (int)status);
            send_ack(false, "decode failed");
            continue;
        }

        if (!queue_push(&queue, &message))
        {
            debug_log("queue full");
            send_ack(false, "queue full");
            continue;
        }

        while (queue_pop(&queue, &message))
        {
            handle_message(&message);
        }
    }

    debug_log("TTP slave stopped");
    if ((debug_stream != NULL) && (debug_stream != stderr))
    {
        (void)fclose(debug_stream);
    }

    return 0;
}
