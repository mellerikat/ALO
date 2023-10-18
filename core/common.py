import os
import importlib
import sys
import re
import shutil
from datetime import datetime
import yaml
import git

from core.message import _asset_error, print_color

#from pytz import timezone

# 현재 PROJECT PATH
PROJECT_HOME = os.path.dirname(os.path.abspath(os.path.dirname(__file__))) + "/"

# experimental plan yaml의 위치
EXP_PLAN = PROJECT_HOME + "config/tsc_experimental_plan.yaml"

# asset 코드들의 위치
# FIXME wj mnist, titanic example을 만들기 사용하는 함수 리스트를 작성
ASSET_HOME = PROJECT_HOME + "assets/"

INPUT_DATA_HOME = PROJECT_HOME + "input/"

artifacts_structure = {
    'input': {}, 
    '.train_artifacts': {
        'score': {},
        'output': {},
        'log': {},
        'report': {},
        'models': {}
    },
    '.inference_artifacts': {
        'score': {},
        'output': {},
        'log': {},
        'report': {}
    },
    '.asset_interface': {},
    '.history': {}
}


# yaml 및 artifacts 백업
# [230927] train과 inference 구분하지 않으면 train ~ inference pipline 연속 실행시 초단위까지 중복돼서 에러 발생가능하므로 구분 
# FIXME current_pipline --> pipeline_name으로 변경 필요 
def get_yaml(_yaml_file):
    exp_plan = dict()

    try:
        with open(_yaml_file, encoding='UTF-8') as f:
            exp_plan = yaml.load(f, Loader=yaml.FullLoader)
    except FileNotFoundError:
        raise ValueError(f"Not Found : {_yaml_file}")
    except:
        raise ValueError(f"Check yaml format : {_yaml_file}")

    return exp_plan
        
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
        ValueError("Artifacts folder not generated!")

    for dir_name in list(artifacts_structure.keys()):
        artifacts_structure[dir_name] = PROJECT_HOME + "/"  + dir_name + "/"
    
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
            raise ValueError(f"@ << {pipe} >> - You have entered unmatching steps between << user_parameters >> and << asset_source >> in your experimental_plan.yaml. \n - steps in user_parameters: {param_steps} \n - steps in asset_source: {source_steps}")
    
    return

