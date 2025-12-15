"""
Centralized Logging Configuration for Pool Cue
"""
import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging(app=None):
    """
    Configure logging for the application.
    
    Log levels:
    - DEBUG: Detailed information for debugging
    - INFO: General operational information
    - WARNING: Something unexpected but not critical
    - ERROR: Something failed
    - CRITICAL: Application cannot continue
    """
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    log_to_file = os.environ.get('LOG_TO_FILE', 'false').lower() == 'true'
    
    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Get the root logger
    logger = logging.getLogger('poolcue')
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_to_file:
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'poolcue.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Also configure Flask's logger if app is provided
    if app:
        app.logger.handlers = logger.handlers
        app.logger.setLevel(logger.level)
    
    return logger


# Create a default logger instance for imports
logger = setup_logging()


def get_logger(name=None):
    """Get a logger instance. If name is provided, creates a child logger."""
    if name:
        return logging.getLogger(f'poolcue.{name}')
    return logger
