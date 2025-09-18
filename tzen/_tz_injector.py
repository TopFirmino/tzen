#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This modules provides the basic dependecy injections. Provides dependecyes via Fixture and Configuration modules."""

from __future__ import annotations
import inspect
from functools import wraps
from .tz_fixture import *
from tzen import tz_conf

def tz_inject(_func=None):
    """Decorator to inject depedencies into a function or method. Valid dependencies are fixtures and configuration values."""
    
    def decorator(func):
        sig = inspect.signature(func)

        @wraps(func)
        def wrapper(*f_args, **f_kwargs):
            # bind parziale: unisce gli argomenti passati esplicitamente
            bound = sig.bind_partial(*f_args, **f_kwargs)
            
            # iniettiamo quelli mancanti
            for name, param in sig.parameters.items():
                if name in bound.arguments:
                    continue                        # già fornito dal chiamante
                if param.default is not inspect._empty:
                    continue                        # ha un default → non toccare
                try:
                    bound.arguments[name] = _tz_provide_dependency(param)
                except KeyError as exc:
                    raise RuntimeError(
                        f"Nessun provider disponibile per '{name}' "
                        f"(annotation={param.annotation})"
                    ) from exc

            return func(*bound.args, **bound.kwargs)

        return wrapper

    # Caso `@inject` senza parentesi
    if callable(_func):
        return decorator(_func)

    # Caso `@inject()` con o senza argomenti futuri
    return decorator

def _provide_configuration_dependency(param: inspect.Parameter):
    """Provides a configuration dependency for a given parameter."""
    return tz_conf.get(param.name, None)
   
def _provide_fixture_dependency(param: inspect.Parameter):
    fixture = tz_get_fixture_by_name(param.name)
    
    if fixture is None:
        if param.annotation is inspect._empty:
            raise RuntimeError(f"Parameter '{param.name}' has no type annotation and no fixture found")
        fixture = tz_get_fixture_by_name(param.annotation)
        if fixture is None:
            raise RuntimeError(f"Parameter '{param.name}' has no type annotation")

    return fixture

def _tz_provide_dependency(param: inspect.Parameter):
    """Provides a dependency for a given parameter."""
    # Check if the parameter name is a configuration value
    dependency = _provide_configuration_dependency(param)
    
    if dependency is None:
        dependency = _provide_fixture_dependency(param)
        
    return dependency
   