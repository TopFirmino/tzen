# TTP (Tzen Test Protocol)

This specification describes the current `schema/ttp.proto` and
`schema/ttp.options` as of 2026-10-30. It describes the schema contract and the current C/Python local implementation.

## Current implementation status

The schema now has two directional envelopes, request sequence IDs, execution run
IDs, structured result codes, abort commands, and nested execution events.
There is no protobuf `package` declaration. Nanopb option selectors and generated
C type names therefore have no `ttp.` / `ttp_` package prefix.

Both language bindings have been regenerated from this schema and its options.
The C codecs/target and Python wrapper/master now use `HostToTarget` and
`TargetToHost`, including CRC-protected framing. The C APIs have explicit direction
names: `Ttp_EncodeHostToTarget`, `Ttp_DecodeHostToTarget`,
`Ttp_EncodeTargetToHost`, and `Ttp_DecodeTargetToHost`, with corresponding
`...Frame` APIs for COBS/CRC framing. Callers initialize generated structs and
select their command/payload/event tags directly; the old ACK constructors are
removed. Raw APIs serialize protobuf only. Ignore decoder output on any error.

Python re-exports the new schema types and result codes. `encode_message` and
`encode_frame` accept either envelope; `decode_message` and `decode_frame` default
to `TargetToHost` and accept `HostToTarget` as an explicit second argument.
Command helpers are `make_get_tests`, `make_get_test_info`, `make_execute_test`,
`make_abort_test`, and `make_sync_release`.

The sample registry contains two tests with two steps each. `sample_test_1`
completes immediately. `sample_test_2` emits step 1 and waits at sync point 1;
a matching release emits step 2 and SUCCESS. Abort while waiting emits ABORTED.
Both are cooperative demonstrations, not a scheduler for arbitrary blocking test
functions. FAIL is represented and encodable but not produced by these samples.

The new schema is wire incompatible with the previous envelope: message tags,
nesting, and some field meanings have changed. Both peers must migrate together.
There is no version negotiation field.

## Serialization and transport

Messages use proto3. Integers are `uint32` (0 through 4294967295), encoded as
varints; booleans and enums also use varints. Strings carry UTF-8 bytes. Nested
messages are length-delimited. Field numbers below are protobuf tags, not byte
offsets. A `oneof` selects at most one alternative; protobuf also permits it to
be unset. The application must validate required selections and semantic rules.

Scalar fields default to zero, false, or empty string and have no explicit
presence tracking. Defaults can be omitted on the wire. For example, omitted
`status` means `RESULT_OK` in `TargetToHost`, or `SUCCESS` in
`TestFinishedEvent`. The comment describing `total_steps` as optional does not
make it a proto3 `optional` field: absent and explicitly zero are indistinguishable.

TTP frames have the following structure in both directions:

```text
0x00 | COBS(protobuf bytes | CRC16 high byte | CRC16 low byte) | 0x00
```

CRC-16/CCITT-FALSE parameters: polynomial `0x1021`, initial value `0xFFFF`,
no input/output reflection, and final XOR `0x0000`. The standard check input
ASCII `123456789` produces `0x29B1`. CRC covers only the serialized protobuf
bytes, excluding delimiters, COBS code bytes, and the CRC itself. Append its
high byte first, then its low byte, and COBS-encode the complete result. This
also escapes any zero bytes in the CRC. CRC is a framing trailer, not a protobuf
field, so no schema or nanopb options change is needed.

Receivers split the stream on zero delimiters, COBS-decode the body, require
at least two decoded bytes, verify and remove the CRC trailer, and only then
parse protobuf. A CRC mismatch returns `TTP_STATUS_CRC_FAILED` in C and raises
`ValueError("CRC16 mismatch")` in Python. Missing trailers and malformed COBS
are framing errors. Rejected frames must not reach command dispatch. The
sample target discards malformed/CRC-invalid frames and writes a debug diagnostic;
it sends no response because the request sequence ID cannot be trusted.

Frame decoders accept the COBS body with delimiters removed. No length field is
needed because the zero delimiters bound each COBS body, and the decoded body's
last two bytes are always the CRC. Protobuf does not itself delimit top-level
messages on a stream; its internal length fields apply to individual fields.
CRC detects accidental corruption with a finite probability of undetected errors;
it is not an absolute correctness guarantee or authentication mechanism.

