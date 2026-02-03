from tzen import tz_fixture, tz_testcase, tz_step

@tz_testcase
class TC_001:
    
    def __init__(self):
        self.a = 1
        print(f"{self.__class__.__name__} Init Method Invoked")
    
    @tz_step
    def step1(self):
        self.logger.info(f"Step1: A value is {self.a}")
        self.a+=1