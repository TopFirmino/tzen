from __future__ import annotations

from typing import Mapping, List
from enum import Enum
import inspect
from dataclasses import dataclass
from .tz_test import TZTest, TZTestObserverMixin


@dataclass
class _TZEN_FIXTURE_TABLE_ITEM_:
    fixture_instance:TZFixture
    fixture_class:TZFixture
    fixture_args:dict
    fixture_mode:TZFixtureMode
    
    
# Table that maps each fixture class declared by inheritsing from TZFixture
__TZEN_FIXTURE_TABLE__:Mapping[str, TZFixture] = {}

# Table that maps each fixture instance created by the test
# Each item has as key the fixture name for its instance and as value the fixture instance
__TZEN_FIXTURE_INSTANCES_TABLE__:Mapping[str, _TZEN_FIXTURE_TABLE_ITEM_] = {}

# This tables maps the relations between fixtures instances and test classes.
__TZEN_FIXTURE_VS_TEST_TABLE__:Mapping[str, List[str] ] = {}
__TZEN_TEST_VS_FIXTURE_TABLE__:Mapping[str, List[str] ] = {}


class TZFixtureMode(str, Enum):
    TEST_MODE       = "TEST_MODE"
    STEP_MODE       = "STEP_MODE"
    SESSION_MODE    = "SESSION_MODE"

class TZFixture(TZTestObserverMixin):
    
    def cmd_setup(self):
        if not self.is_setup:
            self.setup()
            self.is_setup = True
            
    def cmd_teardown(self):
        if self.is_setup:
            self.teardown()
            self.is_setup = False
        
    def setup(self):
        raise NotImplementedError

    def teardown(self):
        raise NotImplementedError

    def set_mode(self, mode:TZFixtureMode):
        self.mode = mode
    
    def __init_subclass__(cls):

        if cls.__name__ not in __TZEN_FIXTURE_TABLE__:
            __TZEN_FIXTURE_TABLE__[cls.__name__] = cls

    def on_test_start(self, test):
        if self.mode == TZFixtureMode.TEST_MODE:
            self.setup()
    
    def on_test_end(self, test):
        if self.mode == TZFixtureMode.TEST_MODE:
            self.teardown()

    def on_step_start(self, test):
        if self.mode == TZFixtureMode.STEP_MODE:
            self.setup()
    
    def on_step_end(self, test):
        if self.mode == TZFixtureMode.STEP_MODE:
            self.teardown()


def get_fixture_instance(fixture_name) -> TZFixture:
    """Creates a fixture instance if it does not exist yet."""
    
    if fixture_name not in __TZEN_FIXTURE_INSTANCES_TABLE__:
        raise ValueError(f"Fixture {fixture_name} not found in the fixture instances table.")

    if __TZEN_FIXTURE_INSTANCES_TABLE__[fixture_name].fixture_instance is None:    
        _instance = __TZEN_FIXTURE_INSTANCES_TABLE__[fixture_name].fixture_class(**__TZEN_FIXTURE_INSTANCES_TABLE__[fixture_name].fixture_args)
        setattr(_instance, "is_setup", False)
        setattr(_instance, "mode", __TZEN_FIXTURE_INSTANCES_TABLE__[fixture_name].fixture_mode)
        __TZEN_FIXTURE_INSTANCES_TABLE__[fixture_name].fixture_instance = _instance
        
        
    return __TZEN_FIXTURE_INSTANCES_TABLE__[fixture_name].fixture_instance

def setup_test_fixtures(test:TZTest):
    """Setup all test fixtures."""
    for fixture_name in __TZEN_TEST_VS_FIXTURE_TABLE__.get(test.__class__.__name__, []):
        fixture = get_fixture_instance(fixture_name)
        setattr(test, fixture_name, fixture)
        fixture.attach_to_test(test)
        
def setup_session_fixtures():
    """Setup all session fixtures."""
    for k, fixture in __TZEN_FIXTURE_INSTANCES_TABLE__.items():
        if fixture.fixture_mode == TZFixtureMode.SESSION_MODE:
            _fixture_instance = get_fixture_instance(k)
            _fixture_instance.cmd_setup()
            
def teardown_all_fixtures():
    """Teardown all fixtures."""
    for fixture_name in __TZEN_FIXTURE_INSTANCES_TABLE__.keys():
        get_fixture_instance(fixture_name).cmd_teardown()

def use_fixture(fixture_class, mode:TZFixtureMode = TZFixtureMode.TEST_MODE, fixture_name:str = None, **args):
    
    if fixture_class.__name__ not in __TZEN_FIXTURE_TABLE__:
        raise ValueError(f"Fixture {fixture_class.__name__} not found in the fixture table. Make sure to inherit from TZFixture class.")
    
    if fixture_name is None:
        fixture_name = fixture_class.__name__
    
    if fixture_name not in __TZEN_FIXTURE_INSTANCES_TABLE__:
        __TZEN_FIXTURE_INSTANCES_TABLE__[fixture_name] = _TZEN_FIXTURE_TABLE_ITEM_(None, fixture_class, args, mode)
    
    def _wrapper(test_class):
        test_name = test_class.__name__
        
        if fixture_name  not in __TZEN_FIXTURE_VS_TEST_TABLE__:
            __TZEN_FIXTURE_VS_TEST_TABLE__[fixture_name] = [test_name]
        else:
            __TZEN_FIXTURE_VS_TEST_TABLE__[fixture_name].append(test_name)

        if test_name not in __TZEN_TEST_VS_FIXTURE_TABLE__:
            __TZEN_TEST_VS_FIXTURE_TABLE__[test_name] = [fixture_name]
        else:
            __TZEN_TEST_VS_FIXTURE_TABLE__[test_name].append(fixture_name)
        
        return test_class
    
    return _wrapper
