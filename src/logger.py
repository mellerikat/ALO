import os 
import logging
import logging.config
from src.constants import *
import logging
import logging.handlers
import inspect 
import colorama
from colorama import Fore, Style
colorama.init()

class ColoredFormatter(logging.Formatter):
    COLORS = {
        #logging.DEBUG: Fore.GRAY,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.BLUE,
        logging.ERROR: Fore.MAGENTA,
        #logging.CRITICAL: Fore.RED # + Style.BRIGHT
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelno, Fore.WHITE)
        message = super().format(record)
        return f"{log_color}{message}{Style.RESET_ALL}"

#--------------------------------------------------------------------------------------------------------------------------
#    ProcessLogger Class : (ALO master에서만 사용)
#--------------------------------------------------------------------------------------------------------------------------
def log_decorator(func):
    def wrapper(*args, **kwargs):
        caller_frame = inspect.stack()[1]
        caller_file = os.path.basename(caller_frame.filename)
        caller_line = caller_frame.lineno
        # FIXME class name 찾는법 복잡해서 일단 제거 
        #caller_name = caller_frame.
        caller_func = caller_frame.function
        # 원본 함수 호출
        logger_method, msg = func(*args, **kwargs)
        logger_method(f'{caller_file}({caller_line})|{caller_func}()] {msg}')
    return wrapper

class ProcessLogger: 
    # envs 미입력 시 설치 과정, 프로세스 진행 과정 등 전체 과정 보기 위한 로그 생성 
    def __init__(self, project_home: str):
        self.project_home = project_home
        self.service = 'ALO'
        if not os.path.exists(TRAIN_LOG_PATH):
            os.makedirs(TRAIN_LOG_PATH)
        if not os.path.exists(INFERENCE_LOG_PATH):
            os.makedirs(INFERENCE_LOG_PATH)
        # 현재 pipeline 등 환경 정보를 알기 전에 큼직한 단위로 install 과정 등에 대한 logging을 alo master에서 진행 가능하도록 config
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
                    "level": "INFO",
                },
                "file_train": {
                    "class": "logging.FileHandler",
                    "filename": TRAIN_LOG_PATH + "process.log", 
                    "formatter": "proc_file",
                    "level": "INFO",
                },
                "file_inference": {
                    "class": "logging.FileHandler",
                    "filename": INFERENCE_LOG_PATH + "process.log", 
                    "formatter": "proc_file",
                    "level": "INFO",
                },
            },
            "root": {"handlers": ["console", "file_train", "file_inference"], "level": "INFO"},
            "loggers": {"ERROR": {"level": "ERROR"}, "WARNING": {"level": "WARNING"}, "INFO": {"level": "INFO"}}
        }
    #--------------------------------------------------------------------------------------------------------------------------
    #    Process Logging API
    #--------------------------------------------------------------------------------------------------------------------------
    @log_decorator
    def process_info(self, msg):
        logging.config.dictConfig(self.process_logging_config)
        info_logger = logging.getLogger("INFO") 
        return info_logger.info, msg 
    
    @log_decorator
    def process_warning(self, msg):
        logging.config.dictConfig(self.process_logging_config)
        warning_logger = logging.getLogger("WARNING") 
        return warning_logger.warning, msg 
    
    @log_decorator
    def process_error(self, msg):
        logging.config.dictConfig(self.process_logging_config)
        error_logger = logging.getLogger("ERROR") 
        return error_logger.error, msg