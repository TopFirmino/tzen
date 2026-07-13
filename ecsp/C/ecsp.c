#include "ecsp.h"

#include <string.h>

#include "pb_decode.h"
#include "pb_encode.h"

Ecsp_Status_t Ecsp_EncodeMessage(const ecsp_HostTargetMessage *message,
                                 uint8_t *buffer,
                                 size_t buffer_size,
                                 size_t *encoded_size)
{
    pb_ostream_t stream;

    if ((message == NULL) || (buffer == NULL) || (encoded_size == NULL))
    {
        return ECSP_STATUS_INVALID_ARGUMENT;
    }

    stream = pb_ostream_from_buffer(buffer, buffer_size);
    if (!pb_encode(&stream, ecsp_HostTargetMessage_fields, message))
    {
        *encoded_size = 0U;
        return ECSP_STATUS_ENCODE_FAILED;
    }

    *encoded_size = stream.bytes_written;
    return ECSP_STATUS_OK;
}

Ecsp_Status_t Ecsp_DecodeMessage(ecsp_HostTargetMessage *message,
                                 const uint8_t *buffer,
                                 size_t buffer_size)
{
    pb_istream_t stream;

    if ((message == NULL) || (buffer == NULL))
    {
        return ECSP_STATUS_INVALID_ARGUMENT;
    }

    (void)memset(message, 0, sizeof(*message));
    stream = pb_istream_from_buffer(buffer, buffer_size);
    if (!pb_decode(&stream, ecsp_HostTargetMessage_fields, message))
    {
        return ECSP_STATUS_DECODE_FAILED;
    }

    return ECSP_STATUS_OK;
}

ecsp_HostTargetMessage Ecsp_MakeAck(bool success, const char *error_message)
{
    ecsp_HostTargetMessage message = ecsp_HostTargetMessage_init_zero;

    message.which_payload = ecsp_HostTargetMessage_ack_tag;
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

ecsp_HostTargetMessage Ecsp_MakeGetTests(void)
{
    ecsp_HostTargetMessage message = ecsp_HostTargetMessage_init_zero;

    message.which_payload = ecsp_HostTargetMessage_get_tests_tag;

    return message;
}

ecsp_HostTargetMessage Ecsp_MakeGetTest(uint32_t index)
{
    ecsp_HostTargetMessage message = ecsp_HostTargetMessage_init_zero;

    message.which_payload = ecsp_HostTargetMessage_get_test_tag;
    message.payload.get_test.index = index;

    return message;
}

ecsp_HostTargetMessage Ecsp_MakeExecuteTest(uint32_t index)
{
    ecsp_HostTargetMessage message = ecsp_HostTargetMessage_init_zero;

    message.which_payload = ecsp_HostTargetMessage_execute_test_tag;
    message.payload.execute_test.index = index;

    return message;
}

ecsp_HostTargetMessage Ecsp_MakeSyncRelease(uint32_t sync_id)
{
    ecsp_HostTargetMessage message = ecsp_HostTargetMessage_init_zero;

    message.which_payload = ecsp_HostTargetMessage_sync_release_tag;
    message.payload.sync_release.sync_id = sync_id;

    return message;
}
