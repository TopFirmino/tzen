# Aggiungere Mechanism for verbosing assertions

from __future__ import annotations

from typing import Mapping, List, Callable
import inspect
from .tz_observer import TZObservable
from dataclasses import dataclass
from enum import Enum
from .tz_logging import TZTestLogger
from .tz_fixture import TZFixtureMarker

# -----------------------------------------------------------------------------

# Definitions
__TZEN_TEST_TABLE__:Mapping[str, TZTest] = {}
__TZEN_TEST_FIXTURES_TABLE__:Mapping[str, List[TZFixtureMarker]] = {}


class TZTestEvents(str, Enum):
    """Enum for test events. It is used to notify observers about test progress."""
    TEST_STARTED        = "TEST_STARTED"
    STEP_STARTED        = "STEP_STARTED"
    STEP_ENDED          = "STEP_ENDED"
    TEST_FAILED         = "TEST_FAILED"
    TEST_COMPLETED      = "TEST_COMPLETED"
    TEST_ENDED          = "TEST_ENDED"
    TEST_STATUS_CHANGED = "TEST_STATUS_CHANGED"

@dataclass
class TZStep:
    """Dataclass to represent a test step. It contains the name of the step, the function to execute and whether it is blocking or not."""
    name: str
    func: Callable
    blocking: bool = False

@dataclass
class TZTestStatus:
    """Dataclass to represent the status of a test. It contains the name of the test, the number of steps and the current step."""
    name: str
    total_steps: int
    current_step: int = 0
    passed: bool = False
    terminated: bool = False
    
# Public API
def tz_get_test_table() -> Mapping[str, TZTest]:
    return __TZEN_TEST_TABLE__

def tz_get_test_fixtures(name:str) -> List[TZFixtureMarker]:
    """Get the fixtures for a test class from the fixtures table."""
    
    if name not in __TZEN_TEST_FIXTURES_TABLE__:
        raise ValueError(f"Fixtures for test '{name}' not found in the fixtures table")

    return __TZEN_TEST_FIXTURES_TABLE__[name] or []

def tz_step(func):
    """Decorator to mark a function as a test step. It will be collected by the TZTest class and executed as a step in the test."""
    # @functools.wraps(func)
    # def wrapper_step(*args, **kwargs):
    #     func(*args, **kwargs)

    func._tzen_step = True
    func._tzen_step_blocking = False
    return func
    
def tz_blocking_step(func):
    """Decorator to mark a function as a blocking test step. It will be collected by the TZTest class and executed as a step in the test.
    Blocking steps will stop the test execution if they fail."""

    # @functools.wraps(func)
    # def wrapper_step(*args, **kwargs):
    #     func(*args, **kwargs)

    func._tzen_step = True
    func._tzen_step_blocking = True
    return func

# -----------------------------------------------------------------------------

# TZTest Metaclass
class TZTestMeta(type):
    
    def __init__(cls, name, bases, namespace):
        
        # Steps configured by user
        explicit_step_names = getattr(cls, "steps", [])
        explicit_blocking_step_names = getattr(cls, "blocking_steps", [])
        explicit_steps = []
        
        for name in explicit_step_names:
            method = namespace.get(name) or getattr(cls, name, None)
            if callable(method):
                explicit_steps.append(TZStep(name, method, name in explicit_blocking_step_names))

        # Steps decorated with @step or @blocking_step
        decorated_steps = []
        
        methods = inspect.getmembers(cls, inspect.isfunction)
        methods = sorted( ((name, method) for name, method in methods if getattr(method, "_tzen_step", False)), key=lambda item: item[1].__code__.co_firstlineno)
        for name, method in methods:
            if name not in explicit_step_names:
                decorated_steps.append(TZStep(name, method, getattr(method, "_tzen_step_blocking", False)))

        # Union of explicit and decorated steps
        cls._steps = explicit_steps + decorated_steps

        _test_class_name = cls.__name__
        
        # Registrazione nel test table
        if _test_class_name not in __TZEN_TEST_TABLE__ and len(cls._steps) > 0:
            __TZEN_TEST_TABLE__[_test_class_name] = cls

        # Register fixture markers
        fixtures = inspect.getmembers(cls, lambda member: isinstance(member, TZFixtureMarker))
        
        for name, obj in fixtures:
            if _test_class_name not in __TZEN_TEST_FIXTURES_TABLE__:
                __TZEN_TEST_FIXTURES_TABLE__[_test_class_name] = [obj]
            else:
                __TZEN_TEST_FIXTURES_TABLE__[_test_class_name].append(obj)
                
        super().__init__(name, bases, namespace)

class TZTest(TZObservable, metaclass=TZTestMeta):
    """ Base class for all tests. It provides a mechanism to run a sequence of steps and notify observers about the test progress.
    It also provide a mechanism to define steps as blocking or non-blocking. Blocking steps will stop the test execution if they fail.
    """
    
    interests:List[str] = [e.value for e in TZTestEvents]

    @staticmethod
    def get_fixture_markers(cls) -> List[TZFixtureMarker]:
        """Get the fixture markers for the test class. It will return a list of TZFixtureMarker objects."""
        if cls.__name__ in __TZEN_TEST_FIXTURES_TABLE__:
            return __TZEN_TEST_FIXTURES_TABLE__[cls.__name__]
        return []
    
    def __init__(self):
        """Constructor of the TZTest class. It initializes the test and the logger."""
        super().__init__()
        self.logger = TZTestLogger(self.__class__.__name__, len(self._steps))
        self.status = TZTestStatus(name=self.__class__.__name__, total_steps=len(self._steps))

    def _set_status(self, **kwargs) -> None:
        """Set the status of the test and notify observers."""
        for key, value in kwargs.items():
            if hasattr(self.status, key) and value is not None:
                setattr(self.status, key, value)
                
        self.notify(TZTestEvents.TEST_STATUS_CHANGED, self.status)
    
    def run(self) -> bool:
        
        self.notify(TZTestEvents.TEST_STARTED, self)

        test_res:bool = True

        for i, _step in enumerate(self._steps):
            
            self.logger.set_test_step(i + 1)
            self.notify(TZTestEvents.STEP_STARTED, self)

            _step_res = False
            
            try:
                _func_res = _step.func(self) 
                _step_res = _func_res if _func_res is not None else True

            except AssertionError as e:
                self.logger.error(f"{e}")
                
            except Exception as e:
                self.logger.error(e)
                
            self.notify(TZTestEvents.STEP_ENDED, self)

            test_res &= _step_res

            if not test_res and _step.blocking:
                break
        
        if test_res:
            self.notify(TZTestEvents.TEST_COMPLETED, self)
        else:
            self.notify(TZTestEvents.TEST_FAILED, self)

        self.notify(TZTestEvents.TEST_ENDED, self)

        return test_res