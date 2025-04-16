"""This module implements the basic tests for the tzen package.
It is used to test the basic functionality of the package."""

from tzen.tz_test import TZTest 
import time


class TC_0001(TZTest):
    """Basic test case to check the functionality of TZTest class.
    
    @requirement RQT-0001
    @requirement RQT-0002
    @expected_result 1
    """
    
    def __init__(self):
        super().__init__()
        self.debug("Initializing TC_0001")
        self.var = 0
        
    @TZTest.step
    def step1(self):
        """Sets the variable to 1."""
        time.sleep(0.2)
        self.debug("Step 1")
        self.var += 1
        
        assert self.var == 1
        
    @TZTest.step
    def step2(self):
        """Makes lot of noise."""
        time.sleep(0.5)
        self.debug("Step 2")
        assert self.var == 1


class TC_0002(TZTest):
    
    def __init__(self):
        super().__init__()
        self.debug("Initializing TC_0002")
        self.counter = 0
        
    @TZTest.step
    def step1(self):
        time.sleep(0.3)
        self.debug("Step 1: Increment counter")
        self.counter += 1
        assert self.counter == 1
        
    @TZTest.step
    def step2(self):
        time.sleep(0.7)
        self.debug("Step 2: Increment counter again")
        self.counter += 1
        assert self.counter == 2
    
    @TZTest.step
    def step3(self):
        time.sleep(0.4)
        self.debug("Step 3: Double counter value")
        self.counter *= 2
        assert self.counter == 4
    
    @TZTest.step
    def step4(self):
        time.sleep(0.8)
        self.debug("Step 4: Add 6 to counter")
        self.counter += 6
        assert self.counter == 10
    
    @TZTest.step
    def step5(self):
        time.sleep(0.6)
        self.debug("Step 5: Divide counter by 2")
        self.counter /= 2
        assert self.counter == 5


class TC_0003(TZTest):
    
    def __init__(self):
        super().__init__()
        self.debug("Initializing TC_0003")
        self.text = "hello"
        
    @TZTest.step
    def step1(self):
        time.sleep(0.5)
        self.debug("Step 1: Append to string")
        self.text += " world"
        assert self.text == "hello world"
        
    @TZTest.step
    def step2(self):
        time.sleep(0.3)
        self.debug("Step 2: Convert to uppercase")
        self.text = self.text.upper()
        assert self.text == "HELLO WORLD"
    
    @TZTest.step
    def step3(self):
        time.sleep(0.9)
        self.debug("Step 3: Replace text")
        self.text = self.text.replace("WORLD", "PYTHON")
        assert self.text == "HELLO PYTHON"
    
    @TZTest.step
    def step4(self):
        time.sleep(1.0)
        self.debug("Step 4: This step will fail")
        # This assertion will fail
        assert "TEST" in self.text, "Expected 'TEST' in string but not found"
    
    @TZTest.step
    def step5(self):
        time.sleep(0.4)
        self.debug("Step 5: Won't be reached due to failure in step 4")
        self.text += " PROGRAMMING"
        assert len(self.text) > 20


class TC_0004(TZTest):
    
    def __init__(self):
        super().__init__()
        self.debug("Initializing TC_0004")
        self.numbers = []
        
    @TZTest.step
    def step1(self):
        time.sleep(0.7)
        self.debug("Step 1: Create list of numbers")
        for i in range(1, 6):
            self.numbers.append(i)
        assert len(self.numbers) == 5
        
    @TZTest.step
    def step2(self):
        time.sleep(0.2)
        self.debug("Step 2: Sort in reverse order")
        self.numbers.sort(reverse=True)
        assert self.numbers[0] == 5
    
    @TZTest.step
    def step3(self):
        time.sleep(0.6)
        self.debug("Step 3: Remove largest number")
        largest = self.numbers.pop(0)
        assert largest == 5
        assert len(self.numbers) == 4
    
    @TZTest.step
    def step4(self):
        time.sleep(0.4)
        self.debug("Step 4: Calculate sum")
        self.sum = sum(self.numbers)
        assert self.sum == 10  # 4+3+2+1 = 10
    
    @TZTest.step
    def step5(self):
        time.sleep(0.8)
        self.debug("Step 5: This step will fail with incorrect calculation")
        result = self.sum * 2
        # This assertion will fail (expecting 21 but it's actually 20)
        assert result == 21, f"Expected 21 but got {result}"
