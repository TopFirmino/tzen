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
from . import tz_constants as conf
from ._tz_loader import import_all_modules_in_directory
from .tz_tree import TzTree 
from .tz_session import TZSession
from ._tz_logging import tz_getLogger
from .tz_plugins import get_pm
from .tz_doc import tz_build_documentation

logger = tz_getLogger(__name__)

class TZFacade:

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
                    
    def start_session(self, tests_folder:str, selector:str = '/', report_output_file: str = "./report.html", **kwargs) -> None:
        """ Start a session and load all the tests from a folder """
        project_path = Path(tests_folder).absolute()

        # Load all the test modules from the folder
        # This triggers the filling of the TZTree
        import_all_modules_in_directory(str(project_path))
        
        # Filter the tree by the selector
        organizer = TzTree().resolve( str(project_path / selector) )
        if organizer is None:
            raise ValueError(f"Cannot find selector {str(project_path / selector)}")
        
        # Create the session
        session = TZSession(organizer)
        session.start()
        
        session.build_report(report_output_file)
        
    def build_documentation(self, tests_folder:str, output_folder:str, requirements_file:str) -> None:
        """ Generate the documentation for the tests """
        
        project_path = Path(tests_folder).absolute()

        # Load all the test modules from the folder
        # This triggers the filling of the TZTree
        import_all_modules_in_directory(str(project_path))
        
        tz_build_documentation(TzTree(), "docs", output_folder)