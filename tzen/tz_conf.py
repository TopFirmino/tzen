#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
from __future__ import annotations
import sys

class TZConfig:
    """ A class to manage configurations. """
    __VARS__ = {}
    __DEPENDENCY_TABLE__ = {}
    
    __all__ = list(__VARS__.keys())
    
    def __getattr__(self, name):
        return self.__VARS__.get(name, None)
    
    def __setattr__(self, name, value):
        TZConfig.__VARS__[name] = value

    def get(self, name, default=None):
        """Get a configuration value by name."""
        return self.__VARS__.get(name, default)
    
sys.modules[__name__] = TZConfig()
