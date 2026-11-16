"""Class-based declarations with ordered, documented Python steps."""
from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Callable


@dataclass(frozen=True)
class Step:
    name: str
    description: str
    critical: bool = False


def step(description: str, *, critical: bool = False):
    """Mark an instance method as a step, in class declaration order."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("step description must be a nonempty string")
    if type(critical) is not bool:
        raise ValueError("step critical must be a boolean")

    def decorate(function: Callable):
        validate_method(function)
        if hasattr(function, "__tzen_step__"):
            raise ValueError("a method may have only one @step decorator")
        function.__tzen_step__ = Step(function.__name__, description, critical)
        return function

    return decorate


def validate_method(function: Callable) -> tuple[str, ...]:
    if not inspect.isfunction(function) or inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function):
        raise ValueError("Tzen methods must be synchronous instance methods")
    parameters = list(inspect.signature(function).parameters.values())
    if not parameters or parameters[0].name != "self":
        raise ValueError("Tzen methods must start with self")
    for parameter in parameters[1:]:
        if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY):
            raise ValueError("Tzen method fixtures must be named parameters")
        if parameter.default is not parameter.empty:
            raise ValueError("Tzen method fixture parameters cannot have defaults")
    return tuple(parameter.name for parameter in parameters[1:])


class TzenTestCase:
    """One instance and one C execution per collected testcase.

    Set target to the exact C name (defaults to the concrete class name).
    Inherit from TzenRemoteTestCase or TzenCompanionTestCase to declare a test.
    Companion constructors and steps may request pytest fixtures.
    The runner assigns run during execution and keeps state on self between
    steps. Resource cleanup belongs to fixture finalizers, not testcase hooks.
    """

    __test__ = False
    target: str | None = None


class TzenRemoteTestCase(TzenTestCase):
    """Declare documentation and identity for C-only execution."""


class TzenCompanionTestCase(TzenTestCase):
    """Declare Python steps cooperating with one C execution."""


def class_steps(cls: type[TzenTestCase]) -> tuple[Step, ...]:
    """Base steps first; overrides keep their position, new steps append.

    A non-step override removes the inherited step. Multiple testcase bases
    are rejected to avoid surprising ordering in diamond hierarchies.
    """
    steps = {}
    for base in reversed(cls.__mro__):
        if base in (object, TzenTestCase):
            continue
        if any(name in vars(base) for name in ("setup", "teardown", "requirements", "tags", "companion")):
            raise ValueError("Use an explicit testcase subclass; companion, setup/teardown, and requirements/tags are not supported")
        if len([parent for parent in base.__bases__ if issubclass(parent, TzenTestCase)]) > 1:
            raise ValueError("Multiple TzenTestCase bases are not supported")
        for name, value in vars(base).items():
            if isinstance(value, (staticmethod, classmethod)) and hasattr(value.__func__, "__tzen_step__"):
                raise ValueError("@step requires an instance method")
            metadata = getattr(value, "__tzen_step__", None)
            if metadata is not None:
                if name in ("setup", "teardown") or name.startswith("__"):
                    raise ValueError("Lifecycle methods cannot be decorated with @step")
                validate_method(value)
                steps[name] = metadata
            elif name in steps:
                del steps[name]
    return tuple(steps.values())


def class_fixtures(cls: type[TzenTestCase], steps: tuple[Step, ...]) -> tuple[str, ...]:
    """Validate step signatures, returning only testcase-lifetime fixtures."""
    if cls.__new__ is not object.__new__:
        raise ValueError("Custom __new__ is not supported")
    for step in steps:
        validate_method(inspect.getattr_static(cls, step.name))
    if cls.__init__ is object.__init__:
        return ()
    return validate_method(inspect.getattr_static(cls, "__init__"))
