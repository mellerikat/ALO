import os
import re
import yaml
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pytz import timezone
from abc import ABCMeta, abstractmethod


date_delta_key = {
    'Y': 'years',
    'y': 'years',
    'years': 'years',
    'm': 'months',
    'months': 'months',
    'd': 'days',
    'days': 'days',
    'H': 'hours',
    'hours': 'hours',
    'M': 'minutes',
    'minutes': 'minutes',
    'S': 'seconds',
    'seconds': 'seconds',
    'f': 'microseconds',
    'microseconds': 'microseconds'
}


def ymd(f='%Y%m%d', tz=None, **kwargs):
    if tz:
        tz = timezone(tz)
    date = datetime.now(tz) if 'datetime' not in kwargs else kwargs['datetime']
    if kwargs:
        date = date + relativedelta(**{date_delta_key[k]: v for k, v in kwargs.items() if k in date_delta_key})
    return date.strftime(f)


def env_constructor(loader, node):
    """!Env tag"""
    value = str(loader.construct_scalar(node))  # get the string value next to !Env
    match = re.compile(".*?\\${(\\w+)}.*?").findall(value)
    if match:
        for key in match:
            if not os.environ.get(key):
                raise ValueError(f"Unable to find the {key} item set in the OS environment variables.\n"
                                 f"Please define the {key} environment variable when running the application.")
            value = value.replace(f'${{{key}}}', os.environ[key])
        return value
    return value


def python_constructor(loader, node):
    """!Python tag"""
    value = str(loader.construct_scalar(node))  # get the string value next to !Env
    return eval(value)

    # def module_constructor(loader, node):
    """!Module tag"""
    # value = str(loader.construct_scalar(node))  # get the string value next to !Env
    # parts = value.split('.')
    # module = ".".join(parts[:-1])
    # return getattr(importlib.import_module(module), parts[-1])


class Schema(metaclass=ABCMeta):
    def __init__(self, name: str, default=None, require=True):
        self.name = name
        self.default = default
        self.require = require

    @abstractmethod
    def validate(self, val: object) -> bool:
        pass


class Integer(int, Schema):
    """Integer"""

    def __init__(self, name: str, require=True, default=0, min: int = None, max: int = None):
        super(Integer, self).__init__(name, default=0, require=require)
        self.min = min
        self.max = max

    def __new__(cls, *args, **kwargs):
        return 1

    def validate(self, val: object) -> bool:
        if not isinstance(val, int):
            ValueError(f"Variable {self.name} only accepts values of integer type.")


def get_loader():
    """Get custom loaders."""
    loader = yaml.SafeLoader  # yaml.FullLoader
    loader.add_constructor("!Env", env_constructor)
    loader.add_constructor("!Python", python_constructor)
    # loader.add_constructor("!Module", module_constructor)
    return loader


def load_yml(path: str):
    with open(path, encoding='UTF-8') as file:
        return yaml.load(file, Loader=get_loader())
