"""Harness wire framing; TTP handles protobuf serialization only."""
from binascii import crc_hqx

from ttp.python import ttp

BytesLike = ttp.BytesLike
Message = ttp.Message
TargetToHost = ttp.TargetToHost
FRAME_DELIMITER = 0
MAX_FRAME_SIZE = 94  # C TargetToHost_size (89) + CRC, COBS code, delimiters.


def cobs_encode(data: BytesLike) -> bytes:
    raw = bytes(data)
    output = bytearray()
    code_index = 0
    output.append(0)
    code = 1

    for value in raw:
        if value == 0:
            output[code_index] = code
            code_index = len(output)
            output.append(0)
            code = 1
        else:
            output.append(value)
            code += 1
            if code == 0xFF:
                output[code_index] = code
                code_index = len(output)
                output.append(0)
                code = 1

    output[code_index] = code
    return bytes(output)


def cobs_decode(data: BytesLike) -> bytes:
    encoded = bytes(data)
    output = bytearray()
    index = 0

    while index < len(encoded):
        code = encoded[index]
        if code == 0:
            raise ValueError("zero byte inside COBS frame")

        index += 1
        end = index + code - 1
        if end > len(encoded):
            raise ValueError("truncated COBS frame")

        if 0 in encoded[index:end]:
            raise ValueError("zero byte inside COBS frame")
        output.extend(encoded[index:end])
        index = end
        if code < 0xFF and index < len(encoded):
            output.append(0)

    return bytes(output)


def encode_frame(message: Message) -> bytes:
    payload = ttp.encode_message(message)
    checksum = crc_hqx(payload, 0xFFFF).to_bytes(2, "big")
    return bytes([FRAME_DELIMITER]) + cobs_encode(payload + checksum) + bytes([FRAME_DELIMITER])


def decode_frame(frame: BytesLike, message_type=TargetToHost) -> Message:
    """Decode a COBS body without delimiters, checking CRC before protobuf."""
    payload = cobs_decode(frame)
    if len(payload) < 2:
        raise ValueError("frame missing CRC16 trailer")
    message, checksum = payload[:-2], int.from_bytes(payload[-2:], "big")
    if crc_hqx(message, 0xFFFF) != checksum:
        raise ValueError("CRC16 mismatch")
    return ttp.decode_message(message, message_type)


