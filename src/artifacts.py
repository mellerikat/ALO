import shutil
from datetime import datetime
from src.constants import *
from src.logger import ProcessLogger
import yaml

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

    def backup_history(self, pipelines, system_envs, backup_exp_plan,  error=False, size=1000):
        """ Description
            -----------
                - 파이프라인 실행 종료 후 사용한 yaml과 결과 artifacts를 history에 백업함 
            Parameters
            ----------- 
                - pipelines: pipeline mode (train, inference)
                - system_envs: 파이프라인을 실행하면서 발생한 정보를 backup 에 저장
                - backup_exp_plan: 실험중에 변경된 experimental_plan 을 반영하여 history 에 저장
                - error: error 발생 시 backup artifact할 땐 구분을 위해 폴더명 구분 
            Return
            -----------
                - 
            Example
            -----------
                - backup_artifacts(pipeline, self.exp_plan_file, self.system_envs, backup_exp_plan, error=False)
        """ 
        ## history 폴더 oversize 시, 폳더 제거
        size_limit = size * 1024 * 1024
        self._delete_old_folders(size_limit)
        ptype = pipelines.split("_")[0]
        # FIXME 추론 시간이 1초 미만일 때는 train pipeline과 history  내 폴더 명 중복 가능성 존재. 임시로 cureent_pipelines 이름 추가하도록 대응. 고민 필요    
        folder_name = system_envs[f"{ptype}_history"]["id"]
        backup_folder_name= f'{folder_name}/' if error == False else f'{folder_name}-error/'
        # TODO current_pipelines 는 차후에 workflow name으로 변경이 필요
        backup_path = HISTORY_PATH + f'{ptype}/' + backup_folder_name
        try: 
            os.makedirs(backup_path, exist_ok=True)
        except: 
            PROC_LOGGER.process_error(f"Failed to make {backup_path} directory") 
        # 이전에 실행이 가능한 환경을 위해 yaml 백업
        try:
            with open(backup_path + 'experimental_plan.yaml', 'w') as f:
                yaml.dump(backup_exp_plan, f, default_flow_style=False)
        except: 
            shutil.rmtree(backup_path) # copy 실패 시 임시 backup_artifacts_home 폴더 삭제 
            PROC_LOGGER.process_error(f"Failed to copy << experimental_plan (updated) >> into << {backup_path} >>")
        ## 솔루션 등록을 위한 준비물 백업
        alo_src = ['main.py', 'src', 'assets', 'solution', 'alolib', '.git', 'requirements.txt', 'solution_requirements.txt', '.package_list']
        backup_source_path = backup_path + "register_source/"
        os.makedirs(backup_source_path, exist_ok=True)
        for item in alo_src:
            src_path = PROJECT_HOME + item
            if os.path.isfile(src_path):
                shutil.copy2(src_path, backup_source_path)
                # PROC_LOGGER.process_info(f'[INFO] copy from " {src_path} "  -->  " {backup_source_path} " ')
            elif os.path.isdir(src_path):
                dst_path = backup_source_path  + os.path.basename(src_path)
                shutil.copytree(src_path, dst_path)
                # PROC_LOGGER.process_info(f'[INFO] copy from " {src_path} "  -->  " {backup_source_path} " ')
        # artifacts 들을 백업
        for key, value in artifacts_structure[f'{ptype}_artifacts'].items():
            dst_path = backup_path + key + "/"
            src_path = PROJECT_HOME + f"{ptype}_artifacts/" + key + "/"
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)

    def _delete_old_folders(self, folder_size_limit):
        """
        Deletes folders within 'train' and 'inference' subdirectories of a specified
        directory proportionally to their sizes if the total size exceeds a given limit.
    
        The function calculates the current sizes of both 'train' and 'inference' folders.
        If the sum of these sizes exceeds the specified limit, it calculates how much data
        needs to be deleted from each based on their proportion of the total size.
        Deletion happens from the oldest folders determined by the UTC timestamp in the folder name.
    
        Parameters:
        - folder_path (str): The path to the directory containing 'train' and 'inference' folders.
        - folder_size_limit (int): The maximum allowed size in bytes for the sum of the sizes of
        the 'train' and 'inference' folders.

        Note: Folder names within 'train' and 'inference' must follow the '{UTC}-{random}-{title}'
        format for the deletion priority to be determined based on their age.
        """
        # 각 폴더 경로 정의
        train_path = os.path.join(HISTORY_PATH, 'train')
        inference_path = os.path.join(HISTORY_PATH, 'inference')
        # 각 폴더의 크기 계산 함수
        def _get_folder_size(start_path):
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(start_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp) and os.path.exists(fp):
                        total_size += os.path.getsize(fp)
            return total_size
        # 각 폴더 크기 계산
        train_size = _get_folder_size(train_path)
        inference_size = _get_folder_size(inference_path)
        total_size = train_size + inference_size
        # 폴더 사이즈가 제한을 초과하지 않으면 아무 것도 하지 않음
        if total_size <= folder_size_limit:
            PROC_LOGGER.process_info("[backup_history] Current total size is within the limit. No deletion required.")
            return
        # 삭제해야 할 전체 양 계산
        total_to_delete = total_size - folder_size_limit
        # 비율에 따라 삭제할 양 계산
        train_to_delete = (train_size / total_size) * total_to_delete
        inference_to_delete = (inference_size / total_size) * total_to_delete
        def _delete_from_folder(folder_path, target_size):
            folders = []
            for item in os.listdir(folder_path):
                full_path = os.path.join(folder_path, item)
                if os.path.isdir(full_path):
                    try:
                        utc_time_str = item.split('-')[0]
                        utc_time = datetime.strptime(utc_time_str, TIME_FORMAT)
                        folders.append((full_path, utc_time))
                    except ValueError:
                        continue
            folders.sort(key=lambda x: x[1])
            current_size = _get_folder_size(folder_path)
            for folder, _ in folders:
                if current_size <= target_size:
                    break
                folder_size = _get_folder_size(folder)
                PROC_LOGGER.process_info(f"Delete history folder: {folder}")  # 삭제 로그 출력
                shutil.rmtree(folder)
                current_size -= folder_size  # 폴더 삭제 후 크기 업데이트
        # 각 폴더에서 유지해야 할 크기로 삭제
        _delete_from_folder(train_path, train_size - train_to_delete)
        _delete_from_folder(inference_path, inference_size - inference_to_delete)
