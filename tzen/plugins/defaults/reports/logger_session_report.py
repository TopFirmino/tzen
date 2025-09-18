import pluggy
from tzen.tz_types import TZSessionInfo

hookimpl = pluggy.HookimplMarker("tzen")

@hookimpl
def build_session_report(session:TZSessionInfo, config, logger, output_file):
    # Report testuale minimo su console
    status = session.name
    total  = session.total_tests
    execd  = session.executed_tests
    logger.info(f"[REPORT] Session: {session.name} | Status: {status} | Executed: {execd}/{total}")