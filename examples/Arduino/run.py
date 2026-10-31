"""Run from repository root: python -m examples.Arduino.run --port COM5"""
import argparse
from tzen import Client
from ttp.python import ttp


def show(event):
    print(str(event).strip(), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Discover and execute Arduino C harness tests")
    parser.add_argument("--port", required=True)
    parser.add_argument("--verify", action="store_true", help="Also verify failure, abort, busy, and sync mismatch")
    args = parser.parse_args()
    with Client.serial(args.port) as client:
        tests = client.discover()
        print("Tests:", tests, flush=True)
        for name in ("LED cycle", "LED host sync"):
            result = client.run(name, on_event=show)
            assert result.passed, result
            print(f"PASS: {name}, run={result.run_id}", flush=True)
        if args.verify:
            result = client.run("Expected failure", on_event=show)
            assert result.status == ttp.TestFinishedEvent.FAIL
            result = client.run("LED host sync", on_event=show, on_sync=lambda event: False)
            assert result.status == ttp.TestFinishedEvent.ABORTED
            from tzen import CommandError
            run_id = client.start(1)
            while True:
                event = client.receive()
                if event.WhichOneof("payload") == "test_event" and event.test_event.WhichOneof("event") == "sync":
                    break
            for command, expected in (
                (ttp.make_execute_test(0, run_id+1), ttp.RESULT_ERR_BUSY),
                (ttp.make_sync_release(run_id, 99), ttp.RESULT_ERR_NOT_FOUND)):
                try:
                    client.request(command)
                except CommandError as error:
                    assert error.response.status == expected
                else:
                    raise AssertionError("expected command rejection")
            client.abort(run_id)
            event = client.receive()
            assert event.test_event.finished.status == ttp.TestFinishedEvent.ABORTED
            # A CRC-damaged execute must not reach the harness.
            raw = bytearray(ttp.cobs_decode(ttp.encode_frame(ttp.make_execute_test(1, 999, seq_id=999))[1:-1]))
            raw[-1] ^= 1
            client.transport.write(b"\x00" + ttp.cobs_encode(raw) + b"\x00")
            # Aborting during a yielded step also has to run teardown.
            run_id = client.start(0)
            client.abort(run_id)
            while True:
                event = client.receive()
                if event.WhichOneof("payload") == "test_event" and event.test_event.WhichOneof("event") == "finished":
                    assert event.test_event.finished.status == ttp.TestFinishedEvent.ABORTED
                    break
            print("PASS: intentional failure, sync abort, busy, wrong sync ID, CRC rejection, running abort", flush=True)


if __name__ == "__main__":
    main()
