import logging
from rich.logging import RichHandler

class TZTestFormatter(logging.Formatter):
    """Custom formatter for TZTest logs using Rich markup."""
        
    def format(self, record: logging.LogRecord) -> str:
        
        # Ottieni informazioni personalizzate
        test_name = getattr(record, "test_name", "UnknownTest")
        test_step = getattr(record, "test_step", -1)
        test_step_num = getattr(record, "test_step_num", -1)

        # Colori e simboli per livelli
        level_icons = {
            "DEBUG": "🐞",
            "INFO": "ℹ️ ",
            "WARNING": "⚠️ ",
            "ERROR": "❌",
            "CRITICAL": "🔥",
        }
        
        icon = level_icons.get(record.levelname, "")
    
        # Allineamento
        test_info = f"[bold magenta]{test_name:<18}[/bold magenta]"
        step_info = f"[green]Step {test_step}/{test_step_num}[/green]" if test_step > 0 else ""
        msg = record.getMessage()

        return f"{icon} {test_info} {step_info:<12} - [bold]{msg}[/bold]"
    
class TZFixtureFormatter(logging.Formatter):
    """Custom formatter for TZFixture logs using Rich markup."""
        
    def format(self, record: logging.LogRecord) -> str:
        
        # Ottieni informazioni personalizzate
        fixture_name = getattr(record, "fixture_name", "UnknownFixture")
        
        # Colori e simboli per livelli
        level_icons = {
            "DEBUG": "🐞",
            "INFO": "ℹ️ ",
            "WARNING": "⚠️ ",
            "ERROR": "❌",
            "CRITICAL": "🔥",
        }
        
        icon = level_icons.get(record.levelname, "")
    
        # Allineamento
        test_info = f"[bold magenta]{fixture_name:<18}[/bold magenta]"
        
        msg = record.getMessage()

        return f"{icon} {test_info} - [bold]{msg}[/bold]"

class LastTraceRichHandler(RichHandler):
    def emit(self, record):
        if record.exc_info:
            exc_type, exc_value, traceback = record.exc_info
            record.exc_info = (exc_type, exc_value, traceback.tb_next)  # Clear traceback to avoid full traceback
            # Get only last line of traceback
            #record.exc_text = f"{exc_type.__name__}: {exc_value}"
        super().emit(record)


TZEN_ROOT_LOGGER_NAME = "tzen"
# Configuring logger for tzen package
root_logger = logging.getLogger(TZEN_ROOT_LOGGER_NAME)
root_logger.setLevel(logging.INFO)
root_handler = RichHandler(rich_tracebacks=True, markup=True, show_path=False, omit_repeated_times=False)
root_handler.setFormatter(logging.Formatter('%(name)s:\t%(message)s'))
root_logger.addHandler(root_handler)

#Configuring logger root for user defines testcases
TZEN_ROOT_TEST_LOGGER_NAME = TZEN_ROOT_LOGGER_NAME + ".test"
root_test_logger = logging.getLogger(TZEN_ROOT_TEST_LOGGER_NAME)
root_test_logger.propagate = False
root_test_logger.setLevel(logging.DEBUG)
root_test_handler = LastTraceRichHandler(rich_tracebacks=True, show_path=False, omit_repeated_times=False, markup=True)
root_test_handler.setFormatter(TZTestFormatter())
root_test_logger.addHandler(root_test_handler)

#Configuring logger for user defines fixtures
TZEN_ROOT_FIXTURE_LOGGER_NAME = TZEN_ROOT_TEST_LOGGER_NAME + ".fixture"
root_fixture_logger = logging.getLogger(TZEN_ROOT_FIXTURE_LOGGER_NAME)
root_fixture_logger.propagate = False
root_fixture_logger.setLevel(logging.DEBUG)
root_fixture_handler = RichHandler(rich_tracebacks=True, show_path=False, omit_repeated_times=False, markup=True)
root_fixture_handler.setFormatter(TZFixtureFormatter())
root_fixture_logger.addHandler(root_fixture_handler)


def tz_getLogger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(TZEN_ROOT_LOGGER_NAME + '.' + name)
    logger.setLevel(level)
    return logger

class TZTestLogger():
    
    def __init__(self, test_name:str, test_step_num:int, level=logging.DEBUG) -> None:
        self.logger = logging.getLogger(f"{TZEN_ROOT_TEST_LOGGER_NAME}.{test_name}")
        self.logger.setLevel(level)  # opzionale, ma utile per override locale
        self.extras = {
            "test_name": test_name,
            "test_step": 0,
            "test_step_num": test_step_num,
        }
        
    def set_test_step(self, step:int) -> None:
        self.extras["test_step"] = step
    
    def debug(self, msg, *args, **kwargs):
        return self.logger.debug(msg, *args, extra=self.extras, **kwargs)

    def info(self, msg, *args, **kwargs):
        return self.logger.info(msg, *args, extra=self.extras, **kwargs)

    def warning(self, msg, *args, **kwargs):
        return self.logger.warning(msg, *args, extra=self.extras, **kwargs)

    def error(self, msg, *args, **kwargs):
        return self.logger.error(msg, *args, extra=self.extras, **kwargs)

    def critical(self, msg, *args, **kwargs):
        return self.logger.critical(msg, *args, extra=self.extras, **kwargs)

    def exception(self, msg, *args, **kwargs):
        return self.logger.exception(msg, *args, extra=self.extras, **kwargs)

class TZFixtureLogger(TZTestLogger):
    
    def __init__(self, fixture_name:str, level=logging.DEBUG) -> None:
        self.logger = logging.getLogger(f"{TZEN_ROOT_FIXTURE_LOGGER_NAME}.{fixture_name}")
        self.logger.setLevel(level)  # opzionale, ma utile per override locale
        self.extras = {
            "fixture_name": fixture_name,
        }
        
