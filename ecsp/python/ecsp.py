from __future__ import annotations

from typing import Union

try:
    from .generated import ecsp_pb2
except ImportError:
    from generated import ecsp_pb2


BytesLike = Union[bytes, bytearray, memoryview]

HostTargetMessage = ecsp_pb2.HostTargetMessage
Ack = ecsp_pb2.Ack
Sync = ecsp_pb2.Sync
SyncRelease = ecsp_pb2.SyncRelease
GetTests = ecsp_pb2.GetTests
GetTest = ecsp_pb2.GetTest
ExecuteTest = ecsp_pb2.ExecuteTest
GetTestsResponse = ecsp_pb2.GetTestsResponse
GetTestResponse = ecsp_pb2.GetTestResponse
TestStep = ecsp_pb2.TestStep
Log = ecsp_pb2.Log
TestFinished = ecsp_pb2.TestFinished


def encode_message(message: HostTargetMessage) -> bytes:
    return message.SerializeToString()


def decode_message(data: BytesLike) -> HostTargetMessage:
    message = HostTargetMessage()
    message.ParseFromString(bytes(data))
    return message


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
