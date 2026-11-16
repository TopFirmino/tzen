"""Python-owned testcase documentation and explicit companion declarations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Callable


@dataclass(frozen=True)
class Documentation:
    target: str
    description: str
    requirements: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    companion: bool = False


@dataclass(frozen=True)
class Declaration:
    documentation: Documentation
    function: Callable
    source: Path


def testcase(*, target: str, companion: bool = False,
             requirements: tuple[str, ...] | list[str] = (),
             tags: tuple[str, ...] | list[str] = ()):
    """Describe a C testcase; only companion=True executes the Python function.

    The target is the exact, unique name in the C registry. The docstring is
    the description. Companion functions must accept the tzen_case fixture.
    """
    if not isinstance(target, str) or not target.strip():
        raise ValueError("testcase target must be a nonempty string")
    if type(companion) is not bool:
        raise ValueError("companion must be a boolean")
    for name, values in (("requirements", requirements), ("tags", tags)):
        if not isinstance(values, (list, tuple)) or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError(f"{name} must be a list or tuple of nonempty strings")

    def decorate(function):
        if not inspect.isfunction(function) or inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function):
            raise ValueError("testcase declarations must be synchronous functions")
        if hasattr(function, "__tzen_documentation__"):
            raise ValueError("a function may declare only one testcase")
        if companion and "tzen_case" not in inspect.signature(function).parameters:
            raise ValueError("a companion must accept the tzen_case fixture")
        function.__tzen_documentation__ = Documentation(
            target, inspect.getdoc(function) or "", tuple(requirements), tuple(tags), companion,
        )
        # These functions are collected only through the slave, never twice.
        function.__test__ = False
        return function

    return decorate


# Importing the decorator into a test module must not collect the factory.
testcase.__test__ = False


def load_declarations(paths: tuple[Path, ...]) -> tuple[dict[str, Declaration], list[ModuleType]]:
    """Import explicit files or case_*.py files within explicit directories."""
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(path.rglob("case_*.py"))
        elif path.is_file() and path.suffix == ".py":
            files.add(path)
        else:
            raise ValueError(f"Invalid companion path: {path}")
    declarations = {}
    modules = []
    for path in sorted(files):
        name = "_tzen_cases_" + hashlib.sha256(str(path).encode()).hexdigest()[:20]
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        modules.append(module)
        for function in vars(module).values():
            doc = getattr(function, "__tzen_documentation__", None)
            if not isinstance(doc, Documentation) or function.__module__ != name:
                continue
            if doc.target in declarations:
                raise ValueError(f"Duplicate declaration for {doc.target!r}")
            declarations[doc.target] = Declaration(doc, function, path)
    return declarations, modules


def write_documentation(path: Path, records: list[dict], *, verified: bool) -> None:
    """Write machine-readable documentation; offline exports are never verified."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "verified_against_slave": verified,
                                "testcases": records}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def documentation_record(declaration: Declaration) -> dict:
    return {**asdict(declaration.documentation), "source": str(declaration.source)}
