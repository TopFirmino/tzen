#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
"""This module provides the basic test organizer classes to manage and run tests in a session."""

from __future__ import annotations

from typing import List, Union, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .tz_test import TZTest
  
class TZTestOrganizer:
    """Class to organize and manage tests in a session."""
    
    def __init__(self, tests: Mapping[str, TZTest], *args, **kwargs):
        self.tests = tests
         
    def size(self) -> int:
        """Get the number of tests in the organizer. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def iterate(self) -> List[TZTest]:
        """Iterate through the tests in the organizer. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")

class TZTestOrganizerList(TZTestOrganizer):
    """Class to organize tests in a list. It allows to add tests and retrieve them in the order they were added."""
    
    def size(self) -> int:
        """Get the number of tests in the organizer."""
        return len(self.tests)
    
    def iterate(self):
        """Iterate through the tests in the organizer."""
        for name, test in self.tests.items():
            yield test

class TZTestOrganizerTree(TZTestOrganizer):
    """Class to organize tests in a tree structure where each test has as parent the module it belongs to."""

    @dataclass
    class TreeNode:
        """Class to represent a node in the test tree."""
        obj:object = None
        name:str = ""
        children: List[TZTestOrganizerTree.TreeNode] = field(default_factory=list)
        path: Path = None
        
    def __init__(self, tests: Mapping[str, TZTest], root_path:Path):
        super().__init__(tests)
        self.root = TZTestOrganizerTree.TreeNode(obj=None, path=root_path)
        self._create_tree()
          
    def _create_tree(self):
        """Populate the tree structure by the tests path."""
        
        for test_name, test in self.tests.items():
            
            _queue = [self.root]
            
            while _queue:
                
                _node = _queue.pop(-1)
                test_class_path_rel = test.get_path().relative_to(_node.path)
                
                # If the rel path has just one part, it means it's a direct child of the current node and it's a test class
                if len(test_class_path_rel.parts) == 1:
                    _node.children.append( TZTestOrganizerTree.TreeNode(obj=test, path=test.get_path(), name=test.name) )
                
                # If the rel path has more than one part, it means it's a subchild of the current node
                elif len(test_class_path_rel.parts) > 1:
                    
                    for child in _node.children:
                        if child.path.parts[-1] == test_class_path_rel.parts[0]:
                            _queue.append(child)
                            break
                    else:
                        # If no child matches, we create a new node for the module
                        new_node = TZTestOrganizerTree.TreeNode(obj=None, name=str(test_class_path_rel.parts[0]), path=self.root.path.joinpath(test_class_path_rel.parts[0]))
                            
                        _node.children.append(new_node)
                        _queue.append(new_node)
                        
    def iterate(self):
        """Iterate through the tests tree in the organizer."""
        _queue = [self.root]
        
        while _queue:
            current_node = _queue.pop(-1)

            if current_node.obj is not None and len(current_node.children) == 0:
                yield current_node.obj
            
            for child in current_node.children[::-1]:    
                _queue.append(child)
            
    def size(self) -> int:
        """Get the number of tests in the organizer. This method should be implemented by subclasses."""
        return len(self.tests)
                    