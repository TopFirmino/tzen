import logging
from rich.logging import RichHandler
from rich.console import Console
from rich.traceback import install

install(show_locals=True)

console = Console()


root_logger = logging.getLogger("tzen")
root_logger.setLevel(logging.NOTSET)
root_handler = RichHandler(rich_tracebacks=True, markup=True, show_path=False, omit_repeated_times=False)
#formatter = logging.Formatter('%(test_name)s - Step%(test_step)d] %(message)s')
#root_handler.setFormatter(formatter)
root_logger.addHandler(root_handler)


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

def exception(msg: str) -> None:
    root_logger.exception(msg, show_locals=True)
    


class TZTestLogger(logging.Logger):
    
    def __init__(self, test_name:str, test_step_num:int, level=logging.NOTSET) -> None:
        super().__init__(test_name, level)
        self.extras = {
            "test_name": test_name,
            "test_step": 0,
            "test_step_num": test_step_num,
        }
        
        test_handler = RichHandler(rich_tracebacks=True, show_path=False, omit_repeated_times=False, markup=True)
        test_formatter = logging.Formatter('[bold]%(test_name)s, Step %(test_step)d[/bold]: %(message)s')
        test_handler.setFormatter(test_formatter)
        self.addHandler(test_handler)
        
    def set_test_step(self, step:int) -> None:
        self.extras["test_step"] = step
    
    def debug(self, msg, *args, exc_info = None, stack_info = False, stacklevel = 1) -> None:
        return super().debug(msg, *args, exc_info=exc_info, stack_info=stack_info, stacklevel=stacklevel, extra=self.extras)
        
    def warning(self, msg, *args, exc_info = None, stack_info = False, stacklevel = 1):
        return super().warning(msg, *args, exc_info=exc_info, stack_info=stack_info, stacklevel=stacklevel, extra=self.extras)
    
    def error(self, msg, *args, exc_info = None, stack_info = False, stacklevel = 1):
        return super().error(msg, *args, exc_info=exc_info, stack_info=stack_info, stacklevel=stacklevel, extra=self.extras)
    
    def info(self, msg, *args, exc_info = None, stack_info = False, stacklevel = 1):
        return super().info(msg, *args, exc_info=exc_info, stack_info=stack_info, stacklevel=stacklevel, extra=self.extras)
    
    def critical(self, msg, *args, exc_info = None, stack_info = False, stacklevel = 1):
        return super().critical(msg, *args, exc_info=exc_info, stack_info=stack_info, stacklevel=stacklevel, extra=self.extras)
    
    def exception(self, msg, *args, exc_info = None, stack_info = False, stacklevel = 1):
        return super().exception(msg, *args, exc_info=exc_info, stack_info=stack_info, stacklevel=stacklevel)

