
import logging
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

LOG_DIR.mkdir(exist_ok=True)

# Cache for log mode to avoid repeated config reads
_log_mode_cache = None

def _get_log_mode():
    """Get log mode from configuration."""
    global _log_mode_cache
    if _log_mode_cache is not None:
        return _log_mode_cache
    
    try:
        from config import load_config
        config = load_config()
        log_mode = config.get('log_mode', 'off')
        _log_mode_cache = log_mode
        return log_mode
    except Exception:
        # If config loading fails, default to 'off'
        return 'off'

def _clear_log_mode_cache():
    """Clear the log mode cache and update all existing loggers (call this when config is updated)."""
    global _log_mode_cache
    _log_mode_cache = None
    
    # Update all existing loggers with new log mode
    log_mode = _get_log_mode()
    target_level = logging.DEBUG if log_mode == 'debug' else logging.INFO
    
    # Create formatter
    log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Update all loggers created by this module
    # Only update loggers that have handlers (i.e., were created by get_logger)
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        logger = logging.getLogger(logger_name)
        if logger.handlers:
            logger.setLevel(target_level)
            
            # Check if FileHandler exists
            has_file_handler = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
            
            # Add or remove FileHandler based on log_mode
            if log_mode != 'off' and not has_file_handler:
                # Need to add FileHandler
                f_handler = logging.FileHandler(LOG_FILE)
                f_handler.setLevel(logging.DEBUG)
                f_handler.setFormatter(log_format)
                logger.addHandler(f_handler)
            elif log_mode == 'off' and has_file_handler:
                # Need to remove FileHandler
                handlers_to_remove = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
                for handler in handlers_to_remove:
                    handler.close()
                    logger.removeHandler(handler)
            
            # Update console handlers
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    if log_mode == 'off':
                        handler.setLevel(logging.CRITICAL + 1)
                    else:
                        handler.setLevel(target_level)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    # Get log mode from config
    log_mode = _get_log_mode()
    
    # Create formatter
    log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Prevent duplicate handlers if logger already configured
    if logger.handlers:
        # Update log level based on current config
        if log_mode == 'debug':
            logger.setLevel(logging.DEBUG)
            console_level = logging.DEBUG
        elif log_mode == 'off':
            # Off mode: disable all logging
            logger.setLevel(logging.CRITICAL + 1)  # Set to a level higher than CRITICAL to disable all
            console_level = logging.CRITICAL + 1
        else:
            logger.setLevel(logging.INFO)
            console_level = logging.INFO
        
        # Check if FileHandler exists
        has_file_handler = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
        
        # Add FileHandler if needed (when switching from off to debug/info)
        if log_mode != 'off' and not has_file_handler:
            f_handler = logging.FileHandler(LOG_FILE)
            f_handler.setLevel(logging.DEBUG)
            f_handler.setFormatter(log_format)
            logger.addHandler(f_handler)
        # Remove FileHandler if log_mode is off
        elif log_mode == 'off' and has_file_handler:
            handlers_to_remove = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
            for handler in handlers_to_remove:
                handler.close()
                logger.removeHandler(handler)
        
        # Update console handlers
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(console_level)
        
        return logger
    
    # Set logger level based on log_mode
    if log_mode == 'debug':
        logger.setLevel(logging.DEBUG)
        console_level = logging.DEBUG
    elif log_mode == 'off':
        # Off mode: disable all logging
        logger.setLevel(logging.CRITICAL + 1)  # Set to a level higher than CRITICAL to disable all
        console_level = logging.CRITICAL + 1
    else:
        logger.setLevel(logging.INFO)
        console_level = logging.INFO

    # File handler - only add if not in off mode
    if log_mode != 'off':
        f_handler = logging.FileHandler(LOG_FILE)
        f_handler.setLevel(logging.DEBUG)
        f_handler.setFormatter(log_format)
        logger.addHandler(f_handler)

    # Console handler - only add if not in off mode
    if log_mode != 'off':
        c_handler = logging.StreamHandler()
        c_handler.setLevel(console_level)
        c_handler.setFormatter(log_format)
        logger.addHandler(c_handler)

    return logger
