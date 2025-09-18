#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------

from .tz_types import *
from .tz_test import TZTest
from ._tz_test_organizer import TZTestOrganizer
from ._tz_logging import tz_getLogger
from .tz_types import TZEventType
from enum import Enum, auto
import time


logger = tz_getLogger("")




class TZSession:
    """ Class to manage a test session. It allows to run tests and notify observers about test events."""
    
    def __init__(self, test_organizer:TZTestOrganizer) -> None:
        super().__init__()
        self.info = TZSessionInfo(name="Test Session", total_tests=test_organizer.size(), details={test.name: None for test in test_organizer.iterate() })
        self.subscribers = {event:[] for event in TZEventType.__members__.values()}
        self.current_test:TZTest = None
        self.result: bool = True
        self.test_organizer = test_organizer
            
    def _on_test_started(self, test:TZTest):
        """Attach the session to a test and notify about the start of the test."""
        self.info.current_test = test.info.name
        self.info.details[test.name] = test.info
        self.info.executed_tests += 1
        self.notify(TZEventType.TEST_STARTED)
    
    def _on_test_terminated(self, test:TZTest):
        self.info.details[test.name] = test.info
        self.notify(TZEventType.TEST_TERMINATED)
    
    def _on_step_started(self, test:TZTest):
        self.info.details[test.name] = test.info
        self.notify(TZEventType.STEP_STARTED)
    
    def _on_step_terminated(self, test:TZTest):
        self.info.details[test.name] = test.info
        self.notify(TZEventType.STEP_TERMINATED)
        
    def _attach_to_test(self, test:TZTest):
        """Attach the session to a test."""
        test.attach(self._on_test_started, TZEventType.TEST_STARTED)
        test.attach(self._on_test_terminated, TZEventType.TEST_TERMINATED)
        test.attach(self._on_step_started, TZEventType.STEP_STARTED)
        test.attach(self._on_step_terminated, TZEventType.STEP_TERMINATED)
            
    def attach(self, subscriber, event):
        if event in self.subscribers:
            self.subscribers[event].append(subscriber)

    def notify(self, event):
        if event in self.subscribers:
            for subscriber in self.subscribers[event]:
                subscriber(self)
 
    def start(self):
        """Run the test session."""
        logger.info(f"#"*30)
        logger.info(f"[green]TZen[/green] Starting session with a total of {self.info.total_tests} tests")
        logger.info(f"#"*30)
        
        self.info.status = TZSessionStatusType.RUNNING
        self.notify(TZEventType.SESSION_STARTED)
        self.info.start = int(time.time())
        
        for test in self.test_organizer.iterate():

            self.current_test = test
            self._attach_to_test(test)
            self.info.current_test = test.name
            self.result = test.run() and self.result
            
            if self.result:
                self.info.passed_tests += 1
            else:
                self.info.failed_tests += 1
        
        self.info.status = TZSessionStatusType.PASSED if self.result else TZSessionStatusType.FAILED
        self.notify(TZEventType.SESSION_TERMINATED)
        self.info.end = int(time.time())
        