# FIXME pipeline name까지 추후 반영해야할지? http://clm.lge.com/issue/browse/DXADVTECH-352?attachmentSortBy=dateTime&attachmentOrder=asc
def external_load_data(pipe_mode, external_path, external_path_permission): 
    """ Description
        -----------
            - external_path로부터 데이터를 다운로드 
        Parameters
        -----------
            - pipe_mode: 호출 시의 파이프라인 (train_pipeline, inference_pipeline)
            - external_path: experimental_plan.yaml에 적힌 external_path 전체를 dict로 받아옴 
            - external_path_permission: experimental_plan.yaml에 적힌 external_path_permission 전체를 dict로 받아옴 
        Return
        -----------
            - 
        Example
        -----------
            - load_data(self.external_path, self.external_path_permission)
    """
    
    ## FIXME 진짜 input 데이터 지우고 시작하는게 맞을지 검토필요 
    # fetch_data 할 때는 항상 input 폴더 비우고 시작한다 
    if os.path.exists(INPUT_DATA_HOME):
        for file in os.scandir(INPUT_DATA_HOME):
            print_color(f">> Start removing pre-existing input data before fetching external data: {file.name}", "blue") # os.DirEntry.name 
            shutil.rmtree(file.path)
            
    # external path가 train, inference 둘다 존재 안하는 경우 
    if ( external_path['load_train_data_path'] is None) and (external_path['load_inference_data_path'] is None): 
        # 이미 input 폴더는 무조건 만들어져 있는 상태임 
        # FIXME input 폴더가 비어있으면 프로세스 종료, 뭔가 서브폴더가 있으면 사용자한테 존재하는 서브폴더 notify 후 yaml의 input_path에는 그 서브폴더들만 활용 가능하다고 notify
        # 만약 input 폴더에 존재하지 않는 서브폴더 명을 yaml의 input_path에 작성 시 input asset에서 에러날 것임   
        if len(os.listdir(INPUT_DATA_HOME)) == 0: # input 폴더 빈 경우 
            _asset_error(f'External path (load_train_data_path, load_inference_data_path) in experimental_plan.yaml are not written & << input >> folder is empty.') 
        else: 
            print_color('[NOTICE] You can write only one of the << {} >> at << input_path >> parameter in your experimental_plan.yaml'.format(os.listdir(INPUT_DATA_HOME)), 'yellow')
        return
    
    # load할 데이터 경로 가져오기 
    # 대전제 : 중복 이름의 데이터 폴더명은 복사 허용 x 
    load_data_path = None 
    if pipe_mode == "train_pipeline": 
        load_data_path = external_path['load_train_data_path'] # 0개 일수도(None), 한 개 일수도(str), 두 개 이상 일수도 있음(list) 
    elif pipe_mode == "inference_pipeline":
        load_data_path = external_path['load_inference_data_path']
    else: 
        _asset_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")

    print_color(f">> Start loading external << {load_data_path} >> data into << input >> directory.", "blue")
    
    try:
        load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
        print_color(f'>> s3 private key file << load_s3_key_path >> loaded successfully.', 'green')   
    except:
        print_color('[NOTICE] You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment.' , 'yellow')
        load_s3_key_path = None
        
    # None일 시 type을 list로 통일 
    if load_data_path is None:
        load_data_path = []

    # external path가 존재하는 경우 
    def _get_ext_path_type(_ext_path: str): # inner function 
        if 's3:/' in _ext_path: 
            return 's3'
        elif os.path.isabs(_ext_path) == True: # 절대경로. nas, local 둘다 가능 
            return 'absolute'
        elif os.path.isabs(_ext_path) == False: 
            _asset_error(f'<< {_ext_path} >> is relative path. This is unsupported type of external load data path. Please enter the absolute path.')
        else: 
            _asset_error(f'<< {_ext_path} >> is unsupported type of external load data path.')
    
    # 1개여서 str인 경우도 list로 바꾸고, 여러개인 경우는 그냥 그대로 list로 
    # None (미입력) 일 땐 별도처리 필요 
    load_data_path = [load_data_path] if type(load_data_path) == str else load_data_path

    for ext_path in load_data_path: 
        print_color(f'>> [@ {pipe_mode}] Start fetching external data from << {ext_path} >> into << input >> directory.', 'blue')
        ext_type = _get_ext_path_type(ext_path) # absolute / s3
        
        if ext_type  == 'absolute':
            # 해당 nas 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
            # nas 접근권한 없으면 에러 발생 
            # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
            try: 
                # 사용자가 실수로 yaml external path에 마지막에 '/' 쓰든 안쓰든, (즉 아래 코드에서 '/'이든 '//' 이든 동작엔 이상X)
                # [참고] https://stackoverflow.com/questions/3925096/how-to-get-only-the-last-part-of-a-path-in-python
                mother_path = os.path.basename(os.path.normpath(ext_path)) # 가령 /nas001/test/ 면 test가 mother_path, ./이면 .가 mother_path 
                if mother_path in os.listdir(INPUT_DATA_HOME): 
                    _asset_error(f"You already have duplicated sub-folder name << {mother_path} >> in the << input >> folder. Please rename your sub-folder name if you use multiple data sources.")
                shutil.copytree(ext_path, PROJECT_HOME + f"input/{mother_path}", dirs_exist_ok=True) # 중복 시 덮어쓰기 됨 
            except: 
                _asset_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong NAS path (must be existing directory!) \n / or You do not have permission to access \n / or You used duplicated sub-folder names for multiple data sources.')
        elif ext_type  == 's3':  
            # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
            # 해당 s3 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
            # s3 접근권한 없으면 에러 발생 
            # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
            s3_downloader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
            try: 
                s3_downloader.download_folder(INPUT_DATA_HOME)
            except:
                _asset_error(f'Failed to download s3 data folder from << {ext_path} >>')
        else: 
            # 미지원 external data storage type
            _asset_error(f'{ext_path} is unsupported type of external data path.') 
            
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
    print_color(f">> Start setting-up << {step_name} >> asset @ << assets >> directory.", "blue")
    # 현재 yaml의 source_code가 git일 땐 control의 check_asset_source가 once이면 한번만 requirements 설치, every면 매번 설치하게 끔 돼 있음 
    ## FIXME ALOv2에서 기본으로 필요한 requirements.txt는 사용자가 알아서 설치 (git clone alov2 후 pip install로 직접) 
    ## asset 배치 (@ scripts 폴더)
    # local 일때는 check_asset_source 가 local인지 git url인지 상관 없음 
    if asset_source_code == "local":
        if step_name in os.listdir(ASSET_HOME): 
            print_color(f"@ local asset_source_code mode: <{step_name}> asset exists.", "green") 
            pass 
        else: 
            _asset_error(f'@ local asset_source_code mode: <{step_name}> asset folder \n does not exist in <assets> folder.')
    else: # git url & branch 
        # git url 확인
        if is_git_url(asset_source_code):
            # _renew_asset(): 다시 asset 당길지 말지 여부 (bool)
            if (check_asset_source == "every") or (check_asset_source == "once" and renew_asset(step_path)): 
                print_color(f">> Start renewing asset : {step_path}", "blue") 
                # git으로 또 새로 받는다면 현재 존재 하는 폴더를 제거 한다
                if os.path.exists(step_path):
                    shutil.rmtree(step_path)  # 폴더 제거
                os.makedirs(step_path)
                os.chdir(PROJECT_HOME)
                repo = git.Repo.clone_from(asset_source_code, step_path)
                try: 
                    repo.git.checkout(git_branch)
                    print_color(f"{step_path} successfully pulled.", "green") 
                except: 
                    raise ValueError(f"Your have written incorrect git branch: {git_branch}")
            # 이미 scripts내에 asset 폴더들 존재하고, requirements.txt도 설치된 상태 
            elif (check_asset_source == "once" and not renew_asset(step_path)):
                modification_time = os.path.getmtime(step_path)
                modification_time = datetime.fromtimestamp(modification_time) # 마지막 수정시간 
                print_color(f"[NOTICE] << {step_name} >> asset had already been created at {modification_time}", "yellow") 
                pass  
            else: 
                _asset_error(f'You have written incorrect check_asset_source: {check_asset_source}')
        else: 
            _asset_error(f'You have written incorrect git url: {asset_source_code}')
    
    return 

