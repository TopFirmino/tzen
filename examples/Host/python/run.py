# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Launch the C or Ada host and exercise real TTP requests over binary pipes."""
import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pipe_transport import PipeTransport  # noqa: E402
from tzen import TestStatus  # noqa: E402
from tzen.config import Settings  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slave", choices=("c", "ada"), help="Host implementation (default: c)")
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s  %(message)s", stream=sys.stdout)
    host_directory = Path(__file__).resolve().parents[1]
    settings = Settings.load(host_directory / "tzen-host.toml")
    slave = args.slave or settings.parameters.get("slave", "c")
    if slave == "ada":
        settings = Settings.load(host_directory / "ADA" / "tzen-host.toml")
    executable = args.executable.resolve() if args.executable else settings.parameters.get("executable")
    transport = PipeTransport(executable, slave=slave)
    with settings.open_client(transport) as client:
        tests = client.discover()
        if [test.name for test in tests] != ["Yield and pass", "Synchronize and pass", "Expected failure"]:
            raise RuntimeError(f"Unexpected {slave} test registry")
        for test in tests:
            result = client.run(test.index)
            for record in result.logs:
                logging.getLogger(test.name).log(record.level, "%s", record.message)
            expected = TestStatus.FAIL if test.name == "Expected failure" else TestStatus.SUCCESS
            print(f"{test.name}: {TestStatus(result.status).name}")
            if result.status != expected:
                raise RuntimeError(f"Unexpected result for {test.name}")
            settings.receive_after_test(client, result)
        result = client.run(1, on_sync=lambda event: False)
        if result.status != TestStatus.ABORTED:
            raise RuntimeError("Synchronization abort failed")
        print("Synchronization abort: ABORTED")
        settings.receive_after_test(client, result)
    print("Pipe integration checks passed")


if __name__ == "__main__":
    main()
