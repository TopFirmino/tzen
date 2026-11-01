# TTP (Tzen Test Protocol)

This specification describes the current `schema/ttp.proto` and
`schema/ttp.options`. The C harness implements discovery and queued execution
with independently polled workers; see its README for scheduling and locking.

## Scope and code layout

`ttp` contains transmission protocol code only: schema/options, generated bindings,
C protobuf codecs in `C/src` with headers in `C/inc`, and Python protobuf codecs
and message constructors in `python`. Include both `C/inc` and `C/generated`,
as well as nanopb headers, when building C code.

The C harness engine and test lifecycle belong to `../testharness-c`.
The Python harness client and USB serial transport belong to `../tzen`.
The runnable Arduino firmware and Python example belong to `../examples/Arduino`.

Both bindings use the package-less schema. The C codec APIs are
`Ttp_EncodeHostToTarget`, `Ttp_DecodeHostToTarget`, `Ttp_EncodeTargetToHost`, and
`Ttp_DecodeTargetToHost`. These APIs handle protobuf only. The former `...Frame`
and `Ttp_DecodeHostToTargetPayload` APIs and framing-size constants were removed.
Ignore output on decoder errors. Python `decode_message` defaults to `TargetToHost`
and accepts `HostToTarget` as its second argument. Python `encode_frame`,
`decode_frame`, COBS helpers and `MAX_FRAME_SIZE` now live in `tzen.framing`.
The C harness owns COBS/CRC directly in `tzen.c`. Message constructors build data;
command execution and response correlation are implemented outside this folder.

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
parse protobuf. The C harness discards CRC mismatches; Python harness framing raises
`ValueError("CRC16 mismatch")`. Missing trailers and malformed COBS
are framing errors. Rejected frames must not reach command dispatch. The
harness rejects malformed/CRC-invalid frames without a response because the
request sequence ID cannot be trusted.

Frame decoders accept the COBS body with delimiters removed. No length field is
needed because the zero delimiters bound each COBS body, and the decoded body's
last two bytes are always the CRC. Protobuf does not itself delimit top-level
messages on a stream; its internal length fields apply to individual fields.
CRC detects accidental corruption with a finite probability of undetected errors;
it is not an absolute correctness guarantee or authentication mechanism.

The C harness and Python `tzen.framing` enforce this CRC framing on both directional envelopes.
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
The `tzen.Client` assigns wire sequence IDs in `request()`, starting at 1 and
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
| 2 | RESULT_ERR_BUSY | Request queue is full or this run ID is already queued/active. |
| 3 | RESULT_ERR_NOT_FOUND | No corresponding active test/run or synchronization point exists. |
| 4 | RESULT_ERR_INVALID | Command is invalid in the current state. |

The target checks transport validity, then BUSY, then index validity on execution. Abort and
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
| GetTestInfoResp | `1: index: uint32`, `2: name: string`, `3: total_steps: uint32` | Returns index, display name, and step count for progress reporting. Zero-step descriptors are discoverable but cannot execute in the current harness. |
| ExecuteTestCmd | `1: index: uint32`, `2: run_id: uint32` | Selects a test and assigns a host-chosen run ID for subsequent events. |
| AbortTestCmd | `1: run_id: uint32` | Requests abort of the matching run; the schema provides ABORTED as its terminal result. The sample acknowledges abort then emits ABORTED and clears the active state. |
| SyncReleaseCmd | `1: run_id: uint32`, `2: sync_id: uint32` | Identifies both the run and synchronization point to resume. |

`seq_id` identifies one command/response exchange. `run_id` identifies an execution
across multiple commands and events; for example, execute and abort have different
sequence IDs but may refer to the same run. The harness accepts any uint32 run ID, including zero, and
permits reuse after the terminal transport attempt. The Python execution iterator allocates increasing
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
| TestStepEvent | `1: step_number: uint32`, `2: success: bool` | Reports a completed step outcome. The engine emits it automatically; explanatory text uses LogEvent. The sample emits steps 1 and 2; failure policy for real tests remains application-specific. |
| SyncWaitEvent | `1: sync_id: uint32` | Announces that the run is waiting until released with the matching run ID and sync ID. The sample uses sync ID 1 and has no wait timeout. |
| TestFinishedEvent | `1: status: Status` | Reports `SUCCESS=0`, `FAIL=1`, or `ABORTED=2`. This result is separate from command acceptance. |
| LogEvent | `1: level: Level`, `2: message: string`, `3: run_id: uint32`, `4: test_index: uint32` | Reports `INFO=0`, `WARNING=1`, or `ERROR=2`, diagnostic text and execution identity. |

