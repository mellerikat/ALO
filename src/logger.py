import os 
import logging
import logging.config
from copy import deepcopy 
import logging
import logging.handlers
import re
from textwrap import wrap

class MultiLineHandler(logging.StreamHandler):
    def __init__(self, line_length: int):
        logging.StreamHandler.__init__(self)
        self.line_length = line_length

    def emit(self, record):
        record.msg = "\n".join(wrap(record.msg, self.line_length))
        super().emit(record)


class ColorCodes:
    grey = "\x1b[38;21m"
    green = "\x1b[1;32m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    blue = "\x1b[1;34m"
    light_blue = "\x1b[1;36m"
    purple = "\x1b[1;35m"
    reset = "\x1b[0m"


class ColorizedArgsFormatter(logging.Formatter):
    arg_colors = [ColorCodes.purple, ColorCodes.light_blue]
    level_fields = ["levelname", "levelno"]
    level_to_color = {
        logging.DEBUG: ColorCodes.grey,
        logging.INFO: ColorCodes.green,
        logging.WARNING: ColorCodes.yellow,
        logging.ERROR: ColorCodes.red,
        logging.CRITICAL: ColorCodes.bold_red,
    }

    def __init__(self, fmt: str):
        super().__init__()
        self.level_to_formatter = {}

        def add_color_format(level: int):
            color = ColorizedArgsFormatter.level_to_color[level]
            _format = fmt
            for fld in ColorizedArgsFormatter.level_fields:
                search = "(%\(" + fld + "\).*?s)"
                _format = re.sub(search, f"{color}\\1{ColorCodes.reset}", _format)
            formatter = logging.Formatter(_format)
            self.level_to_formatter[level] = formatter

        add_color_format(logging.DEBUG)
        add_color_format(logging.INFO)
        add_color_format(logging.WARNING)
        add_color_format(logging.ERROR)
        add_color_format(logging.CRITICAL)

    @staticmethod
    def rewrite_record(record: logging.LogRecord):
        if not BraceFormatStyleFormatter.is_brace_format_style(record):
            return
        # color 
        msg = record.msg
        msg = msg.replace("{", "_{{")
        msg = msg.replace("}", "_}}")
        placeholder_count = 0
        # add ANSI escape code for next alternating color before each formatting parameter
        # and reset color after it.
        while True:
            if "_{{" not in msg:
                break
            color_index = placeholder_count % len(ColorizedArgsFormatter.arg_colors)
            color = ColorizedArgsFormatter.arg_colors[color_index]
            msg = msg.replace("_{{", color + "{", 1)
            msg = msg.replace("_}}", "}" + ColorCodes.reset, 1)
            placeholder_count += 1
        record.msg = msg.format(*record.args)
        record.args = []

    def format(self, record):
        orig_msg = record.msg
        orig_args = record.args
        formatter = self.level_to_formatter.get(record.levelno)
        self.rewrite_record(record)
        formatted = formatter.format(record)
        record.msg = orig_msg
        record.args = orig_args
        
        return formatted


class BraceFormatStyleFormatter(logging.Formatter):
    def __init__(self, fmt: str):
        super().__init__()
        self.formatter = logging.Formatter(fmt)

    @staticmethod
    def is_brace_format_style(record: logging.LogRecord):
        if len(record.args) == 0:
            return False

        msg = record.msg
        if '%' in msg:
            return False

        count_of_start_param = msg.count("{")
        count_of_end_param = msg.count("}")

        if count_of_start_param != count_of_end_param:
            return False

        if count_of_start_param != len(record.args):
            return False

        return True

    @staticmethod
    def rewrite_record(record: logging.LogRecord):
        if not BraceFormatStyleFormatter.is_brace_format_style(record):
            return

        record.msg = record.msg.format(*record.args)
        record.args = []

    def format(self, record):
        orig_msg = record.msg
        orig_args = record.args
        self.rewrite_record(record)
        formatted = self.formatter.format(record)
        # restore log record to original state for other handlers
        record.msg = orig_msg
        record.args = orig_args
        return formatted

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
LINE_LENGTH = 120
# PROJECT_HOME = os.path.dirname(os.path.abspath(os.path.dirname(__file__))) + "/"
# TRAIN_LOG_PATH =  PROJECT_HOME + "train_artifacts/log/"
# INFERENCE_LOG_PATH = PROJECT_HOME + "inference_artifacts/log/"
# print_color related variables 
COLOR_RED = '\033[91m'
COLOR_END = '\033[0m'
ARG_NAME_MAX_LENGTH = 30
COLOR_DICT = {
   'PURPLE':'\033[95m',
   'CYAN':'\033[96m',
   'DARKCYAN':'\033[36m',
   'BLUE':'\033[94m',
   'GREEN':'\033[92m',
   'YELLOW':'\033[93m',
   'RED':'\033[91m',
   'BOLD':'\033[1m',
   'UNDERLINE':'\033[4m',
}
COLOR_END = '\033[0m'

def print_color(msg, _color):
    """ Description
        -----------
            Display text with color 

        Parameters
        -----------
            msg (str) : text
            _color (str) : PURPLE, CYAN, DARKCYAN, BLUE, GREEN, YELLOW, RED, BOLD, UNDERLINE

        example
        -----------
            print_color('Display color text', 'BLUE')
    """
    if _color.upper() in COLOR_DICT.keys():
        print(COLOR_DICT[_color.upper()] + msg + COLOR_END)
    else:
        raise ValueError('[ASSET][ERROR] print_color() function call error. - selected color : {}'.format(COLOR_DICT.keys()))

#--------------------------------------------------------------------------------------------------------------------------
#    ProcessLogger Class : (ALO master에서만 사용)
#--------------------------------------------------------------------------------------------------------------------------
class ProcessLogger: 
    # [%(filename)s:%(lineno)d]
    # envs 미입력 시 설치 과정, 프로세스 진행 과정 등 전체 과정 보기 위한 로그 생성 
    def __init__(self, project_home: str):
        try: 
            self.project_home = project_home
        except: 
            print_color("[LOGGER][ERROR] Argument << project_home: str >> required for initializing ProcessLogger.", color='red')
        self.train_log_path = self.project_home + "train_artifacts/log/"
        self.inference_log_path = self.project_home + "inference_artifacts/log/"
        if not os.path.exists(self.train_log_path):
            os.makedirs(self.train_log_path)
        if not os.path.exists(self.inference_log_path):
            os.makedirs(self.inference_log_path)
        # 현재 pipeline 등 환경 정보를 알기 전에 큼직한 단위로 install 과정 등에 대한 logging을 alo master에서 진행 가능하도록 config
        self.process_logging_config = { 
            "version": 1,
            "formatters": {
                "proc_console": {
                    "()": ColorizedArgsFormatter,
                    "format": f"[%(levelname)s][PROCESS][%(asctime)s]: %(message)s"
                },
                "meta_console": {
                    "()": ColorizedArgsFormatter,
                    "format": f"[%(levelname)s][META][%(asctime)s]: %(message)s"
                },
                "proc_file": {
                    "format": f"[%(levelname)s][PROCESS][%(asctime)s]: %(message)s"
                },
                "meta_file": {
                    "format": f"[%(levelname)s][META][%(asctime)s]: %(message)s"
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "proc_console",
                    "level": "INFO",
                },
                "file_train": {
                    "class": "logging.FileHandler",
                    "filename": self.train_log_path + "process.log", 
                    "formatter": "proc_file",
                    "level": "INFO",
                },
                "file_inference": {
                    "class": "logging.FileHandler",
                    "filename": self.inference_log_path + "process.log", 
                    "formatter": "proc_file",
                    "level": "INFO",
                },
            },
            "root": {"handlers": ["console", "file_train", "file_inference"], "level": "INFO"},
            #"root": {"handlers": ["file_train", "file_inference"], "level": "INFO"},
            "loggers": {"ERROR": {"level": "ERROR"}, "WARNING": {"level": "WARNING"}, "INFO": {"level": "INFO"}}
        }
        self.meta_logging_config = deepcopy(self.process_logging_config)
        self.meta_logging_config["handlers"]["console"]["formatter"] = "meta_console"
        self.meta_logging_config["handlers"]["file_train"]["formatter"] = "meta_file"
        self.meta_logging_config["handlers"]["file_inference"]["formatter"] = "meta_file"


    #--------------------------------------------------------------------------------------------------------------------------
    #    Process Logging API
    #--------------------------------------------------------------------------------------------------------------------------
    # process 로깅은 alo master에서만 쓰므로, 굳이 str type check 안함 
    def process_meta(self, msg): 
        logging.config.dictConfig(self.meta_logging_config)
        meta_logger = logging.getLogger("INFO")
        meta_logger.info(f'{msg}')
        
        
    def process_info(self, msg):
        logging.config.dictConfig(self.process_logging_config)
        info_logger = logging.getLogger("INFO") 
        info_logger.info(f'{msg}')


    def process_warning(self, msg):
        logging.config.dictConfig(self.process_logging_config)
        warning_logger = logging.getLogger("WARNING") 
        warning_logger.warning(f'{msg}')


    def process_error(self, msg):
        logging.config.dictConfig(self.process_logging_config)
        error_logger = logging.getLogger("ERROR") 
        error_logger.error(f'{msg}') #, stack_info=True, exc_info=True)
        raise