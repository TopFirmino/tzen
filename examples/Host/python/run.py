"""Launch the C host and exercise real TTP requests over binary pipes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tzen.client import Client
from ttp.python import ttp
from pipe_transport import PipeTransport
from log_output import LogOutput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path,
                        default=Path(__file__).resolve().parents[1] / "C" / "tzen_host.exe")
    args = parser.parse_args()
    output = LogOutput()
    with Client(PipeTransport(args.executable.resolve())) as client, \
            client.events.subscribe(output):
        tests = client.discover()
        if [test.name for test in tests] != ["Yield and pass", "Synchronize and pass", "Expected failure"]:
            raise RuntimeError("Unexpected C test registry")
        for test in tests:
            result = client.run(test.index)
            expected = ttp.TestFinishedEvent.FAIL if test.name == "Expected failure" else ttp.TestFinishedEvent.SUCCESS
            print(f"{test.name}: {ttp.TestFinishedEvent.Status.Name(result.status)}")
            if result.status != expected:
                raise RuntimeError(f"Unexpected result for {test.name}")
            output.wait_summary(client, result)
        result = client.run(1, on_sync=lambda event: False)
        if result.status != ttp.TestFinishedEvent.ABORTED:
            raise RuntimeError("Synchronization abort failed")
        print("Synchronization abort: ABORTED")
        output.wait_summary(client, result)
    print("Pipe integration checks passed")


if __name__ == "__main__":
    main()
