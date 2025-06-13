from __future__ import annotations

from typing import Mapping, List
from enum import Enum
from dataclasses import dataclass


class TZFixtureScope(Enum):
    """Enum to represent the scope of a fixture."""
    TEST = "test"
    MODULE = "module"
    SESSION = "session"
    
@dataclass
class TZFixtureMarker():
    """Dataclass to represent a fixtures marker for objects."""
    cls: type[TZFixture]
    obj: object = None # Instance of the fixture, will be set when the fixture is used
    args: List[object] = None
    kwargs: Mapping[str, object] = None
    scope: TZFixtureScope = TZFixtureScope.TEST
    
    def __getattr__(self, name):
        if self.obj is not None:
            return getattr(self.obj, name)
        raise AttributeError(f"'TZFixtureMarker' has no attribute '{name}' and `obj` is not set.")

    def __setattr__(self, name, value):
        if name in {'obj', 'cls', 'args', 'kwargs', 'scope'} or self.obj is None:
            super().__setattr__(name, value)
        else:
            setattr(self.obj, name, value)

    def __call__(self, *args, **kwargs):
        if self.obj is not None and callable(self.obj):
            return self.obj(*args, **kwargs)
        raise TypeError(f"'TZFixtureMarker' object is not callable or `obj` is not set.")

    def __getitem__(self, key):
        if self.obj is not None:
            return self.obj[key]
        raise TypeError(f"'TZFixtureMarker' object is not subscriptable or `obj` is not set.")
    
    def __hash__(self):
        return hash((self.cls, tuple(self.args), frozenset(self.kwargs.items()), self.scope))
    
def tz_use_fixture(fixture_class: type[TZFixture], *args, scope: TZFixtureScope = TZFixtureScope.TEST, **kwargs) -> TZFixture:
    """Use a fixture class to create an instance of it."""
    if not issubclass(fixture_class, TZFixture):
        raise TypeError("fixture_class must be a subclass of TZFixture")
    
    return TZFixtureMarker (
        obj=None,  # This will be set later when the fixture is used
        cls=fixture_class,
        args=list(args),
        kwargs=dict(kwargs),
        scope=scope)

class TZFixtureManager:
    """Manager for fixtures. It will keep track of all created fixtures and will return the correct instance based on the Marker."""
    
    def __init__(self):
        self.fixtures: Mapping[TZFixtureMarker, TZFixture] = {}
    
    def get_fixture(self, marker: TZFixtureMarker) -> TZFixture:
        """Get a fixture instance based on the marker."""
        if marker not in self.fixtures:
            fixture = marker.cls(*marker.args, **marker.kwargs)
            self.fixtures[marker] = fixture
            fixture.setup()
        
        marker.obj = self.fixtures[marker]  # Set the instance in the marker
            
        return self.fixtures[marker]
    
    def release_fixture(self, marker: TZFixtureMarker):
        """Release a fixture instance based on the marker."""
        if marker in self.fixtures:
            fixture = self.fixtures[marker]
            fixture.teardown()
            del self.fixtures[marker]
            
        marker.obj = None
    
    def release_all(self):
        """Release all fixtures."""
        for marker in list(self.fixtures.keys()):
            self.release_fixture(marker)
            
class TZFixture:
    
    def setup(self):
        raise NotImplementedError

    def teardown(self):
        raise NotImplementedError
    