#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""TZen test framework."""

from __future__ import annotations

__name__ = "TZen"
__all__ = []
__version__ = "0.2.0"

from .tz_test import tz_add_test, tz_add_step
from .tz_fixture import tz_add_fixture, TZFixtureScope
from .tz_tree import TzTree
from pathlib import Path
from typing import List


def tz_testcase(*args, requirements:List[str] = [], **kwargs):
    """This method is used to declare a testcase. This decorator can only be used for classes"""
    def decorator(test_class):
        test = tz_add_test(test_class.__name__, test_class)
        test.test_class.__init__ = TzTree().inject(test_class.__init__, test.get_selector())

        for r in requirements:
            TzTree().add_object( r, (Path(test.get_selector()) / r).as_posix(), kind='requirement')

        return test_class
    
    # If called directly with a class
    if len(args) == 1:
        return decorator(args[0])
    
    # If called with parentheses
    return decorator
    
def tz_step(*args, index = -1, blocking = True, repeat = 1, requirements:List[str] = [], **kwargs):
    """This decorator is used to declare a step. This decorator can only be used for methods of classes decorated with @TZTest.testcase"""
    
    def decorator(func):
        step = tz_add_step(func.__name__, index, func, blocking, repeat)
        for r in requirements:
            TzTree().add_object( r, (Path(step.get_selector()) / r).as_posix(), kind='requirement')

        return func
    
    if len(args) == 1:
        return decorator(args[0])
    
    return decorator

def tz_fixture(*args, scope:TZFixtureScope=TZFixtureScope.TEST):
    """This method is used to declare a fixture. This decorator can be used on functions of classes that implements the setup and teardown methods."""

    def decorator(func):
        tz_add_fixture(func.__name__, func, scope)
        return func

    if len(args) == 1:
        return decorator(args[0])
    
    return decorator

def tz_fut(*args):
    """This method is used to declare a FunctionUnderTest. This decorator can be used for functions outside of a class. It adds time checking and logging."""
    pass