# Session management for tests
## This module provides a session management system for tests, allowing to run tests in a controlled environment.
from __future__ import annotations
from .tz_test import TZTest, TZTestEvents, TZTestStatus
from .tz_observer import TZObservable, TZEN_ALL_EVENT
from .tz_logging import tz_getLogger, TZEN_GLOBAL_CONSOLE
from .tz_test_organizer import TZTestOrganizer
from .tz_fixture import TZFixtureManager

from typing import Mapping
from dataclasses import dataclass
from enum import Enum

from rich.table import Table
from rich import box
from rich.live import Live
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.panel import Panel


import threading
import time

logger = tz_getLogger(__name__)

#Definitions
class TZSessionEvents(str, Enum):
    """Enum for session events. It is used to notify observers about session progress."""
    SESSION_STARTED         = "SESSION_STARTED"
    SESSION_ENDED           = "SESSION_ENDED"
    TEST_STARTED            = "TEST_STARTED"
    TEST_COMPLETED          = "TEST_COMPLETED"
    TEST_FAILED             = "TEST_FAILED"
    STEP_STARTED            = "STEP_STARTED"
    STEP_ENDED              = "STEP_ENDED"
    SESSION_STATUS_CHANGED  = "SESSION_STATUS_CHANGED"
    
@dataclass
class TZSessionStatus:
    """Dataclass to represent the status of a test session."""
    name: str
    total_tests: int
    current_test: int = 0
    passed: bool = False
    terminated: bool = False
    details: Mapping[str, TZTestStatus] = None

class TZSession(TZObservable):
    """ Class to manage a test session. It allows to run tests and notify observers about test events."""
    interests = [e.value for e in TZSessionEvents]
    
    def __init__(self, test_organizer:TZTestOrganizer) -> None:
        super().__init__()
        self.status = TZSessionStatus(name="Test Session", total_tests=test_organizer.get_test_num(), details={test.__class__.__name__: None for test in test_organizer.get_all_tests() })
        self.current_test: TZTest = None
        self.test_organizer = test_organizer
        self.fixture_manager = TZFixtureManager()
        
    def _on_test_event(self, event: TZTestEvents, tz_test:TZTest) -> None:
        """Handle test events and update session status accordingly."""
        if event == TZTestEvents.TEST_STARTED:
            self.status.current_test += 1
            self.status.passed = True
            self.status.terminated = False
            self.notify(TZSessionEvents.TEST_STARTED, tz_test)
        
        elif event == TZTestEvents.TEST_COMPLETED:
            self.status.passed = self.status.passed and tz_test.status.passed
            self.notify(TZSessionEvents.TEST_COMPLETED, tz_test)
        
        elif event == TZTestEvents.TEST_FAILED:
            self.status.passed = False
            self.notify(TZSessionEvents.TEST_FAILED, tz_test)
        
        elif event == TZTestEvents.STEP_STARTED:
            self.notify(TZSessionEvents.STEP_STARTED, tz_test)
        
        elif event == TZTestEvents.STEP_ENDED:
            self.notify(TZSessionEvents.STEP_ENDED, tz_test)
        
        elif event == TZTestEvents.TEST_ENDED:
            self.notify(TZSessionEvents.TEST_ENDED, tz_test)
            # Teardown fixtures for the test
            for marker in tz_test.get_fixture_markers():
                self.fixture_manager.release_fixture(marker)    
            
        elif event == TZTestEvents.TEST_STATUS_CHANGED:
            self.status.details[tz_test.__class__.__name__] = tz_test.status
            self.notify(TZSessionEvents.SESSION_STATUS_CHANGED, self)
         
    def start(self) -> None:
        """Start the test session."""
        self.status.current_test = 0
        self.status.passed = True
        self.status.terminated = False
        self.notify(TZSessionEvents.SESSION_STARTED, self)
        
        for test in self.test_organizer.get_all_tests():
        
            self.status.passed = self.status.passed and self._run_test(test)
            

        self.status.terminated = True
        self.notify(TZSessionEvents.SESSION_ENDED, self)
        self.fixture_manager.release_all()
        
    def _run_test(self, test:TZTest) -> bool:
        """Run a test and attach event handlers to it."""
        # Instantiate all necessary fixture and inject them into the test
        for marker in TZTest.get_fixture_markers(test):
            self.fixture_manager.get_fixture(marker)
            
        # Test creation and attachment of event handlers
        self.current_test = test()
        self.current_test.attach(self._on_test_event, TZEN_ALL_EVENT)
                    
                    
        return self.current_test.run()


class TZSessionMonitor:
    """Monitor and display the current session state of tests."""
    
    def __init__(self, session:TZSession, test_organizer:TZTestOrganizer, console:Console = None) -> None:
        self.session: TZSession = session
        self.organizer: TZTestOrganizer = test_organizer
        self.monitor_thread = threading.Thread(target=self.create_session_live_report, daemon=True)
        self.monitor_thread_event = threading.Event()
        self.console: Console = console if console else TZEN_GLOBAL_CONSOLE
        
    def update_session_live_report(self, table) -> None:
        """Update the live report of the session."""
        # This method can be implemented to update a live report of the session
        table.add_column("Testcase", justify="left", min_width=50, style="cyan")
        table.add_column("Status")
        table.add_column("Result")
        
    
    def create_session_live_report(self) -> None:
        """Create a live report of the session."""
        REFRESH_PER_SEC = 4
        
        overall_progress = Progress( "Session Progress", SpinnerColumn(), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%") )
        overall_progress_task = overall_progress.add_task("Session Progress", total=self.session.status.total_tests, completed=0, visible=True)
        
        table = Table(title="Session Status", show_header=False, box=box.SIMPLE, show_footer=True).grid()
        table.add_row( Panel.fit( overall_progress, title="Overall Progress", border_style="green", padding=(2, 2) ) )
        
        # This method can be implemented to create a live report of the session
        with Live(table, console = self.console, refresh_per_second=REFRESH_PER_SEC) as live:
            while not self.monitor_thread_event.is_set():                
                time.sleep( 1 / REFRESH_PER_SEC)
                overall_progress.update(overall_progress_task, advance=0.5)
                live.update(self.update_session_live_report(table))
            
            live.stop()
            
 
    def start(self) -> None:
        """Start the session monitor."""
        self.session.attach(self.update_session_live_report, TZSessionEvents.SESSION_STATUS_CHANGED)
        self.monitor_thread.start()

    def stop(self) -> None:
        """Stop the session monitor."""
        self.monitor_thread_event.set()
        self.monitor_thread.join()
        self.session.detach(self.update_session_live_report, TZSessionEvents.SESSION_STATUS_CHANGED)
        