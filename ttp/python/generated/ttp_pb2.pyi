from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ResultCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESULT_OK: _ClassVar[ResultCode]
    RESULT_ERR_INDEX: _ClassVar[ResultCode]
    RESULT_ERR_BUSY: _ClassVar[ResultCode]
    RESULT_ERR_NOT_FOUND: _ClassVar[ResultCode]
    RESULT_ERR_INVALID: _ClassVar[ResultCode]
RESULT_OK: ResultCode
RESULT_ERR_INDEX: ResultCode
RESULT_ERR_BUSY: ResultCode
RESULT_ERR_NOT_FOUND: ResultCode
RESULT_ERR_INVALID: ResultCode

class HostToTarget(_message.Message):
    __slots__ = ("seq_id", "get_tests", "get_test_info", "execute_test", "abort_test", "sync_release")
    SEQ_ID_FIELD_NUMBER: _ClassVar[int]
    GET_TESTS_FIELD_NUMBER: _ClassVar[int]
    GET_TEST_INFO_FIELD_NUMBER: _ClassVar[int]
    EXECUTE_TEST_FIELD_NUMBER: _ClassVar[int]
    ABORT_TEST_FIELD_NUMBER: _ClassVar[int]
    SYNC_RELEASE_FIELD_NUMBER: _ClassVar[int]
    seq_id: int
    get_tests: GetTestsCmd
    get_test_info: GetTestInfoCmd
    execute_test: ExecuteTestCmd
    abort_test: AbortTestCmd
    sync_release: SyncReleaseCmd
    def __init__(self, seq_id: _Optional[int] = ..., get_tests: _Optional[_Union[GetTestsCmd, _Mapping]] = ..., get_test_info: _Optional[_Union[GetTestInfoCmd, _Mapping]] = ..., execute_test: _Optional[_Union[ExecuteTestCmd, _Mapping]] = ..., abort_test: _Optional[_Union[AbortTestCmd, _Mapping]] = ..., sync_release: _Optional[_Union[SyncReleaseCmd, _Mapping]] = ...) -> None: ...

class TargetToHost(_message.Message):
    __slots__ = ("seq_id", "status", "tests_count", "test_info", "test_event", "log")
    SEQ_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TESTS_COUNT_FIELD_NUMBER: _ClassVar[int]
    TEST_INFO_FIELD_NUMBER: _ClassVar[int]
    TEST_EVENT_FIELD_NUMBER: _ClassVar[int]
    LOG_FIELD_NUMBER: _ClassVar[int]
    seq_id: int
    status: ResultCode
    tests_count: GetTestsResp
    test_info: GetTestInfoResp
    test_event: TestEvent
    log: LogEvent
    def __init__(self, seq_id: _Optional[int] = ..., status: _Optional[_Union[ResultCode, str]] = ..., tests_count: _Optional[_Union[GetTestsResp, _Mapping]] = ..., test_info: _Optional[_Union[GetTestInfoResp, _Mapping]] = ..., test_event: _Optional[_Union[TestEvent, _Mapping]] = ..., log: _Optional[_Union[LogEvent, _Mapping]] = ...) -> None: ...

