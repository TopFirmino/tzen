from __future__ import annotations

from .tz_test import *
from . import tz_conf as conf
from .tz_loader import import_all_modules_in_directory
from .tz_doc import build_documentation
import os
from .tz_test_organizer import TZTestOrganizerList
from .tz_session import TZSession
from .tz_logging import tz_getLogger

logger = tz_getLogger(__name__)
class TZFacade:
    
    def __init__(self):
        pass

    def _get_testcase_by_name(self, name:str) -> TZTest:
        return get_test_table().get(name, None)
    
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
                    
    def start_session(self, tests_folder:str, tests:List[str] = []) -> None:
        """ Start a session and load all the tests from a folder """
        
        # Load all the test modules from the folder
        import_all_modules_in_directory(tests_folder, "tests")
        
        # Create the correct test organizer based on the tests list
        organizer = TZTestOrganizerList(tests)
        
        # Create the session
        session = TZSession(organizer)
        session.start()
        
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
        