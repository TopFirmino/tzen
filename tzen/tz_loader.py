import importlib
import os
from .tz_logging import tz_getLogger
from typing import Mapping, Any

# -----------------------------------------------------------------------------
logger = tz_getLogger( __name__)

# -----------------------------------------------------------------------------

def import_all_modules_in_directory(directory: str, package: str) -> Mapping[str, Any]:
    """
    Import all modules in a given directory.

    Args:
        directory (str): The directory containing the modules to import.
        package (str): The package name to use for the imported modules.

    Returns:
        list: A list of imported module names.
    """
    imported_modules = {}
    
    # Check if directory is an absolute path
    if not os.path.isabs(directory):
        directory = os.path.abspath(directory)
                    
    for address, dirs, files in os.walk(directory):
        for filename in files:
           
            if filename.endswith('.py'):
                
                try:
                    # Get the module absolute path
                    module_path = os.path.join(address, filename)
                    
                    # Crea uno spec da cui caricare il modulo
                    spec = importlib.util.spec_from_file_location(filename, module_path)

                    # Crea un modulo a partire dallo spec
                    module = importlib.util.module_from_spec(spec)

                    # Registra il modulo in sys.modules
                    # sys.modules[filename] = module

                    # Esegui il codice del modulo
                    spec.loader.exec_module(module)

                    # Get the module name
                    module_name = filename[:-3]

                    # Add the module to the imported modules dictionary
                    imported_modules[module_name] = module
                    
                except Exception as e:
                    logger.exception(f"Error importing module {os.path.join(address, filename)}: {e}")
                
                                           
    return imported_modules
