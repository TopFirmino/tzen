# Aggiungere Fixtures
# Aggiungere Mechanism for verbosing assertions

from __future__ import annotations

from typing import Mapping, List, Callable, Tuple
import functools
import inspect
from .tz_observer import TZObservable
from typing import get_type_hints
from dataclasses import dataclass
from enum import Enum
from . import tz_logging


__TZEN_TEST_TABLE__:Mapping[str, TZTest] = {}


def get_test_table() -> Mapping[str, TZTest]:
    return __TZEN_TEST_TABLE__


class TZTestObserverMixin:
    """ This class is used to attach the test observer to the test """
    
    def attach_to_test(self, test:TZTest):
        test.attach(self.on_step_start,     TZTestObservable.TZTestEventsEnum.STEP_STARTED)
        test.attach(self.on_step_end,       TZTestObservable.TZTestEventsEnum.STEP_ENDED)
        test.attach(self.on_test_start,     TZTestObservable.TZTestEventsEnum.TEST_STARTED)
        test.attach(self.on_test_end,       TZTestObservable.TZTestEventsEnum.TEST_ENDED)
        test.attach(self.on_test_completed, TZTestObservable.TZTestEventsEnum.TEST_COMPLETED)
        test.attach(self.on_test_failed,    TZTestObservable.TZTestEventsEnum.TEST_FAILED)
        
    def on_test_start(self, test):
        pass
    
    def on_test_end(self, test):
        pass
    
    def on_step_end(self, test):
        pass
    
    def on_step_start(self, test):
        pass
    
    def on_test_completed(self, test):
        pass
    
    def on_test_failed(self, test):
        pass
    
    
@dataclass
class TZStep:
    args: List
    kwargs: Mapping
    
    idx: int = 0
    func: Callable[...,bool] = None
    blocking: bool = False
    
class TZTestObservable(TZObservable):

    class TZTestEventsEnum(str, Enum):
        TEST_STARTED    = "TEST_STARTED"
        STEP_STARTED    = "STEP_STARTED"
        STEP_ENDED      = "STEP_ENDED"
        TEST_FAILED     = "TEST_FAILED"
        TEST_COMPLETED  = "TEST_COMPLETED"
        TEST_ENDED      = "TEST_ENDED"


    def attach(self, observer_func:Callable[[TZTest],None], interest:TZTestEventsEnum):
        return super().attach(observer_func, interest)

    def detach(self, observer_func:Callable[[TZTest],None], interest:TZTestEventsEnum):
        return super().detach(observer_func, interest)

    def notify(self, interest:TZTestEventsEnum, message:TZTest):
        return super().notify(interest, message)

class TZTest(TZTestObservable):
    """ Base class for all tests. It provides a mechanism to run a sequence of steps and notify observers about the test progress.
    It also provides a mechanism to define steps as blocking or non-blocking. Blocking steps will stop the test execution if they fail.
    """
    
    interests:List[str] = [e.value for e in TZTestObservable.TZTestEventsEnum]

    def __init__(self):
        """Constructor of the TZTest class. It initializes the test and the logger."""
        super().__init__()
        self.logger = tz_logging.TZTestLogger(self.__class__.__name__, len(self.steps))

    def run(self) -> bool:
        
        self.notify(TZTest.TZTestEventsEnum.TEST_STARTED, self)

        test_res:bool = True

        for i, _step in enumerate(self._steps_class):
            
            self.logger.set_test_step(i + 1)
            self.notify(TZTest.TZTestEventsEnum.STEP_STARTED, self)

            try:
                _step_res = _step.func(self)

            except AssertionError as e:
                _step_res = False
                self.error(f"{e}")
                
                
            except Exception as e:
                _step_res = False
                self.exception(e, show_locals=True)
                
            self.notify(TZTest.TZTestEventsEnum.STEP_ENDED, self)

            test_res &= _step_res if _step_res is not None else True

            if not test_res and _step.blocking:
                break
        
        if test_res:
            self.notify(TZTest.TZTestEventsEnum.TEST_COMPLETED, self)
        else:
            self.notify(TZTest.TZTestEventsEnum.TEST_FAILED, self)

        self.notify(TZTest.TZTestEventsEnum.TEST_ENDED, self)

        return test_res

    def __init_subclass__(cls):
        
        # New TestClass initialization
        if not hasattr(cls, "steps"):
            cls.steps = []

        if not hasattr(cls, "blocking_steps"):
            cls.blocking_steps = []
        
        cls._steps_class = []
        
        TZTest._collect_steps_names(cls)
        if cls.__name__ not in __TZEN_TEST_TABLE__ and len(getattr(cls, 'steps', [])) > 0:
            __TZEN_TEST_TABLE__[cls.__name__] = cls
            TZTest._collect_steps_classes(cls)

    @staticmethod
    def _collect_steps_classes(test_class):
        
        for i, _step_name in enumerate(test_class.steps):
            test_class._steps_class.append( TZStep(   idx=i, 
                                                func=getattr(test_class, _step_name), 
                                                blocking= _step_name in test_class.blocking_steps,
                                                args=[ get_type_hints(getattr(test_class, _step_name)).get(name) for name, param in inspect.signature(getattr(test_class, _step_name)).parameters.items() if param.kind in [inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY] ],
                                                kwargs={} 
                                            ) 
                                    )
    
    @staticmethod  
    def _collect_steps_names(test_class):
        # Find all steps that has _tzen_step attribute
        for attr_name in dir(test_class):
            attr = getattr(test_class, attr_name)

            if callable(attr) and getattr(attr, "_tzen_step", False):
                test_class.steps.append(attr_name)

                if getattr(attr, "_tzen_step_blocking", False):
                    test_class.blocking_steps.append(attr_name)

    @staticmethod
    def step(func):
        class_name = func.__qualname__.split('.')[-2]
        #__TZEN_TEST_TABLE__[class_name] = None

        @functools.wraps(func)
        def wrapper_step(*args, **kwargs):
            func(*args, **kwargs)

        wrapper_step._tzen_step = True
        wrapper_step._tzen_step_blocking = False
        return wrapper_step
    
    @staticmethod
    def blocking_step(func):
        class_name = func.__qualname__.split('.')[-2]
        #__TZEN_TEST_TABLE__[class_name] = None

        @functools.wraps(func)
        def wrapper_step(*args, **kwargs):
            func(*args, **kwargs)


        wrapper_step._tzen_step = True
        wrapper_step._tzen_step_blocking = True
        return wrapper_step

    def info(self, msg):
        self.logger.info(msg)
    
    def warning(self, msg):
        self.logger.warning(msg)
    
    def error(self, msg):
        self.logger.error(msg)
    
    def exception(self, msg):
        self.logger.exception(msg)
    
    def debug(self, msg):
        self.logger.debug(msg)
    
    def critical(self, msg):
        self.logger.critical(msg)