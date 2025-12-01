#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
from __future__ import annotations
import sys
from .tz_tree import TzTree, tz_tree_register_type
from typing import Any, Callable
import inspect
from pathlib import Path
import functools

_TZEN_CONSTANTS_ = {}

def tz_add_constant(name:str, value:Any):
    if name in _TZEN_CONSTANTS_:
        raise RuntimeError(f"Constant '{name}' already exists")
    
    _TZEN_CONSTANTS_[name] = TZConstant(name, value)
    return _TZEN_CONSTANTS_[name]

def _tz_constant_provider(name:str, selector:str):
    if name not in _TZEN_CONSTANTS_:
        raise RuntimeError(f"Constant '{name}' does not exist")
    return _TZEN_CONSTANTS_[name]

def _tz_constant_injector(func:Callable, consumer:str) -> Callable:
    
    base = inspect.unwrap(func)
    sig = inspect.signature(base)
    for name, param in sig.parameters.items():
        if name in _TZEN_CONSTANTS_:
            _constant_node = TzTree().add_object(name, str((Path(consumer) / name)), kind='constant')

    @functools.wraps(func)
    def _wrapper(*f_args, **f_kwargs):
        
        bound = sig.bind_partial(*f_args, **f_kwargs)
            
        for name, param in sig.parameters.items():
            if name in bound.arguments:
                continue
            if param.default is not inspect._empty:
                continue
            if name in _TZEN_CONSTANTS_:
                bound.arguments[name] = _TZEN_CONSTANTS_[name].value

        return func(*bound.args, **bound.kwargs)

    return _wrapper

@tz_tree_register_type('constant', provider=_tz_constant_provider, injector=_tz_constant_injector)
class TZConstant:
    __slots__ = ('name', 'value', 'doc')

    def __init__(self, name:str, value:Any, doc:str = '') -> None:
        self.name = name
        self.value = value
        self.doc = ''

