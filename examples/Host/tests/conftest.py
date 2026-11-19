"""Show custom messages using the same API available to any pytest user."""
import logging
from pathlib import Path

import pytest

from examples.Host.python.log_output import LogOutput


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if not config.getoption("tzen_config") and not (config.rootpath / "tzen.toml").is_file():
        config.option.tzen_config = str(Path(__file__).resolve().parents[1] / "tzen-host.toml")


@pytest.fixture(autouse=True)
def show_messages(tzen_client, tzen_case):
    output = LogOutput(display=False)
    logger = logging.getLogger("tzen.target.coverage")

    def record_coverage(event):
        logger.log({"INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}[
            event.log.Level.Name(event.log.level)], "[source=%d] %s", event.log.source, event.log.message)

    with (tzen_client.events.subscribe(output),
          tzen_client.events.subscribe(record_coverage, source=7)):
        yield
        execution = tzen_case.execution
        if execution is not None and execution.result is not None:
            output.wait_summary(tzen_client, execution.result)
