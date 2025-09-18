#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This modules provides the feature in order to create and execute a testcase."""

from __future__ import annotations
from ._tz_logging import TZTestLogger
from .tz_types import TZEventType, TZTestInfo, TZTestStatusType
from dataclasses import dataclass
from enum import Enum, auto
from typing import Mapping, List
import inspect
from pathlib import Path
import time
import hashlib

_TZEN_TESTS_:Mapping[str, TZTest] = {}


class TZTest:
    """This class provides a container for testcases. It is used in order to provide abstraction and dependency injection. 
    test_class parameter is a Class. It is used to store the testcases and their steps."""
    
    def __init__(self, name:str, test_class: type, steps = []):
        self.name = name
        self.doc = test_class.__doc__
        self.test_class = test_class
        self.test_instance = None
        self.steps = steps
        self.subscribers = {event:[] for event in TZEventType.__members__.values()}
        self.info = TZTestInfo(name=self.name, total_steps=len(steps))
        self.uuid = hashlib.sha256(self.name.encode()).hexdigest()
        
    def attach(self, subscriber, event):
        if event in self.subscribers:
            self.subscribers[event].append(subscriber)

    def notify(self, event):
        if event in self.subscribers:
            for subscriber in self.subscribers[event]:
                subscriber(self)
    
    def get_path(self) -> Path:
        """Returns the absolute path of the test class."""
        module = inspect.getmodule(self.test_class)
        return Path(module.__spec__.origin).joinpath(self.test_class.__name__) 
    
    def run(self) -> bool:
        """This method is used to run the testcases. It will create an instance of the test_class and run the steps."""
        
        # Setup the test class and test logger
        test = self.test_class()
        test.logger = TZTestLogger(self.name, len(self.steps))
        self.logger = test.logger
        
        
        self.logger.info(f"Starting Testcase", show_step_info=False)
        self.info.start = int(time.time())
        self.info.status = TZTestStatusType.RUNNING
        self.notify(TZEventType.TEST_STARTED)
        
        
        # Execute test steps
        test_res:bool = True 
        for i, step in enumerate(self.steps):
            test.logger.set_test_step(i + 1)
            self.info.current_step = i + 1
            
            self.notify(TZEventType.STEP_STARTED)
            step_res:bool = False
            try:
                _res = step(test)
                step_res = _res if _res is not None else True
            
            except Exception as e:
                self.info.error = str(e)
                test.logger.error(e)
            
            test_res &= step_res
            self.notify(TZEventType.STEP_TERMINATED)
        
        self.info.end = int(time.time())
        self.logger.info(f"Testcase terminated: {'[bold green]PASSED[/bold green]' if test_res else '[bold magenta]FAILED[/bold magenta]'}", show_step_info=False)
        self.info.status = TZTestStatusType.PASSED if test_res else TZTestStatusType.FAILED
        self.notify(TZEventType.TEST_TERMINATED)
        
        return test_res

def tz_add_test(name:str, test_class: type, steps = []):
    """This function is used to add a test to the test table. It is used to register the test class."""
    
    if name in _TZEN_TESTS_:
        raise ValueError(f"Test '{name}' already exists.")

    test_container = TZTest(name, test_class, steps)
    _TZEN_TESTS_[name] = test_container
    
    return test_container

def tz_get_test(name:str) -> TZTest:
    """This function is used to get a test from the test table. It is used to retrieve the test class."""
    
    if name not in _TZEN_TESTS_:
        raise ValueError(f"Test '{name}' does not exist.")
    
    return _TZEN_TESTS_[name]

def tz_get_test_table(tests: List[str] = []) -> Mapping[str, TZTest]:
    """This function is used to get the test table. It will return a mapping of test names to test classes. If tests is specified, it will return only the tests in the list."""
    if not tests:
        return _TZEN_TESTS_
    
    return {name: _TZEN_TESTS_[name] for name in tests if name in _TZEN_TESTS_}