Both C and Python codecs enforce this CRC framing on both directional envelopes.
CRC-less frames are no longer supported. There is no schema-defined timestamp, retry mechanism,
timeout, or transport configuration.

## Host-to-target envelope

`HostToTarget` carries one command per request.

| Field | Tag | Type | Meaning |
| --- | ---: | --- | --- |
| `seq_id` | 1 | uint32 | Host increments this for each request; use a nonzero value so the response can be distinguished from an event. |
| `get_tests` | 2 | GetTestsCmd | Requests the registered test count. |
| `get_test_info` | 3 | GetTestInfoCmd | Requests metadata for one test. |
| `execute_test` | 4 | ExecuteTestCmd | Requests execution with a host-selected run ID. |
| `abort_test` | 5 | AbortTestCmd | Requests cancellation of a run. |
| `sync_release` | 6 | SyncReleaseCmd | Releases a synchronization point for a run. |

The five command fields form `oneof cmd`. An unset command is representable but
is rejected with RESULT_ERR_INVALID when its sequence ID is nonzero.
The Python master assigns wire sequence IDs in `send()`, starting at 1 and
wrapping from 4294967295 to 1. It overwrites any supplied command sequence ID.
The C target silently discards requests with sequence ID zero. Duplicate requests
are not detected or cached; each is processed again.

## Target-to-host envelope

`TargetToHost` carries either a direct response or an asynchronous event.

| Field | Tag | Type | Meaning |
| --- | ---: | --- | --- |
| `seq_id` | 1 | uint32 | Nonzero: echoes the request ID. Zero: asynchronous event. |
| `status` | 2 | ResultCode | Command result, meaningful only for nonzero `seq_id`. |
| `tests_count` | 3 | GetTestsResp | Successful GetTests response data. |
| `test_info` | 4 | GetTestInfoResp | Successful GetTestInfo response data. |
| `test_event` | 5 | TestEvent | Asynchronous step, sync, or completion event. |
| `log` | 6 | LogEvent | Asynchronous diagnostic event. |

The four data fields form `oneof payload`. For a successful discovery command,
select its corresponding response payload. Execute, abort, and sync release
have no dedicated response data: return the echoed `seq_id` and `RESULT_OK`
with no payload. Error responses carry a result code without a payload.
For asynchronous messages, use `seq_id=0` and select `test_event` or `log`;
`status` has no meaning in this case. These relationships are described by the
schema comments but are not enforced by protobuf encoding.

`ResultCode` replaces the old ACK/NACK message and free-text error field:

| Value | Name | Meaning |
| ---: | --- | --- |
| 0 | RESULT_OK | Command accepted or completed successfully as appropriate. Execution acceptance does not imply that the test passed. |
| 1 | RESULT_ERR_INDEX | Test index is outside `0 <= index < total_tests`. |
| 2 | RESULT_ERR_BUSY | A test is already executing. |
| 3 | RESULT_ERR_NOT_FOUND | No corresponding active test/run or synchronization point exists. |
| 4 | RESULT_ERR_INVALID | Command is invalid in the current state. |

The sample target checks BUSY before index validity on execution. Abort and
release return NOT_FOUND for a missing run or mismatched identity; release also
requires a pending matching sync point. Unset/unknown commands return INVALID.
There is no command error text field; LogEvent has no sequence correlation.

## Command and response payloads

Field numbers here are local to each nested message.

| Message | Fields (`tag: name: type`) | Behavior |
| --- | --- | --- |
| GetTestsCmd | None | Requests how many tests are registered. |
| GetTestsResp | `1: total_tests: uint32` | Returns the count; zero represents an empty registry. |
| GetTestInfoCmd | `1: index: uint32` | Selects a test by zero-based index. |
| GetTestInfoResp | `1: index: uint32`, `2: name: string`, `3: total_steps: uint32` | Returns index, display name, and step count for progress reporting. Meaning of a zero/unknown step count is not specified. |
| ExecuteTestCmd | `1: index: uint32`, `2: run_id: uint32` | Selects a test and assigns a host-chosen run ID for subsequent events. |
| AbortTestCmd | `1: run_id: uint32` | Requests abort of the matching run; the schema provides ABORTED as its terminal result. The sample acknowledges abort then emits ABORTED and clears the active state. |
| SyncReleaseCmd | `1: run_id: uint32`, `2: sync_id: uint32` | Identifies both the run and synchronization point to resume. |

