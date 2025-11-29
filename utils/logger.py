import logging
import sys
from datetime import datetime
from config import Config

def setup_logger(name: str) -> logging.Logger:
    """Setup a logger with proper formatting."""
    logger = logging.getLogger(name)
    
    # Set level based on environment
    level = logging.DEBUG if Config.ENVIRONMENT == 'development' else logging.INFO
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    return logger
