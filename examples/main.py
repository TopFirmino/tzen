from tzen.tz_test import TZTest 
from tzen.tz_facade import TZFacade
from tzen.tz_fixture import TZFixture, use_fixture
import tzen.tz_conf as conf


@conf.use_config("ADDRESS", "PORT")
class MyFixture(TZFixture):
     
    def __init__(self):
        print("Initializing fixture MyFixture")
        
    def setup(self):
        # Open the connection
        self.connection = ( self.address, self.port )
        print("Setup fixture")
        
    def teardown(self):
        print("Teardown fixture")
    
    def send_msg(self, dst, payload):
        print(f"Sending message to {self.connection} = {payload}")


@use_fixture(MyFixture, fixture_name="fixturea")
class TestExample(TZTest):
    
    # Needed for IDE linting
    fixturea:MyFixture = None

    def __init__(self):
        super().__init__()
        self.logger.info("TestExample initialized")
        self.lallero = 0
        
    @TZTest.step
    def step1(self):
        self.lallero += 1
        self.logger.warning("Step1")
        self.fixturea.send_msg("test", "Ciao ciao")
        
        
    @TZTest.step
    def step2(self):
        self.logger.warning( f"Step2 {self.lallero}")
        assert self.lallero == 4

    @TZTest.step
    def step3(self):
        self.logger.error( f"Step3 {self.lallero}")
        assert self.lallero == 5


tz_facade = TZFacade()
tz_facade.load_configuration({"ADDRESS":"localhost", "PORT":8080, "OTHER": 33})
tz_facade.run_tests(["TestExample"])


