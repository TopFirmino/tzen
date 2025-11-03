#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This module implements the tree structure of a teen project. 
The tree is composed by TzTreeNode objects and uses the path of the object in order to identify dependencies. 
It is possible to register different kind of nodes via tz_tree_register_type decorator providing a factory and a provider for the registered type.
"""

from __future__ import annotations
from typing import Protocol, Dict, List, Callable, Tuple, Any
from pathlib import Path
import inspect
import os

TZ_TREE_TYPES:Dict[str, TzTreeTypeSpec] = {}

class TzTreeTypeSpec:
    __slots__ = ("cls", "provider",  "injector")

    def __init__(self, cls, provider, injector) -> None:
        self.cls = cls
        self.provider = provider
        self.injector = injector

class TzTreeProviderHook(Protocol):
    def __call__(self, name: str, selector: str) -> None: ...

class TzTreeConsumerHook(Protocol):
    def __call__(self, func:Callable) -> Tuple[str,str] | None: ...

class TzTreeInjectorHook(Protocol):
    def __call__(self, func:Callable, consumer:str) -> Callable: ...


def tz_tree_register_type(kind:str, *, provider:TzTreeProviderHook, injector:TzTreeInjectorHook|None = None):
    """Decorator used to register a new kind of node"""

    def _wrapper(cls):
        TZ_TREE_TYPES[kind] = TzTreeTypeSpec(cls, provider, injector)
        return cls
    
    return _wrapper

class TzTreeNode:

    __slots__ = ("name", "kind", "parent", "children", "obj")

    def __init__(self, name:str, kind) -> None:
        self.name = name
        self.parent = None
        self.children = []
        self.kind = kind

    def add(self, child:TzTreeNode) -> None:
        child.parent = self
        self.children.append(child)

    def _dfs_search(self, predicate:Callable[[TzTreeNode],bool], just_one=False) -> List[TzTreeNode]:
        results = []
        queue = []
        queue.append(self)

        while len(queue) > 0:

            _node = queue.pop(-1)

            if predicate(_node):
                results.append(_node)
                if just_one:
                    break

            for c in _node.children[::-1]:
                queue.append(c)
            
        return results
    
    def visit(self, callback:Callable[[TzTreeNode], Any]):
        
        def _predicate(_node:TzTreeNode) -> bool:
            callback(_node)
            return False
        
        self._dfs_search(_predicate)

    def get_by_name(self, name):
        res = self._dfs_search(lambda node: node.name == name, just_one=True)
        return res[0] if len(res) > 0 else None
    
    def find(self, kind) -> List[TzTreeNode]:    
        return self._dfs_search(lambda node: node.kind == kind)

    def get_children_of_kind(self, kind:str) -> List[TzTreeNode]:
        _res = []

        for c in self.children:
            if c.kind == kind:
                _res.append(c)
        
        return _res

    def get_child(self, name:str) -> TzTreeNode | None:
        _res = None
        for c in self.children:
            if c.name == name:
                _res = c
        return _res 

    def resolve(self, selector:str):

        _selector = Path(selector)
        relative = _selector

        if _selector.is_absolute():
            relative = Path(selector).relative_to(Path(self.get_selector()))
       
        _node = self
        for p in Path(relative).parts:

            if p == '.':
                pass
            
            elif p == '..':
                _node = _node.parent
            
            else:
                _node = _node.get_child(p)

            if _node is None:
                return None
        
        return _node

    def get_selector(self) -> str:
        
        parts = []
        _queue = [self]

        while len(_queue) > 0:

            _node = _queue.pop(0)
            
            if _node == None:
                break

            parts.append(_node.name)
            _queue.append(_node.parent)

        return os.path.join(*parts[::-1])

    def get_object(self, *args, **kwargs):
        return TZ_TREE_TYPES[self.kind].provider(self.name, self.get_selector(), *args, **kwargs)

    def __str__(self, level=0):
        ret = "\t"*level+repr(self.name)+"\n"
        for child in self.children:
            ret += child.__str__(level+1)
        return ret


_TZEN_CONTAINERS_ = {}

def _container_provider(name:str, selector:str):
    if name not in _TZEN_CONTAINERS_:
        _TZEN_CONTAINERS_[name] = TzTreeContainerNode(name, selector)

    return _TZEN_CONTAINERS_.get(name)

@tz_tree_register_type("container", provider=_container_provider )
class TzTreeContainerNode:

    __slots__ = ("name", "selector", "doc")

    def __init__(self, name:str, selector:str) -> None:
        self.name = name
        self.selector = selector
        self.doc = ""

class TzSimpleSingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs) -> Any:
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

class TzTree(TzTreeNode, metaclass=TzSimpleSingletonMeta):

    def __init__(self) -> None:
        super().__init__("/", 'container')

    def inject(self, func, consumer):
       
        if not self.resolve(consumer):
            raise RuntimeError("Cannot find a valid consumer with selector {consumer}")
        
        # Inject the function 
        for k, v in TZ_TREE_TYPES.items():
            if v.injector:
                func = v.injector(func, consumer=consumer)
        
        return func
    
    def load(self, path: Path) -> None:
        """Loads the tree by calling the loader hook for every node types"""
        pass

        """ abs_path = path.absolute()

        for k, v in TZ_TREE_TYPES.items():
            slugs = v.loader()
        
            for name, slug in slugs:
                
                _relative = Path(slug).resolve().relative_to(abs_path)
                _node = self.create_containers(_relative.as_posix())
                
                if _node:
                    _node.name = name
                    _node.kind = k     """            
                    
    def create_containers(self, selector:str) -> TzTreeNode | None:
        """Creates all containers in the resolver. Returns the last container"""

        _node = self

        for p in Path(selector).parts:
            
            _new_node = _node.resolve(p)

            if _new_node is None:
                _new_node = TzTreeNode(p, "container")
                _node.add( _new_node )

            _node = _new_node
        
        return self.resolve(selector)
    
    def add_object(self, name:str, selector:str, kind:str) -> TzTreeNode:
        _p = Path(selector)

        if not _p.is_absolute():
            raise RuntimeError("selector shall be an absolute path")

        _obj = self.create_containers(_p.as_posix())
        
        if _obj:
            _obj.kind = kind
            _obj.name = name
        
        return _obj