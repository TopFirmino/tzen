#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This modules provides the feature in order to create and fixtures."""


from __future__ import annotations
from enum import Enum
from typing import Dict, Callable, Type
from .tz_tree import tz_tree_register_type, TzTree
from pathlib import Path
import sys
import inspect
import functools

class TZFixtureScope(Enum):
    """Enumeration of fixture scopes."""
    TEST = "test"
    SESSION = "session"
    STEP = "step"  

_TZEN_FIXTURES_ = {}

def tz_add_fixture(name:str, fixture_class:Callable | Type, scope:TZFixtureScope = TZFixtureScope.TEST) -> TZFixtureContainer:
    """Add a fixture to the specified scope."""
    
    if name in _TZEN_FIXTURES_:
        raise RuntimeError(f"Fixture '{name}' already exists")
    
    fixture = TZFixtureContainer(name, scope, fixture_class)
    _TZEN_FIXTURES_[name] = fixture
    
    return fixture

def _fixture_provider(name:str, selector:str):
    if name not in _TZEN_FIXTURES_:
        raise RuntimeError("Fixture '{name}' does not exists")

    return _TZEN_FIXTURES_[name]

def _fixture_injector(func:Callable, consumer:str) -> Callable:

    base = inspect.unwrap(func)

    sig = inspect.signature(base)
    for name, param in sig.parameters.items():
        if param.annotation in _TZEN_FIXTURES_:
            _fixture_node = TzTree().add_object(param.annotation, (Path(consumer) / param.annotation).as_posix(), kind='fixture')
            _fixture_node.get_object().fixture_class.__init__ = TzTree().inject(_fixture_node.get_object().fixture_class.__init__, _fixture_node.get_selector())

    @functools.wraps(func)
    def _wrapper(*f_args, **f_kwargs):
        
        bound = sig.bind_partial(*f_args, **f_kwargs)
            
        for name, param in sig.parameters.items():
            if name in bound.arguments:
                continue
            if param.default is not inspect._empty:
                continue
            if param.annotation in _TZEN_FIXTURES_:
                bound.arguments[name] = _TZEN_FIXTURES_[param.annotation].get_fixture()

        return func(*bound.args, **bound.kwargs)

    return _wrapper

@tz_tree_register_type("fixture", provider=_fixture_provider, injector=_fixture_injector)
class TZFixtureContainer:
    
    def __init__(self, name:str, scope:TZFixtureScope, fixture_class:Callable | Type):
        self.name = name
        self.scope = scope
        self.fixture_class = fixture_class
        self.fixture_instance = None
        self.is_setup = False
    
    def get_fixture(self):
        """Get the fixture instance."""
        if not self.is_setup:
            self.setup()
            
        return self.fixture_instance
    
    def setup(self):
        """Setup the fixture instance."""
        if not self.is_setup:
            
            if inspect.isclass(self.fixture_class):
                self.fixture_instance = self.fixture_class()
                self.fixture_instance.setup()
                
            elif inspect.isfunction(self.fixture_class):
                # For function fixtures, we can call the fixture directly
                # assuming it is a callable that returns the fixture instance
                self.fixture_instance = self.fixture_class()
                
            elif inspect.isgeneratorfunction(self.fixture_class):   
                self.fixture_instance = next(self.fixture_class()) 
                
            else:
                raise ValueError(f"Unsupported fixture type")
            
            self.is_setup = True
            
    def teardown(self):
        """Teardown the fixture instance."""
        if self.is_setup:
            if inspect.isclass(self.fixture_class):
                self.fixture_instance.teardown()
                self.fixture_instance = None
            elif inspect.isgeneratorfunction(self.fixture_class):  
                self.fixture_class()
            
            self.is_setup = False

