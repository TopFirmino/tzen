# tzen/_tz_plugins.py
from __future__ import annotations
import importlib
import pluggy
from .plugins import hookspecs
from . import tz_constants
import os

_PM = pluggy.PluginManager("tzen")
_PM.add_hookspecs(hookspecs)

def _safe_register(obj):
    # evita doppie registrazioni
    name = getattr(obj, "__name__", repr(obj))
    for p in _PM.get_plugins():
        if hasattr(p, "__name__") and p.__name__ == name:
            break
    else:
        _PM.register(obj, name=name)

def load_default_plugins():
    """Loads default plugins searching in plugins/defaults folder and subfolders"""
    defaults_folder = f"{__file__[:-14]}plugins/defaults"
    for root, dirs, files in os.walk(defaults_folder):
        if '__pycache__' not in root:
            for _file in files:
                if _file.endswith('.py'):
                    mod = importlib.import_module(f"tzen.plugins.defaults.{os.path.relpath(root, defaults_folder).replace(os.path.sep, '.')}.{_file[:-3]}")
                    _safe_register(mod)
                
def load_user_plugins(module_paths: list[str] | None = None, use_entrypoints: bool = True):
    # 1) via entry points (pyproject.toml) → [project.entry-points."tzen_plugins"]
    if use_entrypoints:
        _PM.load_setuptools_entrypoints("tzen_plugins")
        return 
    
    # 2) via lista di moduli pienamente qualificati (es. "my_pkg.my_plugin")
    for modpath in module_paths or []:
        mod = importlib.import_module(modpath)
        _safe_register(mod)

def get_pm() -> pluggy.PluginManager:
    return _PM