def backup_artifacts(pipelines, exp_plan_file):
    """ Description
        -----------
            - 파이프라인 실행 종료 후 사용한 yaml과 결과 artifacts를 .history에 백업함 
        Parameters
        -----------
            - pipelines: pipeline mode (train, inference)
            - exp_plan_file: 사용자가 입력한, 혹은 default (experimental_plan.yaml) yaml 파일의 절대경로 
        Return
        -----------
            - 
        Example
        -----------
            - backup_artifacts(pipe_mode)
    """

    current_pipeline = pipelines.split("_pipelines")[0]
    # artifacts_home_생성시간 폴더를 제작
    timestamp_option = True
    hms_option = True

    if timestamp_option == True:  
        if hms_option == True : 
            timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
        else : 
            timestamp = datetime.now().strftime("%y%m%d")     
        # FIXME 추론 시간이 1초 미만일 때는 train pipeline과 .history  내 폴더 명 중복 가능성 존재. 임시로 cureent_pipelines 이름 추가하도록 대응. 고민 필요    
        backup_folder= '{}_artifacts'.format(timestamp) + f"_{current_pipeline}/"
    
    # TODO current_pipelines 는 차후에 workflow name으로 변경이 필요
    temp_backup_artifacts_dir = PROJECT_HOME + backup_folder
    try: 
        os.mkdir(temp_backup_artifacts_dir)
    except: 
        raise NotImplementedError(f"Failed to make {temp_backup_artifacts_dir} directory") 
    # 이전에 실행이 가능한 환경을 위해 yaml 백업
    try: 
        shutil.copy(exp_plan_file, temp_backup_artifacts_dir)
    except: 
        shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
        raise NotImplementedError(f"Failed to copy << {exp_plan_file} >> into << {temp_backup_artifacts_dir} >>")
    # artifacts 들을 백업
    
    if current_pipeline == "train_pipeline":
        try: 
            os.mkdir(temp_backup_artifacts_dir + ".train_artifacts")
            shutil.copytree(PROJECT_HOME + ".train_artifacts", temp_backup_artifacts_dir + ".train_artifacts", dirs_exist_ok=True)
        except: 
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            raise NotImplementedError(f"Failed to copy << .train_artifacts >> into << {temp_backup_artifacts_dir} >>")
            
    elif current_pipeline == "inference_pipeline":
        try: 
            os.mkdir(temp_backup_artifacts_dir + ".inference_artifacts")
            shutil.copytree(PROJECT_HOME + ".inference_artifacts", temp_backup_artifacts_dir + ".inference_artifacts", dirs_exist_ok=True)
        except: 
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            raise NotImplementedError(f"Failed to copy << .inference_artifacts >> into << {temp_backup_artifacts_dir} >>")
    else:
        shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
        raise ValueError(f"You entered wrong pipeline in the experimental yaml file: << {current_pipeline} >> \n Only << train_pipeline >> or << inference_pipeline>> is allowed.")
    
    # backup artifacts를 .history로 이동 
    try: 
        shutil.move(temp_backup_artifacts_dir, PROJECT_HOME + ".history/")
    except: 
        shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
        raise NotImplementedError(f"Failed to move {temp_backup_artifacts_dir} into {PROJECT_HOME}/.history/")
    # 잘 move 됐는 지 확인  
    if os.path.exists(PROJECT_HOME + ".history/" + backup_folder):
        print_color(">> [DONE] << .history >> backup (config yaml & artifacts) completes successfully.", "green")
            


