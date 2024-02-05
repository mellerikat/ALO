import pkg_resources
import os
import subprocess
import sys
import yaml 
from collections import defaultdict
from src.logger import ProcessLogger 
from src.constants import *

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)

#--------------------------------------------------------------------------------------------------------------------------

class Packages:
    def __init__(self):
        pass
    
    def set_alolib(self):
        """ALO 는 Master (파이프라인 실행) 와 slave (Asset 실행) 로 구분되어 ALO API 로 통신합니다. 
        기능 업데이트에 따라 API 의 버전 일치를 위해 Master 가 slave 의 버전을 확인하여 최신 버전으로 설치 되도록 강제한다.
        
        """
        # TODO 버전 mis-match 시, git 재설치하기. (미존재시, 에러 발생 시키기)
        if not os.path.exists(PROJECT_HOME + 'alolib'): 
            ALOMAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cmd = f'cd {ALOMAIN} && git symbolic-ref --short HEAD'
            result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
            ALOVER = result.stdout.decode('utf-8').strip()
            repository_url = ALO_LIB_URI
            destination_directory = ALO_LIB
            result = subprocess.run(['git', 'clone', '-b', ALOVER, repository_url, destination_directory], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                print("alolib git pull success.")
            else:
                raise NotImplementedError("alolib git pull failed.")
        else: 
            print("alolib already exists in local path.")
            pass
        alolib_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/alolib/"
        sys.path.append(alolib_path)
        
        req = os.path.join(alolib_path, "requirements.txt")
        result = subprocess.run(['pip', 'install', '-r', req], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("패키지 설치 성공")
            print(result.stdout)
            return True
        else:
            print("패키지 설치 실패")
            print(result.stderr)
            return False

    def extract_requirements_txt(self, step_name): 
        """ Description
            -----------
                - master 혹은 각 asset (=slave) 내의 requirements.txt가 존재 시 내부에 작성된 패키지들을 list로 추출 
            Parameters
            -----------
                - step_name: assets 밑에 설치될 asset 이름 
            Return
            -----------
                - 
            Example
            -----------
                - extract_req_txt(step_name)
        """
        fixed_txt_name  = 'requirements.txt'
        packages_in_txt = []

        if fixed_txt_name in os.listdir(ASSET_HOME + step_name):
            with open(ASSET_HOME + step_name + '/' + fixed_txt_name, 'r') as req_txt:  
                for pkg in req_txt: 
                    pkg = pkg.strip() # Remove the newline character at the end of the line (=package)
                    packages_in_txt.append(pkg)
            return packages_in_txt
        else: 
            PROC_LOGGER.process_error(f"<< {fixed_txt_name} >> dose not exist in << assets/{step_name} folder >>. \n \
                However, you have written {fixed_txt_name} at that step in << config/experimental_plan.yaml >>. \n \
                Please remove {fixed_txt_name} in the yaml file.")

    def _install_packages(self, dup_checked_requirements_dict, dup_chk_set): 
        fixed_txt_name  = 'requirements.txt'

        total_num_install = len(dup_chk_set)
        count = 1
        # 사용자 환경에 priority_sorted_pkg_list의 각 패키지 존재 여부 체크 및 없으면 설치
        for step_name, package_list in dup_checked_requirements_dict.items(): # 마지막 step_name 은 force-reinstall 
            PROC_LOGGER.process_info(f"======================================== Start dependency installation : << {step_name} >> ")
            for package in package_list:
                PROC_LOGGER.process_info(f"Start checking existence & installing package - {package} | Progress: ( {count} / {total_num_install} total packages ) ")
                count += 1
                
                if "--force-reinstall" in package: 
                    try: 
                        PROC_LOGGER.process_info(f'>>> Start installing package - {package}')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package.replace('--force-reinstall', '').strip(), '--force-reinstall'])            
                    except OSError as e:
                        PROC_LOGGER.process_error(f"Error occurs while --force-reinstalling {package} ~ " + e)  
                    continue 
                        
                try: # 이미 같은 버전 설치 돼 있는지 
                    # [pkg_resources 관련 참고] https://stackoverflow.com/questions/44210656/how-to-check-if-a-module-is-installed-in-python-and-if-not-install-it-within-t 
                    # 가령 aiplib @ git+http://mod.lge.com/hub/smartdata/aiplatform/module/aip.lib.git@ver2  같은 version 표기가 requirements.txt에 존재해도 conflict 안나는 것 확인 완료 
                    # FIXME 사용자가 가령 pandas 처럼 (==version 없이) 작성하여도 아래 코드는 통과함 
                    pkg_resources.get_distribution(package) # get_distribution tact-time 테스트: 약 0.001s
                    PROC_LOGGER.process_info(f'[OK] << {package} >> already exists')
                except pkg_resources.DistributionNotFound: # 사용자 가상환경에 해당 package 설치가 아예 안 돼있는 경우 
                    try: # nested try/except 
                        PROC_LOGGER.process_info(f'>>> Start installing package - {package}')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                    except OSError as e:
                        # 가령 asset을 만든 사람은 abc.txt라는 파일 기반으로 pip install -r abc.txt 하고 싶었는데, 우리는 requirements.txt 라는 이름만 허용하므로 관련 안내문구 추가  
                        PROC_LOGGER.process_error(f"Error occurs while installing {package}. If you want to install from packages written file, make sure that your file name is << {fixed_txt_name} >> ~ " + e)
                except pkg_resources.VersionConflict: # 설치 돼 있지만 버전이 다른 경우 재설치 
                    try: # nested try/except 
                        PROC_LOGGER.process_warning(f'VersionConflict occurs. Start re-installing package << {package} >>. \n You should check the dependency for the package among assets.')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                    except OSError as e:
                        PROC_LOGGER.process_error(f"Error occurs while re-installing {package} ~ " + e)  
                # FIXME 그 밖의 에러는 아래에서 그냥 에러 띄우고 프로세스 kill 
                # pkg_resources의 exception 참고 코드 : https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
                except pkg_resources.ResolutionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                    PROC_LOGGER.process_error(f'ResolutionError occurs while installing package {package} @ {step_name} step. \n Please check the package name or dependency with other asset.')
                except pkg_resources.ExtractionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                    PROC_LOGGER.process_error(f'ExtractionError occurs while installing package {package} @ {step_name} step. \n Please check the package name or dependency with other asset.')
                # # FIXME 왜 unrechable 이지? https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
                # except pkg_resources.UnknownExtra: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                #     PROC_LOGGER.process_error(f'UnknownExtra occurs while installing package {package} @ {step_name} step. \n Please check the package name or dependency with other asset.')   
                
        PROC_LOGGER.process_info(f"======================================== Finish dependency installation \n")
        
        return 

    ## FIXME 사용자 환경의 패키지 설치 여부를 매 실행마다 체크하는 것을 on, off 하는 기능이 필요할 지?   
    # FIXME aiplib @ git+http://mod.lge.com/hub/smartdata/aiplatform/module/aip.lib.git@ver2 같은 이름은 아예 미허용 
    def check_install_requirements(self, requirements_dict):
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
        # 2. experimental_plan.yaml에 requirements.txt가 기입 돼 있다면 먼저 assets 폴더 내 해당 asset 폴더 밑에 requirements.txt가 존재하는 지 확인 (없으면 에러)
        # 3. 만약 이미 설치돼 있는 패키지 중 버전이 달라서 재설치 하는 경우는 (pandas==3.4 & pandas==3.2) PROC_LOGGER.process_info로 사용자 notify  
        fixed_txt_name = 'requirements.txt'

        # 어떤 step에 requirements.txt가 존재하면, assets/asset폴더 내에 txt파일 존재유무 확인 후 그 내부에 기술된 패키지들을 추출  
        extracted_requirements_dict = dict() 
        for step_name, requirements_list in requirements_dict.items(): 
            # yaml의 requirements에 requirements.txt를 적었다면, 해당 step 폴더에 requirements.txt가 존재하는 지 확인하고 존재한다면 내부에 작성된 패키지 명들을 추출하여 아래 loop에서 check & install 수행 
            if fixed_txt_name in requirements_list:
                requirements_txt_list = self.extract_requirements_txt(step_name)
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
                    PROC_LOGGER.process_info(f'>>> Ignored installing << {pkg_name} >>. Another version would be installed in the previous step.')
                else: 
                    dup_chk_set.add(base_pkg_name)
                    dup_checked_requirements_dict[step_name].append(pkg_name)
        
        # force reinstall은 마지막에 한번 다시 설치 하기 위해 추가 
        dup_checked_requirements_dict['force-reinstall'] = force_reinstall_list
        
        # 패키지 설치 
        self._install_packages(dup_checked_requirements_dict, dup_chk_set)

        return dup_checked_requirements_dict

class AssetSetup:
    def __init__():
        pass