# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Example of an application-owned log sink configured in tzen-host.toml."""
import json
from pathlib import Path

from tzen import TargetLog


class Coverage2Sink:
    def __init__(self, path: str):
        # Resolve relative paths from the Host example directory.
        self.path = Path(__file__).resolve().parents[1] / path

    def write(self, record: TargetLog) -> None:
        execution = record.execution
        sample = {
            "source": record.source,
            "run_id": execution.run_id if execution else None,
            "test_index": execution.test_index if execution else None,
            "message": record.message,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(sample) + "\n")
