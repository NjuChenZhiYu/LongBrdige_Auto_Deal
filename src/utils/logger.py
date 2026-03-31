import logging
from logging.handlers import RotatingFileHandler
import sys
import os

def setup_logger(name: str, log_file: str = "logs/monitor.log", level=logging.INFO):
    """
    Setup a logger with console and file handlers
    """
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.hasHandlers():
        return logger

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler
    # Ensure logs directory exists if path contains directories
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    try:
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=10 * 1024 * 1024, 
            backupCount=3, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging: {e}")
    
    return logger

# Create a default global logger
logger = setup_logger("LongBridgeMonitor")
