from __future__ import annotations

from typing import Mapping, List
from enum import Enum
import inspect
from dataclasses import dataclass
from .tz_test import TZTest, TZTestObserverMixin
from datetime import datetime


class TZSessionStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"

class TZTestStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"
    
class TZTestResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    NOT_EXECUTED = "NOT_EXECUTED"
    
@dataclass
class TZTestState:
    """ A class to manage the state of the test. """
    test_name: str = None
    test_state: TZTestStatus = TZTestStatus.IDLE
    test_result: TZTestResult = TZTestResult.NOT_EXECUTED
    test_start_time: datetime = None
    test_end_time: datetime = None
    test_step: int = 0
    test_step_num: int = 0
    
@dataclass
class TZSessionState:
    """ A class to manage the session state of the test. """
    session_id: str = None
    session_status: TZSessionStatus = TZSessionStatus.IDLE
    tests: Mapping[str, TZTestState] = None
    started:datetime = None
    finished:datetime = None

class TZTestMonitor(TZTestObserverMixin):
    """ A class to monitor the test execution and maintain the state of the session. """
    
    def __init__(self):
        self.session: TZSessionState = None
        
    def start_session(self, session_id:str, tests:List[str]):
        """ Start a new session. """
        self.session = TZSessionState(session_id=session_id, tests={k:TZTestState(test_name=k) for k in tests}, started=datetime.now())
        self.session.session_state = TZSessionStatus.RUNNING

    def end_session(self):
        """ End the current session. """
        if self.session:
            self.session.session_state = TZSessionStatus.TERMINATED
            self.session.finished = datetime.now()
            self.session = None

    def on_test_start(self, test:TZTest):
        _test_status = self.session.tests[test.__class__.__name__]
        _test_status.test_state = TZTestStatus.RUNNING
        _test_status.test_start_time=datetime.now()
        _test_status.test_step_num = len(test.steps)
        
    def on_test_end(self, test:TZTest):
        _test_status = self.session.tests[test.__class__.__name__]
        _test_status.test_state = TZTestStatus.TERMINATED
        _test_status.test_end_time=datetime.now()
    
    def on_step_start(self, test:TZTest):
        _test_status = self.session.tests[test.__class__.__name__]
        _test_status.test_step = _test_status.test_step + 1
    
    def on_test_completed(self, test):
        _test_status = self.session.tests[test.__class__.__name__]
        _test_status.test_result = TZTestResult.SUCCESS
    
    def on_test_failed(self, test):
        _test_status = self.session.tests[test.__class__.__name__]
        _test_status.test_result = TZTestResult.FAILURE
            