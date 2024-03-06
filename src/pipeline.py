# set up pipeline class
import hashlib
import importlib
import inspect
import sys
import os
import re
from datetime import datetime
import shutil
from typing import Dict, List, Tuple, Union, Optional, Any
from collections import Counter
import git
import json

from src.constants import *
# from src.assets import *
from src.install import Packages
from src.external import ExternalHandler
from src.logger import ProcessLogger
from src.artifacts import Aritifacts

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
    # def __init__(self, experiment_plan: Dict, skip_mode: Dict, pipeline_type: str, redis: bool, system_envs: Dict ):
    def __init__(self, experiment_plan: Dict, pipeline_type: str, system_envs: Dict ):
        # self.experiment_plan = experiment_plan
        if not os.path.exists(ASSET_HOME):
            try:
                os.makedirs(ASSET_HOME)
            except:
                PROC_LOGGER.process_error(f"Failed to create directory: {ASSET_HOME}")

        self.pipeline_type = pipeline_type
        self.system_envs = system_envs

        # TODO ALO 에 대한 클래스는 pipeline에서만 사용 나중에 옮겨야 할지 논의
        self.install = Packages()
        self.external = ExternalHandler()
        self.asset_structure = AssetStructure()
        self.artifact = Aritifacts()

        def get_yaml_data(key, pipeline_type = 'all'): # inner func.
            data_dict = {}
            if key == "name":
                return
            if key == "version":
                return
            for data in experiment_plan[key]:
                data_dict.update(data)

            if 'train_pipeline' in data_dict and 'inference_pipeline' in data_dict:
                if pipeline_type == 'train_pipeline':
                    remove_key = 'inference_pipeline'
                    del data_dict[remove_key]
                else:
                    remove_key = 'train_pipeline'
                    del data_dict[remove_key]

            return data_dict

        # 각 key 별 value 클래스 self 변수화 --> ALO init() 함수에서 ALO 내부변수로 넘김
        values = {}
        for key, value in experiment_plan.items():
            setattr(self, key, get_yaml_data(key, pipeline_type))

    def setup(self):
        self._empty_artifacts(self.pipeline_type)
        _, packs, = self._setup_asset(self.asset_source[self.pipeline_type], self.control['get_asset_source'])
        self._set_asset_structure()

        self._create_package(packs)

        # TODO return 구성
        # return

    def load(self):

        # TODO 분기 태우는 코드가 필요
        if self.pipeline_type == 'inference_pipeline':
            if (self.external_path['load_model_path'] != None) and (self.external_path['load_model_path'] != ""):
                self.external.external_load_model(self.external_path, self.external_path_permission)

        if self.system_envs['boot_on'] == False:  ## boot_on 시, skip
            # NOTE [중요] wrangler_dataset_uri 가 solution_metadata.yaml에 존재했다면,
            # 이미 _update_yaml할 때 exeternal load inference data path로 덮어쓰기 된 상태
            data_checksums = self.external.external_load_data(self.pipeline_type, self.external_path, self.external_path_permission, self.control['get_external_data'])

            # v2.3.0 NEW: 실험 history 를 위한 data_id 생성
            type = self.pipeline_type.split('_')[0]
            self.system_envs[f'{type}_history'] = data_checksums


        # TODO return 구성
        # return



    def run(self, steps = 'All'):
        if steps == 'All':
            for step, asset_config in enumerate(self.asset_source[self.pipeline_type]):
                PROC_LOGGER.process_info(f"==================== Start pipeline: {self.pipeline_type} / step: {asset_config['step']}")
                self.asset_structure.args[asset_config['step']] = self.get_parameter(asset_config['step'])
                try:
                    self.process_asset_step(asset_config, step)
                except:
                    PROC_LOGGER.process_error(f"Failed to process step: << {asset_config['step']} >>")
        else:
            if type(steps) == list:
                for step in steps:
                    PROC_LOGGER.process_info(f"==================== Start pipeline: {self.pipeline_type} / step: {step}")
                    self.asset_structure.args[step] = self.get_parameter(step)
                    for i, asset_configs in enumerate(self.asset_source[self.pipeline_type]):
                        if asset_configs['step'] == step:
                            asset_config = asset_configs
                            break
                        else:
                            continue
                    try:
                        self.process_asset_step(asset_config, i)
                    except:
                        PROC_LOGGER.process_error(f"Failed to process step: << {step} >>")
                        continue
            else:
                PROC_LOGGER.process_info(f"==================== Start pipeline: {self.pipeline_type} / step: {steps}")
                self.asset_structure.args[steps] = self.get_parameter(steps)
                step = 0
                for i, asset_configs in enumerate(self.asset_source[self.pipeline_type]):
                    if asset_configs['step'] == steps:
                        asset_config = asset_configs
                        step = i
                        break
                    else:
                        continue
                try:
                    self.process_asset_step(asset_config, step)
                except:
                    PROC_LOGGER.process_error(f"Failed to process step: << {steps} >>")
        
        ## v2.3.0 NEW: param_id 생성 
        params = self.user_parameters[self.pipeline_type]
        type = self.pipeline_type.split('_')[0]
        self.system_envs[f'{type}_history']['param_id'] = self._parameter_checksum(params)
        
        ## v2.3.0 NEW: code id 생성
        total_checksum = hashlib.md5()
        checksum_dict = {}
        for i, asset_config in enumerate(self.asset_source[self.pipeline_type]):
            _path = ASSET_HOME + asset_config['step'] + "/"
            checksum = self._code_checksum(_path)
            checksum_dict[asset_config['step']] = checksum

            # 폴더별 checksum을 문자열로 변환 후 total_checksum 업데이트
            total_checksum.update(str(checksum).encode())

        # 최종 total_checksum을 64비트 정수로 변환
        total_checksum = int(total_checksum.hexdigest(), 16) & ((1 << 64) - 1)
        self.system_envs[f'{type}_history']['code_id_description'] = checksum_dict
        self.system_envs[f'{type}_history']['code_id'] = total_checksum


    def save(self):

        ###################################
        ## Step7: summary yaml, output 정상 생성 체크
        ###################################
        if (self.pipeline_type == 'inference_pipeline') and (self.system_envs['boot_on'] == False):
            self._check_output()

        # 추론 output 생성이 완료 됐다는 성공 msg를 edgeapp으로 전송
        if self.system_envs['loop'] and (self.system_envs['boot_on'] == False):
            self.system_envs['success_str'] = self._send_summary()

        ###################################
        ## Step8: Artifacts 저장
        ###################################
        if self.system_envs['boot_on'] == False:
            # save_artifacts 내에도 edgeapp redis 전송 있음
            self._save_artifacts()

        ###################################
        ## Step9: Artifacts 를 history 에 backup
        ###################################
        if self.control['backup_artifacts'] == True:
            try:
                self.artifact.backup_history(self.pipeline_type, self.system_envs['experimental_plan'], self.system_envs['pipeline_start_time'], size=self.control['backup_size'])
            except:
                PROC_LOGGER.process_error("Failed to backup artifacts into << .history >>")

    def _parameter_checksum(self, params):
        # params를 문자열로 변환하여 해시 입력값으로 사용
        # 여기서는 params가 문자열이라고 가정합니다. 실제 사용 시 params를 적절히 변환해야 할 수 있습니다.
        params_str = str(params)
        # hashlib을 사용해 params_str의 해시 계산
        checksum = hashlib.sha256(params_str.encode('utf-8'))
        # 해시 객체에서 hexdigest 메소드를 호출하여 16진수 해시 문자열 얻기
        hexdigest_str = checksum.hexdigest()
        # 16진수 문자열을 정수로 변환하고, 64비트로 제한
        return int(hexdigest_str, 16) & ((1 << 64) - 1)

    def _code_checksum(self,folder_path):
        """폴더 내 모든 Python 파일들의 내용 기반으로 checksum을 계산합니다."""
        checksum = hashlib.md5()
        # 폴더를 순회하며 모든 .py 파일들에 대해 작업 수행
        for root, dirs, files in os.walk(folder_path):
            for file in sorted(files):
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    # 파일 내용을 읽고 checksum 업데이트
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            checksum.update(chunk)
    
        # 최종적인 checksum을 64비트 정수로 변환
        return int(checksum.hexdigest(), 16) & ((1 << 64) - 1)


    def _check_output(self):
        """inference_summary.yaml 및 output csv / image 파일 (jpg, png, svg) 정상 생성 체크
            csv 및 image 파일이 각각 1개씩만 존재해야 한다.
        Args:
          -
        """
        # check inference summary
        if "inference_summary.yaml" in os.listdir(INFERENCE_SCORE_PATH):
            PROC_LOGGER.process_info(f"[Success] << inference_summary.yaml >> exists in the inference score path: << {INFERENCE_SCORE_PATH} >>")
        else:
            PROC_LOGGER.process_error(f"[Failed] << inference_summary.yaml >> does not exist in the inference score path: << {INFERENCE_SCORE_PATH} >>")
        # check output files
        output_files = []
        for file_path in os.listdir(INFERENCE_OUTPUT_PATH):
        # check if current file_path is a file
            if os.path.isfile(os.path.join(INFERENCE_OUTPUT_PATH, file_path)):
                # add filename to list
                output_files.append(file_path)
        if len(output_files) == 1:
            if os.path.splitext(output_files[0])[-1] not in TABULAR_OUTPUT_FORMATS + IMAGE_OUTPUT_FORMATS:
                PROC_LOGGER.process_error(f"[Failed] output file extension must be one of << {TABULAR_OUTPUT_FORMATS + IMAGE_OUTPUT_FORMATS} >>. \n Your output: {output_files}")
        elif len(output_files) == 2:
            output_extension = set([os.path.splitext(i)[-1] for i in output_files]) # must be {'.csv', '.jpg' (or other image ext)}
            allowed_extensions = [set(TABULAR_OUTPUT_FORMATS + [i]) for i in IMAGE_OUTPUT_FORMATS]
            if output_extension not in allowed_extensions:
                PROC_LOGGER.process_error(f"[Failed] output files extension must be one of << {allowed_extensions} >>. \n Your output: {output_files}")
        else:
            PROC_LOGGER.process_error(f"[Failed] the number of output files must be 1 or 2. \n Your output: {output_files}")

    def _send_summary(self):
        """save artifacts가 완료되면 OK를 redis q로 put. redis q는 _update_yaml 이미 set 완료
        solution meta 존재하면서 (운영 모드) &  redis host none아닐때 (edgeapp 모드 > AIC 추론 경우는 아래 코드 미진입) & boot-on이 아닐 때 & inference_pipeline 일 때 save_summary 먼저 반환 필요
        외부 경로로 잘 artifacts 복사 됐나 체크 (edge app에선 고유한 경로로 항상 줄것임)

        Args:
          - success_str(str): 완료 메시지
          - ext_saved_path(str): 외부 경로
        """
        success_str = None
        summary_dir = INFERENCE_SCORE_PATH
        if 'inference_summary.yaml' in os.listdir(summary_dir):
            summary_dict = self.experimental_plan.get_yaml(summary_dir + 'inference_summary.yaml')
            success_str = json.dumps({'status':'success', 'message': summary_dict})
            self.system_envs['q_inference_summary'].rput(success_str)
            PROC_LOGGER.process_info("Successfully completes putting inference summary into redis queue.")
            self.system_envs['runs_status'] = 'summary'
        else:
            PROC_LOGGER.process_error("Failed to redis-put. << inference_summary.yaml >> not found.")
        return success_str

    def _save_artifacts(self):
        """파이프라인 실행 시 생성된 결과물(artifacts) 를 ./*_artifacts/ 에 저장한다.
        always-on 모드에서는 redis 로 inference_summary 결과를 Edge App 으로 전송한다.

        만약, 외부로 결과물 저장 설정이 되있다면, local storage 또는 S3 로 결과값 저장한다.
        """
        # s3, nas 등 외부로 artifacts 압축해서 전달 (복사)
        try:
            ext_saved_path = self.external.external_save_artifacts(self.pipeline_type, self.external_path, self.external_path_permission)
        except:
            PROC_LOGGER.process_error("Failed to save artifacts into external path.")
        # 운영 추론 모드일 때는 redis로 edgeapp에 artifacts 생성 완료 전달
        if self.system_envs['loop']:
            if 'inference_artifacts.tar.gz' in os.listdir(ext_saved_path): # 외부 경로 (= edgeapp 단이므로 무조건 로컬경로)
                # send_summary에서 생성된 summary yaml을 다시 한번 전송
                self.system_envs['q_inference_artifacts'].rput(self.system_envs['success_str'])
                PROC_LOGGER.process_info("Completes putting artifacts creation << success >> signal into redis queue.")
                self.system_envs['runs_status'] = 'artifacts'
            else:
                PROC_LOGGER.process_error("Failed to redis-put. << inference_artifacts.tar.gz >> not found.")

        return ext_saved_path

    def get_parameter(self, step_name):
        for step in self.user_parameters[self.pipeline_type]:
            if step['step'] == step_name:
                if type(step['args']) == list:
                    return step['args'][0]
                else:
                    return dict()
        raise ValueError("error")

    def get_asset_source(self, step_name, source = None):
        for step in self.asset_source[self.pipeline_type]:
            if step['step'] == step_name:
                if source == None:
                    return step['source']
                else:
                    return step['source'][source]

        raise ValueError("error")

    # def process_asset_step(self, asset_config, step, pipeline, asset_structure):
    def process_asset_step(self, asset_config, step):
        # step: int
        self.asset_structure.envs['pipeline'] = self.pipeline_type

        _path = ASSET_HOME + asset_config['step'] + "/"
        _file = "asset_" + asset_config['step']
        # asset2등을 asset으로 수정하는 코드
        _file = ''.join(filter(lambda x: x.isalpha() or x == '_', _file))
        user_asset = self.import_asset(_path, _file)
        if self.system_envs['boot_on'] == True:
            PROC_LOGGER.process_info(f"===== Booting... completes importing << {_file} >>")
            return

        meta_dict = {'artifacts': self.system_envs['artifacts'], 'pipeline': self.pipeline_type, 'step': step, 'step_number': step, 'step_name': self.user_parameters[self.pipeline_type][step]['step']}

        self.asset_structure.config['meta'] = meta_dict #nested dict

        if step > 0:
            self.asset_structure.envs['prev_step'] = self.user_parameters[self.pipeline_type][step - 1]['step'] # asset.py에서 load config, load data 할때 필요
        self.asset_structure.envs['step'] = self.user_parameters[self.pipeline_type][step]['step']
        self.asset_structure.envs['num_step'] = step # int
        self.asset_structure.envs['asset_branch'] = asset_config['source']['branch']
        asset_structure = AssetStructure()
        asset_structure.config = self.asset_structure.config
        asset_structure.data = self.asset_structure.data
        asset_structure.envs = self.asset_structure.envs
        asset_structure.args = self.asset_structure.args[self.user_parameters[self.pipeline_type][step]['step']]
        ua = user_asset(asset_structure)
        self.asset_structure.data, self.asset_structure.config = ua.run()

        # FIXME memory release : on/off 필요
        try:
            if self.control['reset_assets']:
                self.memory_release(_path)
                sys.path = [item for item in sys.path if self.asset_structure.envs['step'] not in item]
            else:
                pass
        except:
            self.memory_release(_path)
            sys.path = [item for item in sys.path if self.asset_structure.envs['step'] not in item]

        PROC_LOGGER.process_info(f"==================== Finish pipeline: {self.pipeline_type} / step: {asset_config['step']}")


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

    def _set_asset_structure(self):
        """Asset 의 In/Out 을 data structure 로 전달한다.
        파이프라인 실행에 필요한 환경 정보를 envs 에 setup 한다.
        """

        self.asset_structure.envs['project_home'] = PROJECT_HOME

        self.asset_structure.envs['solution_metadata_version'] = self.system_envs['solution_metadata_version']
        self.asset_structure.envs['artifacts'] = self.system_envs['artifacts']
        self.asset_structure.envs['alo_version'] = self.system_envs['alo_version']
        if self.control['interface_mode'] not in INTERFACE_TYPES:
            PROC_LOGGER.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")
        self.asset_structure.envs['interface_mode'] = self.control['interface_mode']
        self.asset_structure.envs['proc_start_time'] = self.system_envs['start_time']
        self.asset_structure.envs['save_train_artifacts_path'] = self.external_path['save_train_artifacts_path']
        self.asset_structure.envs['save_inference_artifacts_path'] = self.external_path['save_inference_artifacts_path']


    def _install_steps(self, asset_source, get_asset_source='once'):
        requirements_dict = dict()
        for step, asset_config in enumerate(asset_source):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴
            self._install_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']

        return self.install.check_install_requirements(requirements_dict)

    def _empty_artifacts(self, pipeline):
        '''
        - pipe_prefix: 'train', 'inference'
        - 주의: log 폴더는 지우지 않기
        '''
        pipe_prefix = pipeline.split('_')[0]
        dir_artifacts = PROJECT_HOME + f"{pipe_prefix}_artifacts/"
        try:
            for subdir in os.listdir(dir_artifacts):
                if subdir == 'log':
                    continue
                else:
                    shutil.rmtree(dir_artifacts + subdir, ignore_errors=True)
                    os.makedirs(dir_artifacts + subdir)
                    PROC_LOGGER.process_info(f"Successfully emptied << {dir_artifacts + subdir} >> ")
        except:
            PROC_LOGGER.process_error(f"Failed to empty & re-make << {pipe_prefix}_artifacts >>")

    def import_asset(self, _path, _file):
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

    def memory_release(self, _path):
        all_files = os.listdir(_path)
        # .py 확장자를 가진 파일만 필터링하여 리스트에 추가하고 확장자를 제거
        python_files = [file[:-3] for file in all_files if file.endswith(".py")]
        try:
            for module_name in python_files:
                if module_name in sys.modules:
                    del sys.modules[module_name]
        except:
            PROC_LOGGER.process_error("An issue occurred while releasing the memory of module")

    def _install_asset(self, asset_config, check_asset_source='once'):
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
        PROC_LOGGER.process_info(f"Start setting-up << {step_name} >> asset @ << assets >> directory.")
        # 현재 yaml의 source_code가 git일 땐 control의 check_asset_source가 once이면 한번만 requirements 설치, every면 매번 설치하게 끔 돼 있음
        ## FIXME ALOv2에서 기본으로 필요한 requirements.txt는 사용자가 알아서 설치 (git clone alov2 후 pip install로 직접)
        ## asset 배치 (@ scripts 폴더)
        # local 일때는 check_asset_source 가 local인지 git url인지 상관 없음
        if asset_source_code == "local":
            if step_name in os.listdir(ASSET_HOME):
                PROC_LOGGER.process_info(f"Now << local >> asset_source_code mode: <{step_name}> asset exists.")
                pass
            else:
                PROC_LOGGER.process_error(f'Now << local >> asset_source_code mode: \n <{step_name}> asset folder does not exist in <assets> folder.')
        else: # git url & branch
            # git url 확인
            if is_git_url(asset_source_code):
                # _renew_asset(): 다시 asset 당길지 말지 여부 (bool)
                if (check_asset_source == "every") or (check_asset_source == "once" and renew_asset(step_path)):
                    PROC_LOGGER.process_info(f"Start renewing asset : {step_path}")
                    # git으로 또 새로 받는다면 현재 존재 하는 폴더를 제거 한다
                    if os.path.exists(step_path):
                        shutil.rmtree(step_path)  # 폴더 제거
                    os.makedirs(step_path)
                    os.chdir(PROJECT_HOME)
                    repo = git.Repo.clone_from(asset_source_code, step_path)
                    try:
                        repo.git.checkout(git_branch)
                        PROC_LOGGER.process_info(f"{step_path} successfully pulled.")
                    except:
                        PROC_LOGGER.process_error(f"Your have written incorrect git branch: {git_branch}")
                # 이미 scripts내에 asset 폴더들 존재하고, requirements.txt도 설치된 상태
                elif (check_asset_source == "once" and not renew_asset(step_path)):
                    modification_time = os.path.getmtime(step_path)
                    modification_time = datetime.fromtimestamp(modification_time) # 마지막 수정시간
                    PROC_LOGGER.process_info(f"<< {step_name} >> asset had already been created at {modification_time}")
                    pass
                else:
                    PROC_LOGGER.process_error(f'You have written wrong check_asset_source: {check_asset_source}')
            else:
                PROC_LOGGER.process_error(f'You have written wrong git url: {asset_source_code}')

        return

    def _create_package(self, packs):
        # 폴더가 있는지 확인하고 있으면 제거합니다.
        pipes_dir = ASSET_PACKAGE_PATH + self.pipeline_type + '/'
        if os.path.exists(pipes_dir):
            shutil.rmtree(pipes_dir)
            print(f"Folder '{pipes_dir}' has been removed.")

        # 새로운 폴더를 생성합니다.
        os.makedirs(pipes_dir)
        print(f"Folder '{pipes_dir}' has been created.")
        step_number = 0
        for key, values in packs.items():
            if values:
                file_name = pipes_dir + f"step_{step_number}.txt"
                step_number += 1
                with open(file_name, 'w') as file:
                    for value in values:
                        if "force" in value:
                            continue
                        file.write(value + '\n')