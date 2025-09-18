#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""TZen test framework."""

from __future__ import annotations

__all__ = []
__version__ = "0.1.1"

from ._tz_injector import tz_inject
from .tz_test import tz_add_test
from .tz_fixture import tz_add_fixture, TZFixtureScope, TZFixtureType
import inspect


def tz_testcase(cls, *args, **kwargs):
    """This method is used to declare a testcase. This decorator can only be used for classes"""
    def decorator(test_class):
        test_class.__init__ = tz_inject(test_class.__init__)
        tz_add_test(test_class.__name__, test_class, [getattr(test_class, name) for name in dir(test_class) if callable(getattr(test_class, name)) and hasattr(getattr(test_class, name), 'is_step')])
        return test_class
    
    # If called directly with a class
    if len(args) == 0 and callable(cls) and not kwargs:
        return decorator(cls)
    
    # If called with parentheses
    return decorator
    
def tz_step(func, *args, **kwargs):
    """This method is used to declare a step. This decorator can only be used for methods of classes decorated with @TZTest.testcase"""
    
    def decorator(func):
        _f = tz_inject(func)
        _f.is_step = True
        return _f
    
    # If called directly with a class
    if len(args) == 0 and callable(func) and not kwargs:
        return decorator(func)
    
    return decorator

def tz_fixture(*args, scope:TZFixtureScope=TZFixtureScope.TEST, on_demand:bool = True):
    """This method is used to declare a fixture. This decorator can be used on functions of classes that implements the setup and teardown methods."""

    def decorator(func):
    
        if inspect.isclass(func):
            func.__init__ = tz_inject(func.__init__)
            tz_add_fixture(func.__name__, func, scope, TZFixtureType.CLASS, on_demand=on_demand)
            return func
        
        elif inspect.isgeneratorfunction(func):
            func = tz_inject(func)
            tz_add_fixture(func.__name__, func, scope, TZFixtureType.GENERATOR, on_demand=on_demand)
            return func
        
        elif inspect.isfunction(func):
            func = tz_inject(func)
            tz_add_fixture(func.__name__, func, scope, TZFixtureType.FUNCTION, on_demand=on_demand)
            return func
    
    if len(args) == 1:
        return decorator(args[0])
    
    
    return decorator

def tz_fut(*args):
    """This method is used to declare a FunctionUnderTest. This decorator can be used for functions outside of a class. It adds time checking and logging."""
    pass