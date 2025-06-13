from .tz_test import TZTest, tz_get_test_table

class TZTestOrganizer:
    """Class to organize and manage tests in a session."""
    
    def fetch_all(self, **kwargs) -> None:
        """Fetch tests to be run. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def get_next(self) -> TZTest:
        """Get the next test to run. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def get_test_num(self) -> int:
        """Get the number of tests in the organizer. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def get_all_tests(self) -> list[TZTest]:
        """Get all tests in the organizer. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def from_name_list(self, names: list[str]) -> None:
        """Fetch tests by their names. This method should be implemented by subclasses."""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
class TZTestOrganizerList(TZTestOrganizer):
    """Class to organize tests in a list. It allows to add tests and retrieve them in the order they were added."""
    def __init__(self, tests: list[TZTest] | list[str] = None):
        super().__init__()
        self.tests: list[TZTest] = []

        # Handle initialization with a list of test classes or names
        if tests and len(tests) > 0:
            if isinstance(tests[0], str):
                self.fetch_from_name_list(tests)
            elif issubclass(tests[0], TZTest):
                self.tests.extend(tests)
                
    def fetch_all(self, order="asc"):
        """Fetch tests to be run. It will populate the tests list with all tests from the test table."""
        _test_table = tz_get_test_table()
        
        for test_name in sorted(_test_table.keys(), reverse=(order == "desc")):
            test_class = _test_table[test_name]
            self.tests.append(test_class) 
    
    def get_next(self) -> TZTest:
        """Get the next test to run."""
        if not self.tests:
            raise IndexError("No tests available")
        return self.tests.pop(0)
    
    def get_test_num(self) -> int:
        """Get the number of tests in the organizer."""
        return len(self.tests)
    
    def get_all_tests(self) -> list[TZTest]:
        """Get all tests in the organizer."""
        return self.tests
    
    def fetch_from_name_list(self, names):
        """Fetch tests by their names. It will populate the tests list with the specified test classes."""
        if not isinstance(names, list):
            raise TypeError("names must be a list of test class names") 
        _test_table = tz_get_test_table()
        for name in names:
            if name not in _test_table:
                raise ValueError(f"Test class '{name}' not found in the test table")
            self.tests.append(_test_table[name])
            
    


# # Remove Test Node from here, it is not used in the public API
# class TestTreeNode:
#     def __init__(self, name):
#         self.name = name  # nome locale, es. "a", "b", "test1"
#         self.children: dict[str, TestTreeNode] = {}
#         self.test_class = None  # classe associata se foglia

#     def add(self, test_class):
#         parts = tz_get_class_full_name_parts(test_class)
#         self._add_parts(list(parts), test_class)

#     def _add_parts(self, parts: list[str], test_class):
#         if not parts:
#             self.test_class = test_class
#             return
#         head = parts[0]
#         if head not in self.children:
#             self.children[head] = TestTreeNode(head)
#         self.children[head]._add_parts(parts[1:], test_class)

#     def print(self, indent=0):
#         prefix = "  " * indent
#         label = self.name + (f" [TestClass: {self.test_class.__name__}]" if self.test_class else "")
#         print(f"{prefix}{label}")
#         for child in sorted(self.children.values(), key=lambda c: c.name):
#             child.print(indent + 1)

#     def find(self, abs_path: str):
#         parts = Path(abs_path).parts
#         return self._find_parts(list(parts))

#     def _find_parts(self, parts: list[str]):
#         if not parts:
#             return self
#         head = parts[0]
#         if head not in self.children:
#             return None
#         return self.children[head]._find_parts(parts[1:])
        
# __TZEN_TEST_TREE_ROOT__ = TestTreeNode(".")        
        
    