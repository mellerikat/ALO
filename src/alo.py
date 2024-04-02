import os
import random
import sys
import json 
import shutil
import traceback
import subprocess
from datetime import datetime, timezone
from time import time 
from git import Repo, GitCommandError
import yaml
import pyfiglet
# local import
from src.utils import print_color, init_redis, _log_process
from src.constants import *
from src.artifacts import Aritifacts
from src.install import Packages
from src.pipeline import Pipeline
from src.solution_register import SolutionRegister
from src.assets import Assets
from src.external import ExternalHandler 
from src.logger import ProcessLogger  
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
    # 저작권 및 라이선스 고지문
    copyright_notice = """
    Copyright (c) 2024, ALO Software
    
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of ALO Software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.
    
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

    Contributor: Sehyun Song, Wonjun Sung, Woosung Jang
    """


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
        self._make_art(" Let's ALO  -  ! !")
        print_color(self.copyright_notice, 'BOLD')

        # logger 초기화
        self._init_logger()

        # 필요 class init
        self._init_class()

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

        self._get_alo_version()

        self.set_metadata(exp_plan_path, pipeline_type)
        # artifacts home 초기화 (from src.utils)
        self.system_envs['artifacts'] = self.artifact.set_artifacts()
        self.system_envs['train_history'] ={}
        self.system_envs['inference_history'] ={}
        if self.system_envs['boot_on'] and self.system is not None:
            self.q = init_redis(self.system)  ## from src.utils import init_redis

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
        if os.path.exists(ASSET_PACKAGE_PATH):
            shutil.rmtree(ASSET_PACKAGE_PATH)
            self.proc_logger.process_message(f"Folder '{ASSET_PACKAGE_PATH}' has been removed & regenerated.")
        os.makedirs(ASSET_PACKAGE_PATH)
        # [loop] only 운영 - pipeline은 inference_pipeline 1개로 고정된 상태 / 최초에 boot_on=True 상태 
        if self.loop: 
            # boot-on 
            try:
                pipe = self.system_envs['pipeline_list'][0] # inference_pipeline only 
                # set current pipeline into system envs
                self.system_envs['current_pipeline'] = pipe
                _log_process(f"{pipe} in loop")
                # execute pipline 
                pipeline = self._execute_pipeline(pipe) 
                _log_process(f"Finish boot-on")
                # 최초 boot_on 모드 동작 후 boot 모드 취소
                self.system_envs['boot_on'] = False
            except: 
                try: 
                    self.proc_logger.process_error("Failed to boot-on.")
                finally:
                    self._error_backup(self, pipe)
            # infinite loop 
            while True: 
                try:
                    # wait redis msg from edgeapp
                    msg_dict = self._get_redis_msg() 
                    self.system = msg_dict['solution_metadata']
                    self.set_metadata(pipeline_type=pipe.split('_')[0])
                    pipeline = self._execute_pipeline(pipe)
                    # redis runs state update 
                    self.system_envs['runs_status'] = pipeline.system_envs['runs_status']
                except:
                    # error 발생 시에도 redis runs state update 필요 (runs_status를 pipeline.py --> alo.py로 update해주기 위해)
                    self.system_envs['runs_status'] = pipeline.system_envs['runs_status']
                    _ = self.error_loop(pipe) # return & continue 
                    self.set_metadata(pipeline_type=pipe.split('_')[0]) # inference pipeline의 metadata 초기화 
        # [sagemaker] sagemaker run 시에 최초 boot_on 
        elif self.computing == 'sagemaker':
            try: 
                for pipe in self.system_envs['pipeline_list']:
                    self.system_envs['current_pipeline'] = pipe
                    _log_process(f"{pipe} in sagemaker")
                    # execute pipline  
                    pipeline = self._execute_pipeline(pipe)
                    if self.system_envs['boot_on'] == True: 
                        _log_process(f"Finish boot-on")
                    if 'train_pipeline' in pipe: 
                        self.sagemaker_runs() # sagemaker 클라우드 리소스 활용은 train 시에만 
                        # local 환경에서 inference를 한번 진행 하기전 boot_on은 False로 변경  
                        self.system_envs['boot_on'] = False
            except: 
                self.error_batch(pipe) 
        # [normal] batch execution
        else:  
            try:
                for pipe in self.system_envs['pipeline_list']:
                    self.system_envs['current_pipeline'] = pipe
                    _log_process(f"Current pipeline: {pipe}")
                    # execute pipline  
                    pipeline = self._execute_pipeline(pipe)
                    # pipeline.history()
            except:
                self.error_batch(pipe) 
    
    def _execute_pipeline(self, pipe): 
        try: 
            pipeline_start_time = time()
            pipeline = self.pipeline(pipeline_type=pipe)
            pipeline.setup()
            pipeline_setup_time = time()
            pipeline.load()
            pipeline_load_time = time()
            pipeline.run()
            pipeline_run_time = time()
            pipeline.save()
            pipeline_save_time = time()
            self.proc_logger.process_info(f"{pipe} setup time: {pipeline_setup_time-pipeline_start_time}") 
            self.proc_logger.process_info(f"{pipe} load time: {pipeline_load_time-pipeline_setup_time}") 
            self.proc_logger.process_info(f"{pipe} run time: {pipeline_run_time-pipeline_load_time}") 
            self.proc_logger.process_info(f"{pipe} save time: {pipeline_save_time-pipeline_run_time}") 
            self.proc_logger.process_info(f"{pipe} total time: {pipeline_save_time-pipeline_start_time}") 
            return pipeline 
        except: 
            self.proc_logger.process_error("Failed to execute pipeline.")
    
    def error_loop(self, pipe):
        # loop 일땐 error 발생시켜서 program을 죽이는 것이 아니라 warning만 하고 다시 loop 모드로 진입하여 대기 
        self.proc_logger.process_warning(f"==========       Error occurs in loop        ==========") 
        self.proc_logger.process_warning(traceback.format_exc())
        # backup error history & save error artifacts 
        self._error_backup(pipe)
        # [redis] send error status to edgeapp 
        fail_str = json.dumps({'status':'fail', 'message':traceback.format_exc()})
        if self.system_envs['runs_status'] == 'init':
            self.system_envs['q_inference_summary'].rput(fail_str)
            self.system_envs['q_inference_artifacts'].rput(fail_str)
        elif self.system_envs['runs_status'] == 'summary': # 이미 summary는 success로 보낸 상태 
            self.system_envs['q_inference_artifacts'].rput(fail_str) 
        return 
        
    def error_batch(self, pipe): 
        # backup error history & save error artifact
        # raise error and kill the program    
        try:  
            self.proc_logger.process_error(traceback.format_exc())
        finally:
            self._error_backup(pipe)   

    
    def _error_backup(self, pipe):
        ''' 
        1. backup error history
        2. save error artifacts 
        '''
        ## id 생성 
        sttime = self.system_envs['experimental_start_time']
        exp_name = self.system_envs['experimental_name']
        curr = self.system_envs['current_pipeline'].split('_')[0]
        random_number = '{:08}'.format(random.randint(0, 99999999))
        self.system_envs[f"{curr}_history"]['id'] = f'{sttime}-{random_number}-{exp_name}'
        # 에러 발생 시 self.control['backup_artifacts'] 가 True, False던 상관없이 무조건 backup (폴더명 뒤에 _error 붙여서) 
        # TODO error 발생 시엔 external save 되는 tar.gz도 다른 이름으로 해야할까 ? 
        self.artifact.backup_history(pipe, self.system_envs, backup_exp_plan=self.exp_yaml, error=True, size=self.control['backup_size'])
        # error 발생해도 external save artifacts 하도록        
        _ = self.ext_data.external_save_artifacts(pipe, self.external_path, self.external_path_permission)
        
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

    def register(self, solution_info=None, infra_setup=None,  train_id = '', inference_id = '', username='', password='', upload=True ):
        ## train_id 존재 검사. exp_plan 불러오기 
        meta = Metadata()
        exp_plan = meta.read_yaml(exp_plan_file=None)
        def _load_pipeline_expplan(pipeline_type, history_id, meta): #inner func.
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
        def _pipe_run(exp_plan, pipeline_type): #inner func.
            pipeline = self.pipeline(exp_plan, pipeline_type)
            pipeline.setup()
            pipeline.load()
            pipeline.run()
            pipeline.save()
        ## id 폴더에서 exp_plan 가져와서, pipeline 을 실행한다. (artifact 상태를 보장할 수 없으므로)
        if train_id != '':
            train_exp_plan = _load_pipeline_expplan('train', train_id, meta)
            _pipe_run(train_exp_plan, 'train_pipeline')    
        else:
            _pipe_run(exp_plan, 'train_pipeline')    
        if inference_id != '':
            inference_exp_plan = _load_pipeline_expplan('inference', inference_id, meta)
            _pipe_run(inference_exp_plan, 'inference_pipeline')
        else:
            print_color('experimental_plan: \n {}'.format(exp_plan), 'BOLD')
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
            register.login(username, password)
            register.run(username=username, password=password)
        return register
        

    #####################################
    ####    Part1. Initialization    ####
    #####################################
    def _make_art(self, str):
        ascii_art = pyfiglet.figlet_format(str, font="slant")
        print_color("=" * 80 + "\n", 'BOLD-CYAN')
        print_color(ascii_art, 'BOLD-CYAN')
        print_color("\n" + "=" * 80, 'BOLD-CYAN')
    
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

    def _init_class(self):
        _log_process("Start setting-up ALO source code into the memory..")
        # TODO 지우기 -> Pipeline 클래스에서 사용 예정
        self.ext_data = ExternalHandler()
        self.install = Packages()
        self.asset = Assets(ASSET_HOME)
        self.artifact = Aritifacts()
        self.meta = Metadata()
        _log_process("Finish setting-up ALO source code")

    def _set_alolib(self):
        """ALO 는 Master (파이프라인 실행) 와 slave (Asset 실행) 로 구분되어 ALO API 로 통신합니다. 
        기능 업데이트에 따라 API 의 버전 일치를 위해 Master 가 slave 의 버전을 확인하여 최신 버전으로 설치 되도록 강제한다.
        """
        _log_process("Start ALO library installation")
        # TODO 버전 mis-match 시, git 재설치하기. (미존재시, 에러 발생 시키기)
        try:
            if not os.path.exists(PROJECT_HOME + 'alolib'): 
                ALOMAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                repo = Repo(ALOMAIN)
                ALOVER = repo.active_branch.name
                # repository_url = ALO_LIB_URI
                # destination_directory = ALO_LIB
                cloned_repo = Repo.clone_from(ALO_LIB_URI, ALO_LIB, branch=ALOVER)
                self.proc_logger.process_message(f"alolib {ALOVER} git pull success.\n")
            else: 
                self.proc_logger.process_message("alolib already exists in local path.\n")
            alolib_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/alolib/"
            sys.path.append(alolib_path)
        except GitCommandError as e:
            self.proc_logger.process_error(e)
            raise NotImplementedError("alolib git pull failed.")
        req = os.path.join(alolib_path, "requirements.txt")
        # pip package의 안정성이 떨어지기 때문에 subprocess 사용을 권장함
        result = subprocess.run(['pip', 'install', '-r', req], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            self.proc_logger.process_message("Success installing alolib requirements.txt")
            self.proc_logger.process_message(result.stdout)
        else:
            self.proc_logger.process_error(f"Failed installing alolib requirements.txt : \n {result.stderr}")
        _log_process("Finish ALO library installation")
        
    def _get_alo_version(self):
        _log_process("Check ALO version")
        with open(PROJECT_HOME + '.git/HEAD', 'r') as f:
            ref = f.readline().strip()
        # ref는 형식이 'ref: refs/heads/브랜치명' 으로 되어 있으므로, 마지막 부분만 가져옵니다.
        if ref.startswith('ref:'):
            __version__ = ref.split('/')[-1]
        else:
            __version__ = ref  # Detached HEAD 상태 (브랜치명이 아니라 커밋 해시)
        self.system_envs['alo_version'] = __version__
        self.proc_logger.process_message(f"ALO version = {self.system_envs['alo_version']}")
        _log_process("Finish ALO version check")

    def set_metadata(self, exp_plan_path = DEFAULT_EXP_PLAN, pipeline_type = 'train_pipeline'):
        """ 실험 계획 (experimental_plan.yaml) 과 운영 계획(solution_metadata) 을 읽어옵니다.
        실험 계획 (experimental_plan.yaml) 은 입력 받은 config 와 동일한 경로에 있어야 합니다.  
        운영 계획 (solution_metadata) 은 입력 받은 solution_metadata 값과 동일한 경로에 있어야 합니다.
        """
        ## load solution_metadata
        sol_meta = self.load_solution_metadata()

        ## update system_envs
        self.system_envs['experimental_start_time'] = datetime.now(timezone.utc).strftime(TIME_FORMAT)
        self.system_envs['solution_metadata'] = sol_meta
        self.system_envs['experimental_plan_path'] = exp_plan_path

        ## load experimental_plan.yaml
        self.exp_yaml, sys_envs = self.load_exp_plan(sol_meta, exp_plan_path, self.system_envs)
        self._set_attr()
        # loop 모드면 항상 처음에 boot 모드
        if self.computing != 'local': #sagemaker
            self.system_envs = self._set_system_envs(pipeline_type, True, self.system_envs)
        else:
            if 'boot_on' in self.system_envs.keys(): # loop mode - boot on 이후 (boot on 꺼놨으므로 False임)
                self.system_envs = self._set_system_envs(pipeline_type, self.system_envs['boot_on'], self.system_envs)
            else: # loop mode - 최초 boot on 시 / 일반 flow  
                self.system_envs = self._set_system_envs(pipeline_type, self.loop, self.system_envs)
        # metadata까지 완성되면 출력
        if self.system_envs['boot_on'] == True: 
            self.proc_logger.process_message(f"==================== Start booting sequence... ====================")
        # ALO 설정 완료 info 와 로깅

    def _set_system_envs(self, pipeline_type, boot_on, _system_envs):
        _log_process("Setup ALO system environments")
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
        system_envs['loop'] = self.loop
        system_envs['start_time'] = datetime.now().strftime("%y%m%d_%H%M%S")
        if self.computing != 'local': # sagemaker in local 
            # FIXME sagemaker resource로 학습 후 로컬에서 inference 한 번 돌도록 설정 
            system_envs['pipeline_list'] = ['train_pipeline', 'inference_pipeline']
        elif boot_on:
            system_envs['pipeline_list'] = ['inference_pipeline']
        else:
            if pipeline_type == 'all':
                if os.getenv('COMPUTING') == 'sagemaker': # sagemaker in docker 
                    system_envs = self._set_sagemaker(system_envs)    
                else: 
                    system_envs['pipeline_list'] = [*self.user_parameters]
            else:
                system_envs['pipeline_list'] = [f"{pipeline_type}_pipeline"]

        self.proc_logger.process_message(f"system_envs['start_time']: {system_envs['experimental_start_time']}")
        self.proc_logger.process_message(f"system_envs['run_status']: {system_envs['runs_status']}")
        self.proc_logger.process_message(f"system_envs['pipeline_list']: {system_envs['pipeline_list']}")

        self.proc_logger.process_message(f"system_envs['pipeline_mode (main config.)']: {system_envs['pipeline_mode']}")
        self.proc_logger.process_message(f"system_envs['loop (main config.)']: {system_envs['loop']}")
        self.proc_logger.process_message(f"system_envs['boot_on (main config.)']: {system_envs['boot_on']}")
        _log_process("Finish ALO system environments setup")
        return system_envs

    def load_solution_metadata(self):
        # TODO solution meta version 관리 필요??
        # system 은 입력받은 solution metadata / args.system 이 *.yaml 이면 파일 로드하여 string 화 하여 입력 함
        _log_process("Load solution-metadata")
        filename = self.system
        if (filename is not None) and filename.endswith('.yaml'):
            try:
                with open(filename, encoding='UTF-8') as file:
                    content = yaml.load(file, Loader=yaml.FullLoader)  # 파일 내용을 읽고 자료구조로 변환
                # 로드한 YAML 내용을 JSON 문자열로 변환
                self.system = json.dumps(content)
            except FileNotFoundError:
                self.proc_logger.process_error(f"The file {filename} does not exist.")
        else:
            self.proc_logger.process_message("Solution metadata file name not entered. Skip updating solution metadata into experimental_plan.")
        _log_process("Finish loading solution-metadata")
        self.proc_logger.process_message(f"==========        Loaded solution_metadata: \n{json.loads(self.system)}")
        return json.loads(self.system) if self.system != None else None # None or dict from json 
    
    def load_exp_plan(self, sol_meta, experimental_plan, system_envs):
        _log_process("Load experimental_plan.yaml")
        exp_plan = self.meta.read_yaml(sol_me_file = sol_meta, exp_plan_file = experimental_plan, system_envs = system_envs)
        ## system_envs 를 linked 되어 있으므로, read_yaml 에서 update 된 사항이 자동 반영되어 있음
        _log_process("Finish loading experimental_plan.yaml")
        return exp_plan, system_envs 

    ########################################
    ####    Part2. Internal fuctions    ####
    ########################################
    def _set_sagemaker(self, system_envs):
        # # TODO 2.2.1 added (sagemaker 일 땐 학습만 진행)
        system_envs['pipeline_list'] = ["train_pipeline"]
        from sagemaker_training import environment      
        # save_train_artifacts_path를 sagemaker model 저장 경로로 변경 
        for i, v in enumerate(self.exp_yaml['external_path']):
            if 'save_train_artifacts_path' in v.keys(): 
                self.exp_yaml['external_path'][i] = {'save_train_artifacts_path': environment.Environment().model_dir}
        # docker 내에서 git에서 asset 다시 받으면 안되므로 무조건 once로 저장 
        for i, v in enumerate(self.exp_yaml['control']):
            if 'get_asset_source' in v.keys(): 
                self.exp_yaml['control'][i] = {'get_asset_source': 'once'}
        # pipline.py에서 바뀐 save path를 읽을 수 있게 yaml을 수정하여 저장
        self.meta.save_yaml(self.exp_yaml, DEFAULT_EXP_PLAN)
        return system_envs 
        
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
        self.proc_logger.process_message(f"The model is copied from {src_path} to {dst_path}.")
            
    def _external_load_data(self, pipeline):
        """외부 데이터를 가져 옴 (local storage, S3)

        Args:
          - pipelne (str): train / inference 인지를 구분함
        """
        ## from external.py
        self.ext_data.external_load_data(pipeline, self.external_path, self.external_path_permission, )

    def get_args(self, pipeline, step):
        if type(self.user_parameters[pipeline][step]['args']) == type(None):
            return dict()
        else:
            return self.user_parameters[pipeline][step]['args'][0]

    def _set_attr(self):
        self.user_parameters = self.meta.user_parameters
        self.asset_source = self.meta.asset_source
        self.external_path = self.meta.external_path
        self.external_path_permission = self.meta.external_path_permission
        self.control = self.meta.control

    def _get_redis_msg(self):
        # wait redis msg 
        start_msg = self.q.lget(isBlocking=True)
        if start_msg is not None:
            msg_dict = json.loads(start_msg.decode('utf-8')) ## 수정
        return msg_dict
