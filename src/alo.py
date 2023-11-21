import os
import sys
import json 
import shutil
import subprocess
from datetime import datetime
from collections import Counter
import pkg_resources
from copy import deepcopy
# local import
from src.constants import *
####################### ALO master requirements 리스트업 및 설치 #######################
# ALO master requirements 는 최우선 순위로 설치 > 만약 ALO master requirements는 aiplib v2.1인데 slave 제작자가 aiplib v2.2로 명시해놨으면 2.1이 우선 
try: 
    alo_ver = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    alolib_git = f'alolib @ git+http://10.185.66.38/hub/dxadvtech/aicontents-framework/alolib-source.git@{alo_ver}'
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
from src.utils import set_artifacts, setup_asset, match_steps, import_asset, release, backup_artifacts
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
        # wrangler 관련 
        self.system_envs['wrangler_code_uri'] = None
        self.system_envs['wrangler_dataset_uri'] = None
        # edgeapp interface 관련 
        self.system_envs['q_inference_summary'] = None 
        self.system_envs['q_inference_artifacts'] = None 
        self.system_envs['redis_host'] = None
        self.system_envs['redis_port'] = None
        
        
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
    

    def load_experimental_plan(self, exp_plan_file): # called at preset func.
        if exp_plan_file == None: 
            if os.path.exists(EXP_PLAN):
                return EXP_PLAN
            else: 
                self.proc_logger.process_error(f"<< {EXP_PLAN} >> not found.")
        else: 
            try: 
                # 입력한 경로가 로컬 절대경로인지 체크 
                _path, _file = os.path.split(exp_plan_file) 
                if os.path.isabs(_path) == True:
                    pass
                else: 
                    self.proc_logger.process_error(f"Only absolute local experimental_plan.yaml path is allowed for << --config >> option. \n You entered: {_path}")
                # 외부 exp plan yaml을 config/ 밑으로 복사 
                if _file in os.listdir(PROJECT_HOME + 'config/'):
                    self.proc_logger.process_warning(f"<< {_file} >> already exists in config directory. The file is overwritten.")
                try: 
                    shutil.copy(exp_plan_file, PROJECT_HOME + 'config/')
                except: 
                    self.proc_logger.process_error(f"Failed to copy << {exp_plan_file} >> into << {PROJECT_HOME + 'config/'} >>")
                # self.exp_plan_file 변수에 config/ 경로로 대입하여 return 
                return  PROJECT_HOME + 'config/' + _file 
            except: 
                self.proc_logger.process_error(f"Failed to load experimental plan. \n You entered for << --config >> : {_path}")
            
            
    def preset(self):
        # exp_plan_file은 config 폴더로 복사해서 가져옴. 단, 외부 exp plan 파일 경로는 로컬 절대 경로만 지원 
        self.exp_plan_file = self.load_experimental_plan(self.exp_plan_file) 
        self.proc_logger.process_info(f"Successfully loaded << experimental_plan.yaml >> from: \n {self.exp_plan_file}", color = 'green')
        if not os.path.exists(ASSET_HOME):
            try:
                os.makedirs(ASSET_HOME)
            except: 
                self.proc_logger.process_error(f"Failed to create directory: {ASSET_HOME}")
        self.read_yaml() # self.exp_plan default 셋팅 완료 
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
        # preset 과정도 logging 필요하므로 process logger에서는 preset 전에 실행되려면 alolib-source/asset.py에서 log 폴더 생성 필요 (artifacts 폴더 생성전)
        # 큼직한 단위의 alo.py에서의 로깅은 process logging (인자 X) - train, inference artifacts/log 양쪽에 다 남김 
        self.set_proc_logger()
        if self.system_envs['boot_on'] == True: 
            self.proc_logger.process_info(f"==================== Start booting sequence... ====================")
        self.proc_logger.process_info(f"Process start-time: {self.proc_start_time}")
        self.proc_logger.process_meta(f"ALO version = {self.alo_version}")
        self.proc_logger.process_info("==================== Start ALO preset ==================== ")
        self.preset()
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
            
            # solution meta가 존재 할 때 (운영 모드), save artifacts 경로 미입력 시 에러
            if self.sol_meta is not None:
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
            
            # wrangler code 및 데이터가 존재한다면 input 폴더 경로로 wrangling 해서 데이터 덮어쓰기부터 진행 
            # wrangler는 boot_on 이 아닐때만 작동 
            # TODO wrangler 종속 패키지는 이미 AIC에서 패키지 충돌 테스트 맞친 상태여야하고, ALO에서는 추후 asset 패키지들 다 설치한 이후 마지막에 설치한다 (boot-on때)
            # FIXME wrangler_dataset_uri 조건 필요할지? 
            # [참고] 아래 try 문 실행 시간 print문 하나만 넣었어도 0.04초 정도 소요 
            if (self.system_envs['wrangler_code_uri'] != None) and (self.system_envs['boot_on'] == False) and (pipeline == 'inference_pipeline'): # and (self.system_envs['wrangler_dataset_uri'] != None):
                wrangler_resp = None 
                try:
                    base_dir = os.path.basename(os.path.normpath(self.external_path['load_inference_data_path'])) + '/'
                    wrangler_data_path = INPUT_DATA_HOME + "inference/" + base_dir
                    wrangler_resp = subprocess.run(["python", self.system_envs['wrangler_code_uri'], "--data_path", wrangler_data_path], capture_output=True, check=False)
                    self.proc_logger.process_info(f"==================== Done wrangling \n {wrangler_resp.stdout.decode('utf-8')}", color='green')
                except:  
                    self.proc_logger.process_error(wrangler_resp.stderr.decode('utf-8'))
        
            # 각 asset import 및 실행 
            self.run_import(pipeline)

            # summary yaml를 redis q로 put. redis q는 _update_yaml 이미 set 완료  
            # solution meta 존재하면서 (운영 모드) & redis host none아닐때 (edgeapp 모드 > AIC 추론 경우는 아래 코드 미진입) & boot-on이 아닐 때 & inference_pipeline 일 때 save_summary 먼저 반환 필요 
            # FIXME train - inference pipeline type 일땐 괜찮나? 
            if (self.sol_meta is not None) and (self.system_envs['redis_host'] is not None) and (self.system_envs['boot_on'] == False) and (pipeline == 'inference_pipeline'):
                summary_dir = PROJECT_HOME + '.inference_artifacts/score/'
                if 'inference_summary.yaml' in os.listdir(summary_dir):
                    summary_str = json.dumps(get_yaml(summary_dir + 'inference_summary.yaml'))
                    self.system_envs['q_inference_summary'].rput(summary_str)
                    self.proc_logger.process_info("Completes putting inference summary into redis queue.", color='green')
                else: 
                    self.proc_logger.process_error("Failed to redis-put. << inference_summary.yaml >> not found.")
            
            # artifacts backup --> .history 
            if self.control['backup_artifacts'] == True:
                backup_artifacts(pipeline, self.exp_plan_file, self.proc_start_time)
            
            # solution meta가 존재 (운영 모드) 할 때는 artifacts 압축 전에 .*_artifacts/output/<step> 들 중 마지막 step sub-folder만 남기고 나머진 삭제 
            if self.sol_meta is not None:
                output_path = PROJECT_HOME + f".{pipeline_prefix}_artifacts/output/"    
                output_subdirs = os.listdir(output_path)
                last_output = None 
                for step in [item['step'] for item in self.asset_source[pipeline]]: 
                    if step in output_subdirs: 
                        last_output = step 
                for subdir in output_subdirs: 
                    if subdir != last_output: # last output이 아니면 삭제 
                        shutil.rmtree(output_path + subdir, ignore_errors=True)
                        self.proc_logger.process_info(f"Removed output sub-directory without last one: \n << {output_path + subdir} >>")
            
            # s3, nas 등 외부로 artifacts 압축해서 전달 (복사)      
            ext_saved_path = external_save_artifacts(pipeline, self.external_path, self.external_path_permission)
            # save artifacts가 완료되면 OK를 redis q로 put. redis q는 _update_yaml 이미 set 완료  
            # solution meta 존재하면서 (운영 모드) &  redis host none아닐때 (edgeapp 모드 > AIC 추론 경우는 아래 코드 미진입) & boot-on이 아닐 때 & inference_pipeline 일 때 save_summary 먼저 반환 필요 
            if (self.sol_meta is not None) and (self.system_envs['redis_host'] is not None) and (self.system_envs['boot_on'] == False) and (pipeline == 'inference_pipeline'):
                # 외부 경로로 잘 artifacts 복사 됐나 체크 
                if 'inference_artifacts.tar.gz' in os.listdir(ext_saved_path): # 외부 경로 (= edgeapp 단이므로 무조건 로컬경로)
                    artifacts_saved_str = json.dumps({"status": "OK"})
                    self.system_envs['q_inference_artifacts'].rput(artifacts_saved_str)
                    self.proc_logger.process_info("Completes putting artifacts creation OK signal into redis queue.", color='green')
                else: 
                    self.proc_logger.process_error("Failed to redis-put. << inference_artifacts.tar.gz >> not found.")
                    
            self.proc_finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.proc_logger.process_info(f"Process finish-time: {self.proc_finish_time}")
        
        
    
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
        
        # wrangler 정보 가져오기 (만약 둘 중 하나라도 부재 시 뒤쪽에서 wrangler.py 돌릴 때 에러날 것임)
        # FIXME wrangler 도 edgeapp only interface 일지? (train 땐 안한다고 했으니) --> 로컬에서 wrangler 붙여서 추론 실험해볼 수 있으니 일단 밖으로 뺌 
        if self.sol_meta['wrangler_code_uri'] == None: 
            self.proc_logger.process_info("<< wrangler_code_uri >> in the solution_metadata.yaml is << None >>")
        else: 
            self.system_envs['wrangler_code_uri'] = self.sol_meta['wrangler_code_uri']
            self.proc_logger.process_info(f"Success loading << wrangler_code_uri >>: {self.system_envs['wrangler_code_uri']}", color='green')
        if self.sol_meta['wrangler_dataset_uri'] == None: 
            self.proc_logger.process_info("<< wrangler_dataset_uri >> in the solution_metadata.yaml is << None >>")
        else:
            self.system_envs['wrangler_dataset_uri'] = self.sol_meta['wrangler_dataset_uri']
            # [중요] wrangler_dataset_uri를 external path의 load_inference_data_path로 지정
            self.proc_logger.process_info(f"Success loading << wrangler_dataset_uri >>: {self.system_envs['wrangler_dataset_uri']}", color='green')
        
        # EdgeAPP 전용 : redis server uri 있으면 가져오기 (없으면 pass >> AIC 대응) 
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
                sol_args = sol_step_dict['args']
                # sol_args None이면 패스 
                if sol_args is None: 
                    continue
                for idx, plan_step_dict in enumerate(init_exp_plan):  
                    if sol_step == plan_step_dict['step']:
                        self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'][idx]['args'][0].update(sol_args)
                        # [중요] input_path에 뭔가 써져 있으면, system 인자 존재 시에는 해당 란 비운다. 
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
                        # [중요] wrangler_dataset_uri 존재 시 external path의 load_inference_data_path로 덮어쓰기 
                        if self.system_envs['wrangler_dataset_uri'] is not None: 
                            self.exp_plan['external_path'][idx]['load_inference_data_path'] = self.system_envs['wrangler_dataset_uri']
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
        asset_structure = AssetStructure() 
        # asset structure envs pipeline 별 공통부 
        asset_structure.envs['project_home'] = PROJECT_HOME
        asset_structure.envs['pipeline'] = pipeline
        asset_structure.envs['solution_metadata_version'] = self.system_envs['solution_metadata_version']
        asset_structure.envs['artifacts'] = self.artifacts
        asset_structure.envs['alo_version'] = self.alo_version
        if self.control['interface_mode'] not in INTERFACE_TYPES:
            self.proc_logger.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")
        asset_structure.envs['interface_mode'] = self.control['interface_mode']
        asset_structure.envs['proc_start_time'] = self.proc_start_time
        asset_structure.envs['save_train_artifacts_path'] = self.external_path['save_train_artifacts_path']
        asset_structure.envs['save_inference_artifacts_path'] = self.external_path['save_inference_artifacts_path']
        
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

        
