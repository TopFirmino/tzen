

def test1():
    print("test1")
    return 4

class TestSlave:
    
    def __init__(self):
        self.tests = {
            'test1': {'name': "test1", "steps": 2, "func": test1}
        }
    
    def get_tests(self):
        return len(self.tests)

    def get_test_details(self, idx):
        return list( self.tests.values() )[idx]
    
    def sync(self):
        return True
    
    def start_test(self, idx):
        list( self.tests.values() )[idx].get("func")()
    

class TestMaster:
    
    def __init__(self, slave:TestSlave):
        self.slave = slave
        self.tests_manifest = {}
        
    def get_test_manifest(self):
        for t in range(0, self.slave.get_tests()):
            test = self.slave.get_test_details(t)
            name = test.pop("name")
            self.tests_manifest[name] = test
        
        print(self.tests_manifest)

    def lauch_test(self, test_name):
        if test_name in self.tests_manifest:
            self.slave.start_test(list(self.tests_manifest.keys()).index(test_name))
            
            
ts = TestSlave()

tm = TestMaster(slave=ts)

tm.get_test_manifest()
tm.lauch_test("test1")