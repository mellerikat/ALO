import os
import random
import sys
import json 
import shutil
import traceback
import subprocess
# Packge
from datetime import datetime, timezone
from collections import Counter
from copy import deepcopy
from git import Repo, GitCommandError
import yaml
# local import
from src.utils import init_redis
from src.constants import *
from src.artifacts import Aritifacts
from src.install import Packages
from src.pipeline import Pipeline
from src.solution_register import SolutionRegister

# 이름을 한번 다시 생각
from src.assets import Assets

from src.external import ExternalHandler 
from src.redisqueue import RedisQueue
from src.logger import ProcessLogger  
# s3를 옮김
from src.sagemaker_handler import SagemakerHandler 
from src.yaml import Metadata
#######################################################################################

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
        
class ALO:
    # def __init__(self, exp_plan_file = None, solution_metadata = None, pipeline_type = 'all', boot_on = False, computing = 'local'):
    # 'config': None, 'system': None, 'mode': 'all', 'loop': False, 'computing': 'local'
    def __init__(self, config = None, system = None, mode = 'all', loop = False, computing = 'local'):
        """실험 계획 (experimental_plan.yaml), 운영 계획(solution_metadata), 
        파이프라인 종류(train, inference), 동작방식(always-on) 에 대한 설정을 완료함

        Args:
            exp_plan_file: 실험 계획 (experimental_plan.yaml) 을 yaml 파일 위치로 받기
            solution_metadata: 운영 계획 (solution_metadata(str)) 정보를 string 으로 받기
            pipeline_type: 파이프라인 모드 (all, train, inference, boot)
            boot_on: always-on 시, boot 과정 인지 아닌지를  구분 (True, False)
            computing: 학습하는 컴퓨팅 자원 (local, sagemaker)
        Returns:
        """
        # 필요 class init
        self._init_class()
        
        # logger 초기화
        self._init_logger()

        # alolib을 설치
        self._set_alolib()

        exp_plan_path = config
        self.system = system
        self.loop = loop
        self.computing = computing
        pipeline_type = mode

        self.system_envs = {}

        # TODO default로 EXP PLAN을 넣어 주었는데 아래 if 문과 같이 사용할 되어 지는지 확인***
        if exp_plan_path == "" or exp_plan_path == None:
            exp_plan_path = DEFAULT_EXP_PLAN

        # 입력 받은 args를 전역변수로 변환
        # config, system, mode, loop, computing

        self._get_alo_version()
        self.set_metadata(exp_plan_path, pipeline_type)
        # 현재 ALO 버전

        # artifacts home 초기화 (from src.utils)
        self.system_envs['artifacts'] = self.artifact.set_artifacts()
        self.system_envs['train_history'] ={}
        self.system_envs['inference_history'] ={}

        if self.system_envs['boot_on'] and self.system is not None:
            self.q = init_redis(self.system)

    #############################
    ####    Main Function    ####
    #############################
    def pipeline(self, experimental_plan=None, pipeline_type = 'train_pipeline', train_id=''):

        if not pipeline_type in ['train_pipeline', 'inference_pipeline']:
            raise Exception(f"The pipes must be one of train_pipeline or inference_pipeline. (pipes={pipeline_type})") 

        ## train_id 는 inference pipeline 에서만 지원
        if not train_id == '':
            if pipeline_type == 'train_pipeline':
                raise Exception(f"The train_id must be empty. (train_id={train_id})")
            else:
                self._load_history_model(train_id)
                self.system_envs['inference_history']['train_id'] = train_id
        else:
            ## train_id 를 이전 정보로 업로드 해두고 시작한다. (데이터를 이미 train_artifacts 에 존재)
            file = TRAIN_ARTIFACTS_PATH + f"/log/experimental_history.json"
            if os.path.exists(file):
                with open(file, 'r') as f:
                    history = json.load(f)
                    self.system_envs['inference_history']['train_id'] = history['id']
            else:
                self.system_envs['inference_history']['train_id'] = 'none'

        if experimental_plan == "" or experimental_plan == None:
            experimental_plan = self.exp_yaml


        pipeline = Pipeline(experimental_plan, pipeline_type, self.system_envs)
        return pipeline

    # redis q init 하는 위치
    def main(self):
        """ 실험 계획 (experimental_plan.yaml) 과 운영 계획(solution_metadata) 을 읽어옵니다.
        실험 계획 (experimental_plan.yaml) 은 입력 받은 config 와 동일한 경로에 있어야 합니다.
        운영 계획 (solution_metadata) 은 입력 받은 solution_metadata 값과 동일한 경로에 있어야 합니다.
        """
        try:
            for pipe in self.system_envs['pipeline_list']:

                ## 갑자기 죽는 경우, 기록에 남기기 위해 현 진행상황을 적어둔다.
                self.system_envs['current_pipeline'] = pipe

                self.proc_logger.process_info("#########################################################################################################")
                self.proc_logger.process_info(f"                                                 {pipe}                                                   ") 
                self.proc_logger.process_info("#########################################################################################################")

                pipeline = self.pipeline(pipeline_type=pipe)
                # TODO 한번에 하려고 하니 이쁘지 않음 논의
                pipeline.setup()
                pipeline.load()
                pipeline.run()
                pipeline.save()
                # pipeline.history()


                
                # FIXME loop 모드로 동작 / solution_metadata를 어떻게 넘길지 고민 / update yaml 위치를 새로 선정할 필요가 있음 ***
                if self.loop: 
                    try:
                        # boot 모드 동작 후 boot 모드 취소
                        self.system_envs['boot_on'] = False
                        msg_dict = self._get_redis_msg() ## 수정
                        self.system = msg_dict['solution_metadata'] ## 수정
                        self.set_metadata(pipeline_type='inference') ## 수정
                        self.main()
                    except Exception as e: 
                        ## always-on 모드에서는 Error 가 발생해도 종료되지 않도록 한다. 
                        print("\033[91m" + "Error: " + str(e) + "\033[0m") # print red 
                        continue

                if self.computing == "sagemaker":
                    self.sagemaker_runs()
                
            # train, inference 다 돌고 pip freeze 돼야함 
            # FIXME 무한루프 모드일 땐 pip freeze 할 일 없다 ?
            with open(PROJECT_HOME + 'solution_requirements.txt', 'w') as file_:
                subprocess.Popen(['pip', 'freeze'], stdout=file_).communicate()
        except:
            try:  # 여기에 try, finally 구조로 안쓰면 main.py 로 raise 되버리면서 backup_artifacts가 안됨 
                #self.proc_logger.process_error("Failed to ALO runs():\n" + traceback.format_exc()) #+ str(e)) 
                self.proc_logger.process_error(traceback.format_exc())
            finally:
                ## id 생성 
                sttime = self.system_envs['experimental_start_time']
                exp_name = self.system_envs['experimental_name']
                curr = self.system_envs['current_pipeline'].split('_')[0]
                random_number = '{:08}'.format(random.randint(0, 99999999))
                self.system_envs[f"{curr}_history"]['id'] = f'{sttime}-{random_number}-{exp_name}'

                # 에러 발생 시 self.control['backup_artifacts'] 가 True, False던 상관없이 무조건 backup (폴더명 뒤에 _error 붙여서) 
                # TODO error 발생 시엔 external save 되는 tar.gz도 다른 이름으로 해야할까 ? 
                self.artifact.backup_history(pipe, self.system_envs, backup_exp_plan={}, error=True, size=self.control['backup_size'])
                # error 발생해도 external save artifacts 하도록        
                empty = self.ext_data.external_save_artifacts(pipe, self.external_path, self.external_path_permission)
                if self.loop == True:
                    fail_str = json.dumps({'status':'fail', 'message':traceback.format_exc()})
                    if self.system_envs['runs_status'] == 'init':
                        self.system_envs['q_inference_summary'].rput(fail_str)
                        self.system_envs['q_inference_artifacts'].rput(fail_str)
                    elif self.system_envs['runs_status'] == 'summary': # 이미 summary는 success로 보낸 상태 
                        self.system_envs['q_inference_artifacts'].rput(fail_str)


    def set_metadata(self, exp_plan_path = DEFAULT_EXP_PLAN, pipeline_type = 'train_pipeline'):
        """ 실험 계획 (experimental_plan.yaml) 과 운영 계획(solution_metadata) 을 읽어옵니다.
        실험 계획 (experimental_plan.yaml) 은 입력 받은 config 와 동일한 경로에 있어야 합니다.  
        운영 계획 (solution_metadata) 은 입력 받은 solution_metadata 값과 동일한 경로에 있어야 합니다.
        """
        
        # init solution metadata
        self.system_envs['experimental_start_time'] = datetime.now(timezone.utc).strftime(TIME_FORMAT)
        sol_meta = self.load_solution_metadata()
        self.system_envs['solution_metadata'] = sol_meta
        self.system_envs['experimental_plan_path'] = exp_plan_path
        self.exp_yaml, sys_envs = self.load_exp_plan(sol_meta, exp_plan_path, self.system_envs)
        self._set_attr()
        # loop 모드면 항상 boot 모드
        if self.computing != 'local':
            self.system_envs = self._set_system_envs(pipeline_type, True, self.system_envs)
        else:
            if 'boot_on' in self.system_envs.keys(): # loop mode - boot on 이후 
                self.system_envs = self._set_system_envs(pipeline_type, self.system_envs['boot_on'], self.system_envs)
            else: # loop mode - 최초 boot on 시 / 일반 flow  
                self.system_envs = self._set_system_envs(pipeline_type, self.loop, self.system_envs)
                
        # 입력 받은 config(exp)가 없는 경우 default path에 있는 내용을 사용
        
        # metadata까지 완성되면 출력
        self._alo_info()
        # ALO 설정 완료 info 와 로깅

            
    def sagemaker_runs(self): 
        try:
            try: 
                # FIXME 로컬에서 안돌리면 input 폴더 없으므로 데이터 가져오는 것 여기에 별도 추가 
                self._external_load_data('train_pipeline')
            except Exception as e:
                self.proc_logger.process_error("Failed to get external data. \n" + str(e)) 
                
            try:
                # load sagemaker_config.yaml - (account_id, role, region, ecr_repository, s3_bucket_uri, train_instance_type)
                sm_config = self.meta.get_yaml(SAGEMAKER_CONFIG) 
                sm_handler = SagemakerHandler(self.external_path_permission['aws_key_profile'], sm_config)
                sm_handler.init()
            except Exception as e:
                self.proc_logger.process_error("Failed to init SagemakerHandler. \n" + str(e)) 
              
            try: 
                sm_handler.setup() 
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to setup SagemakerHandler. \n" + str(e))  
            
            try:
                sm_handler.build_solution()
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to build Sagemaker solution. \n" + str(e))  
                
            try:           
                sm_handler.fit_estimator() 
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to Sagemaker estimator fit. \n" + str(e))  
                
            try: 
                sm_handler.download_latest_model()
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to download sagemaker trained model. \n" + str(e)) 
                
        except:
            self.proc_logger.process_error("Failed to sagemaker runs.") 
            
        finally: 
            # 딱히 안해도 문제는 없는듯 하지만 혹시 모르니 설정했던 환경 변수를 제거 
            os.unsetenv("AWS_PROFILE")

    def register(self, solution_info=None, infra_setup=None,  train_id = '', inference_id = '', upload=False):

        ## train_id 존재 검사. exp_plan 불러오기 
        meta = Metadata()
        exp_plan = meta.read_yaml(exp_plan_file=None)

        def load_pipeline_expplan(pipeline_type, history_id, meta):

            if not pipeline_type in ['train', 'inference']:
                raise ValueError("pipeline_type must be 'train' or 'inference'.")

            base_path = HISTORY_PATH + f'{pipeline_type}/'
            entries = os.listdir(base_path)
            folders = [entry for entry in entries if os.path.isdir(os.path.join(base_path, entry))]

            if not history_id in folders:
                raise ValueError(f"{pipeline_type}_id is not exist.")
            else:
                path = base_path + history_id + '/experimental_plan.yaml'
                exp_plan = meta.get_yaml(path)
                merged_exp_plan = meta.merged_exp_plan(exp_plan, pipeline_type=pipeline_type)
                return merged_exp_plan


        def _pipe_run(exp_plan, pipeline_type):
            pipeline = self.pipeline(exp_plan, pipeline_type )
            pipeline.setup()
            pipeline.load()
            pipeline.run()
            pipeline.save()
        ## id 폴더에서 exp_plan 가져와서, pipeline 을 실행한다. (artifact 상태를 보장할 수 없으므로)
        if train_id != '':
            train_exp_plan = load_pipeline_expplan('train', train_id, meta)
            _pipe_run(train_exp_plan, 'train_pipeline')    
        else:
            _pipe_run(exp_plan, 'train_pipeline')    

        if inference_id != '':
            inference_exp_plan = load_pipeline_expplan('inference', inference_id, meta)
            _pipe_run(inference_exp_plan, 'inference_pipeline')
        else:
            print(exp_plan)
            _pipe_run(exp_plan, 'inference_pipeline')

        ## register 에 사용할 exp_plan 제작
        if train_id != '':
            if inference_id != '':
                exp_plan_register = inference_exp_plan
            else:
                exp_plan_register = train_exp_plan
        else:
            if inference_id != '':
                exp_plan_register = inference_exp_plan
            else:
                exp_plan_register = exp_plan

        register = SolutionRegister(infra_setup=infra_setup, solution_info=solution_info, experimental_plan=exp_plan_register)

        if upload:
            reigster.login(username, password)

        return register
        

    #####################################
    ####    Part1. Initialization    ####
    #####################################
    def _init_logger(self):
        """ALO Master 의 logger 를 초기화 합니다. 
        ALO Slave (Asset) 의 logger 를 별도 설정 되며, configuration 을 공유 합니다. 
        """

        # 새 runs 시작 시 기존 log 폴더 삭제 
        train_log_path = TRAIN_LOG_PATH
        inference_log_path = INFERENCE_LOG_PATH
        try: 
            if os.path.exists(train_log_path):
                shutil.rmtree(train_log_path, ignore_errors=True)
            if os.path.exists(inference_log_path):
                shutil.rmtree(inference_log_path, ignore_errors=True)
        except: 
            raise NotImplementedError("Failed to empty log directory.")
        # redundant 하더라도 processlogger은 train, inference 양쪽 다남긴다. 
        self.proc_logger = ProcessLogger(PROJECT_HOME)  

    def _set_system_envs(self, pipeline_type, boot_on, _system_envs):
        system_envs = _system_envs
        # 아래 solution metadata 관련 key들은 이미 yaml.py의 _update_yaml에서 setting 돼서 넘어왔으므로, key가 없을때만 None으로 셋팅
        solution_metadata_keys = ['solution_metadata_version', 'q_inference_summary', \
                'q_inference_artifacts', 'q_inference_artifacts', 'redis_host', 'redis_port', \
                'inference_result_datatype', 'train_datatype']
        for k in solution_metadata_keys: 
            if k not in system_envs.keys(): 
                system_envs[k] = None
        if 'pipeline_mode' not in system_envs.keys():
            system_envs['pipeline_mode'] = pipeline_type

        # 'init': initial status / 'summary': success until 'q_inference_summary'/ 'artifacts': success until 'q_inference_artifacts'
        system_envs['runs_status'] = 'init'         
        system_envs['boot_on'] = boot_on
        system_envs['loop'] = boot_on
        system_envs['start_time'] = datetime.now().strftime("%y%m%d_%H%M%S")

        if self.computing != 'local':
            system_envs['pipeline_list'] = ['train_pipeline']
        elif boot_on:
            system_envs['pipeline_list'] = ['inference_pipeline']
        else:
            if pipeline_type == 'all':
                if os.getenv('COMPUTING') == 'sagemaker':
                    # TODO 2.2.1 added (sagemaker 일 땐 학습만 진행)
                    system_envs['pipeline_list'] = ["train_pipeline"]
                    from sagemaker_training import environment      
                    self.external_path['save_train_artifacts_path'] = environment.Environment().model_dir
                else:
                    system_envs['pipeline_list'] = [*self.user_parameters]
            else:
                system_envs['pipeline_list'] = [f"{pipeline_type}_pipeline"]
            
            
        return system_envs

    def _alo_info(self):
        if self.system_envs['boot_on'] == True: 
            self.proc_logger.process_info(f"==================== Start booting sequence... ====================")
        else: 
            self.proc_logger.process_meta(f"Loaded solution_metadata: \n{self.system_envs['solution_metadata']}\n")
        self.proc_logger.process_info(f"Process start-time: {self.system_envs['start_time']}")
        self.proc_logger.process_meta(f"ALO version = {self.system_envs['alo_version']}")
        self.proc_logger.process_info("==================== Start ALO preset ==================== ")

    def load_solution_metadata(self):
        # TODO solution meta version 관리 필요??
        # system 은 입력받은 solution metadata / args.system 이 *.yaml 이면 파일 로드하여 string 화 하여 입력 함
        filename = self.system
        if (filename is not None) and filename.endswith('.yaml'):
            try:
                with open(filename, encoding='UTF-8') as file:
                    content = yaml.load(file, Loader=yaml.FullLoader)  # 파일 내용을 읽고 자료구조로 변환
                # 로드한 YAML 내용을 JSON 문자열로 변환
                self.system = json.dumps(content)
            except FileNotFoundError:
                print(f"The file {filename} does not exist.")
        return json.loads(self.system) if self.system != None else None # None or dict from json 
    
    def load_exp_plan(self, sol_meta, experimental_plan, system_envs):
        exp_plan = self.meta.read_yaml(sol_me_file = sol_meta, exp_plan_file = experimental_plan, system_envs = system_envs)
        ## system_envs 를 linked 되어 있으므로, read_yaml 에서 update 된 사항이 자동 반영되어 있음
        return exp_plan, system_envs 

    ###################################
    ####    Part2. Runs fuction    ####
    ###################################
    
    def read_structure(self, pipeline, step):
        import pickle 
        
        a = self.asset_structure.config['meta']['artifacts']['.asset_interface'] + pipeline + "/" + self.user_parameters[pipeline][step]['step'] + "_config.pkl"
        b = self.asset_structure.config['meta']['artifacts']['.asset_interface'] + pipeline + "/" + self.user_parameters[pipeline][step]['step'] + "_data.pkl"

        with open(a, 'rb') as f:
            _config = pickle.load(f)
        
        with open(b, 'rb') as f:
            _data = pickle.load(f)
        return _config, _data

    def set_asset_structure(self):
        """Asset 의 In/Out 을 data structure 로 전달한다.
        파이프라인 실행에 필요한 환경 정보를 envs 에 setup 한다.
        """
        self.asset_structure = AssetStructure() 
        self.asset_structure.envs['project_home'] = PROJECT_HOME
        self.asset_structure.envs['solution_metadata_version'] = self.system_envs['solution_metadata_version']
        self.asset_structure.envs['artifacts'] = self.system_envs['artifacts']
        self.asset_structure.envs['alo_version'] = self.system_envs['alo_version']
        if self.control['interface_mode'] not in INTERFACE_TYPES:
            self.proc_logger.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")
        self.asset_structure.envs['interface_mode'] = self.control['interface_mode']
        self.asset_structure.envs['proc_start_time'] = self.system_envs['start_time']
        self.asset_structure.envs['save_train_artifacts_path'] = self.external_path['save_train_artifacts_path']
        self.asset_structure.envs['save_inference_artifacts_path'] = self.external_path['save_inference_artifacts_path']
    
    def setup_asset(self, pipeline):
        """asset 의 git clone 및 패키지를 설치 한다. 
        
        중복된 step 명이 있는지를 검사하고, 존재하면 Error 를 발생한다. 
        always-on 시에는 boot-on 시에만 설치 과정을 진행한다. 

        Args:
          - pipelne(str): train, inference 를 구분한다. 

        Raises:
          - step 명이 동일할 경우 에러 발생 
        """
        # setup asset (asset을 git clone (or local) 및 requirements 설치)
        get_asset_source = self.control["get_asset_source"]  # once, every

        # TODO 현재 pipeline에서 중복된 step 이 있는지 확인
        step_values = [item['step'] for item in self.asset_source[pipeline]]
        step_counts = Counter(step_values)
        for value, count in step_counts.items():
            if count > 1:
                self.proc_logger.process_error(f"Duplicate step exists: {value}")

        # 운영 무한 루프 구조일 땐 boot_on 시 에만 install 하고 이후에는 skip 
        if (self.system_envs['boot_on'] == False) and (self.system_envs['redis_host'] is not None):
            pass 
        else:
            return self._install_steps(pipeline, get_asset_source)
    
    def run_asset(self, pipeline):
        """파이프라인 내의 asset 를 순차적으로 실행한다. 

        Args:
          - pipeline(str) : train, inference 를 구분한다. 

        Raises:
          - Asset 실행 중 에러가 발생할 경우 에러 발생 
          - Asset 실행 중 에러가 발생하지 않았지만 예상하지 못한 에러가 발생할 경우 에러 발생        
        """
        for step, asset_config in enumerate(self.asset_source[pipeline]):    
            self.proc_logger.process_info(f"==================== Start pipeline: {pipeline} / step: {asset_config['step']}")
            # 외부에서 arg를 가져와서 수정이 가능한 구조를 위한 구조
            self.asset_structure.args = self.get_args(pipeline, step)
            try: 
                self.asset_structure = self.process_asset_step(asset_config, step, pipeline, self.asset_structure)
            except: 
                self.proc_logger.process_error(f"Failed to process step: << {asset_config['step']} >>")

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
                    self.proc_logger.process_info(f"Successfully emptied << {dir_artifacts + subdir} >> ")
        except: 
            self.proc_logger.process_error(f"Failed to empty & re-make << .{pipe_prefix}_artifacts >>")
            

    ########################################
    ####    Part3. Internal fuctions    ####
    ########################################
    
    def _load_history_model(self, train_id):
        ## train_id 가 history 에 존재 하는지 확인 
        base_path = HISTORY_PATH + 'train/'
        entries = os.listdir(base_path)
        folders = [entry for entry in entries if os.path.isdir(os.path.join(base_path, entry))]

        if not train_id in folders:
            raise Exception(f"The train_id must be one of {folders}. (train_id={train_id})")

        ## history 에서 model 을 train_artifacts 에 복사
        src_path = HISTORY_PATH + 'train/' + train_id + '/models/'
        dst_path = TRAIN_ARTIFACTS_PATH + 'models/'

        # 대상 폴더가 존재하는지 확인
        if os.path.exists(dst_path):
            shutil.rmtree(dst_path)
        shutil.copytree(src_path, dst_path)
        self.proc_logger.process_info(f"The model is copied from {src_path} to {dst_path}.")
            
    def _external_load_data(self, pipeline):
        """외부 데이터를 가져 옴 (local storage, S3)

        Args:
          - pipelne (str): train / inference 인지를 구분함
        """

        ## from external.py
        self.ext_data.external_load_data(pipeline, self.external_path, self.external_path_permission, )

    def _external_load_model(self):
        """외부에서 모델파일을 가져옴 (model.tar.gz)

        S3 일 경우 permission 체크를 하고 가져온다.

        """

        ## from external.py
        self.ext_data.external_load_model(self.external_path, self.external_path_permission)
        
    def _install_steps(self, pipeline, get_asset_source='once'):
        requirements_dict = dict() 
        for step, asset_config in enumerate(self.asset_source[pipeline]):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴 
            self.asset.setup_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']
        
        return self.install.check_install_requirements(requirements_dict)

    def get_args(self, pipeline, step):
        if type(self.user_parameters[pipeline][step]['args']) == type(None):
            return dict()
        else:
            return self.user_parameters[pipeline][step]['args'][0]

    def process_asset_step(self, asset_config, step, pipeline, asset_structure): 
        # step: int 
        self.asset_structure.envs['pipeline'] = pipeline

        _path = ASSET_HOME + asset_config['step'] + "/"
        _file = "asset_" + asset_config['step']
        # asset2등을 asset으로 수정하는 코드
        _file = ''.join(filter(lambda x: x.isalpha() or x == '_', _file))
        user_asset = self.asset.import_asset(_path, _file)
        if self.system_envs['boot_on'] == True: 
            self.proc_logger.process_info(f"===== Booting... completes importing << {_file} >>")
            return asset_structure

        # 사용자가 config['meta'] 를 통해 볼 수 있는 가변 부
        # FIXME step은 추후 삭제되야함, meta --> metadata 같은 식으로 약어가 아닌 걸로 변경돼야 함 
        meta_dict = {'artifacts': self.system_envs['artifacts'], 'pipeline': pipeline, 'step': step, 'step_number': step, 'step_name': self.user_parameters[pipeline][step]['step']}
        asset_structure.config['meta'] = meta_dict #nested dict

        # TODO 가변부 status는 envs에는 아닌듯 >> 성선임님 논의         
        # asset structure envs pipeline 별 가변부 (alolib에서도 사용하므로 필요)
        if step > 0: 
            asset_structure.envs['prev_step'] = self.user_parameters[pipeline][step - 1]['step'] # asset.py에서 load config, load data 할때 필요 
        asset_structure.envs['step'] = self.user_parameters[pipeline][step]['step']
        asset_structure.envs['num_step'] = step # int  
        asset_structure.envs['asset_branch'] = asset_config['source']['branch']

        ua = user_asset(asset_structure) 
        asset_structure.data, asset_structure.config = ua.run()
        # FIXME memory release : on/off 필요 
        try:
            if self.control['reset_assets']:
                self.asset.memory_release(_path)
                sys.path = [item for item in sys.path if asset_structure.envs['step'] not in item]
            else:
                pass
        except:
            self.asset.memory_release(_path)
            sys.path = [item for item in sys.path if asset_structure.envs['step'] not in item]
        
        self.proc_logger.process_info(f"==================== Finish pipeline: {pipeline} / step: {asset_config['step']}")
        
        return asset_structure
    
    def _init_class(self):
        # TODO 지우기 -> Pipeline 클래스에서 사용 예정
        self.ext_data = ExternalHandler()
        self.install = Packages()
        self.asset = Assets(ASSET_HOME)
        self.artifact = Aritifacts()

        self.meta = Metadata()

    def _set_alolib(self):
        """ALO 는 Master (파이프라인 실행) 와 slave (Asset 실행) 로 구분되어 ALO API 로 통신합니다. 
        기능 업데이트에 따라 API 의 버전 일치를 위해 Master 가 slave 의 버전을 확인하여 최신 버전으로 설치 되도록 강제한다.
        
        """
        # TODO 버전 mis-match 시, git 재설치하기. (미존재시, 에러 발생 시키기)
        try:
            if not os.path.exists(PROJECT_HOME + 'alolib'): 
                ALOMAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                repo = Repo(ALOMAIN)
                ALOVER = repo.active_branch.name
                # repository_url = ALO_LIB_URI
                # destination_directory = ALO_LIB
                cloned_repo = Repo.clone_from(ALO_LIB_URI, ALO_LIB, branch=ALOVER)
                self.proc_logger.process_info(f"alolib {ALOVER} git pull success.")
            else: 
                self.proc_logger.process_info("alolib already exists in local path.")
            alolib_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/alolib/"
            sys.path.append(alolib_path)
        except GitCommandError as e:
            self.proc_logger.process_error(e)
            raise NotImplementedError("alolib git pull failed.")
        req = os.path.join(alolib_path, "requirements.txt")
        # pip package의 안정성이 떨어지기 때문에 subprocess 사용을 권장함
        result = subprocess.run(['pip', 'install', '-r', req], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            self.proc_logger.process_info("Success installing alolib requirements.txt")
            self.proc_logger.process_info(result.stdout)
        else:
            self.proc_logger.process_error(f"Failed installing alolib requirements.txt : \n {result.stderr}")

    def _set_attr(self):
        self.user_parameters = self.meta.user_parameters
        self.asset_source = self.meta.asset_source
        self.external_path = self.meta.external_path
        self.external_path_permission = self.meta.external_path_permission
        self.control = self.meta.control

    def _get_alo_version(self):
        with open(PROJECT_HOME + '.git/HEAD', 'r') as f:
            ref = f.readline().strip()
        # ref는 형식이 'ref: refs/heads/브랜치명' 으로 되어 있으므로, 마지막 부분만 가져옵니다.
        if ref.startswith('ref:'):
            __version__ = ref.split('/')[-1]
        else:
            __version__ = ref  # Detached HEAD 상태 (브랜치명이 아니라 커밋 해시)
        self.system_envs['alo_version'] = __version__

    def _get_redis_msg(self):
        start_msg = self.q.lget(isBlocking=True)
        if start_msg is not None:
            msg_dict = json.loads(start_msg.decode('utf-8')) ## 수정
        else:
            msg = "Empty message recevied for EdgeApp inference request."
            print("\033[91m" + "Error: " + str(msg) + "\033[0m") # print red
        return msg_dict