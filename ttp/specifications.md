# TTP (Tzen Test Protocol)

This document describes the current schema, codecs, and local demonstration as of
2026-10-30. Schema support and application behavior are distinguished below.

## Purpose and implementation

TTP lets a host discover tests on a target, execute a selected test, and receive
progress and a final result. The current demonstration uses a Python host and a
C target subprocess communicating over binary stdin/stdout. Target debug output
goes to stderr or a separate debug file, outside the protocol stream.

Sources:

- `schema/ttp.proto`: message definitions and field numbers.
- `schema/ttp.options`: nanopb string buffer limits.
- `C/ttp.h`, `C/ttp.c`: C protobuf and COBS codecs and command constructors.
- `C/slave_main.c`: sample target and command dispatch.
- `python/ttp.py`: Python codecs and command constructors.
- `python/master.py`: local host, discovery, and execution event iterator.
- `C/generated/ttp.pb.*`, `python/generated/ttp_pb2.py`: generated bindings.

The source API, generated bindings, protobuf package, scripts, and executable use
the TTP name (`Ttp_*`, `TTP_*`, `ttp_*`, `TtpProcessMaster`, `ttp_slave.exe`).
Field numbers, field types, and framing are unchanged by the rename; ordinary
serialized messages remain wire compatible. Generated type and import names have
changed, so source callers must use the new names.

## Wire structure

Each transmitted frame is:

```text
0x00 | COBS(protobuf HostTargetMessage) | 0x00
```

COBS removes zero bytes from the encoded body so zero can delimit frames. There
is no length header, checksum, protocol version, request ID, or test-run ID.
The codecs do not select a serial port, baud rate, or network transport.

`encode_frame` / `Ttp_EncodeFrame` produce both delimiters.
`decode_frame` / `Ttp_DecodeFrame` take only the COBS body, with delimiters removed.
The stream readers discard bytes before an opening delimiter and ignore empty
delimiter intervals. Each frame emitted by the encoder has its own opening and
closing delimiter; callers should preserve both when concatenating frames.
The C reader drops oversized bodies until a delimiter and does not send a NACK
for that drop. EOF ends target input; EOF during an incomplete frame discards it.
The Python reader has no explicit frame-size bound or receive timeout.

Serialization uses proto3, package `ttp`. `uint32` fields are unsigned 32-bit
integers encoded as protobuf varints; strings are UTF-8. Scalar defaults are zero,
false, or empty string and are normally omitted from the encoded nested message.
For example, an omitted `status` in a selected `TestFinished` means `SUCCESS`.

## Envelope and message inventory

`HostTargetMessage` contains `oneof payload`. The selected envelope field identifies
the message type; there is no separate opcode. The numbers below are protobuf
field numbers, not fixed byte offsets. Application messages use one selected
payload. The schema also permits an unset payload; the codecs do not enforce
its presence, and the sample target rejects it as unsupported.

| Envelope field | Tag | Type | Direction and current support |
| --- | ---: | --- | --- |
| `ack` | 1 | `Ack` | Target to host in demo; generic schema message |
| `sync` | 2 | `Sync` | Intended target to host; defined but never emitted by demo |
| `sync_release` | 3 | `SyncRelease` | Host to target; acknowledged only in demo |
| `get_tests` | 50 | `GetTests` | Host to target; implemented |
| `get_test` | 51 | `GetTest` | Host to target; implemented |
| `execute_test` | 52 | `ExecuteTest` | Host to target; implemented |
| `get_tests_response` | 101 | `GetTestsResponse` | Target to host; implemented |
| `get_test_response` | 102 | `GetTestResponse` | Target to host; implemented |
| `test_step` | 103 | `TestStep` | Target to host; emitted during execution |
| `log` | 104 | `Log` | Target to host; demo emits INFO |
| `test_finished` | 105 | `TestFinished` | Target to host; demo produces SUCCESS or FAIL |

The schema groups Ack, Sync, and SyncRelease as common messages but does not
enforce direction. The demo target accepts only the four host commands above;
receiving any other selected payload produces an unsupported-message NACK.

## Payload fields and behavior

Field numbers in this table belong to each nested payload, independently of the
envelope tag.

| Message | Fields (`number: name: type`) | Purpose and current behavior |
| --- | --- | --- |
| `GetTests` | None | Requests the test count. Target replies directly with `GetTestsResponse`, without a preceding ACK. |
| `GetTestsResponse` | `1: total_tests: uint32` | Reports how many tests are registered. Demo reports 2. |
| `GetTest` | `1: index: uint32` | Requests the name of one test by zero-based index. Valid range is `0 <= index < total_tests`. |
| `GetTestResponse` | `1: index: uint32`, `2: name: string` | Returns the requested index and test name. No step count, parameters, or other metadata is included. |
| `ExecuteTest` | `1: index: uint32` | Starts the indexed test. Valid requests receive an ACK followed by execution events; invalid indices receive only a NACK. |
| `Ack` | `1: success: bool`, `2: error_message: string` | `true` accepts the command; `false` is a NACK. Error text explains rejection. An execution ACK means accepted, not passed. Successful demo ACKs have empty error text. |
| `TestStep` | `1: step_number: uint32`, `2: description: string`, `3: success: bool` | Reports a step and its outcome. Demo uses steps 1 and 2. There is no test index, run ID, timestamp, or total-step count. |
| `Log` | `1: level: LogLevel`, `2: message: string` | Carries diagnostic text in the protocol stream. Levels are `INFO=0`, `WARNING=1`, `ERROR=2`. Demo sends INFO with `test started`. |
| `Sync` | `1: sync_id: uint32` | Intended to announce a target synchronization point where execution waits for host release. Encoding is supported; waiting and emission are not implemented in the demo. |
| `SyncRelease` | `1: sync_id: uint32` | Intended to release the corresponding synchronization point. Demo logs the ID and returns a successful ACK for any ID; it tracks no pending sync and resumes no blocked execution. |
| `TestFinished` | `1: status: Status` | Ends the event stream for a test. Status values are `SUCCESS=0`, `FAIL=1`, `ABORTED=2`. Demo chooses SUCCESS/FAIL from the test function's boolean return; ABORTED is defined but not produced. |

