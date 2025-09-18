#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This modules provides the feature in order to create and fixtures."""


from __future__ import annotations
from enum import Enum, auto
from typing import Mapping

class TZFixtureType(Enum):
    """Enumeration of fixture types."""
    FUNCTION = "function"
    CLASS = "class"
    GENERATOR = "generator"

class TZFixtureScope(Enum):
    """Enumeration of fixture scopes."""
    TEST = "test"
    SESSION = "session"
    STEP = "step"  
    
class TZFixtureContainer:
    
    def __init__(self, name:str, scope:TZFixtureScope, ftype:TZFixtureType, fixture_class:type, on_demand:bool = True):
        self.name = name
        self.scope = scope
        self.fixture_class = fixture_class
        self.fixture_instance = None
        self.is_setup = False
        self.ftype = ftype
        self.on_demand = on_demand  
    
    def get_fixture(self):
        """Get the fixture instance."""
        if not self.is_setup:
            self.setup()
            
        return self.fixture_instance
    
    def setup(self):
        """Setup the fixture instance."""
        if not self.is_setup:
            
            if self.ftype == TZFixtureType.CLASS:
                self.fixture_instance = self.fixture_class()
                self.fixture_instance.setup()
                
            elif self.ftype == TZFixtureType.FUNCTION:
                # For function fixtures, we can call the fixture directly
                # assuming it is a callable that returns the fixture instance
                self.fixture_instance = self.fixture_class()
                
            elif self.ftype == TZFixtureType.GENERATOR:   
                self.fixture_instance = next(self.fixture_class()) 
                
            else:
                raise ValueError(f"Unsupported fixture type: {self.ftype}")
            
            
            self.is_setup = True
            
    def teardown(self):
        """Teardown the fixture instance."""
        if self.is_setup:
            if self.ftype == TZFixtureType.CLASS:
                self.fixture_instance.teardown()
            elif self.ftype == TZFixtureType.GENERATOR:
                self.fixture_class()
            
            self.fixture_instance = None    
            self.is_setup = False


__TZEN_FIXTURES__:Mapping[str, TZFixtureContainer] = {scope:{} for scope in TZFixtureScope}

def tz_add_fixture(name:str,  fixture_class:type, scope:TZFixtureScope = TZFixtureScope.TEST, ftype:TZFixtureType = TZFixtureType.FUNCTION, on_demand:bool = True) -> None:
    """Add a fixture to the specified scope."""
    if scope not in __TZEN_FIXTURES__:
        raise ValueError(f"Invalid fixture scope: {scope}")
    
    if name in __TZEN_FIXTURES__[scope]:
        raise ValueError(f"Fixture '{name}' already exists in scope '{scope}'")
    
    __TZEN_FIXTURES__[scope][name] = TZFixtureContainer(name, scope, ftype, fixture_class, on_demand=on_demand)

def tz_get_fixture_by_name(name: str):
    """Get a fixture by its name."""
    if name in __TZEN_FIXTURES__[TZFixtureScope.TEST]:
        return __TZEN_FIXTURES__[TZFixtureScope.TEST][name].get_fixture()
    elif name in __TZEN_FIXTURES__[TZFixtureScope.SESSION]:
        return __TZEN_FIXTURES__[TZFixtureScope.SESSION][name].get_fixture()
    elif name in __TZEN_FIXTURES__[TZFixtureScope.STEP]:
        return __TZEN_FIXTURES__[TZFixtureScope.STEP][name].get_fixture()
    return None    

def tz_teardown_by_scope(scope: TZFixtureScope) -> None:
        """Teardown all fixtures in the specified scope."""
        if scope not in __TZEN_FIXTURES__:
            raise ValueError(f"Invalid fixture scope: {scope}")
        
        for fixture in __TZEN_FIXTURES__[scope].values():
            fixture.teardown()
    
def tz_setup_by_scope(scope: TZFixtureScope) -> None:
    """Setup all fixtures in the specified scope."""
    if scope not in __TZEN_FIXTURES__:
        raise ValueError(f"Invalid fixture scope: {scope}")
    
    for fixture in __TZEN_FIXTURES__[scope].values():
        fixture.setup()       
