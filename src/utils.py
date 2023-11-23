import os
import importlib
import sys
import re
import shutil
from datetime import datetime
from datetime import timedelta
import git

from src.constants import *
from alolib import logger 
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = logger.ProcessLogger(PROJECT_HOME)

#--------------------------------------------------------------------------------------------------------------------------

        
def set_artifacts():
    def create_folders(dictionary, parent_path=''):
        for key, value in dictionary.items():
            folder_path = os.path.join(parent_path, key)
            os.makedirs(folder_path, exist_ok=True)
            if isinstance(value, dict):
                create_folders(value, folder_path)

    # artifacts 폴더 생성 
    try:
        create_folders(artifacts_structure, PROJECT_HOME)
    except:
        PROC_LOGGER.process_error("[PROCESS][ERROR] Artifacts folder not generated!")

    for dir_name in list(artifacts_structure.keys()):
        artifacts_structure[dir_name] = PROJECT_HOME + dir_name + "/"
    
    return artifacts_structure


# FIXME pipeline name 추가 시 추가 고려 필요 
def match_steps(user_parameters, asset_source):
    """ Description
        -----------
            - experimental_plan.yaml에 적힌 user_parameters와 asset_source 내의 steps들이 일치하는 지 확인 
        Parameters
        -----------
            - user_parameters: (dict)
            - asset_source: (dict)
        Return
        -----------

        Example
        -----------
            - match_steps(user_parameters, asset_source)
    """
    for pipe, steps_dict in asset_source.items(): 
        param_steps = sorted([i['step'] for i in user_parameters[pipe]])
        source_steps = sorted([i['step'] for i in asset_source[pipe]])
        if param_steps != source_steps:
            PROC_LOGGER.process_error(f"@ << {pipe} >> - You have entered unmatching steps between << user_parameters >> and << asset_source >> in your experimental_plan.yaml. \n - steps in user_parameters: {param_steps} \n - steps in asset_source: {source_steps}")
    
    return

# FIXME 23.09.27 기준 scripts 폴더 내의 asset (subfolders) 유무 여부로만 check_asset_source 판단    
def setup_asset(asset_config, check_asset_source='once'): 
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
    PROC_LOGGER.process_info(f"Start setting-up << {step_name} >> asset @ << assets >> directory.", "blue")
    # 현재 yaml의 source_code가 git일 땐 control의 check_asset_source가 once이면 한번만 requirements 설치, every면 매번 설치하게 끔 돼 있음 
    ## FIXME ALOv2에서 기본으로 필요한 requirements.txt는 사용자가 알아서 설치 (git clone alov2 후 pip install로 직접) 
    ## asset 배치 (@ scripts 폴더)
    # local 일때는 check_asset_source 가 local인지 git url인지 상관 없음 
    if asset_source_code == "local":
        if step_name in os.listdir(ASSET_HOME): 
            PROC_LOGGER.process_info(f"Now << local >> asset_source_code mode: <{step_name}> asset exists.", "green") 
            pass 
        else: 
            PROC_LOGGER.process_error(f'Now << local >> asset_source_code mode: \n <{step_name}> asset folder does not exist in <assets> folder.')
    else: # git url & branch 
        # git url 확인
        if is_git_url(asset_source_code):
            # _renew_asset(): 다시 asset 당길지 말지 여부 (bool)
            if (check_asset_source == "every") or (check_asset_source == "once" and renew_asset(step_path)): 
                PROC_LOGGER.process_info(f"Start renewing asset : {step_path}", "blue") 
                # git으로 또 새로 받는다면 현재 존재 하는 폴더를 제거 한다
                if os.path.exists(step_path):
                    shutil.rmtree(step_path)  # 폴더 제거
                os.makedirs(step_path)
                os.chdir(PROJECT_HOME)
                repo = git.Repo.clone_from(asset_source_code, step_path)
                try: 
                    repo.git.checkout(git_branch)
                    PROC_LOGGER.process_info(f"{step_path} successfully pulled.", "green") 
                except: 
                    PROC_LOGGER.process_error(f"Your have written incorrect git branch: {git_branch}")
            # 이미 scripts내에 asset 폴더들 존재하고, requirements.txt도 설치된 상태 
            elif (check_asset_source == "once" and not renew_asset(step_path)):
                modification_time = os.path.getmtime(step_path)
                modification_time = datetime.fromtimestamp(modification_time) # 마지막 수정시간 
                PROC_LOGGER.process_info(f"<< {step_name} >> asset had already been created at {modification_time}", "blue") 
                pass  
            else: 
                PROC_LOGGER.process_error(f'You have written wrong check_asset_source: {check_asset_source}')
        else: 
            PROC_LOGGER.process_error(f'You have written wrong git url: {asset_source_code}')
    
    return 

def get_folder_size(folder_path):
    
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp) and os.path.isfile(fp):
                total_size += os.path.getsize(fp)
    return total_size

def delete_old_files(folder_path, days_old):
    cutoff_date = datetime.now() - timedelta(days=days_old)
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for d in dirnames:
            folder = os.path.join(dirpath, d)
            if os.path.isdir(folder):
                folder_modified_date = datetime.fromtimestamp(os.path.getmtime(folder))
                if folder_modified_date < cutoff_date:
                    os.rmdir(folder)
                    print(folder)

