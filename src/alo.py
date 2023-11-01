import os
import sys
import subprocess
from datetime import datetime
from collections import Counter
import pkg_resources
# local import
from src.constants import *
####################### ALO master requirements 리스트업 및 설치 #######################
# ALO master requirements 는 최우선 순위로 설치 > 만약 ALO master requirements는 aiplib v2.1인데 slave 제작자가 aiplib v2.2로 명시해놨으면 2.1이 우선 
try: 
    alo_ver = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    alolib_git = f'alolib @ git+http://mod.lge.com/hub/dxadvtech/aicontents-framework/alolib-source.git@{alo_ver}'
    try: 
        alolib_pkg = pkg_resources.get_distribution('alolib') # get_distribution tact-time 테스트: 약 0.001s
        alo_ver = '0' if alo_ver == 'develop' else alo_ver.split('-')[-1] # 가령 release-1.2면 1.2만 가져옴 
        if str(alolib_pkg.version) != str(alo_ver): 
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', alolib_git, '--force-reinstall']) # alo version과 같은 alolib 설치  
    except: # alolib 미설치 경우 
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', alolib_git, '--force-reinstall'])
except: 
    raise NotImplementedError('Failed to install << alolib >>')
#######################################################################################
from src.install import *
from src.utils import set_artifacts, get_yaml, setup_asset, match_steps, import_asset, release, backup_artifacts, remove_log_files
from src.external import external_load_data, external_save_artifacts
from alolib import logger  


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
        self.artifacts = None 
        self.proc_logger = None
        self.proc_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.alo_version = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
        
    def preset(self):
        if not os.path.exists(ASSET_HOME):
            try:
                os.makedirs(ASSET_HOME)
            except: 
                raise NotImplementedError(f"Failed to create directory: {ASSET_HOME}")
        self.read_yaml()
        # artifacts 세팅
        self.artifacts = set_artifacts()
        # step들이 잘 match 되게 yaml에 기술 돼 있는지 체크
        match_steps(self.user_parameters, self.asset_source)

    def external_load_data(self, pipeline, external_path, external_path_permission, control):
        external_load_data(pipeline, external_path, external_path_permission, control)

    def set_proc_logger(self):
        self.proc_logger = logger.ProcessLogger(PROJECT_HOME) 
    
    def runs(self):
        self.preset()
        print(self.artifacts)
        
        # FIXME setup process logger - 최소한 logging은 artifacts 폴더들이 setup 되고 나서부터 가능하다. (프로세스 죽더라도 .train (or inf) artifacts/log 경로에 저장하고 죽어야하니까)
        # envs (메타정보) 모르는 상태의, 큼직한 단위의 로깅은 process logging (인자 X)
        self.set_proc_logger()
        self.proc_logger.process_info(f"Process start-time: {self.proc_start_time}")
        for pipeline in self.asset_source:
            if pipeline not in ['train_pipeline', 'inference_pipeline']:
                raise ValueError(f'Pipeline name in the experimental_plan.yaml \n must be << train_pipeline >> or << inference_pipeline >>')

            self.external_load_data(pipeline, self.external_path, self.external_path_permission, self.control['get_external_data'])
            self.run_import(pipeline)

            if self.control['backup_artifacts'] == True:
                backup_artifacts(pipeline, self.exp_plan_file)
            
            external_save_artifacts(pipeline, self.external_path, self.external_path_permission)

        self.proc_finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.proc_logger.process_info(f"Process finish-time: {self.proc_finish_time}")
        
        # .log 파일 제거 (안그러면 다음 main.py run 시 로그가 파일에 누적됨)
        remove_log_files(self.artifacts)
        
        
    def read_yaml(self):
        self.exp_plan = get_yaml(self.exp_plan_file)
        compare_yaml = get_yaml(PROJECT_HOME + "config/compare.yaml")

        def compare_dict_keys(dict1, dict2): # inner func.
            keys1 = set(key for d in dict1 for key in d.keys())
            keys2 = set(key for d in dict2 for key in d.keys())

            keys_only_in_dict2 = keys2 - keys1

            if keys_only_in_dict2 == {'train_pipeline'} or keys_only_in_dict2 == {'inference_pipeline'}:
                pass
            elif keys_only_in_dict2:
                self.proc_logger.process_error(f"Missing keys in experimental_plan.yaml: {keys_only_in_dict2}")

        for key in self.exp_plan:
            compare_dict_keys(self.exp_plan[key], compare_yaml[key])

        def get_yaml_data(key): # inner func.
            data_dict = {}
            for data in self.exp_plan[key]:
                data_dict.update(data)
            return data_dict

        for key in self.exp_plan.keys():
            setattr(self, key, get_yaml_data(key))

    def install_steps(self, pipeline, get_asset_source):
        requirements_dict = dict() 
        for step, asset_config in enumerate(self.asset_source[pipeline]):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴 
            setup_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']
        
        check_install_requirements(requirements_dict)

    def run_import(self, pipeline):
        # setup asset (asset을 git clone (or local) 및 requirements 설치)
        get_asset_source = self.control["get_asset_source"]  # once, every

        # TODO 현재 pipeline에서 중복된 step 이 있는지 확인
        step_values = [item['step'] for item in self.asset_source[pipeline]]
        step_counts = Counter(step_values)
        for value, count in step_counts.items():
            if count > 1:
                self.proc_logger.process_error(f"Duplicate step exists: {value}")

        self.install_steps(pipeline, get_asset_source)
        
        # 최초 init 
        envs, args, data, config = {}, {}, {}, {}
        asset_structure = AssetStructure(envs, args, data, config)

        for step, asset_config in enumerate(self.asset_source[pipeline]):    
            self.proc_logger.process_info(f"==================== Start pipeline: {pipeline} / step: {asset_config['step']}")

            # 외부에서 arg를 가져와서 수정이 가능한 구조를 위한 구조
            asset_structure.args = self.get_args(pipeline, step)
            asset_structure = self.process_asset_step(asset_config, step, pipeline, asset_structure)

    def get_args(self, pipeline, step):
        if type(self.user_parameters[pipeline][step]['args']) == type(None):
            return dict()
        else:
            return self.user_parameters[pipeline][step]['args'][0]

    def process_asset_step(self, asset_config, step, pipeline, asset_structure): 
        # step: int 
        _path = ASSET_HOME + asset_config['step'] + "/"
        _file = "asset_" + asset_config['step']
        # asset2등을 asset으로 수정하는 코드
        _file = ''.join(filter(lambda x: x.isalpha() or x == '_', _file))
        user_asset = import_asset(_path, _file)

        if self.control['interface_mode'] not in INTERFACE_TYPES:
            self.proc_logger.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")

        asset_structure.config['artifacts'] = self.artifacts
        asset_structure.config['pipeline'] = pipeline
        # envs에 만들어진 artifacts 폴더 구조 전달 (to slave)
        # envs에 추후 artifacts 이외의 것들도 담을 가능성을 고려하여 dict구조로 생성
        # TODO 가변부 status는 envs에는 아닌듯 >> 성선임님 논의 
        asset_structure.envs['project_home'] = PROJECT_HOME
        asset_structure.envs['pipeline'] = pipeline
        # asset.py에서 load config, load data 할때 필요 
        if step > 0: 
            asset_structure.envs['prev_step'] = self.user_parameters[pipeline][step - 1]['step']
        asset_structure.envs['step'] = self.user_parameters[pipeline][step]['step']
        asset_structure.envs['num_step'] = step # int  
        asset_structure.envs['artifacts'] = self.artifacts
        asset_structure.envs['alo_version'] = self.alo_version
        asset_structure.envs['asset_branch'] = asset_config['source']['branch']
        asset_structure.envs['interface_mode'] = self.control['interface_mode']
            
        ua = user_asset(asset_structure) 
        asset_structure.data, asset_structure.config = ua.run()

        # FIXME memory release : on/off 필요 
        release(_path)
        sys.path = [item for item in sys.path if asset_structure.envs['step'] not in item]
        
        self.proc_logger.process_info(f"==================== Finish pipeline: {pipeline} / step: {asset_config['step']}")
        
        return asset_structure
        
