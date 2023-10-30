import os
import sys
import subprocess
from datetime import datetime
from collections import Counter
import pkg_resources
from src.constants import *
# local import
####################### ALO master requirements 리스트업 및 설치 #######################
# ALO master requirements 는 최우선 순위로 설치 > 만약 ALO master requirements는 aiplib v2.1인데 slave 제작자가 aiplib v2.2로 명시해놨으면 2.1이 우선 
try: 
    alo_ver = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    alolib_git = f'alolib @ git+http://mod.lge.com/hub/dxadvtech/aicontents-framework/alolib-source.git@{alo_ver}'
    try: 
        alolib_pkg = pkg_resources.get_distribution('alolib') # get_distribution tact-time 테스트: 약 0.001s
        if alolib_pkg.version != alo_ver: 
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', alolib_git, '--force-reinstall']) # alo version과 같은 alolib 설치  
    except: # alolib 미설치 경우 
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', alolib_git, '--force-reinstall'])
except: 
    raise NotImplementedError('Failed to install << alolib >>')

#######################################################################################
from src.install import *
from src.utils import set_artifacts, get_yaml, setup_asset, match_steps, find_matching_strings, import_asset, release, backup_artifacts
from src.external import external_load_data, external_save_artifacts
from alolib import logger  

####################### ALO master requirements 리스트업 및 설치 #######################
# ALO master requirements 는 최우선 순위로 설치 > 만약 ALO master requirements는 aiplib v2.1인데 slave 제작자가 aiplib v2.2로 명시해놨으면 2.1이 우선 

# req_list = extract_requirements_txt("master")
# master_req = {"master": req_list}
# check_install_requirements(master_req)



class AssetStructure: 
    def __init__(self, envs, args, data, config):
        self.envs = envs
        self.args = args
        self.data = data 
        self.config = config
        
        
class ALO:
    def __init__(self, exp_plan_file = EXP_PLAN):
        self.exp_plan_file = exp_plan_file
        self.exp_plan = None
        self.proc_logger = None
        self.proc_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def runs(self):
        if not os.path.exists(ASSET_HOME):
            try:
                os.makedirs(ASSET_HOME)
            except: 
                raise NotImplementedError(f"Failed to create directory: {ASSET_HOME}")
        # yaml에 있는 내용들 self.control 등 클래스 파라미터로 setting  
        self.read_yaml()
        # artifacts 세팅
        self.artifacts = set_artifacts()
        # FIXME setup process logger - 최소한 logging은 artifacts 폴더들이 setup 되고 나서부터 가능하다. (프로세스 죽더라도 .train (or inf) artifacts/log 경로에 저장하고 죽어야하니까)
        # envs (메타정보) 모르는 상태의, 큼직한 단위의 로깅은 process logging (인자 X)
        self.proc_logger = logger.ProcessLogger(PROJECT_HOME) 
        self.proc_logger.process_info(f"Process start-time: {self.proc_start_time}")
    
        match_steps(self.user_parameters, self.asset_source) 

        for pipeline in self.asset_source:
            if pipeline not in ['train_pipeline', 'inference_pipeline']:
                raise ValueError(f'Pipeline name in the experimental_plan.yaml \n must be << train_pipeline >> or << inference_pipeline >>')
            
            external_load_data(pipeline, self.external_path, self.external_path_permission, self.control['get_external_data'])

            self._run_import(pipeline)

            if self.control['backup_artifacts'] == True:
                backup_artifacts(pipeline, self.exp_plan_file)
            
            external_save_artifacts(pipeline, self.external_path, self.external_path_permission)

        self.proc_finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.proc_logger.process_info(f"Process finish-time: {self.proc_finish_time}")
        
    def read_yaml(self):
        self.exp_plan = get_yaml(self.exp_plan_file)
        compare_yaml = get_yaml(PROJECT_HOME + "config/compare.yaml")

        def compare_dict_keys(dict1, dict2):
            keys1 = set(key for d in dict1 for key in d.keys())
            keys2 = set(key for d in dict2 for key in d.keys())
            keys_only_in_dict2 = keys2 - keys1
            if keys_only_in_dict2:
                self.proc_logger.process_error(f"Missing keys in experimental_plan.yaml: {keys_only_in_dict2}")

        for key in self.exp_plan:
            compare_dict_keys(self.exp_plan[key], compare_yaml[key])

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
                self.proc_logger.process_error(f"Duplicate step exists: {value}")

        for step, asset_config in enumerate(self.asset_source[pipeline]):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴 
            setup_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']
        
        check_install_requirements(requirements_dict)
        
        for step, asset_config in enumerate(self.asset_source[pipeline]):    
            self.proc_logger.process_info(f"==================== Start pipeline: {pipeline} / step: {asset_config['step']}")

            _path = ASSET_HOME + asset_config['step'] + "/"
            _file = "asset_" + asset_config['step']
            # asset2등을 asset으로 수정하는 코드
            _file = ''.join(filter(lambda x: x.isalpha() or x == '_', _file))
            user_asset = import_asset(_path, _file)

            if self.control['interface_mode'] in INTERFACE_TYPES:
                # 첫 동작시에는 초기화하여 사용 
                if step == 0:
                    data, envs, config  = {}, {}, {}
            else:
                self.proc_logger.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")
                
            args = self.user_parameters[pipeline][step]['args']
            # envs에 만들어진 artifacts 폴더 구조 전달 (to slave)
            # envs에 추후 artifacts 이외의 것들도 담을 가능성을 고려하여 dict구조로 생성
            # TODO 가변부 status는 envs에는 아닌듯 >> 성선임님 논의 
            envs['project_home'] = PROJECT_HOME
            envs['pipeline'] = pipeline
            # asset.py에서 load config, load data 할때 필요 
            if step > 0: 
                envs['prev_step'] = self.user_parameters[pipeline][step - 1]['step']
            envs['step'] = self.user_parameters[pipeline][step]['step']
            envs['num_step'] = step # int  
            envs['artifacts'] = self.artifacts

            alo_version = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=subprocess.PIPE)
            envs['alo_version'] = alo_version.stdout.decode('utf-8').strip()
            envs['asset_branch'] = asset_config['source']['branch']
            envs['interface_mode'] = self.control['interface_mode']
            
            asset_structure = AssetStructure(envs, args[0], data, config)
            ua = user_asset(asset_structure) # mem interface
            data, config = ua.run()

            # FIXME memory release : on/off 필요 
            release(_path)
            sys.path = [item for item in sys.path if envs['step'] not in item]
        
            self.proc_logger.process_info(f"==================== Finish pipeline: {pipeline} / step: {asset_config['step']}")
        