class GetTestsCmd(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetTestsResp(_message.Message):
    __slots__ = ("total_tests",)
    TOTAL_TESTS_FIELD_NUMBER: _ClassVar[int]
    total_tests: int
    def __init__(self, total_tests: _Optional[int] = ...) -> None: ...

class GetTestInfoCmd(_message.Message):
    __slots__ = ("index",)
    INDEX_FIELD_NUMBER: _ClassVar[int]
    index: int
    def __init__(self, index: _Optional[int] = ...) -> None: ...

class GetTestInfoResp(_message.Message):
    __slots__ = ("index", "name", "total_steps")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TOTAL_STEPS_FIELD_NUMBER: _ClassVar[int]
    index: int
    name: str
    total_steps: int
    def __init__(self, index: _Optional[int] = ..., name: _Optional[str] = ..., total_steps: _Optional[int] = ...) -> None: ...

class ExecuteTestCmd(_message.Message):
    __slots__ = ("index", "run_id")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    index: int
    run_id: int
    def __init__(self, index: _Optional[int] = ..., run_id: _Optional[int] = ...) -> None: ...

class AbortTestCmd(_message.Message):
    __slots__ = ("run_id",)
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: int
    def __init__(self, run_id: _Optional[int] = ...) -> None: ...

class SyncReleaseCmd(_message.Message):
    __slots__ = ("run_id", "sync_id")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    SYNC_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: int
    sync_id: int
    def __init__(self, run_id: _Optional[int] = ..., sync_id: _Optional[int] = ...) -> None: ...

class TestEvent(_message.Message):
    __slots__ = ("run_id", "test_index", "step", "sync", "finished")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    TEST_INDEX_FIELD_NUMBER: _ClassVar[int]
    STEP_FIELD_NUMBER: _ClassVar[int]
    SYNC_FIELD_NUMBER: _ClassVar[int]
    FINISHED_FIELD_NUMBER: _ClassVar[int]
    run_id: int
    test_index: int
    step: TestStepEvent
    sync: SyncWaitEvent
    finished: TestFinishedEvent
    def __init__(self, run_id: _Optional[int] = ..., test_index: _Optional[int] = ..., step: _Optional[_Union[TestStepEvent, _Mapping]] = ..., sync: _Optional[_Union[SyncWaitEvent, _Mapping]] = ..., finished: _Optional[_Union[TestFinishedEvent, _Mapping]] = ...) -> None: ...

class TestStepEvent(_message.Message):
    __slots__ = ("step_number", "success")
    STEP_NUMBER_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    step_number: int
    success: bool
    def __init__(self, step_number: _Optional[int] = ..., success: _Optional[bool] = ...) -> None: ...

class SyncWaitEvent(_message.Message):
    __slots__ = ("sync_id",)
    SYNC_ID_FIELD_NUMBER: _ClassVar[int]
    sync_id: int
    def __init__(self, sync_id: _Optional[int] = ...) -> None: ...

class TestFinishedEvent(_message.Message):
    __slots__ = ("status",)
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        SUCCESS: _ClassVar[TestFinishedEvent.Status]
        FAIL: _ClassVar[TestFinishedEvent.Status]
        ABORTED: _ClassVar[TestFinishedEvent.Status]
    SUCCESS: TestFinishedEvent.Status
    FAIL: TestFinishedEvent.Status
    ABORTED: TestFinishedEvent.Status
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: TestFinishedEvent.Status
    def __init__(self, status: _Optional[_Union[TestFinishedEvent.Status, str]] = ...) -> None: ...

class LogEvent(_message.Message):
    __slots__ = ("level", "message", "run_id", "test_index", "source", "scope")
    class Level(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        INFO: _ClassVar[LogEvent.Level]
        WARNING: _ClassVar[LogEvent.Level]
        ERROR: _ClassVar[LogEvent.Level]
    INFO: LogEvent.Level
    WARNING: LogEvent.Level
    ERROR: LogEvent.Level
    class Scope(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        EXECUTION: _ClassVar[LogEvent.Scope]
        GLOBAL: _ClassVar[LogEvent.Scope]
    EXECUTION: LogEvent.Scope
    GLOBAL: LogEvent.Scope
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    TEST_INDEX_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    SCOPE_FIELD_NUMBER: _ClassVar[int]
    level: LogEvent.Level
    message: str
    run_id: int
    test_index: int
    source: int
    scope: LogEvent.Scope
    def __init__(self, level: _Optional[_Union[LogEvent.Level, str]] = ..., message: _Optional[str] = ..., run_id: _Optional[int] = ..., test_index: _Optional[int] = ..., source: _Optional[int] = ..., scope: _Optional[_Union[LogEvent.Scope, str]] = ...) -> None: ...
