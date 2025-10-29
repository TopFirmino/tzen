#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino) 
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
from __future__ import annotations

import os
from pathlib import Path

from .tz_test import *
from . import tz_conf as conf
from ._tz_loader import import_all_modules_in_directory
from .tz_test_organizer import TZTestOrganizerList, TZTestOrganizerTree
from .tz_session import TZSession
from ._tz_logging import tz_getLogger
from ._tz_plugins import get_pm, load_default_plugins, load_user_plugins


logger = tz_getLogger(__name__)

class TZFacade:
    
    def __init__(self):
        self.pm = get_pm()
        # Load plugins once per interface instance
        load_default_plugins()
        #load_user_plugins(["tzen.plugins.reports.html_session_report"], use_entrypoints=False)
        
    def load_configuration_from_file(self, config_file:str) -> None:
        """ Load the configuration from a file. Supported files are .json, .yaml, .yml, .toml """
        
        if not os.path.isfile(config_file):
            raise FileNotFoundError(f"Configuration file {config_file} does not exist")
        
        file_to_dict = None
        
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
            self.load_configuration(file_to_dict(f))
        
    def load_configuration(self, config:dict) -> None:
        """ Load the configuration from a dictionary """
        for k, v in config.items():
            setattr(conf, k, v)
                    
    def start_session(self, tests_folder:str, tests:List[str] = [], report_output_file: Path = "./report.html", **kwargs) -> None:
        """ Start a session and load all the tests from a folder """
        
        # Load all the test modules from the folder
        import_all_modules_in_directory(tests_folder)
        
        # Create the correct test organizer based on the tests list
        if tests and isinstance(tests, list) and len(tests) > 0:
            # If tests is a list of test names, use the list organizer
            organizer = TZTestOrganizerList(tests=tz_get_test_table(tests))
        else:
            organizer = TZTestOrganizerTree(root_path = Path(tests_folder).resolve(), tests=tz_get_test_table(tests))

        # Create the session
        session = TZSession(organizer)
        session.start()
        
        # Hook: Session Report
        self.pm.hook.build_session_report(session=session.info, config=conf, logger=logger, output_file=report_output_file)

    def build_documentation(self, tests_folder:str, output_folder:str, requirements_file:str) -> None:
        """ Generate the documentation for the tests """
        
        # Load all the test modules from the folder
        import_all_modules_in_directory(tests_folder)
        
        organizer = TZTestOrganizerTree(root_path = Path(tests_folder).resolve(), tests=tz_get_test_table())
            
        # Hook: Session Report
        self.pm.hook.build_docs(organizer=organizer, config=conf, logger=logger, output_folder=Path(output_folder).resolve(), requirements_file=Path(requirements_file).resolve())
        