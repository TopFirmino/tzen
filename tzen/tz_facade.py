from __future__ import annotations

from .tz_fixture import *
from .tz_test import *
from . import tz_conf as conf
from .tz_monitor import TZTestMonitor
from .tz_loader import import_all_modules_in_directory
from .tz_doc import build_documentation
import os
import inspect


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
    
    def load_configuration_from_file(self, config_file:str) -> None:
        """ Load the configuration from a file. Supported files are .json, .yaml, .yml, .toml """
        
        # Check if file exists
        if not os.path.isfile(config_file):
            raise FileNotFoundError(f"Configuration file {config_file} does not exist")
        
        file_to_dict = None
        
        # Check the file extension
        if config_file.endswith(".json"):
            import json
            file_to_dict = json.load
        
        elif config_file.endswith(".yaml") or config_file.endswith(".yml"):
            import yaml
            file_to_dict = yaml.safe_load
        
        elif config_file.endswith(".toml"):
            import toml
            file_to_dict = toml.load
        
        # Load the configuration from the file
        with open(config_file, "r") as f:
            self.load_configuration(file_to_dict(f) )
        
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
        
        monitor.end_session()
        
    def start_session(self, tests_folder:str, tests:List[str] = []) -> None:
        """ Start a session and load all the tests from a folder """
        
        # Load all the test modules from the folder
        import_all_modules_in_directory(tests_folder, "tests")
        
        # Get all the test classes
        test_classes = set(get_test_table().keys())
        
        if len(tests) > 0:
            # Filter the test classes by name
            test_classes = test_classes.intersection( set(tests) )
        
        # Sort test_classes by name
        test_classes = sorted(test_classes)
        self.run_tests(test_classes)
            
    def build_documentation(self, tests_folder:str, output_folder:str) -> None:
        """ Generate the documentation for the tests """
        
        # Load all the test modules from the folder
        test_environment_structure = {k:{"module": v, "tests":[], "path": ""} for k, v in import_all_modules_in_directory(tests_folder, "tests").items()}
        common_prefix = os.path.commonprefix([ x["module"].__file__ for x in test_environment_structure.values()])
        
        # Update the test_environment_structure with the path to the test modules and the testcases inside those modules
        for k, v in test_environment_structure.items():
            test_environment_structure[k]["path"] = os.path.relpath(v["module"].__file__[:-3], common_prefix)
            for test_name, test_class in get_test_table().items():
                if test_class.__module__[:-3] == k:
                    test_environment_structure[k]["tests"] += [test_class]
            
       
        build_documentation(test_environment_structure, output_folder)
        