# Session management for tests
## This module provides a session management system for tests, allowing to run tests in a controlled environment.
from __future__ import annotations
from .tz_test import TZTest, TZTestEvents, TZTestStatus
from .tz_observer import TZObservable, TZEN_ALL_EVENT
from .tz_logging import tz_getLogger
from .tz_test_organizer import TZTestOrganizer
from .tz_fixture import TZFixtureManager, TZFixtureMarker

from typing import Mapping, Callable, List
from dataclasses import dataclass
from enum import Enum

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
        self.status = TZSessionStatus(name="Test Session", total_tests=test_organizer.get_test_num(), details={})
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
        