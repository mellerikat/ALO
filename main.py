# python lib
import os
import sys
import time
import argparse
import logging

# local import
from common import Logger, print_color, find_matching_strings, asset_info, extract_requirements_txt, check_install_requirements, backup_artifacts, match_steps 
from datetime import datetime

# 현재 PROJECT PATH
PROJECT_HOME = os.path.dirname(os.path.realpath(__file__)) + "/"

# asset 코드들의 위치
# FIXME wj mnist, titanic example을 만들기 사용하는 함수 리스트를 작성
ASSET_HOME = PROJECT_HOME + "assets/"

SUPPORT_TYPE = ['memory', 'file']
# FIXME wj aiplib lib으로 이동 후 req에 추가
# FIXME ws 위에 프린트문 출력할 위치에 삽입 ?
# FIXME ws input artifacts 이름을 data로 변경 필수 ?

####################### ALO master requirements 리스트업 및 설치 #######################
# ALO master requirements 는 최우선 순위로 설치 > 만약 ALO master requirements는 aiplib v2.1인데 slave 제작자가 aiplib v2.2로 명시해놨으면 2.1이 우선 
req_list = extract_requirements_txt("master")
master_req = {"master": req_list}
check_install_requirements(master_req)
#######################################################################################

# import aiplib
from alolib.asset import Asset
# import alolib.common as common

