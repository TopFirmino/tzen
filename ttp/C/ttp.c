#include "ttp.h"

#include <string.h>

#include "pb_decode.h"
#include "pb_encode.h"

/* CRC-16/CCITT-FALSE: poly=0x1021, init=0xFFFF, refin/refout=false,
 * xorout=0; check("123456789")=0x29B1. */
static uint16_t crc16(const uint8_t *data, size_t size)
{
    uint16_t crc = 0xFFFFU;
    size_t i;
    for (i = 0U; i < size; i++)
    {
        unsigned int bit;
        crc ^= (uint16_t)((uint16_t)data[i] << 8U);
        for (bit = 0U; bit < 8U; bit++)
        {
            crc = (uint16_t)((crc & 0x8000U) != 0U
                ? (crc << 1U) ^ 0x1021U : (unsigned int)crc << 1U);
        }
    }
    return crc;
}

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

            if (input[read_index] == 0U)
            {
                return TTP_STATUS_FRAMING_FAILED;
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

static Ttp_Status_t encode_message(const pb_msgdesc_t *fields, const void *message,
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
    if (!pb_encode(&stream, fields, message))
    {
        *encoded_size = 0U;
        return TTP_STATUS_ENCODE_FAILED;
    }

    *encoded_size = stream.bytes_written;
    return TTP_STATUS_OK;
}

static Ttp_Status_t decode_message(const pb_msgdesc_t *fields, void *message,
                                 const uint8_t *buffer,
                                 size_t buffer_size)
{
    pb_istream_t stream;

    if ((message == NULL) || (buffer == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    stream = pb_istream_from_buffer(buffer, buffer_size);
    if (!pb_decode(&stream, fields, message))
    {
        return TTP_STATUS_DECODE_FAILED;
    }

    return TTP_STATUS_OK;
}

static Ttp_Status_t encode_frame(const pb_msgdesc_t *fields, const void *message,
                               uint8_t *frame,
                               size_t frame_size,
                               size_t *encoded_size)
{
    uint8_t payload[TTP_MAX_FRAME_PAYLOAD_SIZE];
    size_t payload_size = 0U;
    size_t cobs_size = 0U;
    Ttp_Status_t status;

    if ((message == NULL) || (frame == NULL) || (encoded_size == NULL))
    {
        return TTP_STATUS_INVALID_ARGUMENT;
    }

    *encoded_size = 0U;
    if (frame_size < (TTP_CRC_SIZE + 3U))
    {
        return TTP_STATUS_BUFFER_TOO_SMALL;
    }

    status = encode_message(fields, message, payload, TTP_MAX_MESSAGE_SIZE, &payload_size);
    if (status != TTP_STATUS_OK)
    {
        *encoded_size = 0U;
        return status;
    }

    {
        uint16_t checksum = crc16(payload, payload_size);
        payload[payload_size++] = (uint8_t)(checksum >> 8U);
        payload[payload_size++] = (uint8_t)checksum;
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

static Ttp_Status_t decode_frame(const pb_msgdesc_t *fields, void *message,
                               const uint8_t *frame,
                               size_t frame_size)
{
    uint8_t payload[TTP_MAX_FRAME_PAYLOAD_SIZE];
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

    if (payload_size < TTP_CRC_SIZE)
    {
        return TTP_STATUS_FRAMING_FAILED;
    }
    payload_size -= TTP_CRC_SIZE;
    if (crc16(payload, payload_size) !=
        (uint16_t)(((uint16_t)payload[payload_size] << 8U) | payload[payload_size + 1U]))
    {
        return TTP_STATUS_CRC_FAILED;
    }
    return decode_message(fields, message, payload, payload_size);
}


Ttp_Status_t Ttp_EncodeHostToTarget(const HostToTarget *message,
    uint8_t *buffer, size_t capacity, size_t *size)
{
    return encode_message(HostToTarget_fields, message, buffer, capacity, size);
}
Ttp_Status_t Ttp_DecodeHostToTarget(HostToTarget *message,
    const uint8_t *buffer, size_t size)
{
    return decode_message(HostToTarget_fields, message, buffer, size);
}
Ttp_Status_t Ttp_EncodeHostToTargetFrame(const HostToTarget *message,
    uint8_t *buffer, size_t capacity, size_t *size)
{
    return encode_frame(HostToTarget_fields, message, buffer, capacity, size);
}
Ttp_Status_t Ttp_DecodeHostToTargetFrame(HostToTarget *message,
    const uint8_t *buffer, size_t size)
{
    return decode_frame(HostToTarget_fields, message, buffer, size);
}

Ttp_Status_t Ttp_EncodeTargetToHost(const TargetToHost *message,
    uint8_t *buffer, size_t capacity, size_t *size)
{
    return encode_message(TargetToHost_fields, message, buffer, capacity, size);
}
Ttp_Status_t Ttp_DecodeTargetToHost(TargetToHost *message,
    const uint8_t *buffer, size_t size)
{
    return decode_message(TargetToHost_fields, message, buffer, size);
}
Ttp_Status_t Ttp_EncodeTargetToHostFrame(const TargetToHost *message,
    uint8_t *buffer, size_t capacity, size_t *size)
{
    return encode_frame(TargetToHost_fields, message, buffer, capacity, size);
}
Ttp_Status_t Ttp_DecodeTargetToHostFrame(TargetToHost *message,
    const uint8_t *buffer, size_t size)
{
    return decode_frame(TargetToHost_fields, message, buffer, size);
}
