"""Class declarations and ordered Python steps for the C host registry."""
import pytest

from tzen import TzenTestCase, step


class TestYield(TzenTestCase):
    """Verify that a cooperative C step can yield before completing.

    Preconditions: the host harness is connected through binary pipes.
    Procedure: execute the C callback until its third iteration.
    Expected result: one successful step and the completion log.
    """

    target = "Yield and pass"
    companion = False


@pytest.fixture
def host_probe(tmp_path, tzen_case):
    """A host-side resource with normal pytest setup and teardown."""
    path = tmp_path / "sync-observed.txt"
    yield path
    assert path.read_text() == "sync 42 observed before release"
    execution = tzen_case.execution
    if execution is not None and execution.result is not None and execution.result.passed:
        assert any(event.WhichOneof("payload") == "log" and
                   event.log.message == "Yielding test completed" for event in execution.events)


@pytest.fixture
def temporary_probe(tmp_path):
    path = tmp_path / "temporary-probe.txt"
    path.touch()
    yield path
    path.unlink()


class TestSynchronization(TzenTestCase):
    """Verify Python participation at C synchronization point 42.

    Preconditions: a writable host-side probe is available.
    Expected result: every Python step and the C execution succeed.
    """

    target = "Synchronize and pass"

    def __init__(self, host_probe):
        self.probe = host_probe

    @step("Wait for C synchronization point 42", critical=True)
    def wait_for_target(self):
        self.run.wait_sync(42)
        assert self.run.result is None

    @step("Perform and verify the host-side action", critical=True)
    def verify_host_action(self, temporary_probe):
        self.temporary_probe = temporary_probe
        assert temporary_probe.exists()
        self.probe.write_text("sync 42 observed before release")
        assert self.probe.exists()

    @step("Release C to finish its remaining steps", critical=True)
    def release_target(self):
        assert not self.temporary_probe.exists(), "Step fixture was not finalized"
        self.run.release(42)



class TestExpectedFailure(TzenTestCase):
    """Demonstrate propagation of an intentional C failure into pytest.

    Procedure: run the C callback that logs an error and returns FAIL.
    Expected result: pytest reports a failure with the embedded diagnostic.
    This negative example intentionally keeps the full demonstration run red.
    """

    target = "Expected failure"
    companion = False
