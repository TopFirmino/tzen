from __future__ import annotations

from typing import Mapping, List
from enum import Enum
import inspect
from dataclasses import dataclass
from .tz_test import TZTest, TZTestObserverMixin
from datetime import datetime
from .tz_logging import console
import threading
import time
from rich.table import Table
from rich import box
from rich.live import Live

        
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
    test_status: TZTestStatus = TZTestStatus.IDLE
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
        self.session_live_report = threading.Thread(target=self.create_session_live_report)
        self.session_live_report_event = threading.Event()
        
    def update_session_live_report(self):
        
        table = Table(title="Session Status", show_header=False, box=box.SIMPLE, show_footer=True)
        
        table.add_column("Testcase", justify="left", min_width=50, style="cyan")
        table.add_column("Status")
        table.add_column("Result")
        
        for test in self.session.tests.values():
                
            test_name = test.test_name if test.test_status != TZTestStatus.RUNNING else f"[bold]{test.test_name}[/bold]"
            if test.test_status == TZTestStatus.RUNNING:
                test_status = f":fire: [bold]{test.test_step} / {test.test_step_num}[/bold]"
            elif test.test_status == TZTestStatus.TERMINATED:
                test_status = f":waving_white_flag:"
            elif test.test_status == TZTestStatus.IDLE:
                test_status = f":zzz:"
                
            if test.test_result == TZTestResult.NOT_EXECUTED:
                test_result = f":question:"
            elif test.test_result == TZTestResult.SUCCESS:
                test_result = f":japan:"
            elif test.test_result == TZTestResult.FAILURE:
                test_result = f":cross_mark:"
                    
            table.add_row(f"{test_name}", f"{test_status}", f"{test_result}")
        return table
    
    def create_session_live_report(self) -> None:
        """ Create a live report of the session. """
        REFRESH_PER_SEC = 4
        with Live(self.update_session_live_report(), refresh_per_second=REFRESH_PER_SEC) as live:  # update 4 times a second to feel fluid
            while not self.session_live_report_event.is_set():
                time.sleep( 1 / REFRESH_PER_SEC)
                live.update(self.update_session_live_report())
    
    def start_session(self, session_id:str, tests:List[str]):
        """ Start a new session. """
        self.session = TZSessionState(session_id=session_id, tests={k:TZTestState(test_name=k) for k in tests}, started=datetime.now())
        self.session.session_state = TZSessionStatus.RUNNING
        self.session_live_report.start()
        
    def end_session(self):
        """ End the current session. """
        if self.session:
            self.session.session_state = TZSessionStatus.TERMINATED
            self.session.finished = datetime.now()
            self.session_live_report_event.set()
            self.session_live_report.join()
            self.session = None
        
    def on_test_start(self, test:TZTest):
        _test_status = self.session.tests[test.__class__.__name__]
        _test_status.test_status = TZTestStatus.RUNNING
        _test_status.test_start_time=datetime.now()
        _test_status.test_step_num = len(test.steps)
        
    def on_test_end(self, test:TZTest):
        _test_status = self.session.tests[test.__class__.__name__]
        _test_status.test_status = TZTestStatus.TERMINATED
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

 