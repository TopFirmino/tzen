#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
from __future__ import annotations
import pluggy
import tzen

PLUGIN_PROJECT_NAME = tzen.__name__

hookspec = pluggy.HookspecMarker(PLUGIN_PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PLUGIN_PROJECT_NAME)


_PM:pluggy.PluginManager | None = None

def get_pm() -> pluggy.PluginManager:
    global _PM
    if _PM is None:
        _PM = pluggy.PluginManager(PLUGIN_PROJECT_NAME)
    return _PM

