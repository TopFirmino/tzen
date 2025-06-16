from __future__ import annotations

from typing import List, Union, Mapping
from .tz_test import TZTest, tz_get_test_table
from dataclasses import dataclass, field
import inspect
from pathlib import Path

class TZTestOrganizer:
    """Class to organize and manage tests in a session."""
    
    def fetch_all(self, **kwargs) -> None:
        """Fetch tests to be run. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def get_test_num(self) -> int:
        """Get the number of tests in the organizer. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def get_all_tests(self) -> List[TZTest]:
        """Get all tests in the organizer. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def from_name_list(self, names: List[str]) -> None:
        """Fetch tests by their names. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
class TZTestOrganizerList(TZTestOrganizer):
    """Class to organize tests in a list. It allows to add tests and retrieve them in the order they were added."""
    def __init__(self, tests: Union[List[TZTest], List[str]] = None):
        super().__init__()
        self.tests: List[TZTest] = []

        # Handle initialization with a list of test classes or names
        if tests and len(tests) > 0:
            if isinstance(tests[0], str):
                self.fetch_from_name_list(tests)
            elif issubclass(tests[0], TZTest):
                self.tests.extend(tests)
        else:
            self.fetch_all()
            
    def fetch_all(self, order="asc"):
        """Fetch tests to be run. It will populate the tests list with all tests from the test table."""
        _test_table = tz_get_test_table()
        
        for test_name in sorted(_test_table.keys(), reverse=(order == "desc")):
            test_class = _test_table[test_name]
            self.tests.append(test_class) 
    
    def get_test_num(self) -> int:
        """Get the number of tests in the organizer."""
        return len(self.tests)
    
    def get_all_tests(self) -> List[TZTest]:
        """Get all tests in the organizer."""
        return self.tests
    
    def fetch_from_name_list(self, names: List[str]):
        """Fetch tests by their names. It will populate the tests list with the specified test classes."""
        if not isinstance(names, list):
            raise TypeError("names must be a list of test class names") 
        _test_table = tz_get_test_table()
        for name in names:
            if name not in _test_table:
                raise ValueError(f"Test class '{name}' not found in the test table")
            self.tests.append(_test_table[name])
       
class TZTestOrganizerTree(TZTestOrganizer):
    """Class to organize tests in a tree structure where each test has as parent the module it belongs to."""

    @dataclass
    class TreeNode:
        """Class to represent a node in the test tree."""
        obj:object = None
        name:str = ""
        children: 'List[TreeNode]' = field(default_factory=list)
        path: Path = None
        
    def __init__(self, root_path: Path, tests: Union[List[TZTest], List[str]] = None):
        super().__init__()
        self.root = TZTestOrganizerTree.TreeNode(obj=None, path=root_path)
        self.fetch_all()
        
    def _module_in_tree(self, module: object) -> TZTestOrganizerTree.TreeNode:
        """Check if a module is already in the tree."""
        if self.root is None:
            return None
        
        def _check_node(node: TZTestOrganizerTree.TreeNode) -> bool:
            if node.obj == module:
                return node
            for child in node.children:
                if _check_node(child):
                    return child
            return None
        
        return _check_node(self.root)
    
    def fetch_all(self, **kwargs):
        """Fetch tests to be run. It will populate the tests tree."""
        
        for test_name, test_class in tz_get_test_table().items():
            
            # Get the module from the test_class
            module = inspect.getmodule(test_class)
            test_class_path = Path(module.__file__).joinpath(test_class.__name__) 
            test_class_path_rel = test_class_path.relative_to(self.root.path)
            
            _queue = [self.root]
            
            while _queue:
                
                _node = _queue.pop(-1)
                test_class_path_rel = test_class_path.relative_to(_node.path)
                
                # If the rel path has just one part, it means it's a direct child of the current node and it's a test class
                if len(test_class_path_rel.parts) == 1:
                    _node.children.append( TZTestOrganizerTree.TreeNode(obj=test_class, path=test_class_path, name=test_class.__name__) )
                
                # If the rel path has more than one part, it means it's a subchild of the current node
                elif len(test_class_path_rel.parts) > 1:
                    
                    for child in _node.children:
                        if child.path.parts[-1] == test_class_path_rel.parts[0]:
                            _queue.append(child)
                            break
                    else:
                        # If no child matches, we create a new node for the module
                        if len(test_class_path_rel.parts) == 2:
                            new_node = TZTestOrganizerTree.TreeNode(obj=module, path=test_class_path.parent, name=module.__name__)
                        else:
                            new_node = TZTestOrganizerTree.TreeNode(obj=None, name=str(test_class_path_rel.parts[0]), path=self.root.path.joinpath(test_class_path_rel.parts[0]))
                            
                        _node.children.append(new_node)
                        _queue.append(new_node)
                        
    def get_all_tests(self):
        """Get all tests in the organizer. It will yield all test classes in the tree."""
        _queue = [self.root]
        
        while _queue:
            current_node = _queue.pop(-1)

            if current_node.obj is not None and len(current_node.children) == 0 and issubclass(current_node.obj, TZTest):
                yield current_node.obj
            
            for child in current_node.children[::-1]:    
                _queue.append(child)
            
    def get_test_num(self) -> int:
        """Get the number of tests in the organizer. This method should be implemented by subclasses."""
        return len([*self.get_all_tests()])
                    