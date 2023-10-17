import os
from collections import defaultdict
import pkg_resources
import subprocess
import sys
import re
import shutil
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
# yaml 및 artifacts 백업
# [230927] train과 inference 구분하지 않으면 train ~ inference pipline 연속 실행시 초단위까지 중복돼서 에러 발생가능하므로 구분 
# FIXME current_pipline --> pipeline_name으로 변경 필요 

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

## FIXME 사용자 환경의 패키지 설치 여부를 매 실행마다 체크하는 것을 on, off 하는 기능이 필요할 지?   
# FIXME aiplib @ git+http://mod.lge.com/hub/smartdata/aiplatform/module/aip.lib.git@ver2 같은 이름은 아예 미허용 
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
            requirements_txt_list = extract_requirements_txt(step_name)
            requirements_txt_list = sorted(set(requirements_txt_list), key = lambda x: requirements_txt_list.index(x)) 
            yaml_written_list = sorted(set(requirements_list), key = lambda x: requirements_list.index(x)) 
            fixed_txt_index = yaml_written_list.index(fixed_txt_name)                
            extracted_requirements_dict[step_name] = yaml_written_list[ : fixed_txt_index] + requirements_txt_list + yaml_written_list[fixed_txt_index + 1 : ]
        else: #requirements.txt 를 해당 step에 미기입한 경우 (yaml에서)
            extracted_requirements_dict[step_name] = sorted(set(requirements_list), key = lambda x: requirements_list.index(x)) 

    # yaml 수동작성과 requirements.txt 간, 혹은 서로다른 asset 간에 같은 패키지인데 version이 다른 중복일 경우 아래 우선순위에 따라 한번만 설치하도록 지정         
    # 우선순위 : 1. ALO master 종속 패키지 / 2. 이번 파이프라인의 먼저 오는 step (ex. input asset) / 3. 같은 step이라면 requirements.txt보다는 yaml에 직접 작성한 패키지 우선 
    # 위 우선순위는 이미 main.py에서 requirements_dict 만들 때 부터 반영돼 있음 
    dup_checked_requirements_dict = defaultdict(list) # --force-reinstall 인자 붙은 건 중복 패키지여도 별도로 마지막에 재설치 
    dup_chk_set = set() 
    force_reinstall_list = [] 
    for step_name, requirements_list in extracted_requirements_dict.items(): 
        for pkg in requirements_list: 
            pkg_name = pkg.replace(" ", "") # 모든 공백 제거후, 비교 연산자, version 말고 패키지의 base name를 아래 조건문에서 구할 것임
            # force reinstall은 별도 저장 
            if "--force-reinstall" in pkg_name: 
                force_reinstall_list.append(pkg) # force reinstall 은 numpy==1.25.2--force-reinstall 처럼 붙여서 쓰면 인식못하므로 pkg_name이 아닌 pkg로 기입 
                dup_chk_set.add(pkg)
                continue 
            # 버전 및 주석 등을 제외한, 패키지의 base 이름 추출 
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
                
            # package명 위가 아니라 옆 쪽에 주석 달은 경우, 제거  
            if '#' in base_pkg_name: 
                base_pkg_name = base_pkg_name[ : base_pkg_name.index('#')]
            if '#' in pkg_name: 
                pkg_name = pkg_name[ : pkg_name.index('#')]
                                
            # ALO master 및 모든 asset들의 종속 패키지를 취합했을 때 버전 다른 중복 패키지 존재 시 먼저 진행되는 step(=asset)의 종속 패키지만 설치  
            if base_pkg_name in dup_chk_set: 
                print_color(f'>> Ignored installing << {pkg_name} >>. Another version will be installed in the previous step.', 'yellow')
            else: 
                dup_chk_set.add(base_pkg_name)
                dup_checked_requirements_dict[step_name].append(pkg_name)
    
    # force reinstall은 마지막에 한번 다시 설치 하기 위해 추가 
    dup_checked_requirements_dict['force-reinstall'] = force_reinstall_list
    
    # 패키지 설치 
    _install_packages(dup_checked_requirements_dict, dup_chk_set)

    return     

def _install_packages(dup_checked_requirements_dict, dup_chk_set): 
    total_num_install = len(dup_chk_set)
    count = 1
    # 사용자 환경에 priority_sorted_pkg_list의 각 패키지 존재 여부 체크 및 없으면 설치
    for step_name, package_list in dup_checked_requirements_dict.items(): # 마지막 step_name 은 force-reinstall 
        print_color(f"======================================== Start dependency installation : << {step_name} >> ", 'blue')
        for package in package_list:
            print_color(f'>> Start checking existence & installing package - {package} | Progress: ( {count} / {total_num_install} total packages )', 'yellow')
            count += 1
            
            if "--force-reinstall" in package: 
                try: 
                    print_color(f'- Start installing package - {package}', 'yellow')
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package.replace('--force-reinstall', '').strip(), '--force-reinstall'])            
                except OSError as e:
                    raise NotImplementedError(f"Error occurs while --force-reinstalling {package} ~ " + e)  
                continue 
                    
            try: # 이미 같은 버전 설치 돼 있는지 
                # [pkg_resources 관련 참고] https://stackoverflow.com/questions/44210656/how-to-check-if-a-module-is-installed-in-python-and-if-not-install-it-within-t 
                # 가령 aiplib @ git+http://mod.lge.com/hub/smartdata/aiplatform/module/aip.lib.git@ver2  같은 version 표기가 requirements.txt에 존재해도 conflict 안나는 것 확인 완료 
                # FIXME 사용자가 가령 pandas 처럼 (==version 없이) 작성하여도 아래 코드는 통과함 
                pkg_resources.get_distribution(package) # get_distribution tact-time 테스트: 약 0.001s
                print_color(f'- << {package} >> already exists', 'green')
            except pkg_resources.DistributionNotFound: # 사용자 가상환경에 해당 package 설치가 아예 안 돼있는 경우 
                try: # nested try/except 
                    print_color(f'- Start installing package - {package}', 'yellow')
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                except OSError as e:
                    # 가령 asset을 만든 사람은 abc.txt라는 파일 기반으로 pip install -r abc.txt 하고 싶었는데, 우리는 requirements.txt 라는 이름만 허용하므로 관련 안내문구 추가  
                    raise NotImplementedError(f"Error occurs while installing {package}. If you want to install from packages written file, make sure that your file name is << {fixed_txt_name} >> ~ " + e)
            except pkg_resources.VersionConflict: # 설치 돼 있지만 버전이 다른 경우 재설치 
                try: # nested try/except 
                    print_color(f'- VersionConflict occurs. Start re-installing package << {package} >>. You should check the dependency for the package among assets.', 'yellow')
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                except OSError as e:
                    raise NotImplementedError(f"Error occurs while re-installing {package} ~ " + e)  
            # FIXME 그 밖의 에러는 아래에서 그냥 에러 띄우고 프로세스 kill 
            # pkg_resources의 exception 참고 코드 : https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
            except pkg_resources.ResolutionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                raise NotImplementedError(f'ResolutionError occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')
            except pkg_resources.ExtractionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                raise NotImplementedError(f'ExtractionError occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')
            # FIXME 왜 unrechable 이지? https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
            except pkg_resources.UnknownExtra: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                raise NotImplementedError(f'UnknownExtra occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')   
            
    print_color(f"======================================== Finish dependency installation \n", 'blue')
    
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