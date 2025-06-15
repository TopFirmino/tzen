import logging
from .tz_cli import app
from .tz_logging import tz_getLogger

# Configure the root logger for the tzen application
logger = tz_getLogger( __name__)

if __name__ == "__main__":
    logger.info("Starting tzen CLI application")
    app()