import importlib
import sys
import os

from src.logger import ProcessLogger 
from src.constants import *
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)

#--------------------------------------------------------------------------------------------------------------------------

class Assets:
    
    def __init__(self):
        pass

    def import_asset(self, _path, _file):
        _user_asset = 'none'

        try:
            # Asset import
            # asset_path = 상대경로로 지정 : PROJECT_HOME/scripts/data_input
            sys.path.append(_path)
            mod = importlib.import_module(_file)
        except ModuleNotFoundError:
            PROC_LOGGER.process_error(f'Failed to import asset. Not Found : {_path}{_file}.py')

        # UserAsset 클래스 획득
        _user_asset = getattr(mod, "UserAsset")

        return _user_asset

    def release(self, _path):
        all_files = os.listdir(_path)
        # .py 확장자를 가진 파일만 필터링하여 리스트에 추가하고 확장자를 제거
        python_files = [file[:-3] for file in all_files if file.endswith(".py")]
        try:
            for module_name in python_files:
                if module_name in sys.modules:
                    del sys.modules[module_name]
        except:
            PROC_LOGGER.process_error("An issue occurred while releasing the memory of module")