"""This module implements testcases regarding Firware Updates."""

from tzen import tz_testcase, tz_fixture, tz_step
import time


@tz_fixture
class SimpleExampleFixture():
    """This fixture is used as a simple example."""
    
    def __init__(self):
        self.simple_string = "SIMPLE"
        
    def setup(self):
        print("Making Setup of Simple Fixture")
        
    def teardown(self):
        print("Making teardown of Simple Fixture")
        
    def getSimpleString(self):
        return self.simple_string

@tz_testcase
class TC_0001():
    """ This test is a Simple Example """
        
    def __init__(self, simple_fixure:SimpleExampleFixture):
        self.simple_fixture = simple_fixture
    
    @tz_step
    def step1(self):
        """ Simple Step 1 """        
        assert self.simple_fixture.getSimpleString == "SIMPLE"
        
    @tz_step
    def step2(self):
        """ Simple Step 2 """        
        assert self.simple_fixture.getSimpleString == "DIFFICULT"
    
