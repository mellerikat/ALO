import colorama
import inspect 
import logging
import logging.config
import logging.handlers
import os 
from colorama import Fore, Style
from src.constants import *
## initialize colorama
colorama.init()

class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.BLUE,
        logging.ERROR: Fore.MAGENTA,
    }

    def format(self, record):
        """ logger color formatting

        Args:           
            record   (str): logging message
            
        Returns:
            formatted message

        """
        log_color = self.COLORS.get(record.levelno, Fore.WHITE)
        message = super().format(record)
        return f"{log_color}{message}{Style.RESET_ALL}"

def log_decorator(func):
    """ log function decorator for finding original caller 

    Args:           
        func   (function): original function tobe decorated 
        
    Returns:
        wrapper (function): wrapped function 
    
    """
    def wrapper(*args, **kwargs):
        caller_frame = inspect.stack()[1]
        caller_file = os.path.basename(caller_frame.filename)
        caller_line = caller_frame.lineno
        ## TODO insert class name? 
        caller_func = caller_frame.function
        ## Call the original function 
        logger_method, msg = func(*args, **kwargs)
        logger_method(msg = f'{caller_file}({caller_line})|{caller_func}()] {msg}')
        if logger_method.__name__ == "error":
            raise
    return wrapper

def custom_log_decorator(func):
    """ custom log function decorator with integer logger level

    Args:           
        func   (function): original function tobe decorated 
        
    Returns:
        wrapper (function): wrapped function 
    
    """
    def wrapper(*args, **kwargs):
        caller_frame = inspect.stack()[1]
        caller_file = os.path.basename(caller_frame.filename)
        caller_line = caller_frame.lineno
        caller_func = caller_frame.function
        ## Call the original function 
        logger_method, msg, level = func(*args, **kwargs)
        ## integer logger level 
        logger_method(msg = f'{caller_file}({caller_line})|{caller_func}()] {msg}', level = level)
        if logger_method.__name__ == "error":
            raise
    return wrapper

class ProcessLogger: 
    def __init__(self, project_home: str):
        """ initialize process logger config

        Args:           
            project_home    (str): ALO main path 
            
        Returns: -
        
        """
        ## ALO MSG (message) level
        MSG_LOG_LEVEL = 11
        logging.addLevelName(MSG_LOG_LEVEL, 'MSG')
        self.project_home = project_home
        self.service = 'ALO'
        ## create log path 
        if not os.path.exists(TRAIN_LOG_PATH):
            os.makedirs(TRAIN_LOG_PATH)
        if not os.path.exists(INFERENCE_LOG_PATH):
            os.makedirs(INFERENCE_LOG_PATH)
        self.process_logging_config = { 
            "version": 1,
            "formatters": {
                "proc_console": {
                    "()": ColoredFormatter,
                    "format": f"[%(asctime)s|{self.service}|%(levelname)s|%(message)s"
                },
                "proc_file": {
                    "format": f"[%(asctime)s|{self.service}|%(levelname)s|%(message)s"
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "proc_console",
                    "level": "MSG",  
                },
                "file_train": {
                    "class": "logging.FileHandler",
                    "filename": TRAIN_LOG_PATH + "process.log", 
                    "formatter": "proc_file",
                    "level": "MSG",
                },
                "file_inference": {
                    "class": "logging.FileHandler",
                    "filename": INFERENCE_LOG_PATH + "process.log", 
                    "formatter": "proc_file",
                    "level": "MSG",
                },
            },
            "root": {"handlers": ["console", "file_train", "file_inference"], "level": "MSG"},
            "loggers": {"ERROR": {"level": "ERROR"}, "WARNING": {"level": "WARNING"}, "INFO": {"level": "INFO"}, "MSG": {"level": MSG_LOG_LEVEL}}
        }
    
    @custom_log_decorator
    def process_message(self, msg: str):
        """ custom logging API used for ALO process logging  - level MSG_LOG_LEVEL(11)

        Args:           
            msg (str): logging message
            
        Returns: 
            logger.log
            message (str)
            logger.level
        
        """
        logging.config.dictConfig(self.process_logging_config)
        message_logger = logging.getLogger("MSG") 
        level = message_logger.level
        return message_logger.log, msg, level
    
    @log_decorator
    def process_info(self, msg):
        """ info logging API used for ALO process logging

        Args:           
            msg (str): logging message
            
        Returns: 
            logger.info
            message (str)
        
        """
        logging.config.dictConfig(self.process_logging_config)
        info_logger = logging.getLogger("INFO") 
        return info_logger.info, msg
    
    @log_decorator
    def process_warning(self, msg):
        """ warning logging API used for ALO process logging

        Args:           
            msg (str): logging message
            
        Returns: 
            logger.warning
            message (str)
        
        """
        logging.config.dictConfig(self.process_logging_config)
        warning_logger = logging.getLogger("WARNING") 
        return warning_logger.warning, msg
    
    @log_decorator
    def process_error(self, msg):
        """ error logging API used for ALO process logging
            it raises error 
        Args:           
            msg (str): logging message
            
        Returns: 
            logger.error
            message (str)
        
        """
        logging.config.dictConfig(self.process_logging_config)
        error_logger = logging.getLogger("ERROR")
        return error_logger.error, msg