import os
from collections import defaultdict
import pkg_resources
import subprocess
import sys
import re

from datetime import datetime
#from pytz import timezone

# 현재 PROJECT PATH
PROJECT_HOME = os.path.dirname(os.path.realpath(__file__)) + "/"

# experimental plan yaml의 위치
EXP_PLAN = PROJECT_HOME + "config/tsc_experimental_plan.yaml"

# asset 코드들의 위치
# FIXME wj mnist, titanic example을 만들기 사용하는 함수 리스트를 작성
ASSET_HOME = PROJECT_HOME + "assets/"

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

color_dict = {
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
            Display text with color at ipynb

        Parameters
        -----------
            msg (str) : text
            _color (str) : PURPLE, CYAN, DARKCYAN, BLUE, GREEN, YELLOW, RED, BOLD, UNDERLINE

        example
        -----------
            print_color('Display color text', 'BLUE')
    """
    if _color.upper() in color_dict.keys():
        print(color_dict[_color.upper()]+msg+COLOR_END)
    else:
        raise ValueError('Select color : {}'.format(color_dict.keys()))

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

def extract_requirements_txt(step_name): 
    """ Description
        -----------
            - master 혹은 각 asset (=slave) 내의 requirements.txt가 존재 시 내부에 작성된 패키지들을 list로 추출 
        Parameters
        -----------
            - step_name: master 혹은 scripts 밑에 설치될 asset 이름 
        Return
        -----------
            - 
        Example
        -----------
            - extract_req_txt(step_name)
    """
    fixed_txt_name  = 'requirements.txt'
    packages_in_txt = []
    # ALO master 종속 패키지 리스트업 
    if step_name == 'master': 
        try: 
            with open(PROJECT_HOME + fixed_txt_name, 'r') as req_txt:  
                for pkg in req_txt: 
                    pkg = pkg.strip() # Remove the newline character at the end of the line (=package)
                    packages_in_txt.append(pkg)
            return packages_in_txt        
        except: 
            ValueError(f'Failed to install basic dependency. You may have removed requirements.txt in project home.')
    # step (=asset) 종속  패키지 리스트업 
    if fixed_txt_name in os.listdir(ASSET_HOME + step_name):
        with open(ASSET_HOME + step_name + '/' + fixed_txt_name, 'r') as req_txt:  
            for pkg in req_txt: 
                pkg = pkg.strip() # Remove the newline character at the end of the line (=package)
                packages_in_txt.append(pkg)
        return packages_in_txt
    else: 
        ValueError(f"<< {fixed_txt_name} >> dose not exist in << scripts/{step_name} folder >>. However, you have written {fixed_txt_name} at that step in << config/experimental_plan.yaml >>. Please remove {fixed_txt_name} in the yaml file.")

def check_install_requirements(requirements_dict):
    """ Description
        -----------
            - 각 step에서 필요한 package (requirements.txt에 작성됐든 yaml에 직접 작성됐든)가 현재 사용자의 가상환경에 설치 돼 있는지 설치여부 체크 후, 없으면 설치 시도
            - experimental_plan.yaml의 asset_source의 code 모드가 local 이든 git이든 일단 항상 실행 시 마다 사용자 가상환경에 모든 package 깔려있는지는 체크한다 
        Parameters
        -----------
            - requirements_dict: 각 step에서 필요한 requirements dict <dict: key=step name, value=requirements list>
        Return
        -----------
            - 
        Example
        -----------
            - check_install_requirements( requirements_dict)
    """
    # 0. asset_source_code가 local이든 git이든, check_asset_source가 once든 every든 모두 동일하게 항상 모듈의 설치여부는 패키지명, 버전 check 후 없으면 설치 (ver 다르면 notify 후 설치) 
    # 1. 한 pipline 내의 각 step을 루프 돌면서 직접 작성된 패키지 (ex. pandas==3.4)는 직접 설치하고
    # 2. experimental_plan.yaml에 requirements.txt가 기입 돼 있다면 먼저 scripts 폴더 내 해당 asset 폴더 밑에 requirements.txt가 존재하는 지 확인 (없으면 에러)
    # 3. 만약 이미 설치돼 있는 패키지 중 버전이 달라서 재설치 하는 경우는 (pandas==3.4 & pandas==3.2) print_color로 사용자 notify  
    fixed_txt_name = 'requirements.txt'

    # 어떤 step에 requirements.txt가 존재하면, scripts/asset폴더 내에 txt파일 존재유무 확인 후 그 내부에 기술된 패키지들을 추출  
    extracted_requirements_dict = dict() 
    for step_name, requirements_list in requirements_dict.items(): 
        # yaml의 requirements에 requirements.txt를 적었다면, 해당 step 폴더에 requirements.txt가 존재하는 지 확인하고 존재한다면 내부에 작성된 패키지 명들을 추출하여 아래 loop에서 check & install 수행 
        if fixed_txt_name in requirements_list:
            extracted_requirements_dict[step_name] = list(set(requirements_list + extract_requirements_txt(step_name))) # 이번 step 내의 패키지들 중 사용자가 실수로 완전 같은 패키지,버전을 두번 쓴 경우 중복제거 
            extracted_requirements_dict[step_name].remove(fixed_txt_name) # requirements.txt라는 이름은 삭제 
        else: #requirements.txt 를 해당 step에 미기입한 경우 (yaml에서)
            extracted_requirements_dict[step_name] = list(set(requirements_list)) 

    # yaml 수동작성과 requirements.txt 간, 혹은 서로다른 asset 간에 같은 패키지인데 version이 다른 중복일 경우 아래 우선순위에 따라 한번만 설치하도록 지정         
    # 우선순위 : 1. ALO master 종속 패키지 / 2. 이번 파이프라인의 먼저 오는 step (ex. input asset) / 3. 같은 step이라면 requirements.txt보다는 yaml에 직접 작성한 패키지 우선 
    # 위 우선순위는 이미 main.py에서 requirements_dict 만들 때 부터 반영돼 있음 
    dup_checked_requirements_dict = defaultdict(list)
    dup_chk_set = set() 
    for step_name, requirements_list in extracted_requirements_dict.items(): 
        for pkg in requirements_list: 
            pkg_name = pkg.replace(" ", "") # 모든 공백 제거후, 비교 연산자, version 말고 패키지의 base name를 아래 조건문에서 구할 것임
            base_pkg_name = "" 
            if pkg_name.startswith("#") or pkg_name == "": # requirements.txt에도 주석 작성했거나 빈 줄을 첨가한 경우는 패스 
                continue 
            # FIXME 이외의 특수문자 있으면 에러 띄워야할지? 그냥 강제로 무조건 한번 설치 시도하는게 나을수도 있을 듯 한데..  
            # 비교연산자 이외에는 지원안함 
            if '<' in pkg_name: # <, <=  케이스 
                base_pkg_name = pkg_name[ : pkg_name.index('<')]
            elif '>' in pkg_name: # >, >=  케이스 
                base_pkg_name = pkg_name[ : pkg_name.index('>')]
            elif ('=' in pkg_name) and ('<' not in pkg_name) and ('>' not in pkg_name): # == 케이스 
                base_pkg_name = pkg_name[ : pkg_name.index('=')]
            else: # version 명시 안한 케이스 
                base_pkg_name = pkg_name  
                
            # ALO master 및 모든 asset들의 종속 패키지를 취합했을 때 버전 다른 중복 패키지 존재 시 먼저 진행되는 step(=asset)의 종속 패키지만 설치  
            if base_pkg_name in dup_chk_set: 
                print_color(f'Ignored installing << {pkg_name} >>. Another version will be installed in the previous step.', 'red')
            else: 
                dup_chk_set.add(base_pkg_name)
                dup_checked_requirements_dict[step_name].append(pkg_name)
                
    ####################
    total_num_install = len(dup_chk_set)
    count = 1
    # 사용자 환경에 priority_sorted_pkg_list의 각 패키지 존재 여부 체크 및 없으면 설치
    for step_name, package_list in dup_checked_requirements_dict.items(): 
        print_color(f"======================================== Start dependency installation - step : << {step_name} >> ========================================", 'green')
        for package in package_list:
            print_color(f'>> Start checking existence & installing package - {package} | Progress: ( {count} / {total_num_install} total packages )', 'yellow')
            count += 1
            try: 
                # [pkg_resources 관련 참고] https://stackoverflow.com/questions/44210656/how-to-check-if-a-module-is-installed-in-python-and-if-not-install-it-within-t 
                # 가령 aiplib @ git+http://mod.lge.com/hub/smartdata/aiplatform/module/aip.lib.git@ver2  같은 version 표기가 requirements.txt에 존재해도 conflict 안나는 것 확인 완료 
                # FIXME 사용자가 가령 pandas 처럼 (==version 없이) 작성하여도 아래 코드는 통과함 
                pkg_resources.get_distribution(package) # get_distribution tact-time 테스트: 약 0.001s
                print_color(f'- << {package} >> already exists', 'blue')
            except pkg_resources.DistributionNotFound: # 사용자 가상환경에 해당 package 설치가 아예 안 돼있는 경우 
                try: # nested try/except 
                    print_color(f'- Start installing package - {package}', 'green')
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                except OSError as e: 
                    # 가령 asset을 만든 사람은 abc.txt라는 파일 기반으로 pip install -r abc.txt 하고 싶었는데, 우리는 requirements.txt 라는 이름만 허용하므로 관련 안내문구 추가  
                    self._asset_error(f"Error occurs while installing {package}. If you want to install from packages written file, make sure that your file name is << {fixed_txt_name} >> ~ " + e)
            except pkg_resources.VersionConflict: # 설치 돼 있지만 버전이 다른 경우 재설치 
                try: # nested try/except 
                    print_color(f'- VersionConflict occurs. Start re-installing package << {package} >>. You should check the dependency for the package among assets.', 'red')
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                except OSError as e: 
                    self._asset_error(f"Error occurs while re-installing {package} ~ " + e)
            # FIXME 그 밖의 에러는 아래에서 그냥 에러 띄우고 프로세스 kill 
            # pkg_resources의 exception 참고 코드 : https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
            except pkg_resources.ResolutionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                self._asset_error(f'ResolutionError occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')
            except pkg_resources.ExtractionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                self._asset_error(f'ExtractionError occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')    
            # FIXME 왜 unrechable 이지? https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
            except pkg_resources.UnknownExtra: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                self._asset_error(f'UnknownExtra occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')
            # 위 try 코드 에러 없이 통과 했다면 해당 버전의 package 존재하니까 그냥 return 하면됨  
    print_color(f"======================================== Finish dependency installation ======================================== \n", 'green')
    return 

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

# [FIXME] 23.09.27 기준 scripts 폴더 내의 asset (subfolders) 유무 여부로만 check_asset_source 판단    
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
    asset_source_code = asset_config['source']['code'] # local, git url
    step_name = asset_config['step']
    git_branch = asset_config['source']['branch']
    step_path = os.path.join(ASSET_HOME, asset_config['step'])
    
    # 현재 yaml의 source_code가 git일 땐 control의 check_asset_source가 once이면 한번만 requirements 설치, every면 매번 설치하게 끔 돼 있음 
    ## [FIXME] ALOv2에서 기본으로 필요한 requirements.txt는 사용자가 알아서 설치 (git clone alov2 후 pip install로 직접) 
    ## asset 배치 (@ scripts 폴더)
    # local 일때는 check_asset_source 가 local인지 git url인지 상관 없음 
    if asset_source_code == "local":
        if step_name in os.listdir(ASSET_HOME): 
            print_color(f"@ local asset_source_code mode: <{step_name}> asset exists.", "green") 
            pass 
        else: 
            self._asset_error(f'@ local asset_source_code mode: <{step_name}> asset folder \n does not exist in <assets> folder.')
    else: # git url & branch 
        # git url 확인
        if is_git_url(asset_source_code):
            # _renew_asset(): 다시 asset 당길지 말지 여부 (bool)
            if (check_asset_source == "every") or (check_asset_source == "once" and _renew_asset(step_path)): 
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
            elif (check_asset_source == "once" and not _renew_asset(step_path)):
                modification_time = os.path.getmtime(step_path)
                modification_time = datetime.fromtimestamp(modification_time) # 마지막 수정시간 
                print_color(f"{step_name} asset has already been created at {modification_time}", "blue") 
                pass  
            else: 
                self._asset_error(f'You have written incorrect check_asset_source: {check_asset_source}')
        else: 
            self._asset_error(f'You have written incorrect git url: {asset_source_code}')
    
    return 

# yaml 및 artifacts 백업
# [230927] train과 inference 구분하지 않으면 train ~ inference pipline 연속 실행시 초단위까지 중복돼서 에러 발생가능하므로 구분 
def backup_artifacts(pipelines, control):
    """ Description
        -----------
            - 파이프라인 실행 종료 후 사용한 yaml과 결과 artifacts를 .history에 백업함 
        Parameters
        -----------
            - pipelines: pipeline mode (train, inference)
        Return
        -----------
            - 
        Example
        -----------
            - backup_artifacts(pipe_mode)
    """
    if control['backup_artifacts'] == True:
        current_pipelines = pipelines.split("_pipelines")[0]
        # artifacts_home_생성시간 폴더를 제작
        timestamp_option = True
        hms_option = True
    
        if timestamp_option == True:  
            if hms_option == True : 
                timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
            else : 
                timestamp = datetime.now().strftime("%y%m%d")     
            # [FIXME] 추론 시간이 1초 미만일 때는 train pipeline과 .history  내 폴더 명 중복 가능성 존재. 임시로 cureent_pipelines 이름 추가하도록 대응. 수정 필요    
            backup_folder= '{}_artifacts'.format(timestamp) + f"_{current_pipelines}/"
        
        # TODO current_pipelines 는 차후에 workflow name으로 변경이 필요
        backup_artifacts_home = PROJECT_HOME + backup_folder
        os.mkdir(backup_artifacts_home)
        
        # 이전에 실행이 가능한 환경을 위해 yaml 백업
        shutil.copy(PROJECT_HOME + "config/experimental_plan.yaml", backup_artifacts_home)
        # artifacts 들을 백업
        for dir_name in list(artifacts_structure.keys()):
            if dir_name == ".history" or dir_name == "input":
                continue 
            else:
                os.mkdir(backup_artifacts_home + dir_name)
                shutil.copytree(PROJECT_HOME + dir_name, backup_artifacts_home + dir_name, dirs_exist_ok=True)
        # backup artifacts를 .history로 이동 
        try: 
            shutil.move(backup_artifacts_home, PROJECT_HOME + ".history/")
        except: 
            self._asset_error(f"Failed to move {bakcup_artifacts_home} into {PROJECT_HOME}/.history/")
        if os.path.exists(PROJECT_HOME + ".history/" + backup_folder):
            print_color("[Done] .history backup (config yaml & artifacts) complete", "green")


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