def backup_artifacts(pipelines, exp_plan_file, proc_start_time, error=False, size=1000):
    """ Description
        -----------
            - 파이프라인 실행 종료 후 사용한 yaml과 결과 artifacts를 .history에 백업함 
        Parameters
        ----------- 
            - pipelines: pipeline mode (train, inference)
            - exp_plan_file: 사용자가 입력한, 혹은 default (experimental_plan.yaml) yaml 파일의 절대경로 
            - proc_start_time: ALO instance 생성 시간 (~프로세스 시작시간)
            - error: error 발생 시 backup artifact할 땐 구분을 위해 폴더명 구분 
        Return
        -----------
            - 
        Example
        -----------
            - backup_artifacts(pipeline, self.exp_plan_file, self.proc_start_time, error=False)
    """

    size_limit = size * 1024 * 1024

    backup_size = get_folder_size(PROJECT_HOME + ".history/")
    
    if backup_size > size_limit:
        delete_old_files(PROJECT_HOME + ".history/", 10)

    current_pipeline = pipelines.split("_pipelines")[0]
    # FIXME 추론 시간이 1초 미만일 때는 train pipeline과 .history  내 폴더 명 중복 가능성 존재. 임시로 cureent_pipelines 이름 추가하도록 대응. 고민 필요    
    backup_folder= '{}_artifacts'.format(proc_start_time) + f"_{current_pipeline}/" if error == False else '{}_artifacts'.format(proc_start_time) + f"_{current_pipeline}_error/"
    
    # TODO current_pipelines 는 차후에 workflow name으로 변경이 필요
    temp_backup_artifacts_dir = PROJECT_HOME + backup_folder
    try: 
        os.mkdir(temp_backup_artifacts_dir)
    except: 
        PROC_LOGGER.process_error(f"Failed to make {temp_backup_artifacts_dir} directory") 
    # 이전에 실행이 가능한 환경을 위해 yaml 백업
    try: 
        shutil.copy(exp_plan_file, temp_backup_artifacts_dir)
    except: 
        shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
        PROC_LOGGER.process_error(f"Failed to copy << {exp_plan_file} >> into << {temp_backup_artifacts_dir} >>")
    # artifacts 들을 백업
    
    if current_pipeline == "train_pipeline":
        try: 
            os.mkdir(temp_backup_artifacts_dir + ".train_artifacts")
            shutil.copytree(PROJECT_HOME + ".train_artifacts", temp_backup_artifacts_dir + ".train_artifacts", dirs_exist_ok=True)
        except: 
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"Failed to copy << .train_artifacts >> into << {temp_backup_artifacts_dir} >>")
            
    elif current_pipeline == "inference_pipeline":
        try: 
            os.mkdir(temp_backup_artifacts_dir + ".inference_artifacts")
            shutil.copytree(PROJECT_HOME + ".inference_artifacts", temp_backup_artifacts_dir + ".inference_artifacts", dirs_exist_ok=True)
        except: 
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"Failed to copy << .inference_artifacts >> into << {temp_backup_artifacts_dir} >>")
    else:
        shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
        PROC_LOGGER.process_error(f"You entered wrong pipeline in the experimental yaml file: << {current_pipeline} >> \n Only << train_pipeline >> or << inference_pipeline>> is allowed.")
    
    # backup artifacts를 .history로 이동 
    try: 
        shutil.move(temp_backup_artifacts_dir, PROJECT_HOME + ".history/")
    except: 
        shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
        PROC_LOGGER.process_error(f"Failed to move {temp_backup_artifacts_dir} into {PROJECT_HOME}/.history/")
    # 잘 move 됐는 지 확인  
    if os.path.exists(PROJECT_HOME + ".history/" + backup_folder):
        if error == False: 
            PROC_LOGGER.process_info("Successfully completes << .history >> backup (experimental_plan.yaml & artifacts)", "green")
        elif error == True: 
            PROC_LOGGER.process_warning("Error backup completes @ << .history >> (experimental_plan.yaml & artifacts)")
            
    
    
# inner function 

def is_git_url(url):
    git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
    return re.match(git_url_pattern, url) is not None


def find_matching_strings(lst, keyword):
    matching_strings = []
    for string in lst:
        if keyword in string:
            matching_strings.append(string)
    return matching_strings[0]


def import_asset(_path, _file):
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

def release(_path):
    all_files = os.listdir(_path)
    # .py 확장자를 가진 파일만 필터링하여 리스트에 추가하고 확장자를 제거
    python_files = [file[:-3] for file in all_files if file.endswith(".py")]
    try:
        for module_name in python_files:
            if module_name in sys.modules:
                del sys.modules[module_name]
    except:
        PROC_LOGGER.process_error("An issue occurred while releasing the memory of module")


### LEGACY

## alo.py의 empty_artifacts로 대체함 
# def remove_log_files(artifacts): 
#     if '.train_artifacts' in artifacts: 
#         log_path = artifacts['.train_artifacts'] + 'log'
#         if os.path.exists(log_path):
#             shutil.rmtree(log_path, ignore_errors=True)
#     if '.inference_artifacts' in artifacts:
#         log_path = artifacts['.inference_artifacts'] + 'log'
#         if os.path.exists(log_path):
#             shutil.rmtree(log_path, ignore_errors=True)

# # TODO logger 코드 정리하기
# class Logger:
#     def __init__(self, filename):
#         self.terminal = sys.stdout
#         self.log = open(filename, "a")

#     def write(self, message):
#         self.terminal.write(message)
#         self.log.write(message)

#     def flush(self):
#         pass