def asset_info(pipelines, step):
    #time_utc = datetime.now(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')
    #time_kst = datetime.now(timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    print('\n\n')
    print_color("============================= ASSET INFO =============================", 'blue')

    #print_color(f"TIME(UTC)    : {time_utc} (KST : {time_kst})", 'blue')
    print_color(f"PIPELINES    : {pipelines}", 'blue')
    print_color(f"ASSETS       : {step}", 'blue')
    print_color("=======================================================================", 'blue')
    print('\n\n')







def is_git_url(url):
    git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
    return re.match(git_url_pattern, url) is not None

# [FIXME] 추후 단순 폴더 존재 유무 뿐 아니라 이전 실행 yaml과 비교하여 git주소, branch 등도 체크해야함
def _renew_asset(step_path): 
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



# TODO logger 코드 정리하기
class Logger(object):
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        pass

def find_matching_strings(lst, keyword):
    matching_strings = []
    for string in lst:
        if keyword in string:
            matching_strings.append(string)
    return matching_strings[0]
#################### logger 여기까지 ####################


def import_asset(_path, _file):
    _user_asset = 'none'

    try:
        # Asset import
        # asset_path = 상대경로로 지정 : self.project_home/scripts/data_input
        sys.path.append(_path)
        mod = importlib.import_module(_file)
    except ModuleNotFoundError:
        raise ValueError(f'Not Found : {_path}{_file}.py')

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
        _asset_error("An issue occurred while deleting the module")