"""This module implements 2 additional simple tests.
It is used to demonstrate further simple functionality of the tzen package."""

from tzen.tz_test import TZTest, tz_step
import time

class TS_0001(TZTest):
    """Another basic test case to check TZTest functionality."""

    def __init__(self):
        super().__init__()
        self.data = 100

    @tz_step
    def check_initial_data(self):
        """Verifies the initial data value."""
        time.sleep(0.1)
        self.logger.debug(f"Initial data: {self.data}")
        assert self.data == 100

    @tz_step
    def modify_data(self):
        """Modifies the data and verifies the change."""
        time.sleep(0.2)
        self.data -= 25
        self.logger.debug(f"Modified data: {self.data}")
        assert self.data == 75

class TS_0002(TZTest):
    """Test case with string manipulations."""

    def __init__(self):
        super().__init__()
        self.text = "tzen"

    @tz_step
    def append_text(self):
        """Appends to the string and checks."""
        time.sleep(0.15)
        self.text += "_test"
        self.logger.debug(f"Appended text: {self.text}")
        assert self.text == "tzen_test"

    @tz_step
    def uppercase_text(self):
        """Converts text to uppercase and checks."""
        time.sleep(0.25)
        self.text = self.text.upper()
        self.logger.debug(f"Uppercased text: {self.text}")
        assert self.text == "TZEN_TEST"

class TS_0003(TZTest):
    """Test case with a single verification step."""

    def __init__(self):
        super().__init__()
        self.is_ready = False

    @tz_step
    def set_and_verify_ready(self):
        """Sets a boolean flag and verifies it."""
        time.sleep(0.1)
        self.is_ready = True
        self.logger.debug(f"Flag is_ready set to: {self.is_ready}")
        assert self.is_ready is True