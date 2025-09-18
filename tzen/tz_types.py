#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This module defines the types used in the TZen testing framework."""

from __future__ import annotations
from enum import Enum, auto
from typing import Mapping
from dataclasses import dataclass  

class TZTestStatusType(Enum):
    """Enumeration """
    IDLE = auto()
    RUNNING = auto()
    PASSED = auto()
    FAILED = auto()
    
@dataclass
class TZTestInfo:
    """Dataclass to represent the status of a test. It contains all the informations regarding testcases."""
    name: str
    total_steps: int
    current_step: int = 1
    status: TZTestStatusType = TZTestStatusType.IDLE
    error:str = None
    start:int = 0
    end:int = 0

class TZEventType(Enum):
    """Enumeration of event types in the testing system."""
    TEST_STARTED = auto()
    TEST_TERMINATED = auto()
    STEP_STARTED = auto()
    STEP_TERMINATED = auto()
    SESSION_STARTED = auto()
    SESSION_TERMINATED = auto()
    
class TZSessionStatusType(Enum):

    """Enumeration """
    IDLE = auto()
    RUNNING = auto()
    PASSED = auto()
    FAILED = auto()
    
@dataclass
class TZSessionInfo:
    """Dataclass to represent the status of a test session."""
    name: str
    total_tests: int
    executed_tests: int = 0
    current_test: str = ""
    passed_tests:int = 0
    failed_tests:int = 0
    start:int = 0
    end:int = 0
    status:TZSessionStatusType = TZSessionStatusType.IDLE
    details: Mapping[str, TZTestInfo] = None
    