import os
import time
import pathlib
import functools
import shutil
import logging.config
import logging.handlers
import colorama
from colorama import Fore, Style

colorama.init()
LOG_PROCESS_FILE_NAME = "process.log"


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
        return f"{self.COLORS.get(record.levelno, Fore.WHITE)}{super().format(record)}{Style.RESET_ALL}"


class PipelineHistoryHandler(logging.FileHandler):
    """A file handler that deletes old log files if they exist in the folder.
    """

    def __init__(self, filename: str, clean: bool = False, mode: str = 'a', encoding: str = None, retain_days: int = 7):
        paths = filename.split(os.sep)
        target_path = os.sep.join(paths[:-1])
        if clean and os.path.exists(target_path):
            shutil.rmtree(target_path, ignore_errors=True)
        pathlib.Path(target_path).mkdir(parents=True, exist_ok=True)
        super(PipelineHistoryHandler, self).__init__(filename, mode=mode, encoding=encoding)


class SysStdToLogger(object):
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, buf):
        self.logger.log(self.level, "print()\n%s", buf)

    def flush(self):
        pass


def get_logger(prefix_path: str, level: str, name: str = "", backup_count=7):
    if name in logging.Logger.manager.loggerDict.keys():
        return logging.getLogger(name)

    pathlib.Path(prefix_path).mkdir(parents=True, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False if logging.getLevelName(level) < logging.DEBUG else True,
        "formatters": {
            "color": {
                "()": "alo.logger.ColoredFormatter",
                "format": "[%(asctime)s|%(name)s|%(levelname)s|%(filename)s(%(lineno)s)|%(funcName)s()] %(message)s"
            },
            "standard": {
                "format": "[%(asctime)s|%(name)s|%(levelname)s|%(filename)s(%(lineno)s)|%(funcName)s()] %(message)s"
            },
        },
        "handlers": {
            "stdout": {
                "level": level,
                "formatter": "color",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",  # Default is stderr
            },
            "file": {
                "level": level,
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "standard",
                "filename": os.path.join(prefix_path, LOG_PROCESS_FILE_NAME),
                "backupCount": backup_count,
                "interval": 1,
                "when": "midnight",
            },
        },
        "loggers": {
            name: {
                "handlers": ["stdout", "file"],
                "level": level
            },
            'rediscluster': {
                "level": level,
                "propagate": True
            }

        }
    }

    logging.config.dictConfig(config)
    logger = logging.getLogger(name)
    # sys.stdout = SysStdToLogger(logger, logging.INFO) # print() to redirect logger
    # sys_logger = logging.getLogger('sys')
    # sys.stderr = SysStdToLogger(sys_logger, logging.ERROR)

    return logger


def create_pipline_handler(filename, level):
    handler = PipelineHistoryHandler(filename)
    handler.setLevel(level)
    formatter = logging.Formatter('[%(asctime)s|%(name)s|%(levelname)s|%(filename)s(%(lineno)s)|%(funcName)s()] %(message)s')
    handler.setFormatter(formatter)
    return handler


log_highlight = "".join(['\n----------------------------------------------------------------------------------------------------------------------\n',
                         '                                        %s %s\n',
                         '----------------------------------------------------------------------------------------------------------------------'])
log_simple = '--------------------     %s %s'
log_simple_result = '--------------------     %s %s\n%s'


def log_start_finish(logger, message: str, highlight: bool = False, prefix_start: str = "Start", prefix_finish: str = "Finish", include_postfix_result=False,
                     self_attr_names: list = None, args_indexes: list = None, kwargs_names: list = None, show_elapsed_time: bool = True):
    """
    decorator to output the function start and end log format
    Examples:
        highlight:
            False:
                >>> --------------------     Start setting-up ALO source code
                >>> ...
                >>> --------------------     Finish setting-up ALO source code
            True:
                >>> ----------------------------------------------------------------------------------------------------------------------
                >>>                                        Start setting-up ALO source code
                >>> ----------------------------------------------------------------------------------------------------------------------
                >>> ...
                >>> ----------------------------------------------------------------------------------------------------------------------
                >>>                                        Finish setting-up ALO source code
                >>> ----------------------------------------------------------------------------------------------------------------------
    Args:
        logger: logger
        message: output message
        highlight: expression form
        prefix_start: First word of start phrase (default: Start)
        prefix_finish: First word of the end phrase (default: Finish)
        include_postfix_result: Whether to print the function return value
        self_attr_names: Member variable name to retrieve from self object
        args_indexes:  indexes of function arg
        kwargs_names: names of function kwargs
        show_elapsed_time: show elapsed time seconds
    """

    def wrapper(func):
        @functools.wraps(func)
        def decorator(self, *args, **kwargs):
            if self_attr_names:
                msg = message.format(**{attr_name: getattr(self, attr_name) for attr_name in self_attr_names})
            elif args_indexes and args:
                msg = message.format(*(arg for i, arg in enumerate(args) if i in args_indexes))
            elif kwargs_names and kwargs:
                msg = message.format(**({k: v} for k, v in kwargs.items() if k in kwargs_names))
            else:
                msg = message
            logger.debug(log_highlight if highlight else log_simple, prefix_start, msg)
            start_time = time.time()
            result = func(self, *args, **kwargs)
            elapse_time = time.time() - start_time
            if show_elapsed_time:
                msg = f'{msg}({elapse_time:.2f})'
            if include_postfix_result:
                logger.debug(log_highlight if highlight else log_simple_result, prefix_finish, msg, result)
            else:
                logger.debug(log_highlight if highlight else log_simple, prefix_finish, msg)
            return result
        return decorator
    return wrapper
