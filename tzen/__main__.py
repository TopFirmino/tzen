#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
from ._tz_cli import app
from ._tz_logging import tz_getLogger



if __name__ == "__main__":
    # Configure the root logger for the tzen application
    logger = tz_getLogger(__name__)
    app()