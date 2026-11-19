"""Step-local lifetimes for ordinary pytest function-scoped fixtures.

Pytest has no public nested function scope. Keep its version-sensitive request
cache access here; setup itself still uses request.getfixturevalue(), including
fixture dependency resolution, request.addfinalizer(), and yield fixtures.
"""
from collections.abc import Callable
from contextlib import contextmanager


class FixtureTeardownError(RuntimeError):
    """Step cleanup failed; continuing the testcase would be unsafe."""


class FixtureSetupError(RuntimeError):
    """A requested step fixture could not be prepared."""


@contextmanager
def step_fixture_scope(request):
    item = request.node
    existing = dict(request._fixture_defs)
    finalizers: list[Callable[[], None]] = []
    original = item.__dict__.get("addfinalizer")
    # Function-scoped subrequests attach their finalizers to the current item.
    # Broader scopes attach to their module/session and keep their normal life.
    item.addfinalizer = finalizers.append

    def resolve(name):
        try:
            return request.getfixturevalue(name)
        except Exception as error:
            raise FixtureSetupError(f"Step fixture {name!r} setup failed: {error}") from error

    try:
        yield resolve
    finally:
        errors = []
        try:
            while finalizers:
                try:
                    finalizers.pop()()
                except BaseException as error:
                    errors.append(error)
        finally:
            if original is None:
                del item.addfinalizer
            else:
                item.addfinalizer = original
            # Cached values owned by the constructor/autouse fixtures survive.
            # Discard only newly requested function fixtures so the next step
            # resolves a fresh instance rather than a finalized cached value.
            for name, definition in list(request._fixture_defs.items()):
                if name not in existing and definition.scope == "function":
                    del request._fixture_defs[name]
        if errors:
            raise FixtureTeardownError("Step fixture teardown failed: " + "; ".join(
                f"{type(error).__name__}: {error}" for error in errors
            )) from errors[0]
