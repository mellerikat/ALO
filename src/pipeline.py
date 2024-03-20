# set up pipeline class
import hashlib
import importlib
import random
import sys
import os
import re
from datetime import datetime
import shutil
from typing import Dict
from collections import Counter
import git
import json
import yaml
from src.constants import *
# from src.assets import *
from src.install import Packages
from src.external import ExternalHandler
from src.logger import ProcessLogger
from src.artifacts import Aritifacts
from src.yaml import Metadata

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
    def __init__(self, experimental_plan: Dict, pipeline_type: str, system_envs: Dict ):
        if not pipeline_type in ['all', 'train_pipeline', 'inference_pipeline']:
            raise Exception(f"Invalid pipeline type: {pipeline_type}")
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
    
        def _get_yaml_data(key, pipeline_type = 'all'): # inner func.
            data_dict = {}
            if key == "name" or key == "version":
                return experimental_plan[key]
            if experimental_plan[key] == None:
                return []
            for data in experimental_plan[key]:
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
        for key, value in experimental_plan.items():
            setattr(self, key, _get_yaml_data(key, pipeline_type))
        ## pipeline.run() 만 실행 시, init 에 존재해야 함
        self._set_asset_structure()

    def setup(self):
        self._empty_artifacts(self.pipeline_type)
        print(self.asset_source[self.pipeline_type], self.control['get_asset_source'])
        _, packs = self._setup_asset(self.asset_source[self.pipeline_type], self.control['get_asset_source'])
        if packs is not None: 
            self._create_package(packs)
        # TODO return 구성
        # return

    def load(self, data_path=[]):
        ############  Load Model  ##################
        if self.pipeline_type == 'inference_pipeline':
            if (self.external_path['load_model_path'] != None) and (self.external_path['load_model_path'] != ""):
                self.external.external_load_model(self.external_path, self.external_path_permission)
                ## v2.3.0 NEW: 실험 history 의 train_id 를 제거하고, 특수 문장을 기록
                self.system_envs['inference_history']['train_id'] = "load-external-model"
        ############  Load Data  ##################
        ## 데이터 Path 를 args 로 입력 받을 수 있다.
        ptype = self.pipeline_type.split('_')[0]
        if isinstance(data_path, str):
            data_path = [data_path]
        if len(data_path) > 0:
            ## save() 시, 업데이트 된 값으로 exp_plan 저장
            self.external_path[f'load_{ptype}_data_path'] = data_path
        if self.system_envs['boot_on'] == False:  ## boot_on 시, skip
            # NOTE [중요] wrangler_dataset_uri 가 solution_metadata.yaml에 존재했다면,
            # 이미 _update_yaml할 때 exeternal load inference data path로 덮어쓰기 된 상태
            data_checksums = self.external.external_load_data(self.pipeline_type, self.external_path, self.external_path_permission)
            # v2.3.0 NEW: 실험 history 를 위한 data_id 생성
            ptype = self.pipeline_type.split('_')[0]
            self.system_envs[f'{ptype}_history'].update(data_checksums)
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
        ptype = self.pipeline_type.split('_')[0]
        self.system_envs[f'{ptype}_history']['param_id'] = self._parameter_checksum(params)
        ## v2.3.0 NEW: code id 생성
        total_checksum = hashlib.md5()
        checksum_dict = {}
        for i, asset_config in enumerate(self.asset_source[self.pipeline_type]):
            _path = ASSET_HOME + asset_config['step'] + "/"
            checksum = self._code_checksum(_path)
            checksum_dict[asset_config['step']] = checksum
            # 폴더별 checksum을 문자열로 변환 후 total_checksum 업데이트
            total_checksum.update(str(checksum).encode())
        # MD5 해시값을 16진수 문자열로 변환 후 처음부터 12자리만 사용하여 길이를 12로 제한
        total_checksum_str = total_checksum.hexdigest()[:12]
        self.system_envs[f'{ptype}_history']['code_id_description'] = checksum_dict
        # 수정된 부분: total_checksum을 문자열의 형태로 저장하며, 길이가 12가 되도록 조정
        self.system_envs[f'{ptype}_history']['code_id'] = total_checksum_str 

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
            ## backup 까지는 최종 실행 시간으로 정의
            self.system_envs['experimental_end_time'] = datetime.now().strftime(TIME_FORMAT)
            PROC_LOGGER.process_info(f"Process finish-time: {datetime.now().strftime(TIME_FORMAT_DISPLAY)}")
            ptype = self.pipeline_type.split('_')[0]
            sttime = self.system_envs['experimental_start_time']
            exp_name = self.system_envs['experimental_name']
            random_number = '{:08}'.format(random.randint(0, 99999999))
            self.system_envs[f"{ptype}_history"]['id'] = f'{sttime}-{random_number}-{exp_name}'
            self.system_envs[f"{ptype}_history"]['start_time'] = sttime
            self.system_envs[f"{ptype}_history"]['end_time'] = self.system_envs['experimental_end_time']
            ## train 종료 시, inference_history 에 미리 저장. train_id 는 inference 중에 변경될 수 있기 때문.
            if self.pipeline_type == 'train_pipeline':
                try:
                    self.system_envs[f"inference_history"]['train_id'] = self.system_envs["train_history"]['id']
                except: ## single pipeline (only inference)
                    self.system_envs[f"inference_history"]['train_id'] = "none"
            if self.control['backup_artifacts'] == True:
                # system_envs 에서 data, code, param id 를 저장함
                if ptype == 'train':
                    path = TRAIN_ARTIFACTS_PATH + 'log/experimental_history.json'
                else:
                    path = INFERENCE_ARTIFACTS_PATH + 'log/experimental_history.json'
                with open(path, 'w') as f:
                    json.dump(self.system_envs[f"{ptype}_history"], f, indent=4)    
            ###################################
            ## Step9: Artifacts 를 history 에 backup
            ###################################
            if (self.control['backup_artifacts'] == True): 
                try:
                    backup_exp_plan = self._make_expplan_dict()
                    self.artifact.backup_history(self.pipeline_type, self.system_envs, backup_exp_plan, size=self.control['backup_size'])
                except:
                    PROC_LOGGER.process_error("Failed to backup artifacts into << history >>")

    def history(self, data_id="", param_id="", code_id="", parameter_steps=[]):
        """ history 에 저장된 실험 결과를 Table 로 전달. id 로 솔루션 등록 가능하도록 하기
        Attributes:
            - data_id (str): history 에서 experimental_history.yaml 의 data_id 와 동일여부 확인 후, table 생성
            - parame_id (str): history 에서 experimental_history.yaml 의 param_id 와 동일여부 확인 후, table 생성
            - code_id (str): history 에서 experimental_history.yaml 의 code_id 와 동일여부 확인 후, table 생성

            - parameter_steps (list): table 생성 시, 어떤 step 의 parameter 를 같이 보여줄 지 결정
        """
        ## step1: history 폴더에서 폴더 명을 dict key 화 하기 
        ptype = self.pipeline_type.split('_')[0]
        base_path = HISTORY_PATH + f'{ptype}/'
        entries = os.listdir(base_path)
        # 엔트리 중에서 디렉토리만 필터링하여 리스트에 추가합니다.
        folders = [entry for entry in entries if os.path.isdir(os.path.join(base_path, entry))]
        history_dict = {}
        empty_score_dict = {
            "date": '',
            "file_path": '',
            "note": '',
            "probability": {},
            "result": '',
            "score": "",
            "version": "",
        }
        ## TODO: sqllite 도입 고려 (속도 이슈가 있다고 할 경우)
        for folder in folders: 
            ########################## 
            #### Set1: data/code/param id 탐색
            file = base_path + folder + f"/log/experimental_history.json"
            if os.path.exists(file):
                with open(file, 'r') as f:
                    history = json.load(f)
                    history_dict[folder] = history
            else:
                empty_dict = {
                    "data_id_description": {},
                    "data_id": "" ,
                    "param_id": "",
                    "code_id_description": {},
                    "code_id": "",
                    "id": "",
                    "start_time": "20000101T000000Z",
                    "end_time": "20000101T000000Z"
                }
                # experiment_history.json 이 없는 경우 inference 일 경우 train_id 를 none 으로 설정함.
                if ptype == "inference":
                    empty_dict["train_id"] = "none"
                history_dict[folder] = empty_dict
            ########################## 
            #### Set2: score 탐색
            file_score = base_path + folder + f"/score/{ptype}_summary.yaml"
            if os.path.exists(file_score):
                try:
                    with open(file_score, 'r') as f:
                        history_score = yaml.safe_load(f)
                        history_dict[folder].update(history_score)
                except:
                    history_dict[folder].update(empty_score_dict)
            else:
                history_dict[folder].update(empty_score_dict)
            ########################## 
            #### Set3: score 탐색
            file_exp = base_path + folder + f"/experimental_plan.yaml"
            meta = Metadata()
            if os.path.exists(file_exp):
                meta.read_yaml(exp_plan_file=file_exp, update_envs=False)  ## read 하면 exp 변수화 됨
                value_empty=False
            else:
                meta.read_yaml(exp_plan_file=DEFAULT_EXP_PLAN, update_envs=False)
                value_empty=True
            for pipe, steps_dict in meta.user_parameters.items():
                if pipe == self.pipeline_type:
                    ## parameter_steps 가 유효 한지 검사
                    exp_step_list = sorted([i['step'] for i in meta.user_parameters[pipe]])
                    if not all(iten in exp_step_list for iten in parameter_steps):
                        raise ValueError(f"parameter_steps {parameter_steps} is not valid. It should be one of {exp_step_list}")
                    for step_dict in steps_dict:  ## step 별 args 출력 
                        step = step_dict['step']
                        if step in parameter_steps:
                            for key, value in step_dict['args'][0].items():
                                if value_empty:
                                    history_dict[folder][f"{step}.{key}"] = "none"
                                else:
                                    history_dict[folder][f"{step}.{key}"] = value
            ########################## 
            #### Set4: 실패된 실험 탐색
            if '-error' in folder:
                history_dict[folder]['status'] = "error"
            else:
                history_dict[folder]['status'] = "success"
        ## Make Table
        # List of keys we want to remove
        drop_keys = ['data_id_description', 'code_id_description', 'file_path']
        new_order = ['id', 'status', 'start_time', 'end_time', 'score', 'result', 'note', 'probability', 'version', 'data_id', 'code_id', 'param_id']
        if ptype == 'inference':
            new_order.append('train_id')
        # A new dictionary to hold our processed records
        processed_dict = {}
        for key, record in history_dict.items():
            # Exclude unwanted keys
            filtered_record = {k: v for k, v in record.items() if k not in drop_keys}
            # Reorder and select keys according to new_order, filling missing keys with None
            processed_record = {k: filtered_record.get(k, None) for k in new_order}
            # Add remaining keys in their original order
            remaining_keys = [k for k in filtered_record.keys() if k not in new_order]
            for k in remaining_keys:
                processed_record[k] = filtered_record[k]
            # Format the 'start_time' and 'end_time'
            processed_record['start_time'] = datetime.strptime(processed_record['start_time'], TIME_FORMAT).strftime(TIME_FORMAT_DISPLAY)
            processed_record['end_time'] = datetime.strptime(processed_record['end_time'], TIME_FORMAT).strftime(TIME_FORMAT_DISPLAY)
            # Add record to the new processed_dict
            processed_dict[key] = processed_record
        # Sort the records by end_time in descending order (not easily achievable with a dictionary, might need to convert to a list of tuples or a list of dictionaries)
        processed_records_list = list(processed_dict.values())
        # Filtering logic based on data_id, param_id, and code_id
        filtered_records_list = []
        for record in processed_records_list:
            if (not data_id or record.get('data_id') == data_id) and \
            (not param_id or record.get('param_id') == param_id) and \
            (not code_id or record.get('code_id') == code_id):
                filtered_records_list.append(record)
        # Now 'processed_records_list' contains the list of dictionaries sorted by 'end_time' and you can use it as you wish.
        filtered_records_list.sort(key=lambda x: datetime.strptime(x['end_time'], TIME_FORMAT_DISPLAY), reverse=True)
        return filtered_records_list


    ###############################################################
    ####    Part2. Runs fuction    ####
    ###############################################################
    def _make_expplan_dict(self):
        ## exp_plan 만들기. 실험 중에 중간 값들이 변경되어 있으므로, 꼭 ~ 재구성하여 저장한다.
        backup_exp_plan = {}
        backup_exp_plan['name'] = self.name
        backup_exp_plan['version'] = self.version
        backup_exp_plan['external_path'] = [{k: v} for k, v in self.external_path.items()]
        backup_exp_plan['external_path_permission'] = [self.external_path_permission]
        backup_exp_plan['user_parameters'] = [self.user_parameters]
        backup_exp_plan['asset_source'] = [self.asset_source]
        backup_exp_plan['control'] = [{k: v} for k, v in self.control.items()]
        try:
            backup_exp_plan['ui_args_detail'] = [{k: v} for k, v in self.ui_args_detail.items()]
        except:
            pass   ## 존재하지 않는 경우 대응
        return backup_exp_plan

    def _parameter_checksum(self, params):
        # params를 문자열로 변환하여 해시 입력값으로 사용
        # 여기서는 params가 문자열이라고 가정합니다. 실제 사용 시 params를 적절히 변환해야 할 수 있습니다.
        params_str = str(params)
        # hashlib을 사용해 params_str의 해시 계산
        checksum = hashlib.sha256(params_str.encode('utf-8'))
        # 해시 객체에서 hexdigest 메소드를 호출하여 16진수 해시 문자열 얻기
        hexdigest_str = checksum.hexdigest()
        # 16진수 문자열을 처음부터 12자리만 사용하여 길이를 12로 제한하고 반환
        return hexdigest_str[:12]

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
            meta = Metadata()
            summary_dict = meta.get_yaml(summary_dir + 'inference_summary.yaml')
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
            PROC_LOGGER.process_info(f"==================== Booting... completes importing << {_file} >>")
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
        # FIXME memory release : on/off 필요? > 우선 spec-out 
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
            return None, None
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
        def _renew_asset(step_path): #inner func.
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
                    - whether_to_renew_asset =__renew_asset(step_path)
            """
            whether_renew_asset = False
            if os.path.exists(step_path):
                pass
            else:
                whether_renew_asset = True
            return whether_renew_asset
        # git url 확인 -> lib
        def _is_git_url(url): #inner func.
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
            if _is_git_url(asset_source_code):
                # __renew_asset(): 다시 asset 당길지 말지 여부 (bool)
                if (check_asset_source == "every") or (check_asset_source == "once" and _renew_asset(step_path)):
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
                elif (check_asset_source == "once" and not _renew_asset(step_path)):
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