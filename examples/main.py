from tzen.tz_test import TZTest, tz_step
from tzen.tz_fixture import TZFixture, tz_use_fixture
from tzen.tz_session import TZSession
from tzen.tz_test_organizer import TZTestOrganizerList

import time

class MyFixture(TZFixture):
    """Example fixture class."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.debug("Hello from MyFixture")
        self.data = "Fixture data"
        
    def setup(self):
        self.logger.debug("MyFixture setup called")
        
    def teardown(self):
        self.logger.debug("MyFixture teardown called")
        
        
class TestExample(TZTest):
    
    my_fixture:MyFixture = tz_use_fixture(MyFixture)
    
    def __init__(self):
        super().__init__()
        self.lallero = 0
        
    @tz_step
    def step1(self):
        self.lallero += 1
        self.logger.warning("Step1")
        time.sleep(4)
        
    @tz_step
    def step2(self):
        self.logger.warning( f"Step2 {self.lallero}")
        assert self.lallero == 4

    @tz_step
    def step3(self):
        self.logger.error( f"Step3 {self.lallero}")
        assert self.lallero == 5


session = TZSession(TZTestOrganizerList([TestExample]))
session.start()


# tz_facade = TZFacade()
# tz_facade.load_configuration({"ADDRESS":"localhost", "PORT":8080, "OTHER": 33})
# tz_facade.run_tests(["TestExample"])


