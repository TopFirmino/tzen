#ifndef ECSP_H
#define ECSP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "generated/ecsp.pb.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    ECSP_STATUS_OK = 0,
    ECSP_STATUS_INVALID_ARGUMENT,
    ECSP_STATUS_ENCODE_FAILED,
    ECSP_STATUS_DECODE_FAILED
} Ecsp_Status_t;

Ecsp_Status_t Ecsp_EncodeMessage(const ecsp_HostTargetMessage *message,
                                 uint8_t *buffer,
                                 size_t buffer_size,
                                 size_t *encoded_size);

Ecsp_Status_t Ecsp_DecodeMessage(ecsp_HostTargetMessage *message,
                                 const uint8_t *buffer,
                                 size_t buffer_size);

ecsp_HostTargetMessage Ecsp_MakeAck(bool success, const char *error_message);
ecsp_HostTargetMessage Ecsp_MakeGetTests(void);
ecsp_HostTargetMessage Ecsp_MakeGetTest(uint32_t index);
ecsp_HostTargetMessage Ecsp_MakeExecuteTest(uint32_t index);
ecsp_HostTargetMessage Ecsp_MakeSyncRelease(uint32_t sync_id);

#ifdef __cplusplus
}
#endif

#endif
