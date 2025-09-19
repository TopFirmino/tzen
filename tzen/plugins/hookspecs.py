#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino) 
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""Declaration of TZen hooks"""

import pluggy
from pathlib import Path
from ..tz_types import TZSessionInfo 
from typing import Mapping, Any

hookspec = pluggy.HookspecMarker("tzen")

@hookspec
def build_session_report(session:TZSessionInfo, config:Mapping[str, Any], logger, output_file: Path):
    """Used to generate the session report. This hook allows for customization of the report content and format.
    This will be executed immediately after the session has ended.
    """

@hookspec
def build_docs(organizer, config:Mapping[str, Any], logger, output_folder: Path):
    """ Used in order to generate the test documentation. It will be executed once loaded the testcases and the organizer has been created."""
