from __future__ import annotations

from typing import Union

try:
    from .generated import ttp_pb2
except ImportError:
    from generated import ttp_pb2


BytesLike = Union[bytes, bytearray, memoryview]
FRAME_DELIMITER = 0

HostTargetMessage = ttp_pb2.HostTargetMessage
Ack = ttp_pb2.Ack
Sync = ttp_pb2.Sync
SyncRelease = ttp_pb2.SyncRelease
GetTests = ttp_pb2.GetTests
GetTest = ttp_pb2.GetTest
ExecuteTest = ttp_pb2.ExecuteTest
GetTestsResponse = ttp_pb2.GetTestsResponse
GetTestResponse = ttp_pb2.GetTestResponse
TestStep = ttp_pb2.TestStep
Log = ttp_pb2.Log
TestFinished = ttp_pb2.TestFinished


def encode_message(message: HostTargetMessage) -> bytes:
    return message.SerializeToString()


def decode_message(data: BytesLike) -> HostTargetMessage:
    message = HostTargetMessage()
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

        output.extend(encoded[index:end])
        index = end
        if code < 0xFF and index < len(encoded):
            output.append(0)

    return bytes(output)


def encode_frame(message: HostTargetMessage) -> bytes:
    return bytes([FRAME_DELIMITER]) + cobs_encode(encode_message(message)) + bytes([FRAME_DELIMITER])


def decode_frame(frame: BytesLike) -> HostTargetMessage:
    return decode_message(cobs_decode(frame))


def make_ack(success: bool, error_message: str = "") -> HostTargetMessage:
    return HostTargetMessage(ack=Ack(success=success, error_message=error_message))


def make_get_tests() -> HostTargetMessage:
    return HostTargetMessage(get_tests=GetTests())


def make_get_test(index: int) -> HostTargetMessage:
    return HostTargetMessage(get_test=GetTest(index=index))


def make_execute_test(index: int) -> HostTargetMessage:
    return HostTargetMessage(execute_test=ExecuteTest(index=index))


def make_sync_release(sync_id: int) -> HostTargetMessage:
    return HostTargetMessage(sync_release=SyncRelease(sync_id=sync_id))