class ALOv2(Asset):
    def __init__(self, exp_plan_file = "config/experimental_plan.yaml"):
        
        # TODO ALOv2 class 자체를 제거 하는게 필요함
        envs = {}
        envs['project_home'] = PROJECT_HOME

        super().__init__(envs=envs, argv=0, version=0.1)  # Asset 초기화
        # self.artifacts는 asset.Asset에서 정의 및 set
        # self.artifacts = self.asset.set_artifact(PROJECT_HOME, True, True)
        self.exp_plan_file = exp_plan_file
        self.exp_plan = None # get_yaml 할 때 채워짐 

        if 'STTIME' in os.environ:
            self.inference_start_time = os.environ['STTIME']
            print_color(self.inference_start_time, 'yellow')
        else:
            print_color('>> STTIME does not exist. Instead, get current time as << start time >>', 'yellow')
            current_time = datetime.now()
            # FIXME : inference_start_time이 아니라 alo start time 아닌가? 이 시간은 어디쓰이는 건지? 
            self.inference_start_time = current_time.strftime("%Y-%m-%d %H:%M:%S")

        # TODO 현재 ALO master 버전의 체크

    def runs(self):
        if not os.path.exists(ASSET_HOME):
            os.makedirs(ASSET_HOME)
            print_color(f">> Created << {ASSET_HOME} >> directory.", "green")
        else:
            print_color(f">> << {ASSET_HOME} >> directory already exists.", "green")
        
        # get_yaml 시 self.exp_plan 변수에 내용 dict로 채워짐 
        self.asset.get_yaml(PROJECT_HOME + self.exp_plan_file)
        self.external_path = self.asset.get_external_path()
        self.external_path_permission = self.asset.get_external_path_permission()
        self.pipelines_list = self.asset.get_pipeline() # asset source - dict(list(dict)) 
        self.user_parameters = self.asset.get_user_parameters()
        self.controls = self.asset.get_control()
        self.artifacts = self.asset.set_artifacts()
        # yaml의 user parameters과 asset source 간 step 명들 일치여부 체크 
        # FIXME multi pipeline 지원 시, pipeline name matching까지 추가개발 필요 
        match_steps(self.user_parameters, self.pipelines_list) 
        # pipe_mode : train, inference
        for pipe_mode in self.pipelines_list:
            print_color("\n================================================================================================================================================================================================================================================", "bold")
            print_color(f"                                                                                                        pipeline : < {pipe_mode} >                                                                                                             ", "bold")
            print_color("================================================================================================================================================================================================================================================\n", "bold")
            # 외부 데이터 다운로드 (input 폴더에) - 하나의 pipeline
            # FIXME self.asset.~ 이런 함수들 일단 common으로 다 빼고 리팩토링 필요할 듯 
            self.asset.external_load_data(pipe_mode, self.external_path, self.external_path_permission)
            matching_strings = find_matching_strings(list(self.artifacts.keys()), pipe_mode.split('_')[0])
            log_filename = self.artifacts[matching_strings] + "log/pipeline.log"
            logging.basicConfig(filename=log_filename, level=logging.INFO)

            logger = Logger(log_filename)
            sys.stdout = logger

            # scripts 폴더없으면 만들고 있으면 그냥 두고
            os.makedirs(PROJECT_HOME + "scripts/", exist_ok=True)
            self._run_import(pipe_mode)
            
            if self.control['backup_artifacts'] == True:
                backup_artifacts(pipe_mode, PROJECT_HOME + self.exp_plan_file)
            
            self.asset.external_save_artifacts(pipe_mode, self.external_path, self.external_path_permission)
            
            
    def _run_import(self, _pipe_num):
        # scripts 폴더에 폴더가 있는지 확인
        # folder_list = os.listdir(ASSET_HOME)
        # folder_list = [folder for folder in folder_list if os.path.isdir(os.path.join(ASSET_HOME, folder))]

        ####################### Slave Asset 설치 및 Slave requirements 리스트업 #######################
        requirements_dict = dict() 
        # setup asset (asset을 git clone (or local) 및 requirements 설치)
        get_asset_source = self.controls["get_asset_source"]  # once, every
        for step, asset_config in enumerate(self.pipelines_list[_pipe_num]):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴 
            self.asset.setup_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']
            # local 모드일 땐 이번 step(=asset)의 종속 package들이 내 환경에 깔려있는 지 항상 체크 후 없으면 설치 
            # git 모드일 땐 every이거나 once면서 첫 실행 시에만 requirements 설치 
        ####################### Master & Slave requirements 설치 #######################
        # 이미 asset (step) 폴더들은 input 폴더에 다 setup된 상태 
        # 각 asset의 yaml에 직접 작성 된 패키지들 + asset 내의 requirements.txt를 참고하여 쭉 리스트업 
        # asset 간 중복 패키지 존재 시 먼저 실행되는 pipeline, asset에 대해 우선순위 부여하여 설치되게끔   
        # 패키지 설치 중에 진행중인 asset 단계 표시 및 총 설치 중 몇번 째 설치인지 표시 > pipeline 별로는 별도로 진행 
        self.asset.check_install_requirements(requirements_dict) 
        for step, asset_config in enumerate(self.pipelines_list[_pipe_num]):    
            asset_info(_pipe_num, asset_config['step'])

            _path = ASSET_HOME + asset_config['step'] + "/"
            _file = "asset_" + asset_config['step']
            user_asset = self.asset.import_asset(_path, _file)

            if self.controls['interface_mode'] in SUPPORT_TYPE:
                # 첫 동작시에는 초기화하여 사용 
                if step == 0:
                    data = 0
                    config = {}
                else:
                    if self.controls['interface_mode'] == 'memory':
                        pass
                    elif self.controls['interface_mode'] == 'file':
                        data, config = self.asset.get_toss(_pipe_num, envs) # file interface
            else:
                return ValueError("only file and memory")
            
            args = self.user_parameters[_pipe_num][step]['args']
            # envs에 만들어진 artifacts 폴더 구조 전달 (to slave)
            # envs에 추후 artifacts 이외의 것들도 담을 가능성을 고려하여 dict구조로 생성
            envs = {}
            envs['project_home'] = PROJECT_HOME
            envs['pipeline'] = _pipe_num
            envs['step'] = self.user_parameters[_pipe_num][step]['step']
            envs['artifacts'] = self.artifacts

            ua = user_asset(envs, args[0], data, config) # mem interface
            data, config = ua.run()

            # config
            if self.controls['interface_mode'] == 'file':
                self.asset.toss(data, config, _pipe_num, envs) # file interface

            self.asset.release(_path)
            sys.path = [item for item in sys.path if envs['step'] not in item]

# --------------------------------------------------------------------------------------------------------------------------
#    MAIN
# --------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    # while(1):

    parser = argparse.ArgumentParser(description="exp yaml의 경로를 입력하세요(ex:)./config/experimental_plan.yaml")

    parser = argparse.ArgumentParser(description="특정 파일을 처리하는 스크립트")
    parser.add_argument("--config", type=str, default=0, help="config 옵션")
    parser.add_argument("--system", type=str, default="system", help="system 옵션")

    args = parser.parse_args()
    start_time = time.time()

    try:
        alo = ALOv2(exp_plan = args.config)  # exp plan path
    except:
        alo = ALOv2()  # exp plan path
    alo.runs()
    end_time = time.time()
    execution_time = end_time - start_time

    print_color(f"Total Program run-time: {execution_time} sec", 'yellow')
