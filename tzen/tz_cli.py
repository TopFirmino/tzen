import typer
from typing import List
from .tz_facade import TZFacade
from .tz_logging import tz_getLogger

logger = tz_getLogger( __name__)
app = typer.Typer()

@app.command()
def start_session(
    directory: str,
    testcases: List[str] = [],
    config_file: str = None
) -> None:
    """Start a test session.
    Args:
        directory (str): The directory containing the test cases.
        testcases (List[str]): List of test case names to execute.
        config_file (str): Path to the configuration file (optional).
    """

    logger.info(f"Starting session in directory: {directory}")
    logger.info(f"Test cases to execute: {', '.join(testcases)}")
    logger.info(f"Using configuration file: {config_file}")

    facade = TZFacade()
    
    if config_file:
        # Load configuration from the specified file
        facade.load_configuration_from_file(config_file)
    
    facade.start_session(directory, testcases)

@app.command()
def build_doc(
    directory: str = typer.Argument(..., help="The directory containing the test cases to document"),
    config_file: str = typer.Option(None, help="Path to the configuration file"),
    output_folder: str = typer.Option("./docs", help="Folder where documentation will be generated")
) -> None:
    """Build documentation for test cases.
    
    Args:
        directory (str): The directory containing the test cases to document.
        config_file (str): Path to the configuration file (optional).
        output_folder (str): Folder where documentation will be generated.
    """
    
    logger.info(f"Building documentation for test cases in: {directory}")
    logger.info(f"Using configuration file: {config_file}")
    logger.info(f"Output will be saved to: {output_folder}")
    
    facade = TZFacade()
    
    if config_file:
        # Load configuration from the specified file
        facade.load_configuration_from_file(config_file)
    
    facade.build_documentation(directory, output_folder)


