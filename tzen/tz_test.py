#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This modules provides the feature in order to create and execute a testcase."""

from __future__ import annotations
from ._tz_logging import TZTestLogger
from ._tz_doc import parse_atdoc
from .tz_types import TZEventType, TZTestInfo, TZTestStatusType
from typing import List
import inspect
from pathlib import Path
import time
import hashlib
from typing import Callable, Dict, Mapping, Tuple
import sys

from .tz_tree import tz_tree_register_type, TzTree

_TZEN_STEPS_ = {}

def _step_provider(name:str, selector:str):
    if selector not in _TZEN_STEPS_:
        raise RuntimeError(f"Step with selector {selector} does not exists")
    return _TZEN_STEPS_[selector]

def tz_add_step(name:str, index:int, func:Callable[[object], bool | None], blocking:bool=True, repeat:int=1):
    
    _step = TZStep(name, func, blocking=blocking, repeat=repeat, index = index )

    if _step.get_selector() in _TZEN_STEPS_:
        raise RuntimeError(f"Step with selector {_step.get_selector()} already exists")
    
    _TZEN_STEPS_[_step.get_selector()] = _step
    TzTree().add_object(_step.name, _step.get_selector(), 'step')

    return _step


@tz_tree_register_type("step", provider=_step_provider)
class TZStep:
    """This class provides a container for steps. It is used in order to provide abstraction and dependency injection. 
    step parameter is a callable. It is used to store the step function."""
    

    def __init__(self, name:str, func: Callable[[object], bool | None], blocking:bool=True, repeat:int=1, index:int=-1):
        self.name = name
        self.index = index
        self.doc = " " # parse_atdoc(func.__doc__)
        self.func = func
        self.blocking = blocking
        self.repeat = repeat
    
    def run(self, test_instance):
        """This method is used to run the step."""
        res = True
        for _ in range(self.repeat):
            _res = self.func(test_instance)
            res &= _res if _res is not None else True
        
        return res

    def get_selector(self) -> str:
        return ( Path(sys.modules[self.func.__module__].__file__[:-3]) / self.func.__qualname__.replace('.','/') ).as_posix()

_TZEN_TESTS_ = {}

def tz_add_test(name:str, test_class: type, steps = []):
    """This function is used to add a test to the test table. It is used to register the test class."""
    
    if name in _TZEN_TESTS_:
        raise ValueError(f"Test '{name}' already exists.")

    _test = TZTest(name, test_class, steps)
    _TZEN_TESTS_[name] = _test
    TzTree().add_object(name, _test.get_selector(), 'test')

    return _test

def _test_provider(name:str, selector:str):
    if name not in _TZEN_TESTS_:
        raise RuntimeError(f"Test with name {name} does not exists")
    
    return _TZEN_TESTS_[name]

@tz_tree_register_type("test", provider=_test_provider)
class TZTest:
    """This class provides a container for testcases. It is used in order to provide abstraction and dependency injection. 
    test_class parameter is a Class. It is used to store the testcases and their steps."""
    
    def __init__(self, name:str, test_class: type, steps:List[TZStep] = []):
        self.name = name
        self.doc = ""#parse_atdoc(test_class.__doc__)
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
    
    def get_selector(self) -> str:
        """Returns the absolute path of the test class."""
        module = inspect.getmodule(self.test_class)
        if module is None:
            raise RuntimeError(f"Cannot find module of testcase {self.test_class.__name__}")
        return (Path(module.__file__[:-3]) / self.test_class.__name__).as_posix()
    
    def run(self) -> bool:
        """This method is used to run the testcases. It will create an instance of the test_class and run the steps."""
        
        # Setup the test class and test logger
        test = self.test_class()
        steps = [x.get_object() for x in TzTree().get_by_name(self.name).get_children_of_kind('step')]
        test.logger = TZTestLogger(self.name, len(steps))
        self.logger = test.logger
        
        self.logger.info(f"Starting Testcase", show_step_info=False)
        self.info.start = int(time.time())
        self.info.status = TZTestStatusType.RUNNING
        self.notify(TZEventType.TEST_STARTED)
        
        # Execute test steps
        test_res:bool = True 
        for i, step in enumerate(steps):
            test.logger.set_test_step(i + 1)
            self.info.current_step = i + 1
            
            self.notify(TZEventType.STEP_STARTED)
            step_res:bool = False
            try:
                _res = step.run(test)
                step_res = _res 
                
            except Exception as e:
                self.info.error = str(e)
                test.logger.error(e)
            
            test_res &= step_res
            self.notify(TZEventType.STEP_TERMINATED)
            if step.blocking and not step_res:
                test_res = False
                break
                
        self.info.end = int(time.time())
        self.logger.info(f"Testcase terminated: {'[bold green]PASSED[/bold green]' if test_res else '[bold magenta]FAILED[/bold magenta]'}", show_step_info=False)
        self.info.status = TZTestStatusType.PASSED if test_res else TZTestStatusType.FAILED
        self.notify(TZEventType.TEST_TERMINATED)
        
        return test_res


