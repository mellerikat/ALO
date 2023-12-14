import os
import sys
import json 
import shutil
import subprocess
import traceback
from datetime import datetime
from collections import Counter
from src.constants import *
# local import
#######################################################################################
# alolib 설치 

def set_alolib():
    if not os.path.exists(PROJECT_HOME + 'alolib'): 
        repository_url = "http://mod.lge.com/hub/dxadvtech/aicontents-framework/alolib-source.git"
        destination_directory = "./alolib"
        result = subprocess.run(['git', 'clone', repository_url, destination_directory], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
    else:
        print("패키지 설치 실패")
        print(result.stderr)
        
set_alolib()

#######################################################################################
from src.install import *
from src.utils import set_artifacts, setup_asset, match_steps, import_asset, release, backup_artifacts, move_output_files
from src.compare_yamls import get_yaml, compare_yaml
from src.external import external_load_data, external_load_model, external_save_artifacts
from src.redisqueue import RedisQueue
from alolib import logger  


class AssetStructure: 
    def __init__(self):
        self.envs = {}
        self.args = {}
        self.data = {} 
        self.config = {}


class ALO:
    def __init__(self, exp_plan_file = None, sol_meta_str = None, alo_mode = 'all', boot_on = False):
        self.proc_start_time = datetime.now().strftime("%y%m%d_%H%M%S")
        self.exp_plan_file = exp_plan_file
        self.sol_meta = json.loads(sol_meta_str) if sol_meta_str != None else None # None or dict from json 
        # solution metadata를 통해, 혹은 main.py 실행 시 인자로 받는 정보는 system_envs로 wrapping 
        self.system_envs = {}
        self.set_system_envs() 
        self.system_envs['alo_mode'] = alo_mode 
        self.system_envs['boot_on'] = boot_on 
        
        self.exp_plan = None
        self.artifacts = None 
        self.proc_logger = None

        self.alo_version = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()


    def set_system_envs(self):
        # solution meta 버전 
        self.system_envs['solution_metadata_version'] = None 
        # edgeapp interface 관련 
        self.system_envs['q_inference_summary'] = None 
        self.system_envs['q_inference_artifacts'] = None 
        self.system_envs['redis_host'] = None
        self.system_envs['redis_port'] = None
        # 'init': initial status / 'summary': success until 'q_inference_summary'/ 'artifacts': success until 'q_inference_artifacts'
        self.system_envs['runs_status'] = 'init'
        # edgeconductor interface 관련 
        self.system_envs['inference_result_datatype'] = None 
        self.system_envs['train_datatype'] = None 


    def set_proc_logger(self):
        # 새 runs 시작 시 기존 log 폴더 삭제 
        train_log_path = PROJECT_HOME + ".train_artifacts/log/"
        inference_log_path = PROJECT_HOME + ".inference_artifacts/log/"
        try: 
            if os.path.exists(train_log_path):
                shutil.rmtree(train_log_path, ignore_errors=True)
            if os.path.exists(inference_log_path):
                shutil.rmtree(inference_log_path, ignore_errors=True)
        except: 
            raise NotImplementedError("Failed to empty log directory.")
        # redundant 하더라도 processlogger은 train, inference 양쪽 다남긴다. 
        self.proc_logger = logger.ProcessLogger(PROJECT_HOME)  


    def load_experimental_plan(self, exp_plan_file_path): # called at preset func.
        if exp_plan_file_path == None: 
            if os.path.exists(EXP_PLAN):
                return EXP_PLAN
            else: 
                self.proc_logger.process_error(f"<< {EXP_PLAN} >> not found.")
        else: 
            try: 
                # 입력한 경로가 상대 경로이면 config 기준으로 경로 변환  
                _path, _file = os.path.split(exp_plan_file_path) 
                if os.path.isabs(_path) == True:
                    pass
                else: 
                    exp_plan_file_path = PROJECT_HOME + 'config/' + exp_plan_file_path  
                    _path, _file = os.path.split(exp_plan_file_path) 
                # 경로가 config랑 동일하면 (samefile은 dir, file 다 비교가능) 그냥 바로 return 
                if os.path.samefile(_path, PROJECT_HOME + 'config/'): 
                    self.proc_logger.process_info(f"Successfully loaded experimental plan yaml: \n {PROJECT_HOME + 'config/' + _file}")
                    return  PROJECT_HOME + 'config/' + _file 
                
                # 경로가 config랑 동일하지 않으면 
                # 외부 exp plan yaml을 config/ 밑으로 복사 
                if _file in os.listdir(PROJECT_HOME + 'config/'):
                    self.proc_logger.process_warning(f"<< {_file} >> already exists in config directory. The file is overwritten.")
                try: 
                    shutil.copy(exp_plan_file_path, PROJECT_HOME + 'config/')
                except: 
                    self.proc_logger.process_error(f"Failed to copy << {exp_plan_file_path} >> into << {PROJECT_HOME + 'config/'} >>")
                # self.exp_plan_file 변수에 config/ 경로로 대입하여 return 
                self.proc_logger.process_info(f"Successfully loaded experimental plan yaml: \n {PROJECT_HOME + 'config/' + _file}")
                return  PROJECT_HOME + 'config/' + _file 
            except: 
                self.proc_logger.process_error(f"Failed to load experimental plan. \n You entered for << --config >> : {exp_plan_file_path}")
            
            
    def preset(self):
        # exp_plan_file은 config 폴더로 복사해서 가져옴. 단, 외부 exp plan 파일 경로는 로컬 절대 경로만 지원 
        self.exp_plan_file = self.load_experimental_plan(self.exp_plan_file) 
        self.proc_logger.process_info(f"Successfully loaded << experimental_plan.yaml >> from: \n {self.exp_plan_file}") 
        if not os.path.exists(ASSET_HOME):
            try:
                os.makedirs(ASSET_HOME)
            except: 
                self.proc_logger.process_error(f"Failed to create directory: {ASSET_HOME}")
        try:
            self.read_yaml() # self.exp_plan default 셋팅 완료 
        except: 
            self.proc_logger.process_error("Failed to read experimental plan yaml.")
        # artifacts 세팅
        # FIXME train만 돌든 inference만 돌든 일단 artifacts 폴더는 둘다 만든다 
        self.artifacts = set_artifacts()
        # step들이 잘 match 되게 yaml에 기술 돼 있는지 체크
        match_steps(self.user_parameters, self.asset_source)


    def external_load_data(self, pipeline):
        external_load_data(pipeline, self.external_path, self.external_path_permission, self.control['get_external_data'])


    def external_load_model(self):
        external_load_model(self.external_path, self.external_path_permission)


    def runs(self):
        try: 
            # preset 과정도 logging 필요하므로 process logger에서는 preset 전에 실행되려면 alolib-source/asset.py에서 log 폴더 생성 필요 (artifacts 폴더 생성전)
            # 큼직한 단위의 alo.py에서의 로깅은 process logging (인자 X) - train, inference artifacts/log 양쪽에 다 남김 
            self.set_proc_logger()
            if self.system_envs['boot_on'] == True: 
                self.proc_logger.process_info(f"==================== Start booting sequence... ====================")
            else: 
                self.proc_logger.process_meta(f"Loaded solution_metadata: \n{self.sol_meta}\n")
            self.proc_logger.process_info(f"Process start-time: {self.proc_start_time}")
            self.proc_logger.process_meta(f"ALO version = {self.alo_version}")
            self.proc_logger.process_info("==================== Start ALO preset ==================== ")
            try:
                self.preset()
            except:
                self.proc_logger.process_error("Failed to preset ALO.")
            self.proc_logger.process_info("==================== Finish ALO preset ==================== ")
            
            for pipeline in self.asset_source:
                # alo mode (운영 시에는 SOLUTION_PIPELINE_MODE와 동일)에 따른 pipeline run 분기 
                if self.system_envs['alo_mode'] == 'train':
                    if 'inf' in pipeline: 
                        continue
                elif self.system_envs['alo_mode'] == 'inf' or self.system_envs['alo_mode'] == 'inference':
                    if 'train' in pipeline:
                        continue
                elif self.system_envs['alo_mode'] == 'all':
                    pass
                else:
                    raise ValueError(f"{self.system_envs['alo_mode']} is not supported mode.")
                
                # TODO 추후 멀티 파이프라인 시에는 아래 코드 수정 필요 (ex. train0, train1..)
                pipeline_prefix = pipeline.split('_')[0] # ex. train_pipeline --> train 
                # 현재 파이프라인에 대응되는 artifacts 폴더 비우기 
                # [주의] 단 .~_artifacts/log 폴더는 지우지 않기! 
                self.empty_artifacts(pipeline_prefix)
                
                if pipeline not in ['train_pipeline', 'inference_pipeline']:
                    self.proc_logger.process_error(f'Pipeline name in the experimental_plan.yaml \n It must be << train_pipeline >> or << inference_pipeline >>')
                # summary yaml를 redis q로 put. redis q는 _update_yaml 에서 이미 set 완료  
                # solution meta 존재하면서 (운영 모드) & redis host none아닐때 (edgeapp 모드 > AIC 추론 경우는 아래 코드 미진입) & boot-on이 아닐 때 & inference_pipeline 일 때 save_summary 먼저 반환 필요 
                # FIXME train - inference pipeline type 일땐 괜찮나? 
                # Edgeapp과 interface 중인지 (운영 모드인지 체크)
                self.is_operation_mode = (self.sol_meta is not None) and (self.system_envs['redis_host'] is not None) \
                    and (self.system_envs['boot_on'] == False) and (pipeline == 'inference_pipeline')

                # solution meta가 존재 할 때 (운영 모드), save artifacts 경로 미입력 시 에러
                if self.is_operation_mode:
                    if self.external_path[f"save_{pipeline_prefix}_artifacts_path"] is None:  
                        self.proc_logger.process_error(f"You did not enter the << save_{pipeline_prefix}_artifacts_path >> in the experimental_plan.yaml") 
                
                # 외부 데이터 가져오기 (boot on 시엔 skip)
                if self.system_envs['boot_on'] == False:
                    # [중요] wrangler_dataset_uri 가 solution_metadata.yaml에 존재했다면,
                    # 이미 _update_yaml할 때 exeternal load inference data path로 덮어쓰기 된 상태
                    self.external_load_data(pipeline)
                    
                # inference pipeline 인 경우, plan yaml의 load_model_path 가 존재 시 .train_artifacts/models/ 를 비우고 외부 경로에서 모델을 새로 가져오기   
                # 왜냐하면 train - inference 둘 다 돌리는 경우도 있기때문 
                # FIXME boot on 때도 모델은 일단 있으면 가져온다 ? 

                if pipeline == 'inference_pipeline':
                    if (self.external_path['load_model_path'] != None) and (self.external_path['load_model_path'] != ""): 
                        self.external_load_model() 

                # 각 asset import 및 실행 
                try:
                    self.run_import(pipeline)
                except: 
                    self.proc_logger.process_error(f"Failed to run import: {pipeline}")
                
                if self.is_operation_mode:
                    summary_dir = PROJECT_HOME + '.inference_artifacts/score/'
                    if 'inference_summary.yaml' in os.listdir(summary_dir):
                        summary_dict = get_yaml(summary_dir + 'inference_summary.yaml')
                        self.success_str = json.dumps({'status':'success', 'message': summary_dict})
                        self.system_envs['q_inference_summary'].rput(self.success_str)
                        self.proc_logger.process_info("Successfully completes putting inference summary into redis queue.")
                        self.system_envs['runs_status'] = 'summary'
                    else: 
                        self.proc_logger.process_error("Failed to redis-put. << inference_summary.yaml >> not found.")
      
                # solution meta가 존재 (운영 모드) 할 때는 artifacts 압축 전에 .inference_artifacts/output/<step> 들 중 
                # solution_metadata yaml의 edgeconductor_interface를 참고하여 csv 생성 마지막 step의 csv, jpg 생성 마지막 step의 jpg (혹은 png, jpeg)를 
                # .inference_artifacts/output/ 바로 하단 (step명 없이)으로 move한다 (copy (x) : cost down 목적)
                if self.is_operation_mode:
                    try:
                        move_output_files(pipeline, self.asset_source, self.system_envs['inference_result_datatype'], self.system_envs['train_datatype'])
                    except: 
                        self.proc_logger.process_error("Failed to move output files for edge conductor view.")
                        
                # s3, nas 등 외부로 artifacts 압축해서 전달 (복사)
                try:      
                    ext_saved_path = external_save_artifacts(pipeline, self.external_path, self.external_path_permission)
                except:
                    self.proc_logger.process_error("Failed to save artifacts into external path.") 
                
                # artifacts backup --> .history 
                if self.control['backup_artifacts'] == True:
                    try:
                        backup_artifacts(pipeline, self.exp_plan_file, self.proc_start_time, size=self.control['backup_size'])
                    except: 
                        self.proc_logger.process_error("Failed to backup artifacts into << .history >>") 
                # save artifacts가 완료되면 OK를 redis q로 put. redis q는 _update_yaml 이미 set 완료  
                # solution meta 존재하면서 (운영 모드) &  redis host none아닐때 (edgeapp 모드 > AIC 추론 경우는 아래 코드 미진입) & boot-on이 아닐 때 & inference_pipeline 일 때 save_summary 먼저 반환 필요 
                if self.is_operation_mode:
                    # 외부 경로로 잘 artifacts 복사 됐나 체크 (edge app에선 고유한 경로로 항상 줄것임)
                    if 'inference_artifacts.tar.gz' in os.listdir(ext_saved_path): # 외부 경로 (= edgeapp 단이므로 무조건 로컬경로)
                        self.system_envs['q_inference_artifacts'].rput(self.success_str) # summary yaml을 다시 한번 전송 
                        self.proc_logger.process_info("Completes putting artifacts creation << success >> signal into redis queue.")
                        self.system_envs['runs_status'] = 'artifacts'
                    else: 
                        self.proc_logger.process_error("Failed to redis-put. << inference_artifacts.tar.gz >> not found.")
                        
                self.proc_finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.proc_logger.process_info(f"Process finish-time: {self.proc_finish_time}")
        except: 
            # [ref] https://medium.com/@rahulkumar_33287/logger-error-versus-logger-exception-4113b39beb4b 
            # [ref2] https://stackoverflow.com/questions/3702675/catch-and-print-full-python-exception-traceback-without-halting-exiting-the-prog
            # + traceback.format_exc() << 이 방법은 alolib logger에서 exc_info=True 안할 시에 사용가능
            try:  # 여기에 try, finally 구조로 안쓰면 main.py 로 raise 되버리면서 backup_artifacts가 안됨 
                self.proc_logger.process_error("Failed to ALO runs():\n" + traceback.format_exc()) #+ str(e)) 
            finally:
                # 에러 발생 시 self.control['backup_artifacts'] 가 True, False던 상관없이 무조건 backup (폴더명 뒤에 _error 붙여서) 
                backup_artifacts(pipeline, self.exp_plan_file, self.proc_start_time, error=True, size=self.control['backup_size'])
                # TODO error 발생 시엔 external save 되는 tar.gz도 다른 이름으로 해야할까 ? 
                # error 발생해도 external save artifacts 하도록                
                ext_saved_path = external_save_artifacts(pipeline, self.external_path, self.external_path_permission)
                if self.is_operation_mode:
                    fail_str = json.dumps({'status':'fail', 'message':traceback.format_exc()})
                    if self.system_envs['runs_status'] == 'init':
                        self.system_envs['q_inference_summary'].rput(fail_str)
                        self.system_envs['q_inference_artifacts'].rput(fail_str)
                    elif self.system_envs['runs_status'] == 'summary': # 이미 summary는 success로 보낸 상태 
                        self.system_envs['q_inference_artifacts'].rput(fail_str)
      
                
    def empty_artifacts(self, pipe_prefix): 
        '''
        - pipe_prefix: 'train', 'inference'
        - 주의: log 폴더는 지우지 않기 
        '''
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
            
            
    def read_yaml(self):
        self.exp_plan = get_yaml(self.exp_plan_file)
        self.exp_plan = compare_yaml(self.exp_plan) # plan yaml을 최신 compare yaml 버전으로 업그레이드 

        # solution metadata yaml --> exp plan yaml overwrite 
        if self.sol_meta is not None:
            self._update_yaml() 
            self.proc_logger.process_info("Finish updating solution_metadata.yaml --> experimental_plan.yaml")
        
        def get_yaml_data(key): # inner func.
            data_dict = {}
            for data in self.exp_plan[key]:
                data_dict.update(data)
            return data_dict

        # 각 key 별 value 클래스 self 변수화 
        for key in self.exp_plan.keys():
            setattr(self, key, get_yaml_data(key))


    def _update_yaml(self):  
        '''
        sol_meta's << dataset_uri, artifact_uri, selected_user_parameters ... >> into exp_plan 
        '''
        # [중요] SOLUTION_PIPELINE_MODE라는 환경 변수는 ecr build 시 생성하게 되며 (ex. train, inference, all) 이를 ALO mode에 덮어쓰기 한다. 
        sol_pipe_mode = os.getenv('SOLUTION_PIPELINE_MODE')
        if sol_pipe_mode is not None: 
            self.system_envs['alo_mode'] = sol_pipe_mode
        else:   
            raise OSError("Environmental variable << SOLUTION_PIPELINE_MODE >> is not set.")
        # solution metadata version 가져오기 --> inference summary yaml의 version도 이걸로 통일 
        self.system_envs['solution_metadata_version'] = self.sol_meta['version']
        # solution metadata yaml에 pipeline key 있는지 체크 
        if 'pipeline' not in self.sol_meta.keys(): # key check 
            self.proc_logger.process_error("Not found key << pipeline >> in the solution metadata yaml file.") 
        
        # EdgeConductor Interface
        self.system_envs['inference_result_datatype'] = self.sol_meta['edgeconductor_interface']['inference_result_datatype']
        self.system_envs['train_datatype'] =  self.sol_meta['edgeconductor_interface']['train_datatype']
        if (self.system_envs['inference_result_datatype'] not in ['image', 'table']) or (self.system_envs['train_datatype'] not in ['image', 'table']):
            self.proc_logger.process_error(f"Only << image >> or << table >> is supported for \n \
                train_datatype & inference_result_datatype of edge-conductor interface.")
        
        # EdgeAPP Interface : redis server uri 있으면 가져오기 (없으면 pass >> AIC 대응) 
        def _check_edgeapp_interface(): # inner func.
            if 'edgeapp_interface' not in self.sol_meta.keys():
                return False 
            if 'redis_server_uri' not in self.sol_meta['edgeapp_interface'].keys():
                return False 
            if self.sol_meta['edgeapp_interface']['redis_server_uri'] == None:
                return False
            if self.sol_meta['edgeapp_interface']['redis_server_uri'] == "":
                return False 
            return True 
        
        if _check_edgeapp_interface() == True: 
            try: 
                # get redis server host, port 
                self.system_envs['redis_host'], _redis_port = self.sol_meta['edgeapp_interface']['redis_server_uri'].split(':')
                self.system_envs['redis_port'] = int(_redis_port)
                if (self.system_envs['redis_host'] == None) or (self.system_envs['redis_port'] == None): 
                    self.proc_logger.process_error("Missing host or port of << redis_server_uri >> in solution metadata.")
                # set redis queues
                self.system_envs['q_inference_summary'] = RedisQueue('inference_summary', host=self.system_envs['redis_host'], port=self.system_envs['redis_port'], db=0)
                self.system_envs['q_inference_artifacts'] = RedisQueue('inference_artifacts', host=self.system_envs['redis_host'], port=self.system_envs['redis_port'], db=0)
            except: 
                self.proc_logger.process_error(f"Failed to parse << redis_server_uri >>") 
                
        # TODO: multi (list), single (str) 일때 모두 실험 필요 
        for sol_pipe in self.sol_meta['pipeline']: 
            pipe_type = sol_pipe['type'] # train, inference 
            artifact_uri = sol_pipe['artifact_uri']
            dataset_uri = sol_pipe['dataset_uri']
            selected_params = sol_pipe['parameters']['selected_user_parameters']  
            # plan yaml에서 현재 sol meta pipe type의 index 찾기 
            cur_pipe_idx = None 
            for idx, plan_pipe in enumerate(self.exp_plan['user_parameters']):
                # pipeline key가 하나이고, 해당 pipeline에 대응되는 plan yaml pipe가 존재할 시 
                if (len(plan_pipe.keys()) == 1) and (f'{pipe_type}_pipeline' in plan_pipe.keys()): 
                    cur_pipe_idx = idx 
                
            # selected params를 exp plan으로 덮어 쓰기 
            init_exp_plan = self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'].copy()
            for sol_step_dict in selected_params: 
                sol_step = sol_step_dict['step']
                sol_args = sol_step_dict['args'] #[주의] solution meta v9 기준 elected user params의 args는 list아니고 dict
                # sol_args None 이거나 []이면 패스 
                # FIXME (231202 == [] 체크추가) 종원선임님처럼 마지막에 custom step 붙일 때 - args: null
                # 라는 식으로 args 가 필요없는 step이면 업데이트를 시도하는거 자체가 잘못된거고 스킵되는게 맞다
                if sol_step != 'input':
                    if (sol_args is None) or (sol_args == {}) or (len(sol_args) == 0): 
                        continue
                for idx, plan_step_dict in enumerate(init_exp_plan):  
                    if sol_step == plan_step_dict['step']:
                        self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'][idx]['args'][0].update(sol_args) #dict update
                        # [중요] input_path에 뭔가 써져 있으면, system 인자 존재 시에는 해당 란 비운다. (그냥 s3에서 다운받으면 그 밑에있는거 다사용하도록) 
                        if sol_step == 'input':
                            self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'][idx]['args'][0]['input_path'] = None
            
            # external path 덮어 쓰기 
            if pipe_type == 'train': 
                for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                    if 'load_train_data_path' in ext_dict.keys(): 
                        self.exp_plan['external_path'][idx]['load_train_data_path'] = dataset_uri 
                    if 'save_train_artifacts_path' in ext_dict.keys(): 
                        self.exp_plan['external_path'][idx]['save_train_artifacts_path'] = artifact_uri          
            elif pipe_type == 'inference':
                for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                    if 'load_inference_data_path' in ext_dict.keys():
                        self.exp_plan['external_path'][idx]['load_inference_data_path'] = dataset_uri  
                    if 'save_inference_artifacts_path' in ext_dict.keys():  
                        self.exp_plan['external_path'][idx]['save_inference_artifacts_path'] = artifact_uri 
                    # inference type인 경우 model_uri를 plan yaml의 external_path의 load_model_path로 덮어쓰기
                    if 'load_model_path' in ext_dict.keys():
                        self.exp_plan['external_path'][idx]['load_model_path'] = sol_pipe['model_uri']
            else: 
                self.proc_logger.process_error(f"Unsupported pipeline type for solution metadata yaml: {pipe_type}")

        # [중요] system 인자가 존재해서 _update_yaml이 실행될 때는 항상 get_external_data를 every로한다. every로 하면 항상 input/train (or input/inference)를 비우고 새로 데이터 가져온다.
        self.exp_plan['control'][0]['get_external_data'] = 'every'

        
    def install_steps(self, pipeline, get_asset_source):
        requirements_dict = dict() 
        for step, asset_config in enumerate(self.asset_source[pipeline]):
            # self.asset.setup_asset 기능 :
            # local or git pull 결정 및 scripts 폴더 내에 위치시킴 
            setup_asset(asset_config, get_asset_source)
            requirements_dict[asset_config['step']] = asset_config['source']['requirements']
        
        check_install_requirements(requirements_dict)


    def set_asset_structure(self):
        self.asset_structure = AssetStructure() 
        
        self.asset_structure.envs['project_home'] = PROJECT_HOME
        
        self.asset_structure.envs['solution_metadata_version'] = self.system_envs['solution_metadata_version']
        self.asset_structure.envs['artifacts'] = self.artifacts
        self.asset_structure.envs['alo_version'] = self.alo_version
        if self.control['interface_mode'] not in INTERFACE_TYPES:
            self.proc_logger.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")
        self.asset_structure.envs['interface_mode'] = self.control['interface_mode']
        self.asset_structure.envs['proc_start_time'] = self.proc_start_time
        self.asset_structure.envs['save_train_artifacts_path'] = self.external_path['save_train_artifacts_path']
        self.asset_structure.envs['save_inference_artifacts_path'] = self.external_path['save_inference_artifacts_path']


    def run_import(self, pipeline):
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
            self.install_steps(pipeline, get_asset_source)
        
        # AssetStructure instance 생성 
        self.set_asset_structure()

        for step, asset_config in enumerate(self.asset_source[pipeline]):    
            self.proc_logger.process_info(f"==================== Start pipeline: {pipeline} / step: {asset_config['step']}")
            # 외부에서 arg를 가져와서 수정이 가능한 구조를 위한 구조
            self.asset_structure.args = self.get_args(pipeline, step)
            try: 
                self.asset_structure = self.process_asset_step(asset_config, step, pipeline, self.asset_structure)
            except: 
                self.proc_logger.process_error(f"Failed to process step: << {asset_config['step']} >>")
                

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
        user_asset = import_asset(_path, _file)
        if self.system_envs['boot_on'] == True: 
            self.proc_logger.process_info(f"===== Booting... completes importing << {_file} >>")
            return asset_structure

        # 사용자가 config['meta'] 를 통해 볼 수 있는 가변 부
        # FIXME step은 추후 삭제되야함, meta --> metadata 같은 식으로 약어가 아닌 걸로 변경돼야 함 
        meta_dict = {'artifacts': self.artifacts, 'pipeline': pipeline, 'step': step, 'step_number': step, 'step_name': self.user_parameters[pipeline][step]['step']}
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
                release(_path)
                sys.path = [item for item in sys.path if asset_structure.envs['step'] not in item]
            else:
                pass
        except:
            release(_path)
            sys.path = [item for item in sys.path if asset_structure.envs['step'] not in item]
        
        self.proc_logger.process_info(f"==================== Finish pipeline: {pipeline} / step: {asset_config['step']}")
        
        return asset_structure

        
