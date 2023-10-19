import os
import sys
import logging

# local import

from src.install import *
from src.message import print_color
from datetime import datetime

from collections import Counter

from src.constants import *


# # 현재 PROJECT PATH
# PROJECT_HOME = os.path.dirname(os.path.abspath(os.path.dirname(__file__))) + "/"

# # experimental plan yaml의 위치
# EXP_PLAN = PROJECT_HOME + "config/experimental_plan.yaml"

# # asset 코드들의 위치
# # FIXME wj mnist, titanic example을 만들기 사용하는 함수 리스트를 작성
# ASSET_HOME = PROJECT_HOME + "assets/"

# INPUT_DATA_HOME = PROJECT_HOME + "input/"

SUPPORT_TYPE = ['memory', 'file']
# FIXME wj aiplib lib으로 이동 후 req에 추가
# FIXME ws 위에 프린트문 출력할 위치에 삽입
# FIXME ws input artifacts 이름을 data로 변경

####################### ALO master requirements 리스트업 및 설치 #######################
# ALO master requirements 는 최우선 순위로 설치 > 만약 ALO master requirements는 aiplib v2.1인데 slave 제작자가 aiplib v2.2로 명시해놨으면 2.1이 우선 
req_list = extract_requirements_txt("master")
master_req = {"master": req_list}
check_install_requirements(master_req)
#######################################################################################

from src.utils import Logger, set_artifacts, get_yaml, setup_asset, match_steps, find_matching_strings, import_asset, release, compare_yaml_dicts, backup_artifacts
from src.external import external_load_data, external_save_artifacts
from src.message import asset_info, asset_error
class ALO:
    def __init__(self, exp_plan_file = EXP_PLAN):
        envs = {}
        envs['project_home'] = PROJECT_HOME

        self.exp_plan_file = exp_plan_file
        self.exp_plan = None

        if 'STTIME' in os.environ:
            self.inference_start_time = os.environ['STTIME']
            print(self.inference_start_time)
        else:
            print('STTIME does not exist. instead get current time')
            current_time = datetime.now()
            self.inference_start_time = current_time.strftime("%Y-%m-%d %H:%M:%S")

    def runs(self):
        
        if not os.path.exists(ASSET_HOME):
            os.makedirs(ASSET_HOME)
            print_color(f">> Created << {ASSET_HOME} >> directory.", "green")
        else:
            print_color(f">> << {ASSET_HOME} >> directory already exists.", "green")

        self.read_yaml()

        # artifacts 세팅
        self.artifacts = set_artifacts()
        
        match_steps(self.user_parameters, self.asset_source)  # match_steps(self.user_parameters, self.pipelines_list) 

        for pipeline in self.asset_source:
            print_color("\n===============================================================================================================================", "bold")
            print_color(f"                                                 pipeline : < {pipeline} >                                                 ", "bold")
            print_color("===============================================================================================================================\n", "bold")
            # 외부 데이터 다운로드 (input 폴더에) - 하나의 pipeline
            # FIXME self.asset.~ 이런 함수들 일단 common으로 다 빼고 리팩토링 필요할 듯 
            external_load_data(pipeline, self.external_path, self.external_path_permission)
            matching_strings = find_matching_strings(list(self.artifacts.keys()), pipeline.split('_')[0])
            log_filename = self.artifacts[matching_strings] + "log/pipeline.log"
            logging.basicConfig(filename=log_filename, level=logging.INFO)

            logger = Logger(log_filename)
            sys.stdout = logger

            self._run_import(pipeline)

            if self.control['backup_artifacts'] == True:
                backup_artifacts(pipeline, self.exp_plan_file)
            
            external_save_artifacts(pipeline, self.external_path, self.external_path_permission)

    def read_yaml(self):
        self.exp_plan = get_yaml(self.exp_plan_file)
        yaml_v2_11 = get_yaml(PROJECT_HOME + "config/temp.yaml")

        # TODO dict로 되어 있는 경우 yaml과 비교를 할 수 있는지 확인, 추가로 어떻게 할지 확인
        compare_yaml_dicts(yaml_v2_11, self.exp_plan)

        def get_yaml_data(key):
            data_dict = {}
            for data in self.exp_plan[key]:
                data_dict.update(data)
            return data_dict

        for key in self.exp_plan.keys():
            setattr(self, key, get_yaml_data(key))

    def _run_import(self, pipeline):
        ####################### Slave Asset 설치 및 Slave requirements 리스트업 #######################
        requirements_dict = dict() 
        # setup asset (asset을 git clone (or local) 및 requirements 설치)
        get_asset_source = self.control["get_asset_source"]  # once, every

        # TODO 현재 pipeline에서 중복된 step 이 있는지 확인
        step_values = [item['step'] for item in self.asset_source[pipeline]]
        step_counts = Counter(step_values)
        for value, count in step_counts.items():
            if count > 1:
                asset_error(f"Duplicate value found: {value}")

        for step, asset_config in enumerate(self.asset_source[pipeline]):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴 
            setup_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']
        
        check_install_requirements(requirements_dict)
        
        for step, asset_config in enumerate(self.asset_source[pipeline]):    
            asset_info(pipeline, asset_config['step'])

            _path = ASSET_HOME + asset_config['step'] + "/"
            _file = "asset_" + asset_config['step']
            # TODO asset2등을 asset으로 수정하는 코드
            _file = ''.join(filter(lambda x: x.isalpha() or x == '_', _file))
            user_asset = import_asset(_path, _file)
            envs = {}

            if self.control['interface_mode'] in SUPPORT_TYPE:
                # 첫 동작시에는 초기화하여 사용 
                if step == 0:
                    data = 0
                    config = {}
                else:
                    if self.control['interface_mode'] == 'memory':
                        pass
                    elif self.control['interface_mode'] == 'file':
                        data, config = get_toss(pipeline, envs) # file interface
            else:
                return ValueError("only file and memory")

            args = self.user_parameters[pipeline][step]['args']
            # envs에 만들어진 artifacts 폴더 구조 전달 (to slave)
            # envs에 추후 artifacts 이외의 것들도 담을 가능성을 고려하여 dict구조로 생성
            
            envs['project_home'] = PROJECT_HOME
            envs['pipeline'] = pipeline
            envs['step'] = self.user_parameters[pipeline][step]['step']
            envs['artifacts'] = self.artifacts

            ua = user_asset(envs, args[0], data, config) # mem interface
            data, config = ua.run()

            # config
            if self.control['interface_mode'] == 'file':
                toss(data, config, pipeline, envs) # file interface

            release(_path)
            sys.path = [item for item in sys.path if envs['step'] not in item]
        
        
