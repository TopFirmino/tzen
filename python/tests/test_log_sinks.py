import binascii
import logging

import pytest
from tzen.config import Settings

from ttp.python import ttp


class Transport:
    def close(self):
        pass


def test_binary_sink_after_logging(tmp_path, caplog):
    config = tmp_path / "tzen.toml"
    config.write_text('''
[tzen.transport]
class = "unused:Transport"
[[tzen.logging.sources]]
source = 7
logger = "coverage"
[tzen.logging.sources.sink]
class = "tzen:FileLogSink"
[tzen.logging.sources.sink.parameters]
format = "binary"
path = "out/coverage.bin"
''')
    output = tmp_path / "out/coverage.bin"
    with Settings.load(config).open_client(Transport()) as client:
        def emit(source, message):
            client.events.dispatch(ttp.TargetToHost(log=ttp.LogEvent(source=source, message=message)))

        caplog.set_level(logging.WARNING)
        emit(8, "ignored")
        assert not output.exists()
        emit(7, "AP8=")
        emit(7, "Cg==")
        assert output.read_bytes() == bytes([0, 255, 10])
        assert not caplog.records
        caplog.set_level(logging.INFO)
        with pytest.raises(binascii.Error):
            emit(7, "invalid binary!")
        assert caplog.records[-1].message == "invalid binary!"
        assert output.read_bytes() == bytes([0, 255, 10])
