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

        for dir_name in list(artifacts_structure.keys()):
            artifacts_structure[dir_name] = PROJECT_HOME + dir_name + "/"
        
        return artifacts_structure

    def backup_history(self, pipelines, exp_plan_file, proc_start_time, error=False, size=1000):
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

        size_limit = size * 1024 * 1024

        backup_size = self._get_folder_size(HISTORY_PATH)
        
        if backup_size > size_limit:
            self._delete_old_files(HISTORY_PATH, 10)

        current_pipeline = pipelines.split("_pipelines")[0]
        # FIXME 추론 시간이 1초 미만일 때는 train pipeline과 .history  내 폴더 명 중복 가능성 존재. 임시로 cureent_pipelines 이름 추가하도록 대응. 고민 필요    
        backup_folder= '{}_artifacts'.format(proc_start_time) + f"_{current_pipeline}/" if error == False else '{}_artifacts'.format(proc_start_time) + f"_{current_pipeline}_error/"
        
        # TODO current_pipelines 는 차후에 workflow name으로 변경이 필요
        temp_backup_artifacts_dir = PROJECT_HOME + backup_folder
        try: 
            os.mkdir(temp_backup_artifacts_dir)
        except: 
            PROC_LOGGER.process_error(f"Failed to make {temp_backup_artifacts_dir} directory") 
        # 이전에 실행이 가능한 환경을 위해 yaml 백업
        try: 
            shutil.copy(exp_plan_file, temp_backup_artifacts_dir)
        except: 
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"Failed to copy << {exp_plan_file} >> into << {temp_backup_artifacts_dir} >>")
        # artifacts 들을 백업
        
        if current_pipeline == "train_pipeline":
            try: 
                os.mkdir(temp_backup_artifacts_dir + "train_artifacts")
                shutil.copytree(PROJECT_HOME + "train_artifacts", temp_backup_artifacts_dir + "train_artifacts", dirs_exist_ok=True)
            except: 
                shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
                PROC_LOGGER.process_error(f"Failed to copy << train_artifacts >> into << {temp_backup_artifacts_dir} >>")
                
        elif current_pipeline == "inference_pipeline":
            try: 
                os.mkdir(temp_backup_artifacts_dir + "inference_artifacts")
                shutil.copytree(PROJECT_HOME + "inference_artifacts", temp_backup_artifacts_dir + "inference_artifacts", dirs_exist_ok=True)
            except: 
                shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
                PROC_LOGGER.process_error(f"Failed to copy << inference_artifacts >> into << {temp_backup_artifacts_dir} >>")
        else:
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"You entered wrong pipeline in the experimental yaml file: << {current_pipeline} >> \n Only << train_pipeline >> or << inference_pipeline>> is allowed.")
        
        # backup artifacts를 .history로 이동 
        try: 
            shutil.move(temp_backup_artifacts_dir, HISTORY_PATH)
        except: 
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"Failed to move << {temp_backup_artifacts_dir} >> into << {HISTORY_PATH} >>")
        # 잘 move 됐는 지 확인  
        if os.path.exists(HISTORY_PATH + backup_folder):
            if error == False: 
                PROC_LOGGER.process_info("Successfully completes << .history >> backup (experimental_plan.yaml & artifacts)")
            elif error == True: 
                PROC_LOGGER.process_warning("Error backup completes @ << .history >> (experimental_plan.yaml & artifacts)")

    
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