`LogEvent` is directly inside `TargetToHost`, outside `TestEvent`. Its new
`run_id` (tag 3) and `test_index` (tag 4) identify the originating execution,
including logs from setup and teardown. There is no timestamp. Zero is a valid
run ID, not a global-log marker. The new scalar fields preserve previous tags;
older decoders may ignore them, but peers must update their receive bounds.

## Message flow examples

Illustrative discovery and execution (values are examples, not a fixed registry):

```text
Host -> Target: HostToTarget { seq_id: 1, get_tests: {} }
Target -> Host: TargetToHost { seq_id: 1, status: RESULT_OK, tests_count: { total_tests: 2 } }
Host -> Target: HostToTarget { seq_id: 2, get_test_info: { index: 0 } }
Target -> Host: TargetToHost { seq_id: 2, status: RESULT_OK, test_info: { index: 0, name: "example", total_steps: 2 } }
Host -> Target: HostToTarget { seq_id: 3, execute_test: { index: 0, run_id: 100 } }
Target -> Host: TargetToHost { seq_id: 3, status: RESULT_OK }
Target -> Host: TargetToHost { seq_id: 0, test_event: { run_id: 100, test_index: 0, step: { step_number: 1, success: true } } }
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

`TestStepEvent` tag 3 and the name `description` are reserved. They must not be
reused. Explanatory text belongs in `LogEvent.message`. Older step descriptions
are ignored as unknown fields by regenerated receivers, subject to frame bounds.
Deploy regenerated host and firmware together to include execution identities
in logs and the updated maximum frame bound.

## Execution semantics

The wire schema represents command acceptance, step reports, synchronization
waits, and terminal results. Step results are generated internally when a step completes (after release for
a synchronization wait); yielding or aborting an unfinished step adds no step
result. Scheduling, setup/teardown, command queues, and
execution state belong to the C harness, not the transmission codec. See
`../testharness-c/README.md` for the implementation contract and
`../tzen/README.md` for host orchestration and timeout behavior.

## Nanopb storage limits

`schema/ttp.options` matches the package-less message names:

| Selector | max_size / C array bytes | Maximum UTF-8 text bytes excluding NUL |
| --- | ---: | ---: |
| GetTestInfoResp.name | 32 | 31 |
| LogEvent.message | 64 | 63 |

`max_size` includes the terminating NUL. These are byte limits, not Unicode
character counts. Python protobuf does not enforce nanopb string limits;
applications must respect them for C interoperability. There is no Ack error
string to configure in the new schema. All other fields are scalar or nested
messages, requiring no string/repeated-field size options.

Temporary generation against the current schema/options produces static arrays
for both strings and these maximum encoded sizes:

| Message | Maximum protobuf bytes |
| --- | ---: |
| HostToTarget | 20 |
| TargetToHost | 89 |
| TestEvent | 22 |
| TestStepEvent | 8 |
| LogEvent | 79 |
| GetTestInfoResp | 45 |

These are bounds, not fixed lengths. With two CRC bytes, the frame-size bound is
`(N + 2) + floor((N + 2) / 254) + 3`, including both delimiters. Allocate
25 bytes for a framed HostToTarget and 94 bytes for a framed TargetToHost.
The C `TTP_MAX_MESSAGE_SIZE` macro uses the larger envelope bound (89 protobuf
bytes). The harness adds two CRC bytes, giving a 91-byte decoded payload and
a 94-byte complete frame bound. TTP encode/decode APIs do not add or check CRC;
framing belongs to the harness.

## Validation and regeneration

```powershell
cmd /c ttp\generate_pb_files.bat
python -m unittest discover -s ttp/tests -v
```

The generator recreates both language bindings. Codec tests compile a C bridge
with warnings treated as errors and cover both directions, payload alternatives,
maximum-size messages, small encode buffers and malformed protobuf. Framing,
CRC, worker queues and lifecycle tests live in `../testharness-c/tests`; Python
framing/client tests live in `../tzen/tests`. Live Arduino verification is recorded in
`../examples/Arduino/verification.md`.
