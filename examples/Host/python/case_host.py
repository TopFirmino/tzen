"""Documentation and one Python companion for the C host registry."""
import pytest

from tzen import testcase


@testcase(target="Yield and pass", requirements=["HOST-YIELD-001"], tags=["scheduler"])
def yielding():
    """Verify that a cooperative C step can yield before completing.

    Preconditions: the host harness is connected through binary pipes.
    Procedure: execute the C callback until its third iteration.
    Expected result: one successful step and the completion log.
    """


@pytest.fixture
def host_probe(tmp_path):
    """A host-side resource with normal pytest setup and teardown."""
    path = tmp_path / "sync-observed.txt"
    yield path
    assert path.read_text() == "sync 42 observed before release"


@testcase(target="Synchronize and pass", companion=True,
          requirements=["HOST-SYNC-001"], tags=["synchronization"])
def synchronization(tzen_case, host_probe):
    """Verify explicit Python participation at C synchronization point 42.

    Preconditions: a writable host-side probe is available.
    Procedure: wait for C sync 42, record the host action, then release C.
    Expected result: C completes successfully and emits its completion log.
    """
    with tzen_case.run() as run:
        run.wait_sync(42)
        assert run.result is None
        host_probe.write_text("sync 42 observed before release")
        assert host_probe.exists()
        run.release(42)
    assert run.result.passed
    assert any(event.WhichOneof("payload") == "log" and
               event.log.message == "Yielding test completed" for event in run.events)


@testcase(target="Expected failure", requirements=["HOST-FAIL-001"], tags=["negative"])
def intentional_failure():
    """Demonstrate propagation of an intentional C failure into pytest.

    Procedure: run the C callback that logs an error and returns FAIL.
    Expected result: pytest reports a failure with the embedded diagnostic.
    This negative example intentionally keeps the full demonstration run red.
    """
