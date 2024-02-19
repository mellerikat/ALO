# set up pipeline class
from collections import Counter

from src.constants import *
from src.assets import *
from src.logger import ProcessLogger

PROC_LOGGER = ProcessLogger(PROJECT_HOME)

class AssetStructure: 
    """Asset 의 In/Out 정보를 저장하는 Data Structure 입니다.

    Attributes:
        self.envs: ALO 가 파이프라인을 실행하는 환경 정보
        self.args: Asset 에서 처리하기 위한 사용자 변수 (experimental_plan 에 정의한 변수를 Asset 내부에서 사용)
            - string, integer, list, dict 타입 지원
        self.data: Asset 에서 사용될 In/Out 데이터 (Tabular 만 지원. 이종의 데이터 포맷은 미지원)
        self.config: Asset 들 사이에서 global 하게 shared 할 설정 값 (Asset 생성자가 추가 가능)
    """
    def __init__(self):
        self.envs = {}
        self.args = {}
        self.data = {} 
        self.config = {}

class Pipeline:
    # TODO ALO에 init한 class를 넘겨주면서 사용하는게 맞는건지 논의
    def __init__(self, system_envs, install, ext_data):
        self.system_envs = system_envs
        # TODO asset 에 대한 클래스는 pipeline에서만 사용 나중에 옮겨야 할지 논의
        self.asset = Assets(ASSET_HOME)
        self.install = install
        self.ext_data = ext_data

    
    def setup(self, pipe, experimental_plan):
        self._empty_artifacts(pipe)
        self._setup_asset(experimental_plan.asset_source[pipe], experimental_plan.control['get_asset_source'])
        self._set_asset_structure(experimental_plan)

    def load(self, pipe, experimental_plan):

        # TODO 분기 태우는 코드가 필요        
        if pipe == 'inference_pipeline':
            self.ext_data.external_load_model(experimental_plan.external_path, experimental_plan.external_path_permission)
        
        if self.system_envs['boot_on'] == False:  ## boot_on 시, skip
            # NOTE [중요] wrangler_dataset_uri 가 solution_metadata.yaml에 존재했다면,
            # 이미 _update_yaml할 때 exeternal load inference data path로 덮어쓰기 된 상태
            self.ext_data.external_load_data(pipe, experimental_plan.external_path, experimental_plan.external_path_permission, experimental_plan.control['get_external_data'])

    # 한번만 실행, 특정 에셋만 설치 할 수도 있음
    def _setup_asset(self, asset_source, get_asset_source):
        """asset 의 git clone 및 패키지를 설치 한다. 
        
        중복된 step 명이 있는지를 검사하고, 존재하면 Error 를 발생한다. 
        always-on 시에는 boot-on 시에만 설치 과정을 진행한다. 

        Args:
          - pipelne(str): train, inference 를 구분한다. 

        Raises:
          - step 명이 동일할 경우 에러 발생 
        """
        # setup asset (asset을 git clone (or local) 및 requirements 설치)
        # get_asset_source = control['get_asset_source']  # once, every

        # TODO 현재 pipeline에서 중복된 step 이 있는지 확인
        step_values = [item['step'] for item in asset_source]
        step_counts = Counter(step_values)
        for value, count in step_counts.items():
            if count > 1:
                PROC_LOGGER.process_error(f"Duplicate step exists: {value}")

        # 운영 무한 루프 구조일 땐 boot_on 시 에만 install 하고 이후에는 skip 
        if (self.system_envs['boot_on'] == False) and (self.system_envs['redis_host'] is not None):
            pass 
        else:
            return self._install_steps(asset_source, get_asset_source)
        
    def _set_asset_structure(self, experimental_plan):
        """Asset 의 In/Out 을 data structure 로 전달한다.
        파이프라인 실행에 필요한 환경 정보를 envs 에 setup 한다.
        """
        self.asset_structure = AssetStructure() 
        
        self.asset_structure.envs['project_home'] = PROJECT_HOME
        
        self.asset_structure.envs['solution_metadata_version'] = self.system_envs['solution_metadata_version']
        self.asset_structure.envs['artifacts'] = self.system_envs['artifacts']
        self.asset_structure.envs['alo_version'] = self.system_envs['alo_version']
        if experimental_plan.control['interface_mode'] not in INTERFACE_TYPES:
            self.proc_logger.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")
        self.asset_structure.envs['interface_mode'] = experimental_plan.control['interface_mode']
        self.asset_structure.envs['proc_start_time'] = self.system_envs['start_time']
        self.asset_structure.envs['save_train_artifacts_path'] = experimental_plan.external_path['save_train_artifacts_path']
        self.asset_structure.envs['save_inference_artifacts_path'] = experimental_plan.external_path['save_inference_artifacts_path']
    

    def _install_steps(self, asset_source, get_asset_source='once'):
        requirements_dict = dict() 
        for step, asset_config in enumerate(asset_source):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴 
            self.asset.setup_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']
        
        return self.install.check_install_requirements(requirements_dict) 
    
    
    def _empty_artifacts(self, pipeline): 
        '''
        - pipe_prefix: 'train', 'inference'
        - 주의: log 폴더는 지우지 않기 
        '''
        pipe_prefix = pipeline.split('_')[0]
        dir_artifacts = PROJECT_HOME + f".{pipe_prefix}_artifacts/"
        try: 
            for subdir in os.listdir(dir_artifacts): 
                if subdir == 'log':
                    continue 
                else: 
                    shutil.rmtree(dir_artifacts + subdir, ignore_errors=True)
                    os.makedirs(dir_artifacts + subdir)
                    PROC_LOGGER.process_info(f"Successfully emptied << {dir_artifacts + subdir} >> ")
        except: 
            PROC_LOGGER.process_error(f"Failed to empty & re-make << .{pipe_prefix}_artifacts >>")