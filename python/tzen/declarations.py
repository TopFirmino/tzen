"""Read documentation and validate class-based pytest declarations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import json
from pathlib import Path

from .cases import (
    TzenTestCase, TzenRemoteTestCase, TzenCompanionTestCase,
    Step, class_steps, class_fixtures,
)


@dataclass(frozen=True)
class Documentation:
    target: str
    description: str
    companion: bool
    steps: tuple[Step, ...] = ()


@dataclass(frozen=True)
class Declaration:
    documentation: Documentation
    implementation: type[TzenTestCase]
    source: Path


def declare(cls: type[TzenTestCase], source: Path) -> Declaration:
    remote = issubclass(cls, TzenRemoteTestCase)
    companion = issubclass(cls, TzenCompanionTestCase)
    if remote == companion:
        raise ValueError("Inherit from exactly one of TzenRemoteTestCase or TzenCompanionTestCase")
    steps = class_steps(cls)
    fixtures = class_fixtures(cls, steps)
    if remote and (steps or fixtures or cls.__init__ is not object.__init__):
        raise ValueError("Remote testcases cannot define Python steps or constructors; use TzenCompanionTestCase")
    if companion and not steps:
        raise ValueError("Companion testcases require at least one @step method")
    if any(mark.name == "parametrize" for mark in getattr(cls, "pytestmark", ())):
        raise ValueError("Testcase parametrization is not supported")
    target = cls.target if cls.target is not None else cls.__name__
    if not isinstance(target, str) or not target.strip():
        raise ValueError("testcase target must be a nonempty string")
    documentation = Documentation(
        target, inspect.cleandoc(cls.__dict__.get("__doc__") or ""), companion, steps,
    )
    return Declaration(documentation, cls, source)


def write_documentation(path: Path, records: list[dict], *, verified: bool) -> None:
    """Write machine-readable documentation; offline exports are never verified."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "verified_against_slave": verified,
                                "testcases": records}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def documentation_record(declaration: Declaration) -> dict:
    return {**asdict(declaration.documentation), "source": str(declaration.source)}


def collection_description(declaration: Declaration) -> str:
    """Display the Python procedure in pytest's verbose collection tree."""
    doc = declaration.documentation
    description = doc.description
    if doc.steps:
        description += "\n\nPython steps:\n" + "\n".join(
            f"{index}. {step.description}" + (" [critical]" if step.critical else "")
            for index, step in enumerate(doc.steps, 1)
        )
    return description
