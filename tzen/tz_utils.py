import inspect
from pathlib import Path
from typing import Tuple

def _tz_get_class_full_path(cls: type) -> Path:
    """Get the full path of a class, including its module."""
    if not inspect.isclass(cls):
        raise TypeError("Expected a class, got {}".format(type(cls).__name__))
    
    module = inspect.getmodule(cls)
    file_path = Path(module.__file__).resolve()
    file_path = file_path.with_suffix('')  # Remove the .py or .pyc suffix
    file_path = file_path.joinpath(cls.__name__)  # Append the class name
    
    return file_path

def tz_get_class_full_name(cls: type) -> str:
    """Get the full name of a class, including its module."""    
    return _tz_get_class_full_path(cls).as_uri()

def tz_get_class_full_name_parts(cls: type) -> Tuple[str, str]:
    """Get the full name of a class, including its module and file path."""
    return _tz_get_class_full_path(cls).parts
