#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino) 
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------

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