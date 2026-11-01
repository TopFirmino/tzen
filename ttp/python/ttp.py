from __future__ import annotations

from typing import Union

try:
    from .generated import ttp_pb2
except ImportError:
    from generated import ttp_pb2


BytesLike = Union[bytes, bytearray, memoryview]

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


def encode_message(message: Message) -> bytes:
    return message.SerializeToString()


def decode_message(data: BytesLike, message_type=TargetToHost) -> Message:
    if message_type not in (HostToTarget, TargetToHost):
        raise TypeError("expected a directional TTP envelope type")
    message = message_type()
    message.ParseFromString(bytes(data))
    return message


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
