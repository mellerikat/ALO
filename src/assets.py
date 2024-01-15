import importlib
import sys
import os
import re
import shutil
import git
from datetime import datetime

from src.logger import ProcessLogger 
from src.constants import *
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)

#--------------------------------------------------------------------------------------------------------------------------

class Assets:
    
    def __init__(self, ASSET_HOME):
        if not os.path.exists(ASSET_HOME):
            try:
                os.makedirs(ASSET_HOME)
            except: 
                self.proc_logger.process_error(f"Failed to create directory: {ASSET_HOME}")

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

    def memory_release(self, _path):
        all_files = os.listdir(_path)
        # .py 확장자를 가진 파일만 필터링하여 리스트에 추가하고 확장자를 제거
        python_files = [file[:-3] for file in all_files if file.endswith(".py")]
        try:
            for module_name in python_files:
                if module_name in sys.modules:
                    del sys.modules[module_name]
        except:
            PROC_LOGGER.process_error("An issue occurred while releasing the memory of module")

    # FIXME 23.09.27 기준 scripts 폴더 내의 asset (subfolders) 유무 여부로만 check_asset_source 판단    
    def setup_asset(self, asset_config, check_asset_source='once'): 
        """ Description
            -----------
                - scripts 폴더 내의 asset들을 code가 local인지 git인지, check_asset_source가 once인지 every인지에 따라 setup  
            Parameters
            -----------
                - asset_config: 현재 step의 asset config (dict 형) 
                - check_asset_source: git을 매번 당겨올지 최초 1회만 당겨올지 ('once', 'every')
            Return
            -----------
                - 
            Example
            -----------
                - setup_asset(asset_config, check_asset_source='once')
        """

        # FIXME 추후 단순 폴더 존재 유무 뿐 아니라 이전 실행 yaml과 비교하여 git주소, branch 등도 체크해야함
        def renew_asset(step_path): 
            """ Description
                -----------
                    - asset을 git으로 부터 새로 당겨올지 말지 결정 
                Parameters
                -----------
                    - step_path: scripts 폴더 내의 asset폴더 경로 
                Return
                -----------
                    - whether_renew_asset: Boolean
                Example
                -----------
                    - whether_to_renew_asset =_renew_asset(step_path) 
            """
            whether_renew_asset = False  
            if os.path.exists(step_path):
                pass
            else: 
                whether_renew_asset = True
            return whether_renew_asset
        
        # git url 확인 -> lib
        def is_git_url(url):
            git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
            return re.match(git_url_pattern, url) is not None
        
        asset_source_code = asset_config['source']['code'] # local, git url
        step_name = asset_config['step']
        git_branch = asset_config['source']['branch']
        step_path = os.path.join(ASSET_HOME, asset_config['step'])
        PROC_LOGGER.process_info(f"Start setting-up << {step_name} >> asset @ << assets >> directory.") 
        # 현재 yaml의 source_code가 git일 땐 control의 check_asset_source가 once이면 한번만 requirements 설치, every면 매번 설치하게 끔 돼 있음 
        ## FIXME ALOv2에서 기본으로 필요한 requirements.txt는 사용자가 알아서 설치 (git clone alov2 후 pip install로 직접) 
        ## asset 배치 (@ scripts 폴더)
        # local 일때는 check_asset_source 가 local인지 git url인지 상관 없음 
        if asset_source_code == "local":
            if step_name in os.listdir(ASSET_HOME): 
                PROC_LOGGER.process_info(f"Now << local >> asset_source_code mode: <{step_name}> asset exists.")
                pass 
            else: 
                PROC_LOGGER.process_error(f'Now << local >> asset_source_code mode: \n <{step_name}> asset folder does not exist in <assets> folder.')
        else: # git url & branch 
            # git url 확인
            if is_git_url(asset_source_code):
                # _renew_asset(): 다시 asset 당길지 말지 여부 (bool)
                if (check_asset_source == "every") or (check_asset_source == "once" and renew_asset(step_path)): 
                    PROC_LOGGER.process_info(f"Start renewing asset : {step_path}") 
                    # git으로 또 새로 받는다면 현재 존재 하는 폴더를 제거 한다
                    if os.path.exists(step_path):
                        shutil.rmtree(step_path)  # 폴더 제거
                    os.makedirs(step_path)
                    os.chdir(PROJECT_HOME)
                    repo = git.Repo.clone_from(asset_source_code, step_path)
                    try: 
                        repo.git.checkout(git_branch)
                        PROC_LOGGER.process_info(f"{step_path} successfully pulled.")
                    except: 
                        PROC_LOGGER.process_error(f"Your have written incorrect git branch: {git_branch}")
                # 이미 scripts내에 asset 폴더들 존재하고, requirements.txt도 설치된 상태 
                elif (check_asset_source == "once" and not renew_asset(step_path)):
                    modification_time = os.path.getmtime(step_path)
                    modification_time = datetime.fromtimestamp(modification_time) # 마지막 수정시간 
                    PROC_LOGGER.process_info(f"<< {step_name} >> asset had already been created at {modification_time}")
                    pass  
                else: 
                    PROC_LOGGER.process_error(f'You have written wrong check_asset_source: {check_asset_source}')
            else: 
                PROC_LOGGER.process_error(f'You have written wrong git url: {asset_source_code}')
        
        return 