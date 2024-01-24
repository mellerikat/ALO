import os
import sys
import json 
import shutil
import traceback
from datetime import datetime
from collections import Counter
from copy import deepcopy 
import subprocess
# local import
from src.constants import *
from src.artifacts import Aritifacts
from src.install import Packages

# 이름을 한번 다시 생각
from src.assets import Assets

from src.external import ExternalHandler #external_load_data, external_load_model, external_save_artifacts
from src.redisqueue import RedisQueue
from src.logger import ProcessLogger  
# s3를 옮김
from src.sagemaker_handler import SagemakerHandler 
from src.yaml import ExperimentalPlan
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
    def __init__(self, exp_plan_file = None, solution_metadata = None, pipeline_type = 'all', boot_on = False, computing = 'local'):
        """실험 계획 (experimental_plan.yaml), 운영 계획(solution_metadata), 
        파이프라인 종류(train, inference), 동작방식(always-on) 에 대한 설정을 완료함

        Args:
            exp_plan_file: 실험 계획 (experimental_plan.yaml) 을 yaml 파일 위치로 받기
            solution_metadata: 운영 계획 (solution_metadata(str)) 정보를 string 으로 받기
            pipeline_type: 파이프라인 모드 (all, train, inference)
            boot_on: always-on 시, boot 과정 인지 아닌지를  구분 (True, False)
            computing: 학습하는 컴퓨팅 자원 (local, sagemaker)
        Returns:
        """
        # 필요 class init
        self.ext_data = ExternalHandler()
        self.install = Packages()
        self.asset = Assets(ASSET_HOME)
        self.artifact = Aritifacts()
        # alolib을 설치
        alolib = self.install.set_alolib()
        if not alolib:
            raise ValueError("ALOLIB이 설치 되지 않아 프로그램을 종료합니다.")

        # 필요한 전역변수 선언
        self.exp_plan = None
        self.proc_logger = None
        self.package_list = []

        if exp_plan_file == "" or exp_plan_file == None:
            self.exp_plan_file = "./config/experimental_plan.yaml"
        else:
            self.exp_plan_file = exp_plan_file
        self.pipeline_type = pipeline_type
        self.boot_on = boot_on

        # logger 초기화
        self.init_logger()
        
        # init solution metadata
        self.sol_meta = json.loads(solution_metadata) if solution_metadata != None else None # None or dict from json 

    def init(self, url = None):
        '''
        git clone --no-checkout http://mod.lge.com/hub/dxadvtech/aicontents/tcr.git
        echo "config/experimental_plan.yaml" >> .git/info/sparse-checkout
        git checkout
        '''

        if url != None:
            self._sparse_checkout_copy(url)
        else:
            def is_file_in_folder():
                # 파일의 전체 경로를 구성
                file_path = EXP_PLAN

                # 파일이 존재하는지 확인
                return os.path.exists(file_path)
            if is_file_in_folder():
                pass
            else:
                print("experimental_plan 이 없습니다. alo.init을 통해 yaml을 설치해주세요. alo.init(git_url)")
        
        system_envs = {}

        self.experimental_plan = ExperimentalPlan(self.exp_plan_file, self.sol_meta)
        self.exp_plan_file, system_envs = self.experimental_plan.read_yaml(system_envs)

        self._set_attr()

        self.system_envs = self._set_system_envs(self.pipeline_type, self.boot_on, system_envs) 

        # 현재 ALO 버전
        self.alo_version = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()

        # ALO 설정 완료 info 와 로깅
        self._alo_info()

        # artifacts home 초기화 (from src.utils)
        self.artifacts = self.artifact.set_artifacts()
    
    def _sparse_checkout_copy(self, url):
        file_path = "config/experimental_plan.yaml"  # 복사할 파일 경로
        target_dir = PROJECT_HOME + "config"  # 파일을 복사할 대상 경로

        # 저장소 이름 추출
        repo_name = url.split('/')[-1]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]

        # 저장소 클론
        subprocess.run(['git', 'clone', url])

        # 파일이 존재하는지 확인
        source_file_path = os.path.join(repo_name, file_path)
        if not os.path.exists(source_file_path):
            print("The specified file does not exist in the repository.")
        else:
            # 대상 디렉토리가 존재하는지 확인하고, 없으면 생성
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            # 파일 복사
            target_file_path = os.path.join(target_dir, os.path.basename(file_path))
            shutil.copyfile(source_file_path, target_file_path)
            print(f"File copied successfully to {target_file_path}")

            shutil.rmtree(PROJECT_HOME + repo_name)
    
    #############################
    ####    Main Function    ####
    #############################
    def runs(self, mode = None):
        """ 파이프라인 실행에 필요한 데이터, 패키지, Asset 코드를 작업환경으로 setup 하고 & 순차적으로 실행합니다. 

        학습/추론 파이프라인을 순차적으로 실행합니다. (각 한개씩만 지원 multi-pipeline 는 미지원) 
        파이프라인은 외부 데이터 (external_load_data) 로드, Asset 들의 패키지 및 git 설치(setup_asset), Asset 실행(run_asset) 순으로 실행 합니다.


        추론 파이프라인에서는 external_model 의 path 가 존재 시에 load 한다. (학습 파이프라인에서 생성보다 우선순위 높음)

        """

        # summary yaml를 redis q로 put. redis q는 _update_yaml 에서 이미 set 완료  
        # solution meta 존재하면서 (운영 모드) & redis host none아닐때 (edgeapp 모드 > AIC 추론 경우는 아래 코드 미진입) & boot-on이 아닐 때 & inference_pipeline 일 때 save_summary 먼저 반환 필요 
        # Edgeapp과 interface 중인지 (운영 모드인지 체크)

        try: 
            # CHECKLIST preset 과정도 logging 필요하므로 process logger에서는 preset 전에 실행되려면 alolib-source/asset.py에서 log 폴더 생성 필요 (artifacts 폴더 생성전)
            # NOTE 큼직한 단위의 alo.py에서의 로깅은 process logging (인자 X) - train, inference artifacts/log 양쪽에 다 남김 
            if mode != None:
                self.run(mode)
            else:
                for pipeline in self.system_envs["pipeline_list"]:
                    # 입력된 pipeline list 확인
                    self.run(pipeline)
        except: 
            # NOTE [ref] https://medium.com/@rahulkumar_33287/logger-error-versus-logger-exception-4113b39beb4b 
            # NOTE [ref2] https://stackoverflow.com/questions/3702675/catch-and-print-full-python-exception-traceback-without-halting-exiting-the-prog
            # + traceback.format_exc() << 이 방법은 alolib logger에서 exc_info=True 안할 시에 사용가능
            try:  # 여기에 try, finally 구조로 안쓰면 main.py 로 raise 되버리면서 backup_artifacts가 안됨 
                self.proc_logger.process_error("Failed to ALO runs():\n" + traceback.format_exc()) #+ str(e)) 
            finally:
                # 에러 발생 시 self.control['backup_artifacts'] 가 True, False던 상관없이 무조건 backup (폴더명 뒤에 _error 붙여서) 
                # TODO error 발생 시엔 external save 되는 tar.gz도 다른 이름으로 해야할까 ? 
                self.artifact.backup_history(pipeline, self.exp_plan_file, self.system_envs['pipeline_start_time'], error=True, size=self.control['backup_size'])
                # error 발생해도 external save artifacts 하도록        
                ext_saved_path = self.ext_data.external_save_artifacts(pipeline, self.external_path, self.external_path_permission)
                if self.is_always_on:
                    fail_str = json.dumps({'status':'fail', 'message':traceback.format_exc()})
                    if self.system_envs['runs_status'] == 'init':
                        self.system_envs['q_inference_summary'].rput(fail_str)
                        self.system_envs['q_inference_artifacts'].rput(fail_str)
                    elif self.system_envs['runs_status'] == 'summary': # 이미 summary는 success로 보낸 상태 
                        self.system_envs['q_inference_artifacts'].rput(fail_str)
        
            

    def sagemaker_runs(self): 
        try:
            try:
                # load sagemaker_config.yaml - (account_id, role, region, ecr_repository, s3_bucket_uri, train_instance_type)
                sm_config = self.experimental_plan.get_yaml(PROJECT_HOME + 'config/sagemaker_config.yaml') 
                sm_handler = SagemakerHandler(sm_config)
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

        
    ############################
    ####    Sub Function    ####
    ############################
            
    def _set_attr(self):
        self.user_parameters = self.experimental_plan.user_parameters
        self.asset_source = self.experimental_plan.asset_source
        self.external_path = self.experimental_plan.external_path
        self.external_path_permission = self.experimental_plan.external_path_permission
        self.control = self.experimental_plan.control
                        
    def run(self, pipeline):
        
        self._set_attr()

        self.system_envs['pipeline_start_time'] = datetime.now().strftime("%y%m%d_%H%M%S")
        # FIXME os env['COMPUTING']은 SagemakerDockerfile에서 설정. sagemaker 일 때만 environment import 
        if os.getenv('COMPUTING') == 'sagemaker':
            from sagemaker_training import environment
            # [중요] sagemaker 사용 시엔 self.external_path['save_train_artifacts_path']를 sagemaker에서 제공하는 model_dir로 변경
            # [참고] https://github.com/aws/sagemaker-training-toolkit        
            self.external_path['save_train_artifacts_path'] = environment.Environment().model_dir
        self.is_always_on = (self.sol_meta is not None) and (self.system_envs['redis_host'] is not None) \
            and (self.system_envs['boot_on'] == False) and (pipeline == 'inference_pipeline')

        if pipeline not in ['train_pipeline', 'inference_pipeline']:
            self.proc_logger.process_error(f'Pipeline name in the experimental_plan.yaml \n It must be << train_pipeline >> or << inference_pipeline >>')
        ###################################
        ## Step1: artifacts 를 초기화 하기 
        ###################################
        # [주의] 단 .~_artifacts/log 폴더는 지우지 않기! 
        self._empty_artifacts(pipeline)

        ###################################
        ## Step2: 데이터 준비 하기 
        ###################################
        if self.system_envs['boot_on'] == False:  ## boot_on 시, skip
            # NOTE [중요] wrangler_dataset_uri 가 solution_metadata.yaml에 존재했다면,
            # 이미 _update_yaml할 때 exeternal load inference data path로 덮어쓰기 된 상태
            self._external_load_data(pipeline)
        
        # inference pipeline 인 경우, plan yaml의 load_model_path 가 존재 시 .train_artifacts/models/ 를 비우고 외부 경로에서 모델을 새로 가져오기   
        # 왜냐하면 train - inference 둘 다 돌리는 경우도 있기때문 
        # FIXME boot on 때도 모델은 일단 있으면 가져온다 ? 
        if pipeline == 'inference_pipeline':
            try:
                if (self.external_path['load_model_path'] != None) and (self.external_path['load_model_path'] != ""): 
                    self._external_load_model()
            except:
                pass

        # 각 asset import 및 실행 
        try:
            ###################################
            ## Step3: Asset git clone 및 패키지 설치 
            ###################################
            packages = self.setup_asset(pipeline)

            ###################################
            ## Step4: Asset interface 용 data structure 준비 
            ###################################
            self.set_asset_structure()

            ###################################
            ## Step5: Asset 실행 (with asset data structure)  
            ###################################
            self.run_asset(pipeline)
        except: 
            self.proc_logger.process_error(f"Failed to run import: {pipeline}")

        ###################################
        ## Step6: Artifacts 저장   
        ###################################
        success_str, ext_saved_path = self.save_artifacts(pipeline)

        ###################################
        ## Step7: Artifacts 를 history 에 backup 
        ###################################
        if self.control['backup_artifacts'] == True:
            try:
                self.artifact.backup_history(pipeline, self.exp_plan_file, self.system_envs['pipeline_start_time'], size=self.control['backup_size'])
            except: 
                self.proc_logger.process_error("Failed to backup artifacts into << .history >>")

        ###################################
        ## Step7-2 : artifacts 저장 완료를 EdgeApp 에 전송
        ###################################
        if self.is_always_on:
            self.send_summary(success_str, ext_saved_path)

        self.system_envs['proc_finish_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.proc_logger.process_info(f"Process finish-time: {self.system_envs['proc_finish_time']}")

        self.package_list.extend(list(packages.items()))

    #####################################
    ####    Part1. Initialization    ####
    #####################################
    def init_logger(self):
        """ALO Master 의 logger 를 초기화 합니다. 
        ALO Slave (Asset) 의 logger 를 별도 설정 되며, configuration 을 공유 합니다. 
        """

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
        self.proc_logger = ProcessLogger(PROJECT_HOME)  

    def _set_system_envs(self, pipeline_type, boot_on, _system_envs):
        system_envs = _system_envs
        # solution meta 버전 
        system_envs['solution_metadata_version'] = None 
        # edgeapp interface 관련 
        system_envs['q_inference_summary'] = None 
        system_envs['q_inference_artifacts'] = None 
        system_envs['redis_host'] = None
        system_envs['redis_port'] = None
        # 'init': initial status / 'summary': success until 'q_inference_summary'/ 'artifacts': success until 'q_inference_artifacts'
        system_envs['runs_status'] = 'init'
        # edgeconductor interface 관련 
        system_envs['inference_result_datatype'] = None 
        system_envs['train_datatype'] = None 

        system_envs['pipeline_mode'] = pipeline_type 
        system_envs['boot_on'] = boot_on
        system_envs['start_time'] = datetime.now().strftime("%y%m%d_%H%M%S")

        if pipeline_type == 'all':
            system_envs['pipeline_list'] = [*self.user_parameters]
        else:
            system_envs['pipeline_list'] = [f"{pipeline_type}_pipeline"]
        # FIXME sagemaker train 을 위해 덮어쓰기 추가 
        try:
            sol_pipe_mode = os.getenv('SOLUTION_PIPELINE_MODE')
            if sol_pipe_mode is not None: 
                system_envs['pipeline_mode'] = sol_pipe_mode
                system_envs['pipeline_list'] = ["train_pipeline"]
            else:   
                raise OSError("Environmental variable << SOLUTION_PIPELINE_MODE >> is not set.")
        except:
            pass
        return system_envs

    def _alo_info(self):
        if self.system_envs['boot_on'] == True: 
            self.proc_logger.process_info(f"==================== Start booting sequence... ====================")
        else: 
            self.proc_logger.process_meta(f"Loaded solution_metadata: \n{self.sol_meta}\n")
        self.proc_logger.process_info(f"Process start-time: {self.system_envs['start_time']}")
        self.proc_logger.process_meta(f"ALO version = {self.alo_version}")
        self.proc_logger.process_info("==================== Start ALO preset ==================== ")

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
        self.asset_structure.envs['artifacts'] = self.artifacts
        self.asset_structure.envs['alo_version'] = self.alo_version
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

    def send_summary(self, success_str, ext_saved_path):
        """save artifacts가 완료되면 OK를 redis q로 put. redis q는 _update_yaml 이미 set 완료  
        solution meta 존재하면서 (운영 모드) &  redis host none아닐때 (edgeapp 모드 > AIC 추론 경우는 아래 코드 미진입) & boot-on이 아닐 때 & inference_pipeline 일 때 save_summary 먼저 반환 필요 
        외부 경로로 잘 artifacts 복사 됐나 체크 (edge app에선 고유한 경로로 항상 줄것임)

        Args:
          - success_str(str): 완료 메시지 
          - ext_saved_path(str): 외부 경로 
        """

        if 'inference_artifacts.tar.gz' in os.listdir(ext_saved_path): # 외부 경로 (= edgeapp 단이므로 무조건 로컬경로)
            self.system_envs['q_inference_artifacts'].rput(success_str) # summary yaml을 다시 한번 전송 
            self.proc_logger.process_info("Completes putting artifacts creation << success >> signal into redis queue.")
            self.system_envs['runs_status'] = 'artifacts'
        else: 
            self.proc_logger.process_error("Failed to redis-put. << inference_artifacts.tar.gz >> not found.")

    def save_artifacts(self, pipeline):
        """파이프라인 실행 시 생성된 결과물(artifacts) 를 ./*_artifacts/ 에 저장한다. 
        always-on 모드에서는 redis 로 inference_summary 결과를 Edge App 으로 전송한다. 

        만약, 외부로 결과물 저장 설정이 되있다면, local storage 또는 S3 로 결과값 저장한다. 
        """
        success_str = None

        if self.is_always_on:
            summary_dir = PROJECT_HOME + '.inference_artifacts/score/'
            if 'inference_summary.yaml' in os.listdir(summary_dir):
                summary_dict = self.experimental_plan.get_yaml(summary_dir + 'inference_summary.yaml')
                success_str = json.dumps({'status':'success', 'message': summary_dict})
                self.system_envs['q_inference_summary'].rput(success_str)
                self.proc_logger.process_info("Successfully completes putting inference summary into redis queue.")
                self.system_envs['runs_status'] = 'summary'
            else: 
                self.proc_logger.process_error("Failed to redis-put. << inference_summary.yaml >> not found.")
        
            # solution meta가 존재 (운영 모드) 할 때는 artifacts 압축 전에 .inference_artifacts/output/<step> 들 중 
            # solution_metadata yaml의 edgeconductor_interface를 참고하여 csv 생성 마지막 step의 csv, jpg 생성 마지막 step의 jpg (혹은 png, jpeg)를 
            # .inference_artifacts/output/ 바로 하단 (step명 없이)으로 move한다 (copy (x) : cost down 목적)
            try:
                self.artifact.move_output_files(pipeline, self.asset_source, self.system_envs['inference_result_datatype'], self.system_envs['train_datatype'])
            except: 
                self.proc_logger.process_error("Failed to move output files for edge conductor view.")
            
        # s3, nas 등 외부로 artifacts 압축해서 전달 (복사)
        try:      
            ext_saved_path = self.ext_data.external_save_artifacts(pipeline, self.external_path, self.external_path_permission)
        except:
            self.proc_logger.process_error("Failed to save artifacts into external path.") 

        return success_str, ext_saved_path

              
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
            
            
    #############################################
    ####    Part3. Edit experimental_plan    ####
    #############################################
    def _update_yaml(self):  
        '''
        sol_meta's << dataset_uri, artifact_uri, selected_user_parameters ... >> into exp_plan 
        '''
        # [중요] SOLUTION_PIPELINE_MODE라는 환경 변수는 ecr build 시 생성하게 되며 (ex. train, inference, all) 이를 ALO mode에 덮어쓰기 한다. 
        sol_pipe_mode = os.getenv('SOLUTION_PIPELINE_MODE')
        if sol_pipe_mode is not None: 
            self.system_envs['pipeline_mode'] = sol_pipe_mode
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

        def _convert_sol_args(_args): # inner func.
            # TODO user parameters 의 type check 해서 selected_user_paramters type 다 체크할 것인가? 
            '''
            # _args: dict 
            # selected user parameters args 중 값이 비어있는 arg는 delete  
            # string type의 comma split은 list로 변환 * 
            '''
            if type(_args) != dict: 
                self.proc_logger.process_error(f"selected_user_parameters args. in solution_medata must have << dict >> type.") 
            if _args == {}:
                return _args
            # multi selection은 비어서 올 때 key는 온다. 
            # 가령, args : { "key" : [] }
            _args_copy = deepcopy(_args)
            for k, v in _args_copy.items():
                # FIXME dict type은 없긴할테지만 혹시 모르니..? (아마 str로 dict 표현해야한다면 할 수 있지 않을까..?)
                if (type(v) == list) or (type(v) == dict): # single(multi) selection 
                     if len(v) == 0: 
                        del _args[k]
                elif isinstance(v, str):
                    if (v == None) or (v == ""): 
                        del _args[k]
                    else:  
                        converted_string = [i.strip() for i in v.split(',')] # 'a, b' --> ['a', 'b']
                        if len(converted_string) == 1: 
                            _args[k] = converted_string[0] # ['a'] --> 'a'
                        elif len(converted_string) > 1:
                            _args[k] = converted_string # ['a', 'b']
                else: # int, float 
                    if v == None: 
                        del _args[k]
            return _args
                         
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
                # 라는 식으로 args가 필요없는 step이면 업데이트를 시도하는거 자체가 잘못된거고 스킵되는게 맞다 
                sol_args = _convert_sol_args(sol_args) # 값이 비어있는 arg는 지우고 반환 
                # 어짜피 sol_args가 비어있는 dict {} 라면 plan yaml args에 update 해도 그대로이므로 괜찮다. 하지만 시간 절약을 위해 그냥 continue
                if sol_args == {}: 
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

            if self.external_path[f"save_inference_artifacts_path"] is None:  
                self.proc_logger.process_error(f"You did not enter the << save_inference_artifacts_path >> in the experimental_plan.yaml") 

        # [중요] system 인자가 존재해서 _update_yaml이 실행될 때는 항상 get_external_data를 every로한다. every로 하면 항상 input/train (or input/inference)를 비우고 새로 데이터 가져온다.
        self.exp_plan['control'][0]['get_external_data'] = 'every'

    def external_load_data(self, pipeline):
        return self._external_load_data(pipeline)

    def install_steps(self, pipeline, get_asset_source):
        return self._install_steps(pipeline)
    ########################################
    ####    Part4. Internal fuctions    ####
    ########################################
        
    def _external_load_data(self, pipeline):
        """외부 데이터를 가져 옴 (local storage, S3)

        Args:
          - pipelne (str): train / inference 인지를 구분함
        """

        ## from external.py
        self.ext_data.external_load_data(pipeline, self.external_path, self.external_path_permission, self.control['get_external_data'])

    def _external_load_model(self):
        """외부에서 모델파일을 가져옴 (model.tar.gz)

        S3 일 경우 permission 체크를 하고 가져온다.

        """

        ## from external.py
        self.ext_data.external_load_model(self.external_path, self.external_path_permission)
        
    def _install_steps(self, pipeline, get_asset_source):
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
                self.asset.memory_release(_path)
                sys.path = [item for item in sys.path if asset_structure.envs['step'] not in item]
            else:
                pass
        except:
            self.asset.memory_release(_path)
            sys.path = [item for item in sys.path if asset_structure.envs['step'] not in item]
        
        self.proc_logger.process_info(f"==================== Finish pipeline: {pipeline} / step: {asset_config['step']}")
        
        return asset_structure
    

    ##########################################
    ####    Part5. Use external method    ####
    ##########################################
    # def run_import(self, pipeline):
    #     # setup asset (asset을 git clone (or local) 및 requirements 설치)
    #     get_asset_source = self.control["get_asset_source"]  # once, every

    #     # TODO 현재 pipeline에서 중복된 step 이 있는지 확인
    #     step_values = [item['step'] for item in self.asset_source[pipeline]]
    #     step_counts = Counter(step_values)
    #     for value, count in step_counts.items():
    #         if count > 1:
    #             self.proc_logger.process_error(f"Duplicate step exists: {value}")

    #     # 운영 무한 루프 구조일 땐 boot_on 시 에만 install 하고 이후에는 skip 
    #     if (self.system_envs['boot_on'] == False) and (self.system_envs['redis_host'] is not None):
    #         pass 
    #     else: 
    #         self._install_steps(pipeline, get_asset_source)
        
    #     # AssetStructure instance 생성 
    #     self.set_asset_structure()

    #     for step, asset_config in enumerate(self.asset_source[pipeline]):    
    #         self.proc_logger.process_info(f"==================== Start pipeline: {pipeline} / step: {asset_config['step']}")
    #         # 외부에서 arg를 가져와서 수정이 가능한 구조를 위한 구조
    #         self.asset_structure.args = self.get_args(pipeline, step)
    #         try: 
    #             self.asset_structure = self.process_asset_step(asset_config, step, pipeline, self.asset_structure)
    #         except: 
    #             self.proc_logger.process_error(f"Failed to process step: << {asset_config['step']} >>")
                
    
                



        