`seq_id` identifies one command/response exchange. `run_id` identifies an execution
across multiple commands and events; for example, execute and abort have different
sequence IDs but may refer to the same run. The sample accepts any uint32 run ID, including zero, and
permits reuse after completion. The Python execution iterator allocates increasing
nonzero run IDs by default, or accepts an explicit ID. There is no run history or
duplicate suppression. Receivers must not infer the run ID from the sequence ID
or test index.

## Execution and diagnostic events

`TargetToHost.test_event` contains a `TestEvent` wrapper:

| Field | Tag | Type | Meaning |
| --- | ---: | --- | --- |
| `run_id` | 1 | uint32 | Host-selected execution ID from ExecuteTestCmd. |
| `test_index` | 2 | uint32 | Index of the test producing the event. |
| `step` | 3 | TestStepEvent | Step result. |
| `sync` | 4 | SyncWaitEvent | Target has reached a synchronization wait point. |
| `finished` | 5 | TestFinishedEvent | Terminal execution result. |

`step`, `sync`, and `finished` form `oneof event`. The wrapper supplies execution
identity for all three alternatives.

| Event | Fields (`tag: name: type`) | Meaning |
| --- | --- | --- |
| TestStepEvent | `1: step_number: uint32`, `2: success: bool`, `3: description: string` | Reports a step outcome and description. The sample emits steps 1 and 2; failure policy for real tests remains application-specific. |
| SyncWaitEvent | `1: sync_id: uint32` | Announces that the run is waiting until released with the matching run ID and sync ID. The sample uses sync ID 1 and has no wait timeout. |
| TestFinishedEvent | `1: status: Status` | Reports `SUCCESS=0`, `FAIL=1`, or `ABORTED=2`. This result is separate from command acceptance. |
| LogEvent | `1: level: Level`, `2: message: string` | Reports `INFO=0`, `WARNING=1`, or `ERROR=2` and diagnostic text. |

`LogEvent` is directly inside `TargetToHost`, outside `TestEvent`; it has no
`run_id`, `test_index`, or timestamp. Logs cannot be explicitly assigned to a
run from their fields alone.

## Message flow examples

Illustrative discovery and execution (values are examples, not a fixed registry):

```text
Host -> Target: HostToTarget { seq_id: 1, get_tests: {} }
Target -> Host: TargetToHost { seq_id: 1, status: RESULT_OK, tests_count: { total_tests: 2 } }
Host -> Target: HostToTarget { seq_id: 2, get_test_info: { index: 0 } }
Target -> Host: TargetToHost { seq_id: 2, status: RESULT_OK, test_info: { index: 0, name: "example", total_steps: 2 } }
Host -> Target: HostToTarget { seq_id: 3, execute_test: { index: 0, run_id: 100 } }
Target -> Host: TargetToHost { seq_id: 3, status: RESULT_OK }
Target -> Host: TargetToHost { seq_id: 0, test_event: { run_id: 100, test_index: 0, step: { step_number: 1, success: true, description: "ready" } } }
Target -> Host: TargetToHost { seq_id: 0, test_event: { run_id: 100, test_index: 0, sync: { sync_id: 7 } } }
Host -> Target: HostToTarget { seq_id: 4, sync_release: { run_id: 100, sync_id: 7 } }
Target -> Host: TargetToHost { seq_id: 4, status: RESULT_OK }
Target -> Host: TargetToHost { seq_id: 0, test_event: { run_id: 100, test_index: 0, finished: { status: SUCCESS } } }
```

An accepted abort uses a new command sequence ID and the active run ID:

```text
Host -> Target: HostToTarget { seq_id: 5, abort_test: { run_id: 101 } }
Target -> Host: TargetToHost { seq_id: 5, status: RESULT_OK }
Target -> Host: TargetToHost { seq_id: 0, test_event: { run_id: 101, test_index: 0, finished: { status: ABORTED } } }
```

The sample sends the direct command response before events caused by that
command. A rejected command returns its nonzero sequence ID and error status,
without response data or a new completion event.

## Execution states and remaining policy decisions

The schema has no explicit state field. The sample target tracks idle versus
active execution and a pending sync ID, implementing these transitions:

