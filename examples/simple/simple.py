"""This module implements 2 simple tests.
It is used to demonstrate the simple functionality of the package."""

from tzen.tz_test import TZTest, tz_step
import time


class TC_0001(TZTest):
    """Basic test case to check the functionality of TZTest class. """
    
    def __init__(self):
        super().__init__()
        self.var = 0
        
    @tz_step
    def step1(self):
        """Sets the variable to 1."""
        time.sleep(0.2)
        self.logger.debug("Step 1")
        self.var += 1
        assert self.var == 1
        
    @tz_step
    def step2(self):
        """Makes lot of noise."""
        time.sleep(0.5)
        self.logger.debug("Step 2")
        assert self.var == 1


class TC_0002(TZTest):
    """Test case to check the functionality of TZTest class with multiple steps."""

    def __init__(self):
        super().__init__()
        self.counter = 0
        
    @tz_step
    def step1(self):
        time.sleep(0.3)
        self.logger.debug("Step 1: Increment counter")
        self.counter += 1
        assert self.counter == 1
        
    @tz_step
    def step2(self):
        time.sleep(0.7)
        self.logger.debug("Step 2: Increment counter again")
        self.counter += 1
        assert self.counter == 2
    
    @tz_step
    def step3(self):
        time.sleep(0.4)
        self.logger.debug("Step 3: Double counter value")
        self.counter *= 2
        assert self.counter == 4
    
    @tz_step
    def step4(self):
        time.sleep(0.8)
        self.logger.debug("Step 4: Add 6 to counter")
        self.counter += 6
        assert self.counter == 10
    
    @tz_step
    def step5(self):
        time.sleep(0.6)
        self.logger.debug("Step 5: Divide counter by 2")
        self.counter /= 2
        assert self.counter == 5


