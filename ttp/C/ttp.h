#ifndef TTP_H
#define TTP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "generated/ttp.pb.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    TTP_STATUS_OK = 0,
    TTP_STATUS_INVALID_ARGUMENT,
    TTP_STATUS_BUFFER_TOO_SMALL,
    TTP_STATUS_ENCODE_FAILED,
    TTP_STATUS_DECODE_FAILED,
    TTP_STATUS_FRAMING_FAILED
} Ttp_Status_t;

#define TTP_MAX_MESSAGE_SIZE ((size_t)ttp_HostTargetMessage_size)
#define TTP_MAX_FRAME_SIZE (TTP_MAX_MESSAGE_SIZE + (TTP_MAX_MESSAGE_SIZE / 254U) + 3U)

Ttp_Status_t Ttp_EncodeMessage(const ttp_HostTargetMessage *message,
                                 uint8_t *buffer,
                                 size_t buffer_size,
                                 size_t *encoded_size);

Ttp_Status_t Ttp_DecodeMessage(ttp_HostTargetMessage *message,
                                 const uint8_t *buffer,
                                 size_t buffer_size);

Ttp_Status_t Ttp_EncodeFrame(const ttp_HostTargetMessage *message,
                               uint8_t *frame,
                               size_t frame_size,
                               size_t *encoded_size);

Ttp_Status_t Ttp_DecodeFrame(ttp_HostTargetMessage *message,
                               const uint8_t *frame,
                               size_t frame_size);

ttp_HostTargetMessage Ttp_MakeAck(bool success, const char *error_message);
ttp_HostTargetMessage Ttp_MakeGetTests(void);
ttp_HostTargetMessage Ttp_MakeGetTest(uint32_t index);
ttp_HostTargetMessage Ttp_MakeExecuteTest(uint32_t index);
ttp_HostTargetMessage Ttp_MakeSyncRelease(uint32_t sync_id);

#ifdef __cplusplus
}
#endif

#endif
