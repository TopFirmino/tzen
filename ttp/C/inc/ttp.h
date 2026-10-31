#ifndef TTP_H
#define TTP_H

#include <stdbool.h>
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
    TTP_STATUS_DECODE_FAILED,
    TTP_STATUS_FRAMING_FAILED,
    TTP_STATUS_CRC_FAILED
} Ttp_Status_t;

#define TTP_MAX_MESSAGE_SIZE ((size_t)((HostToTarget_size > TargetToHost_size) ? HostToTarget_size : TargetToHost_size))
#define TTP_CRC_SIZE 2U
#define TTP_MAX_FRAME_PAYLOAD_SIZE (TTP_MAX_MESSAGE_SIZE + TTP_CRC_SIZE)
#define TTP_MAX_FRAME_SIZE (TTP_MAX_FRAME_PAYLOAD_SIZE + (TTP_MAX_FRAME_PAYLOAD_SIZE / 254U) + 3U)

/* Raw message APIs encode/decode protobuf only. Frame APIs add/verify
 * CRC-16/CCITT-FALSE (high byte first) inside COBS. Frame decoders accept
 * only the COBS body without delimiters; CRC is checked before protobuf.
 * Callers must ignore output messages on any decoding error. */

Ttp_Status_t Ttp_EncodeHostToTarget(const HostToTarget *message,
    uint8_t *buffer, size_t capacity, size_t *size);
Ttp_Status_t Ttp_DecodeHostToTarget(HostToTarget *message,
    const uint8_t *buffer, size_t size);
Ttp_Status_t Ttp_EncodeHostToTargetFrame(const HostToTarget *message,
    uint8_t *buffer, size_t capacity, size_t *size);
Ttp_Status_t Ttp_DecodeHostToTargetFrame(HostToTarget *message,
    const uint8_t *buffer, size_t size);

Ttp_Status_t Ttp_EncodeTargetToHost(const TargetToHost *message,
    uint8_t *buffer, size_t capacity, size_t *size);
Ttp_Status_t Ttp_DecodeTargetToHost(TargetToHost *message,
    const uint8_t *buffer, size_t size);
Ttp_Status_t Ttp_EncodeTargetToHostFrame(const TargetToHost *message,
    uint8_t *buffer, size_t capacity, size_t *size);
Ttp_Status_t Ttp_DecodeTargetToHostFrame(TargetToHost *message,
    const uint8_t *buffer, size_t size);

#ifdef __cplusplus
}
#endif
#endif