## String and buffer limits

The nanopb options allocate fixed C string arrays, including the terminating NUL:

| Field | C array size | Maximum text bytes excluding NUL |
| --- | ---: | ---: |
| `GetTestResponse.name` | 32 | 31 |
| `Ack.error_message` | 64 | 63 |
| `Log.message` | 64 | 63 |
| `TestStep.description` | 64 | 63 |

These are byte limits, not Unicode character counts. The comments in the options
file say 32/64 characters, but `max_size` includes the terminator. C text-copy
helpers truncate to fit. Python bindings do not enforce these nanopb limits;
oversized Python strings can fail decoding on the C side.

The generated C maximum encoded envelope size is 76 bytes. `TTP_MAX_FRAME_SIZE`
is 79 bytes, including delimiters, and the target allows 77 bytes for the COBS
body. These are buffer bounds, not fixed message lengths.

## Discovery and execution flow

The Python host discovers tests sequentially:

```text
Host -> Target: GetTests {}
Target -> Host: GetTestsResponse { total_tests: 2 }
Host -> Target: GetTest { index: 0 }
Target -> Host: GetTestResponse { index: 0, name: "sample_test_1" }
Host -> Target: GetTest { index: 1 }
Target -> Host: GetTestResponse { index: 1, name: "sample_test_2" }
```

For each valid execution, the sample target sends this exact sequence:

```text
Host -> Target: ExecuteTest { index: 0 }
Target -> Host: Ack { success: true }
Target -> Host: Log { level: INFO, message: "test started" }
Target -> Host: TestStep { step_number: 1, description: "calling test function", success: true }
               [target calls the selected test function]
Target -> Host: TestStep { step_number: 2, description: "test function returned", success: result }
Target -> Host: TestFinished { status: SUCCESS or FAIL }
```

Both registered sample functions currently return true. The host execution
iterator yields the initial response and stops immediately if it is not a
successful ACK. After acceptance it yields messages until `TestFinished`.
It does not automatically answer a `Sync` event.

## Current state handling and errors

There is no explicit protocol state enum or enforced session state machine.
The target reads a frame, decodes it, queues the message, and drains the queue
synchronously. Queue depth is four, but the current loop drains after every
successful enqueue. Test execution blocks this same loop; commands are not read
while a test function runs. The queue therefore does not provide concurrent
command handling or cancellation during a running test.

Conceptually the current execution flow is idle -> accepted -> running -> finished
-> idle. A rejected execution stays idle and emits no `TestFinished`. A future
waiting-for-sync state is suggested by the schema, but is absent from the demo.

| Condition | Current target response |
| --- | --- |
| Invalid index for GetTest or ExecuteTest | `Ack(false, "test index out of range")` |
| Unsupported or unset payload | `Ack(false, "unsupported message")` |
| COBS/protobuf decoding failure | `Ack(false, "decode failed")` |
| Queue insertion failure | `Ack(false, "queue full")` (defensive path) |
| Oversized frame | Discard and debug log; no protocol response |

The C codec reports local statuses `OK`, `INVALID_ARGUMENT`, `BUFFER_TOO_SMALL`,
`ENCODE_FAILED`, `DECODE_FAILED`, and `FRAMING_FAILED`, prefixed
`TTP_STATUS_`. These are API return values, not wire messages. Python COBS errors
raise `ValueError`; protobuf parse errors propagate from its runtime.

The host request helper reads the next message without request correlation.
There are no retries, receive timeouts, duplicate detection, cancellation command,
heartbeat, or automatic recovery for a hung test. Only sequential discovery and
execution are demonstrated. Terminal failure/abort policy beyond the boolean
test result, synchronization validation, and concurrent test runs are not defined
by the current application.

## Local regeneration and demonstration

From the repository root, with dependencies and gcc available:

```powershell
cmd /c ttp\generate_pb_files.bat
cmd /c ttp\C\build_slave.bat
python -m ttp.python.master --execute 0
```

The generator recreates both language bindings from `schema/ttp.proto` and the
nanopb options. The build produces `ttp/C/ttp_slave.exe`. The host also supports
`--build`, `--slave-exe`, `--execute`, `--debug-log`, and `--debug-shell`.
This describes a local process demonstration; hardware or serial transport
behavior is not established by that demonstration.
