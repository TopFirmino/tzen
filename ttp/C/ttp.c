#include "ttp.h"

#include <string.h>

#include "pb_decode.h"
#include "pb_encode.h"

static Ttp_Status_t cobs_encode(const uint8_t *input,
                                 size_t input_size,
                                 uint8_t *output,
                                 size_t output_size,
                                 size_t *encoded_size)
{
    size_t code_index = 0U;
    size_t read_index = 0U;
    size_t write_index = 1U;
    uint8_t code = 1U;

    if ((input == NULL) || (output == NULL) || (encoded_size == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    if (output_size == 0U)
    {
        return TTP_STATUS_BUFFER_TOO_SMALL;
    }

    while (read_index < input_size)
    {
        if (input[read_index] == 0U)
        {
            output[code_index] = code;
            code_index = write_index;
            write_index++;
            code = 1U;
            read_index++;

            if (write_index > output_size)
            {
                return TTP_STATUS_BUFFER_TOO_SMALL;
            }
        }
        else
        {
            if (write_index >= output_size)
            {
                return TTP_STATUS_BUFFER_TOO_SMALL;
            }

            output[write_index] = input[read_index];
            write_index++;
            read_index++;
            code++;

            if (code == 0xFFU)
            {
                output[code_index] = code;
                code_index = write_index;
                write_index++;
                code = 1U;

                if (write_index > output_size)
                {
                    return TTP_STATUS_BUFFER_TOO_SMALL;
                }
            }
        }
    }

    output[code_index] = code;
    *encoded_size = write_index;

    return TTP_STATUS_OK;
}

static Ttp_Status_t cobs_decode(const uint8_t *input,
                                 size_t input_size,
                                 uint8_t *output,
                                 size_t output_size,
                                 size_t *decoded_size)
{
    size_t read_index = 0U;
    size_t write_index = 0U;

    if ((input == NULL) || (output == NULL) || (decoded_size == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    while (read_index < input_size)
    {
        uint8_t code = input[read_index];
        uint8_t i;

        if (code == 0U)
        {
            return TTP_STATUS_FRAMING_FAILED;
        }

        read_index++;
        for (i = 1U; i < code; i++)
        {
            if (read_index >= input_size)
            {
                return TTP_STATUS_FRAMING_FAILED;
            }
            if (write_index >= output_size)
            {
                return TTP_STATUS_BUFFER_TOO_SMALL;
            }

            output[write_index] = input[read_index];
            write_index++;
            read_index++;
        }

        if ((code < 0xFFU) && (read_index < input_size))
        {
            if (write_index >= output_size)
            {
                return TTP_STATUS_BUFFER_TOO_SMALL;
            }
            output[write_index] = 0U;
            write_index++;
        }
    }

    *decoded_size = write_index;
    return TTP_STATUS_OK;
}

Ttp_Status_t Ttp_EncodeMessage(const ttp_HostTargetMessage *message,
                                 uint8_t *buffer,
                                 size_t buffer_size,
                                 size_t *encoded_size)
{
    pb_ostream_t stream;

    if ((message == NULL) || (buffer == NULL) || (encoded_size == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    stream = pb_ostream_from_buffer(buffer, buffer_size);
    if (!pb_encode(&stream, ttp_HostTargetMessage_fields, message))
    {
        *encoded_size = 0U;
        return TTP_STATUS_ENCODE_FAILED;
    }

    *encoded_size = stream.bytes_written;
    return TTP_STATUS_OK;
}

Ttp_Status_t Ttp_DecodeMessage(ttp_HostTargetMessage *message,
                                 const uint8_t *buffer,
                                 size_t buffer_size)
{
    pb_istream_t stream;

    if ((message == NULL) || (buffer == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    (void)memset(message, 0, sizeof(*message));
    stream = pb_istream_from_buffer(buffer, buffer_size);
    if (!pb_decode(&stream, ttp_HostTargetMessage_fields, message))
    {
        return TTP_STATUS_DECODE_FAILED;
    }

    return TTP_STATUS_OK;
}

Ttp_Status_t Ttp_EncodeFrame(const ttp_HostTargetMessage *message,
                               uint8_t *frame,
                               size_t frame_size,
                               size_t *encoded_size)
{
    uint8_t payload[TTP_MAX_MESSAGE_SIZE];
    size_t payload_size = 0U;
    size_t cobs_size = 0U;
    Ttp_Status_t status;

    if ((message == NULL) || (frame == NULL) || (encoded_size == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    if (frame_size < 3U)
    {
        return TTP_STATUS_BUFFER_TOO_SMALL;
    }

    status = Ttp_EncodeMessage(message, payload, sizeof(payload), &payload_size);
    if (status != TTP_STATUS_OK)
    {
        *encoded_size = 0U;
        return status;
    }

    frame[0] = 0U;
    status = cobs_encode(payload, payload_size, &frame[1], frame_size - 2U, &cobs_size);
    if (status != TTP_STATUS_OK)
    {
        *encoded_size = 0U;
        return status;
    }

    frame[cobs_size + 1U] = 0U;
    *encoded_size = cobs_size + 2U;

    return TTP_STATUS_OK;
}

Ttp_Status_t Ttp_DecodeFrame(ttp_HostTargetMessage *message,
                               const uint8_t *frame,
                               size_t frame_size)
{
    uint8_t payload[TTP_MAX_MESSAGE_SIZE];
    size_t payload_size = 0U;
    Ttp_Status_t status;

    if ((message == NULL) || (frame == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    status = cobs_decode(frame, frame_size, payload, sizeof(payload), &payload_size);
    if (status != TTP_STATUS_OK)
    {
        return status;
    }

    return Ttp_DecodeMessage(message, payload, payload_size);
}

ttp_HostTargetMessage Ttp_MakeAck(bool success, const char *error_message)
{
    ttp_HostTargetMessage message = ttp_HostTargetMessage_init_zero;

    message.which_payload = ttp_HostTargetMessage_ack_tag;
    message.payload.ack.success = success;
    if (error_message != NULL)
    {
        (void)strncpy(message.payload.ack.error_message,
                     error_message,
                     sizeof(message.payload.ack.error_message) - 1U);
        message.payload.ack.error_message[sizeof(message.payload.ack.error_message) - 1U] = '\0';
    }

    return message;
}

ttp_HostTargetMessage Ttp_MakeGetTests(void)
{
    ttp_HostTargetMessage message = ttp_HostTargetMessage_init_zero;

    message.which_payload = ttp_HostTargetMessage_get_tests_tag;

    return message;
}

ttp_HostTargetMessage Ttp_MakeGetTest(uint32_t index)
{
    ttp_HostTargetMessage message = ttp_HostTargetMessage_init_zero;

    message.which_payload = ttp_HostTargetMessage_get_test_tag;
    message.payload.get_test.index = index;

    return message;
}

ttp_HostTargetMessage Ttp_MakeExecuteTest(uint32_t index)
{
    ttp_HostTargetMessage message = ttp_HostTargetMessage_init_zero;

    message.which_payload = ttp_HostTargetMessage_execute_test_tag;
    message.payload.execute_test.index = index;

    return message;
}

ttp_HostTargetMessage Ttp_MakeSyncRelease(uint32_t sync_id)
{
    ttp_HostTargetMessage message = ttp_HostTargetMessage_init_zero;

    message.which_payload = ttp_HostTargetMessage_sync_release_tag;
    message.payload.sync_release.sync_id = sync_id;

    return message;
}
