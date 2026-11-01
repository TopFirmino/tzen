#include "ttp.h"

#include "pb_decode.h"
#include "pb_encode.h"

static Ttp_Status_t encode_message(const pb_msgdesc_t *fields, const void *message,
                                 uint8_t *buffer,
                                 size_t buffer_size,
                                 size_t *encoded_size)
{
    pb_ostream_t stream;

    if (encoded_size != NULL) *encoded_size = 0U;

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
