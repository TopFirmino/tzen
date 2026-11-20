# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Execute the methods of one class-based companion as one pytest testcase."""
from __future__ import annotations

from dataclasses import dataclass

from .cases import Step, TzenTestCase, class_fixtures, validate_method
from .fixture_scope import step_fixture_scope


@dataclass
class StepResult:
    name: str
    description: str
    critical: bool
    outcome: str = "not_run"
    message: str = ""


class StepFailure(AssertionError):
    """One or more Python steps failed."""


def execute_steps(cls: type[TzenTestCase], steps: tuple[Step, ...], case,
                  fixtures: dict, results: list[StepResult]) -> None:
    instance = cls(**{name: fixtures[name] for name in class_fixtures(cls, steps)})
    instance.run = None
    results.extend(StepResult(step.name, step.description, step.critical) for step in steps)

    with case.run() as run:
        instance.run = run
        for result in results:
            try:
                with step_fixture_scope(fixtures["request"]) as resolve:
                    arguments = {name: resolve(name) for name in validate_method(getattr(cls, result.name))}
                    getattr(instance, result.name)(**arguments)
            except AssertionError as error:
                result.outcome = "failed"
                result.message = str(error) or type(error).__name__
                if result.critical:
                    raise StepFailure(f"Critical step {result.name}: {result.message}") from error
            except BaseException as error:
                result.outcome = "error"
                result.message = f"{type(error).__name__}: {error}"
                raise
            else:
                result.outcome = "passed"
        failed = [result for result in results if result.outcome == "failed"]
        if failed:
            raise StepFailure("\n".join(f"{result.name}: {result.message}" for result in failed))
    case.assert_completed()
