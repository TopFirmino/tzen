from __future__ import annotations

from .tz_fixture import *
from .tz_test import *
from . import tz_conf as conf
from .tz_monitor import TZTestMonitor


class TZFacade:
    
    def __init__(self):
        pass

    def _get_testcase_by_name(self, name:str) -> TZTest:
        return get_test_table().get(name, None)

    def _run_test(self, name:str, monitor:TZTestMonitor = None) -> None:
        # Get the test class
        _test_class = self._get_testcase_by_name(name)
        
        # Instantiate the test class eventually pass arguments
        _test = _test_class()
        
        # Setup fixtures for the test
        setup_test_fixtures(_test)
        
        # Attach the monitor to the test
        monitor.attach_to_test(_test)
        
        _test.run()
    
    def load_configuration(self, config:dict) -> None:
        """ Load the configuration from a dictionary """
        for k, v in config.items():
            setattr(conf, k, v)
            
    def run_tests(self, names:List[str]):
        
        # Prepare fixtures for the session
        setup_session_fixtures()
        
        # Create the test monitor
        monitor = TZTestMonitor()
        monitor.start_session(session_id="session1", tests=names)
        
        for test in names:
            self._run_test(test, monitor=monitor)
            
        # At the end make sure to clear_all the fixtures
        teardown_all_fixtures()
