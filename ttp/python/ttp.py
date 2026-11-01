from __future__ import annotations

from binascii import crc_hqx
from typing import Union

try:
    from .generated import ttp_pb2
except ImportError:
    from generated import ttp_pb2


BytesLike = Union[bytes, bytearray, memoryview]
FRAME_DELIMITER = 0

# Re-export schema types and result codes.
HostToTarget = ttp_pb2.HostToTarget
TargetToHost = ttp_pb2.TargetToHost
GetTestsCmd = ttp_pb2.GetTestsCmd
GetTestsResp = ttp_pb2.GetTestsResp
GetTestInfoCmd = ttp_pb2.GetTestInfoCmd
GetTestInfoResp = ttp_pb2.GetTestInfoResp
ExecuteTestCmd = ttp_pb2.ExecuteTestCmd
AbortTestCmd = ttp_pb2.AbortTestCmd
SyncReleaseCmd = ttp_pb2.SyncReleaseCmd
TestEvent = ttp_pb2.TestEvent
TestStepEvent = ttp_pb2.TestStepEvent
SyncWaitEvent = ttp_pb2.SyncWaitEvent
TestFinishedEvent = ttp_pb2.TestFinishedEvent
LogEvent = ttp_pb2.LogEvent
ResultCode = ttp_pb2.ResultCode
RESULT_OK = ttp_pb2.RESULT_OK
RESULT_ERR_INDEX = ttp_pb2.RESULT_ERR_INDEX
RESULT_ERR_BUSY = ttp_pb2.RESULT_ERR_BUSY
RESULT_ERR_NOT_FOUND = ttp_pb2.RESULT_ERR_NOT_FOUND
RESULT_ERR_INVALID = ttp_pb2.RESULT_ERR_INVALID
Message = Union[HostToTarget, TargetToHost]
MAX_FRAME_SIZE = 82


def encode_message(message: Message) -> bytes:
    return message.SerializeToString()


def decode_message(data: BytesLike, message_type=TargetToHost) -> Message:
    if message_type not in (HostToTarget, TargetToHost):
        raise TypeError("expected a directional TTP envelope type")
    message = message_type()
    message.ParseFromString(bytes(data))
    return message


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
    payload = encode_message(message)
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
    return decode_message(message, message_type)


def make_get_tests(seq_id: int = 0) -> HostToTarget:
    return HostToTarget(seq_id=seq_id, get_tests=GetTestsCmd())


def make_get_test_info(index: int, seq_id: int = 0) -> HostToTarget:
    return HostToTarget(seq_id=seq_id, get_test_info=GetTestInfoCmd(index=index))


def make_execute_test(index: int, run_id: int, seq_id: int = 0) -> HostToTarget:
    return HostToTarget(seq_id=seq_id, execute_test=ExecuteTestCmd(index=index, run_id=run_id))


def make_abort_test(run_id: int, seq_id: int = 0) -> HostToTarget:
    return HostToTarget(seq_id=seq_id, abort_test=AbortTestCmd(run_id=run_id))


def make_sync_release(run_id: int, sync_id: int, seq_id: int = 0) -> HostToTarget:
    return HostToTarget(seq_id=seq_id, sync_release=SyncReleaseCmd(run_id=run_id, sync_id=sync_id))