| Trigger | Conceptual behavior |
| --- | --- |
| Valid ExecuteTest while idle | Accept command and begin the selected run. |
| ExecuteTest while a run is active | RESULT_ERR_BUSY. |
| Test reaches sync point | Emit SyncWaitEvent and wait for matching release. |
| Matching SyncRelease | Accept release and resume the run. |
| Completion | Emit TestFinishedEvent with SUCCESS or FAIL; return to idle. |
| Accepted AbortTest | End the identified run with ABORTED; return to idle. |

The sample target has one active run. Its sync wait returns control to the input
loop, so discovery, busy checks, abort, and release remain available while waiting.
There is no queue, background thread, or preemption of blocking application code.
Discovery is allowed during a run. Completion clears the active run and pending
sync before sending the terminal event. A later abort or repeated release returns
NOT_FOUND. Commands are processed sequentially in input order, resolving
release/abort races in that order. EOF terminates the process without an extra
terminal event. There are no retry, timeout, or disconnect-recovery policies.

`TtpProcessMaster.request()` allows one outstanding request and matches the
response sequence ID, preserving intervening asynchronous events in a deque.
`receive()` drains those events first. An unrelated nonzero response raises an
error. The API is single-threaded; it does not support concurrent request callers.
`execute_test(index, run_id=None, auto_release=True)` yields acceptance and events,
checks test/run identity, automatically releases sync points by default, and stops
at the matching terminal event. Set `auto_release=False` to handle sync explicitly
with `release_sync()` or `abort_test()`. Discovery exposes both `get_manifest()`
and `get_test_info()`, the latter including `total_steps`.

The host bounds its incoming COBS body to 100 bytes (102-byte frame minus two
delimiters) and drops oversized frames until a delimiter. The target has the same
shared frame bound. Host CRC/protobuf exceptions propagate to the caller;
requests have no receive timeout, and queued events have no fixed count limit.

## Nanopb storage limits

`schema/ttp.options` matches the package-less message names:

| Selector | max_size / C array bytes | Maximum UTF-8 text bytes excluding NUL |
| --- | ---: | ---: |
| GetTestInfoResp.name | 32 | 31 |
| TestStepEvent.description | 64 | 63 |
| LogEvent.message | 64 | 63 |

`max_size` includes the terminating NUL. These are byte limits, not Unicode
character counts. Python protobuf does not enforce nanopb string limits;
applications must respect them for C interoperability. There is no Ack error
string to configure in the new schema. All other fields are scalar or nested
messages, requiring no string/repeated-field size options.

Temporary generation against the current schema/options produces static arrays
for all three strings and these maximum encoded sizes:

| Message | Maximum protobuf bytes |
| --- | ---: |
| HostToTarget | 20 |
| TargetToHost | 97 |
| TestEvent | 87 |
| TestStepEvent | 73 |
| LogEvent | 67 |
| GetTestInfoResp | 45 |

These are bounds, not fixed lengths. With two CRC bytes, the frame-size bound is
`(N + 2) + floor((N + 2) / 254) + 3`, including both delimiters. Allocate
25 bytes for a framed HostToTarget and 102 bytes for a framed TargetToHost.
The C shared buffer macros use the larger envelope bound (97 protobuf bytes),
giving a 99-byte decoded frame payload and a 102-byte complete frame bound. Raw protobuf encode/decode APIs do not add or check a CRC; CRC applies
to the frame APIs.

## Validation and regeneration

From the repository root, with the Python dependencies and gcc available:

```powershell
cmd /c ttp\generate_pb_files.bat
cmd /c ttp\C\build_slave.bat
python -m ttp.python.master --execute 0
python -m ttp.python.master --execute 1
python -m unittest discover -s ttp/tests -v
```

The generator recreates both binding sets from the current schema and options.
The build produces `ttp/C/ttp_slave.exe`; the Python launcher also supports
`--build`, `--slave-exe`, `--debug-log`, and `--debug-shell`.

Regression tests compile C bridges and the target with warnings treated as errors.
They cover both directional codecs and message alternatives, boundary-size
payloads, CRC check vectors, every single-bit change in a representative payload
and trailer, malformed/truncated frames, discovery, sequence correlation and
wraparound, run identity, busy and invalid-command errors, sync mismatch/release,
abort, zero run IDs, and preservation of events while awaiting responses. Corrupt,
zero-sequence, and oversized requests are verified to leave target execution idle.
Local sample executions complete through both normal and sync paths. Physical
transport behavior, hardware tests, and integration of real blocking test
functions remain unvalidated.
