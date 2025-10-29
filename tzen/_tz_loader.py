""" This module provides utilities for loading Python modules with future annotations support. The current implemementation of the tzen framework requires the use of string annotations,
in order to enhance compatibility and user experience, this module injects the `from __future__ import annotations` directive into the source code of Python files before they are compiled.
This allows the use of string annotations without requiring users to manually add the future import in their code.
"""

import importlib
import sys
from ._tz_logging import tz_getLogger
from .tz_fixture import *
import importlib.machinery
import __future__
import os
from typing import Mapping, Any
import sys, importlib.abc, importlib.machinery
import re, ast
from contextlib import contextmanager


# Flag della future "annotations"
FUTURE_ANN_FLAG = __future__.annotations.compiler_flag

def _inject_future_annotations(src: str) -> str:
    if re.search(r'(?m)^\s*from\s+__future__\s+import\s+annotations\b', src):
        return src
    nl = "\r\n" if "\r\n" in src else "\n"
    shebang_enc_re = re.compile(
        r'^(?P<she>#![^\n]*\n)?'
        r'(?P<enc>(?:[ \t]*#.*coding[:=][ \t]*[-\w.]+[^\n]*\n)?)',
        re.IGNORECASE
    )
    m = shebang_enc_re.match(src)
    insert_off = m.end() if m else 0
    try:
        mod = ast.parse(src)
        if (mod.body and isinstance(mod.body[0], ast.Expr)
            and isinstance(getattr(mod.body[0], "value", None), ast.Constant)
            and isinstance(mod.body[0].value.value, str)):
            lines = src.splitlines(True)
            insert_off = sum(len(l) for l in lines[:mod.body[0].end_lineno-1]) + mod.body[0].end_col_offset
    except SyntaxError:
        pass
    insertion = f"{nl}from __future__ import annotations{nl}"
    return src[:insert_off] + insertion + src[insert_off:]

class FutureAnnInjectingLoader(importlib.machinery.SourceFileLoader):
    """Ignora i .pyc: compila sempre dal sorgente dopo aver iniettato il future."""
    def get_code(self, fullname):
        source_path = self.get_filename(fullname)
        source_bytes = self.get_data(source_path)  # legge sempre il .py
        src = source_bytes.decode('utf-8', errors='replace')
        injected = _inject_future_annotations(src)
        code = compile(
            injected, source_path, 'exec',
            dont_inherit=True,
            flags=FUTURE_ANN_FLAG,
        )
        # (opzionale) self.set_data(self.path, marshal.dumps(code))  # se vuoi ricreare il .pyc
        return code

class _DelegatingFutureAnnFinder(importlib.abc.MetaPathFinder):
    def __init__(self, root: str):
        self.root = os.path.normcase(os.path.abspath(root)) + os.sep

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if not spec or not getattr(spec, "origin", None):
            return None
        origin = os.path.normcase(os.path.abspath(spec.origin))
        if not origin.endswith(".py") or not origin.startswith(self.root):
            return None
        spec.loader = FutureAnnInjectingLoader(fullname, spec.origin)
        return spec

@contextmanager
def future_annotations_for_tree(root_dir: str):
    finder = _DelegatingFutureAnnFinder(root_dir)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass


# -----------------------------------------------------------------------------
logger = tz_getLogger( __name__)
# -----------------------------------------------------------------------------


def import_all_modules_in_directory(directory: str) -> Mapping[str, Any]:
    """
    Import all modules in a given directory ensuring future annotations are injected.

    Args:
        directory (str): The directory containing the modules to import.

    Returns:
        dict: A dictionary of imported module names and their module objects.
    """
    imported_modules = {}
    
    # Check if directory is an absolute path
    if not os.path.isabs(directory):
        directory = os.path.abspath(directory)
        
    # Add parent directory to sys.path to allow relative imports within the package
    parent_dir = os.path.dirname(directory)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    logger.debug(f"Python path: {sys.path}")
    logger.debug(f"Importing modules from directory: {directory}")
    
    # Get the package name from the directory name
    package_name = os.path.basename(directory)
    logger.debug(f"Base package name: {package_name}")
    
    # Collect all Python files first to establish proper import order
    python_files = []
    init_files = []
    
    # 1) invalida i finder caches (PEP 302)
    importlib.invalidate_caches()

    # 2) purge del package dalla cache dei moduli
    to_purge = [m for m in list(sys.modules)
                if m == package_name or m.startswith(package_name + ".")]
    for m in to_purge:
        sys.modules.pop(m, None)
        
    with future_annotations_for_tree(directory):
        # Forst import the package
        pkg = importlib.import_module(package_name)
        
        for root, dirs, files in os.walk(directory):
            if '__pycache__' not in root:
                relative_path = os.path.relpath(root, parent_dir)
                for _file in files:
                    if _file.endswith('.py'):
                        module_name = relative_path.replace(os.path.sep, '.') + "." + _file[:-3]
                        m = importlib.import_module(module_name)
 
    return imported_modules
            

