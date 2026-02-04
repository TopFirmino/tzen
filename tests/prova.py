from __future__ import annotations
from tzen import tz_fixture, tz_testcase, tz_step

@tz_testcase
class TC_001:
    
    def __init__(self):
        self.a = 1
        
    @tz_step
    def step1(self):
        self.logger.info(f"Step1: A value is {self.a}")
        self.a+=1
        
@tz_testcase
class TC_002:
    
    def __init__(self):
        self.a = 1
        
    @tz_step
    def step1(self):
        self.logger.info(f"Step1: A value is {self.a}")
        self.a+=1
        
    @tz_step
    def step2(self):
        self.logger.info(f"Step2: A value is {self.a}")
        self.a+=1

@tz_fixture
class MyFixture:
    
    def __init__(self):
        self.fixture_value = -1
        
    def setup(self):
        self.fixture_value = 5
    
    def teardown(self):
        self.fixture_value = -1
        
@tz_testcase
class TC_003:
    
    def __init__(self, my_fixture:MyFixture):
        self.fix = my_fixture
        
    @tz_step
    def step1(self):
        self.logger.info(f"Step1: Fixture value is {self.fix.fixture_value}")
        assert self.fix.fixture_value == 5, f"Invalid fixture value, expected 5 got {self.fix.fixture_value}"
        self.fix.fixture_value+=1
        
    @tz_step
    def step2(self):
        self.logger.info(f"Step2: Fixture value is {self.fix.fixture_value}")
        assert self.fix.fixture_value == 6, f"Invalid fixture value, expected 5 got {self.fix.fixture_value}"

        
@tz_testcase
class TC_004:
    
    def __init__(self, ):
        pass
        
    @tz_step
    def step1(self, my_fixture:MyFixture):
        self.logger.info(f"Step1: Fixture value is {my_fixture.fixture_value}")
        assert my_fixture.fixture_value == 5, f"Invalid fixture value, expected 5 got {my_fixture.fixture_value}"
        my_fixture.fixture_value+=1
        
    @tz_step
    def step2(self, my_fixture:MyFixture):
        self.logger.info(f"Step2: Fixture value is {my_fixture.fixture_value}")
        assert my_fixture.fixture_value == 5, f"Invalid fixture value, expected 5 got {my_fixture.fixture_value}"
