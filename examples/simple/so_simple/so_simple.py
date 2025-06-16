"""This module implements simple calculator test cases.
It demonstrates basic testing patterns for mathematical operations."""

from tzen.tz_test import TZTest, tz_step
import time


class SimpleAddition(TZTest):
    """Test case for verifying basic addition functionality.
    
    This test ensures that addition operations work correctly
    with various combinations of positive and negative numbers.
    """
    
    def __init__(self):
        super().__init__()
        self.result = 0
        
    @tz_step
    def step1(self):
        """Add two positive numbers."""
        time.sleep(0.3)
        self.logger.debug("Step 1: Adding 5 + 3")
        self.result = 5 + 3
        assert self.result == 8
        
    @tz_step
    def step2(self):
        """Add a positive and negative number."""
        time.sleep(0.4)
        self.logger.debug("Step 2: Adding result + (-10)")
        self.result += -10
        assert self.result == -2
        
    @tz_step
    def step3(self):
        """Add zero to verify identity property."""
        time.sleep(0.2)
        self.logger.debug("Step 3: Adding result + 0")
        self.result += 0
        assert self.result == -2


class MultiplicationTest(TZTest):
    """Test case for verifying multiplication operations.
    
    This test checks multiplication with various scenarios
    including multiplying by zero and negative numbers.
    
    @requirement CALC-001
    @expected_result All multiplication operations produce correct results
    """
    
    def __init__(self):
        super().__init__()
        self.value = 5
        
    @tz_step
    def step1(self):
        """Multiply by a positive number."""
        time.sleep(0.5)
        self.logger.debug("Step 1: Multiplying by 4")
        self.value *= 4
        assert self.value == 20
        
    @tz_step
    def step2(self):
        """Multiply by a negative number."""
        time.sleep(0.3)
        self.logger.debug("Step 2: Multiplying by -2")
        self.value *= -2
        assert self.value == -40
    
    @tz_step
    def step3(self):
        """Multiply by zero."""
        time.sleep(0.2)
        self.logger.debug("Step 3: Multiplying by 0")
        self.value *= 0
        assert self.value == 0


class DivisionValidator(TZTest):
    """Test case for validating division operations.
    
    This test ensures that division operations work correctly
    with different combinations of numbers and includes error handling.
    
    @requirement CALC-002
    @requirement CALC-003
    @expected_result Division operations produce correct results and handle errors
    """
    
    def __init__(self):
        super().__init__()
        self.result = 100
        self.error_occurred = False
        
    @tz_step
    def step1(self):
        """Divide by a positive number."""
        time.sleep(0.4)
        self.logger.debug("Step 1: Dividing 100 by 4")
        self.result /= 4
        assert self.result == 25
        
    @tz_step
    def step2(self):
        """Divide by a negative number."""
        time.sleep(0.3)
        self.logger.debug("Step 2: Dividing result by -5")
        self.result /= -5
        assert self.result == -5
    
    @tz_step
    def step3(self):
        """Test division by zero handling."""
        time.sleep(0.6)
        self.logger.debug("Step 3: Testing division by zero")
        try:
            self.result /= 0
            self.error_occurred = False
        except ZeroDivisionError:
            self.error_occurred = True
        assert self.error_occurred == True, "Division by zero should raise an error"
        
    @tz_step
    def step4(self):
        """Confirm result hasn't changed after error."""
        time.sleep(0.2)
        self.logger.debug("Step 4: Verifying result is unchanged")
        assert self.result == -5, "Result should be unchanged after division by zero error"