import shutil
import glob
from datetime import datetime
from datetime import timedelta

from src.constants import *
from src.logger import ProcessLogger
PROC_LOGGER = ProcessLogger(PROJECT_HOME)

OUTPUT_IMAGE_EXTENSIONS = ["*.jpg", "*.jpeg", "*.png"]

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

        backup_size = self._get_folder_size(PROJECT_HOME + ".history/")
        
        if backup_size > size_limit:
            self._delete_old_files(PROJECT_HOME + ".history/", 10)

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
                os.mkdir(temp_backup_artifacts_dir + ".train_artifacts")
                shutil.copytree(PROJECT_HOME + ".train_artifacts", temp_backup_artifacts_dir + ".train_artifacts", dirs_exist_ok=True)
            except: 
                shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
                PROC_LOGGER.process_error(f"Failed to copy << .train_artifacts >> into << {temp_backup_artifacts_dir} >>")
                
        elif current_pipeline == "inference_pipeline":
            try: 
                os.mkdir(temp_backup_artifacts_dir + ".inference_artifacts")
                shutil.copytree(PROJECT_HOME + ".inference_artifacts", temp_backup_artifacts_dir + ".inference_artifacts", dirs_exist_ok=True)
            except: 
                shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
                PROC_LOGGER.process_error(f"Failed to copy << .inference_artifacts >> into << {temp_backup_artifacts_dir} >>")
        else:
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"You entered wrong pipeline in the experimental yaml file: << {current_pipeline} >> \n Only << train_pipeline >> or << inference_pipeline>> is allowed.")
        
        # backup artifacts를 .history로 이동 
        try: 
            shutil.move(temp_backup_artifacts_dir, PROJECT_HOME + ".history/")
        except: 
            shutil.rmtree(temp_backup_artifacts_dir) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"Failed to move {temp_backup_artifacts_dir} into {PROJECT_HOME}/.history/")
        # 잘 move 됐는 지 확인  
        if os.path.exists(PROJECT_HOME + ".history/" + backup_folder):
            if error == False: 
                PROC_LOGGER.process_info("Successfully completes << .history >> backup (experimental_plan.yaml & artifacts)")
            elif error == True: 
                PROC_LOGGER.process_warning("Error backup completes @ << .history >> (experimental_plan.yaml & artifacts)")

    def move_output_files(pipeline, asset_source, inference_result_datatype, train_datatype):
        """
        # solution meta가 존재 (운영 모드) 할 때는 artifacts 압축 전에 .inference_artifacts/output/<step> 들 중 
        # solution_metadata yaml의 edgeconductor_interface를 참고하여 csv 생성 마지막 step의 csv, jpg 생성 마지막 step의 jpg (혹은 png, jpeg)를 
        # .inference_artifacts/output/ 바로 하단 (step명 없이)으로 move한다 (copy (x) : cost down 목적)
        # custom이라는 step 폴더 밑에 output.csv와 extra_files라는 폴더가 있으면 extra_files 폴더는 무시한다. 
        # inference_result_datatype 와 train_datatype를 or 연산자 하여 edgeconductor에서 보여져야하는 solution type을 결정할 수 있다. 
        """
        pipeline_prefix = pipeline.split('_')[0]
        output_path = PROJECT_HOME + f".{pipeline_prefix}_artifacts/output/"    
        
        # output 하위 경로 중 csv를 가진 모든 경로 
        output_csv_path_list = glob.glob(output_path + "*/*.csv") # 첫번째 *은 step명 폴더, 두번째 *은 모든 csv 
        # .csv를 가진 step 명 (sub폴더 이름)
        steps_csv_exist = list(set([os.path.basename(os.path.normpath(os.path.split(output_csv_path)[0])) for output_csv_path in output_csv_path_list]))
        # output 하위 경로 중 image 파일을 가진 모든 경로 
        output_image_path_list = []
        for ext in OUTPUT_IMAGE_EXTENSIONS:
            output_image_path_list += glob.glob(output_path + f"*/{ext}") 
        # .jpg, .jpeg, .png를 가진 step 명 (sub폴더 이름)
        steps_image_exist = list(set([os.path.basename(os.path.normpath(os.path.split(output_image_path)[0])) for output_image_path in output_image_path_list]))

        csv_last_step = None # csv 파일이 존재하는 마지막 step  
        image_last_step = None # image 파일이 존재하는 마지막 step
        # pipeline의 step 순서대로 순회하며 last step을 찾아냄 
        for step in [item['step'] for item in asset_source[pipeline]]: 
            if step in steps_csv_exist: 
                csv_last_step = step 
            if step in steps_image_exist:
                image_last_step = step
        
        # table only 
        if list(set([inference_result_datatype, train_datatype])) == ['table']:
            csv_list = glob.glob(output_path + f"{csv_last_step}/*.csv")
            if len(csv_list) != 1:
                PROC_LOGGER.process_error(f"Failed to move output files for edge conductor view. \n More than single file exist in the last step: {csv_last_step}")
            shutil.move(csv_list[0], output_path) 
        # image only
        elif list(set([inference_result_datatype, train_datatype])) == ['image']:
            img_list = [] 
            for ext in OUTPUT_IMAGE_EXTENSIONS:
                img_list += glob.glob(output_path + f"{image_last_step}/{ext}")
            if len(img_list) != 1:
                PROC_LOGGER.process_error(f"Failed to move output files for edge conductor view. \n More than single file exist in the last step: {image_last_step}")
            shutil.move(img_list[0], output_path) 
        # table, image both (each 1)
        elif list(set([inference_result_datatype, train_datatype])) == list(set(['table','image'])):
            # table move
            csv_list = glob.glob(output_path + f"{csv_last_step}/*.csv")
            if len(csv_list) != 1:
                PROC_LOGGER.process_error(f"Failed to move output files for edge conductor view. \n More than single file exist in the last step: {csv_last_step}")
            shutil.move(csv_list[0], output_path) 
            # image move 
            img_list = [] 
            for ext in OUTPUT_IMAGE_EXTENSIONS:
                img_list += glob.glob(output_path + f"{image_last_step}/{ext}")
            if len(img_list) != 1:
                PROC_LOGGER.process_error(f"Failed to move output files for edge conductor view. \n More than single file exist in the last step: {image_last_step}")
            shutil.move(img_list[0], output_path) 
    
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

