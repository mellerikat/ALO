import shutil
import glob
from datetime import datetime
from datetime import timedelta

from src.constants import *
from src.logger import ProcessLogger

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
#--------------------------------------------------------------------------------------------------------------------------

class Aritifacts:
    def __init__(self):
        pass

    def set_artifacts(self):
        def create_folders(dictionary, parent_path=''):
            for key, value in dictionary.items():
                folder_path = os.path.join(parent_path, key)
                os.makedirs(folder_path, exist_ok=True)
                if isinstance(value, dict):
                    create_folders(value, folder_path)

        # artifacts 폴더 생성 
        try:
            create_folders(artifacts_structure, PROJECT_HOME)
        except:
            PROC_LOGGER.process_error("[PROCESS][ERROR] Artifacts folder not generated!")

        # artifacts 폴더 경로 설정
        artifacts_dict = {}
        for dir_name in list(artifacts_structure.keys()):
            artifacts_dict[dir_name] = PROJECT_HOME + dir_name + "/"
        
        return artifacts_dict

    def backup_history(self, pipelines, system_envs,  error=False, size=1000):
        """ Description
            -----------
                - 파이프라인 실행 종료 후 사용한 yaml과 결과 artifacts를 .history에 백업함 
            Parameters
            ----------- 
                - pipelines: pipeline mode (train, inference)
                - exp_plan_file: 사용자가 입력한, 혹은 default (experimental_plan.yaml) yaml 파일의 절대경로 
                - proc_start_time: ALO instance 생성 시간 (~프로세스 시작시간)
                - error: error 발생 시 backup artifact할 땐 구분을 위해 폴더명 구분 
            Return
            -----------
                - 
            Example
            -----------
                - backup_artifacts(pipeline, self.exp_plan_file, self.proc_start_time, error=False)
        """
        
        exp_plan_file = system_envs['experimental_plan'] 
        proc_start_time = system_envs['experimental_start_time']
        exp_name = system_envs['experimental_name']
        exp_version = system_envs['experimental_version']


        size_limit = size * 1024 * 1024

        backup_size = self._get_folder_size(HISTORY_PATH)
        
        if backup_size > size_limit:
            self._delete_old_files(HISTORY_PATH, 10)

        current_pipeline = pipelines.split("_")[0]
        # FIXME 추론 시간이 1초 미만일 때는 train pipeline과 .history  내 폴더 명 중복 가능성 존재. 임시로 cureent_pipelines 이름 추가하도록 대응. 고민 필요    
        folder_name = f'{proc_start_time}-{current_pipeline}-{exp_name}-{exp_version}'
        backup_folder_name= f'{folder_name}/' if error == False else f'{folder_name}-error/'
        
        # TODO current_pipelines 는 차후에 workflow name으로 변경이 필요
        backup_path = HISTORY_PATH + f'{current_pipeline}/' + backup_folder_name
        try: 
            os.makedirs(backup_path, exist_ok=True)
        except: 
            PROC_LOGGER.process_error(f"Failed to make {backup_path} directory") 


        # 이전에 실행이 가능한 환경을 위해 yaml 백업
        try: 
            shutil.copy(exp_plan_file, backup_path)
        except: 
            shutil.rmtree(backup_path) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"Failed to copy << {exp_plan_file} >> into << {backup_path} >>")


        ## 솔루션 등록을 위한 준비물 백업
        alo_src = ['main.py', 'src', 'assets', 'solution', 'alolib', '.git', 'requirements.txt', 'solution_requirements.txt', '.package_list']
        backup_source_path = backup_path + "register_source/"
        os.makedirs(backup_source_path, exist_ok=True)
        for item in alo_src:
            src_path = PROJECT_HOME + item
            if os.path.isfile(src_path):
                shutil.copy2(src_path, backup_source_path)
                PROC_LOGGER.process_info(f'[INFO] copy from " {src_path} "  -->  " {backup_source_path} " ')
            elif os.path.isdir(src_path):
                dst_path = backup_source_path  + os.path.basename(src_path)
                shutil.copytree(src_path, dst_path)
                PROC_LOGGER.process_info(f'[INFO] copy from " {src_path} "  -->  " {backup_source_path} " ')


        # artifacts 들을 백업
        for key, value in artifacts_structure[f'{current_pipeline}_artifacts'].items():
            dst_path = backup_path + key + "/"
            src_path = PROJECT_HOME + f"{current_pipeline}_artifacts/" + key + "/"
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)


        
    
    def _get_folder_size(self, folder_path):
    
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp) and os.path.isfile(fp):
                    total_size += os.path.getsize(fp)
        return total_size

    def _delete_old_files(self, folder_path, days_old):
        cutoff_date = datetime.now() - timedelta(days=days_old)
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for d in dirnames:
                folder = os.path.join(dirpath, d)
                if os.path.isdir(folder):
                    folder_modified_date = datetime.fromtimestamp(os.path.getmtime(folder))
                    if folder_modified_date < cutoff_date:
                        os.rmdir(folder)
                        print(folder)

