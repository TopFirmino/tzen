import logging


root_logger = logging.getLogger()
root_logger.setLevel(0)

def debug(msg: str) -> None:
    root_logger.debug(msg)

def warning(msg: str) -> None:
    root_logger.warning(msg)
    
def error(msg: str) -> None:
    root_logger.error(msg)

def critical(msg: str) -> None:
    root_logger.critical(msg)

def info(msg: str) -> None:
    root_logger.info(msg)

def flush(msg: str) -> None:
    root_logger.flush()
    

test_logger = logging.getLogger("test")
test_logger.setLevel(0)

class TZTestLogger:
    
    def __init__(self, test_name:str, test_step_num:int) -> None:
        self.logger = test_logger
        self.extras = {
            "test_name": test_name,
            "test_step": 0,
            "test_step_num": test_step_num,
        }
    
    def set_test_step(self, step:int) -> None:
        self.extras["test_step"] = step
    
    def get_logger(self) -> logging.Logger:
        return self.logger
    
    def debug(self, msg: str) -> None:
        self.logger.debug(msg, extra=self.extras)
    
    def warning(self, msg: str) -> None:
        self.logger.warning(msg, extra=self.extras)
    
    def info(self, msg: str) -> None:
        self.logger.info(msg, extra=self.extras)
    
    def error(self, msg: str) -> None:
        self.logger.error(msg, extra=self.extras)
    
    def critical(self, msg: str) -> None:
        self.logger.critical(msg, extra=self.extras)
    
    def flush(self) -> None:
        self.logger.flush()
        