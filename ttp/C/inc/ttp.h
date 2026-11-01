#ifndef TTP_H
#define TTP_H

#include <stddef.h>
#include <stdint.h>

#include "ttp.pb.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    TTP_STATUS_OK = 0,
    TTP_STATUS_INVALID_ARGUMENT,
    TTP_STATUS_BUFFER_TOO_SMALL,
    TTP_STATUS_ENCODE_FAILED,
    TTP_STATUS_DECODE_FAILED
} Ttp_Status_t;

#define TTP_MAX_MESSAGE_SIZE ((size_t)((HostToTarget_size > TargetToHost_size) ? HostToTarget_size : TargetToHost_size))
/* Protobuf only. Transport framing and CRC belong to the harness.
 * Ignore output messages on decoding errors. Encode size is zero on failure. */

Ttp_Status_t Ttp_EncodeHostToTarget(const HostToTarget *message,
    uint8_t *buffer, size_t capacity, size_t *size);
Ttp_Status_t Ttp_DecodeHostToTarget(HostToTarget *message,
    const uint8_t *buffer, size_t size);
Ttp_Status_t Ttp_EncodeTargetToHost(const TargetToHost *message,
    uint8_t *buffer, size_t capacity, size_t *size);
Ttp_Status_t Ttp_DecodeTargetToHost(TargetToHost *message,
    const uint8_t *buffer, size_t size);
#ifdef __cplusplus
}
#endif
#endif
