import functools
import time
import psutil
import math
import threading
import textwrap
from alo import settings

logger = settings.logger

COLOR_DICT = {
    'PURPLE': '\033[95m',
    'CYAN': '\033[96m',
    'DARKCYAN': '\033[36m',
    'BLUE': '\033[94m',
    'GREEN': '\033[92m',
    'YELLOW': '\033[93m',
    'RED': '\033[91m',
    'BOLD': '\033[1m',
    'BOLD-GREEN': '\033[1m\033[92m',
    'BOLD-CYAN': '\033[1m\033[96m',
    'UNDERLINE': '\033[4m',
}
COLOR_END = '\033[0m'
BYTE_SIZE_NAME = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")


class ColorMessage:

    @classmethod
    def print(cls, msg, escape=COLOR_DICT.get("BOLD", "")) -> None:
        print(f"{escape}{msg}{COLOR_END}")


for color, code in COLOR_DICT.items():
    setattr(ColorMessage, color.lower().replace("-", "_"), lambda msg, escape=code: ColorMessage.print(msg, escape))

log_proc_highlight = "".join(['\n----------------------------------------------------------------------------------------------------------------------\n',
                              '                                        %s\n',
                              '----------------------------------------------------------------------------------------------------------------------\n'])
log_proc_simple = '--------------------     %s'


def _log_process(msg, highlight=False):
    """ logging format for ALO process

    Args:
        msg         (str): message
        highlight   (bool): whetehr to highlight the message

    Returns: -

    """
    if highlight:
        logger.info(log_proc_highlight, msg)
    else:
        logger.info(log_proc_simple, msg)


log_highlight = "".join(['\n----------------------------------------------------------------------------------------------------------------------\n',
                         '                                        %s %s\n',
                         '----------------------------------------------------------------------------------------------------------------------\n'])
log_simple = '--------------------     %s %s'
log_simple_result = '--------------------     %s %s\n%s'


def log_start_finish(message: str, highlight: bool = False, prefix_start: str = "Start", prefix_finish: str = "Finish", include_postfix_result=False,
                     self_attr_names: list = None, args_indexes: list = None):
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
        message: output message
        highlight: expression form
        prefix_start: First word of start phrase (default: Start)
        prefix_finish: First word of the end phrase (default: Finish)
        include_postfix_result: Whether to print the function return value
        self_attr_names: Member variable name to retrieve from self object
        args_indexes:  indexes of function arg
    """

    def wrapper(func):
        @functools.wraps(func)
        def decorator(self, *args, **kwargs):
            if self_attr_names:
                msg = message.format(**{attr_name: getattr(self, attr_name) for attr_name in self_attr_names})
            elif args_indexes and args:
                msg = message.format(*(arg for i, arg in enumerate(args) if i in args_indexes))
            else:
                msg = message
            logger.info(log_highlight if highlight else log_simple, prefix_start, msg)
            result = func(self, *args, **kwargs)
            if include_postfix_result:
                logger.info(log_highlight if highlight else log_simple_result, prefix_finish, msg, result)
            else:
                logger.info(log_highlight if highlight else log_simple, prefix_finish, msg)
            return result

        return decorator

    return wrapper


class RaiseErrorWithMessage:
    def __init__(self, message=None):
        """

        Args:
            message:
        """
        self.message = f"{message} : %s(%s)"

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if isinstance(exc_val, Exception):
            logger.error(self.message, exc_val.__class__.__name__, str(exc_val))


def convert_readable_unit(size: int):
    """ 숫자를 용량 단위로 변환

    Args:
        size (int): byte 크기

    Returns:
        단위별 용량

    """
    if not isinstance(size, int) or size <= 0:
        return "0B"
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    return f"{size / p:.1f}{BYTE_SIZE_NAME[i]}"


MEM_LOCK = threading.Lock()


class ResourceProfile:
    """ H/W CPU/Memory 리소스 확인

    """
    def __init__(self, ppid, cpu):
        self.enable = True
        self.wait = 0.5
        self.ppid = ppid
        self.cpus = [psutil.cpu_percent()]
        self.rsss = [self.ppid.memory_info().rss]

    def run(self):
        while self.enable:
            time.sleep(self.wait)
            cpu = psutil.cpu_percent()
            rss = self.ppid.memory_info().rss
            MEM_LOCK.acquire()
            self.cpus.append(cpu)
            self.rsss.append(rss)
            MEM_LOCK.release()

    def info(self, human_readable=True):
        MEM_LOCK.acquire()
        self.cpus.append(psutil.cpu_percent())
        self.rsss.append(self.ppid.memory_info().rss)
        MEM_LOCK.release()
        if human_readable:
            return ((min(self.cpus), max(self.cpus), sum(self.cpus)/len(self.cpus)),
                    (convert_readable_unit(min(self.rsss)), convert_readable_unit(max(self.rsss)), convert_readable_unit(int(sum(self.rsss)/len(self.rsss)))))

        return ((min(self.cpus), max(self.cpus), sum(self.cpus)/len(self.cpus)),
                (min(self.rsss), max(self.rsss), int(sum(self.rsss)/len(self.rsss))))


def print_table(rows: list, col_max_width=50, col_sort=None, **kwargs):

    # column 유형 추출
    columns = {}
    for item in rows:
        for k, v in item.items():
            type_name = None if v is None else type(v).__name__
            if k not in columns:
                columns[k] = [type_name]
            else:
                columns[k].append(type_name)
    for k in columns.keys():
        types = list(dict.fromkeys(columns[k]))
        if len(types) == 1:
            columns[k] = types[0]
        elif len(types) == 2:
            if None in types:
                types.remove(None)
                columns[k] = types[0]
            else:
                columns[k] = 'str'
        else:
            columns[k] = 'str'

    # 정렬
    if col_sort == 'asc':
        columns = dict(sorted(columns.items()))
    elif col_sort == 'desc':
        columns = dict(sorted(columns.items(), reverse=True))

    wraps = []
    col_len = {}
    for row in rows:
        wrap = []
        for c in columns.keys():
            c_l = col_len.get(c, len(c))
            v = row.get(c, None)
            if v is None:
                wrap.append("")
            else:
                text = textwrap.shorten(str(v), width=col_max_width, placeholder="...")
                text_len = len(text)
                wrap.append(text)
                if c_l < text_len:
                    c_l = text_len
            col_len[c] = c_l
        wraps.append(wrap)

    fmts = []
    for c, t in columns.items():
        fmts.append(f"{{:{'>' if t in ['int', 'float'] else ''}{col_len[c]}}}")
    fmt = f"| {' | '.join(fmts)} |"

    digit = len(str(len(wraps)))
    print(f"{''.join([' ' for i in range(digit)])}", fmt.format(*[textwrap.shorten(c, width=col_max_width, placeholder="...") for c in columns.keys()]))

    for i, wrap in enumerate(wraps):
        print(f"{{:>{digit}}}".format(i), fmt.format(*wrap))
