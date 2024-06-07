import os 
import shutil
import yaml
from datetime import datetime
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
        """ setup artifacts directories

        Args: -
        
        Returns: 
            artifacts_dict  (dict): artifacts directories structure dictionary 

        """
        def create_folders(dictionary, parent_path=''):
            for key, value in dictionary.items():
                folder_path = os.path.join(parent_path, key)
                os.makedirs(folder_path, exist_ok=True)
                if isinstance(value, dict):
                    create_folders(value, folder_path)
        # create artifacts directory 
        try:
            create_folders(BASE_DIRS_STRUCTURE, PROJECT_HOME)
        except:
            PROC_LOGGER.process_error("[PROCESS][ERROR] Artifacts folder not generated!")
        # make structure of artifacts sub-directories
        artifacts_dict = {}
        for dir_name in list(BASE_DIRS_STRUCTURE.keys()):
            artifacts_dict[dir_name] = PROJECT_HOME + dir_name + "/"
        return artifacts_dict

    def backup_history(self, pipe, system_envs, backup_exp_plan,  error=False, size=1000):
        """ backup history (experimental_plan.yaml and artifacts)

        Args:
            pipe            (str): pipeline mode (train_pipeline, inference_pipeline)
            system_envs     (dict): system envs dict 
            backup_exp_plan (dict): experimental plan dict to backup
            error           (bool): normal backup / error backup 
            size            (int): backup history size limit (MB)
        Returns: -

        """
        ## if history directory exceeds size limit, deletes directory
        size_limit = size * 1024 * 1024
        self._delete_old_folders(size_limit)
        ptype = pipe.split("_")[0]
        folder_name = system_envs[f"{ptype}_history"]["id"]
        backup_folder_name= f'{folder_name}/' if error == False else f'{folder_name}-error/'
        backup_path = HISTORY_PATH + f'{ptype}/' + backup_folder_name
        try: 
            os.makedirs(backup_path, exist_ok=True)
        except: 
            PROC_LOGGER.process_error(f"Failed to make {backup_path} directory") 
        ## yaml backup for experiment revival
        try:
            with open(backup_path + 'experimental_plan.yaml', 'w') as f:
                yaml.dump(backup_exp_plan, f, default_flow_style=False)
        except: 
            ## remove backup path if yaml backup fails
            shutil.rmtree(backup_path) 
            PROC_LOGGER.process_error(f"Failed to copy << experimental_plan (updated) >> into << {backup_path} >>")
        ## items for solution registration 
        alo_src = ['main.py', 'src', 'assets', 'alolib', '.git', 'requirements.txt', '.package_list']
        backup_source_path = backup_path + BACKUP_SOURCE_DIRECTORY
        os.makedirs(backup_source_path, exist_ok=True)
        for item in alo_src:
            src_path = PROJECT_HOME + item
            if os.path.isfile(src_path):
                shutil.copy2(src_path, backup_source_path)
            elif os.path.isdir(src_path):
                dst_path = backup_source_path  + os.path.basename(src_path)
                ## [NOTE] do not copy .git in asset directory
                if item == 'assets':
                    shutil.copytree(src_path, dst_path, ignore=shutil.ignore_patterns('.git'))
                else: 
                    shutil.copytree(src_path, dst_path)
        ## only backup experimental_plan.yaml in the solution directory (without sample data)
        os.makedirs(backup_source_path + "solution/", exist_ok=True)
        ## plan path could be default path (solution/experimental_plan.yaml) or custom path 
        shutil.copy2(system_envs['experimental_plan_path'], backup_source_path + 'solution/') 
        ## backup artifacts
        for key, value in BASE_DIRS_STRUCTURE[f'{ptype}_artifacts'].items():
            dst_path = backup_path + key + "/"
            src_path = PROJECT_HOME + f"{ptype}_artifacts/" + key + "/"
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)

    def _delete_old_folders(self, folder_size_limit):
        """ Deletes folders within 'train' and 'inference' subdirectories of a specified
            directory proportionally to their sizes if the total size exceeds a given limit.

        Args:
            folder_path         (str): The path to the directory containing 'train' and 'inference' folders.
            folder_size_limit   (int): The maximum allowed size in bytes for the sum of the sizes of
                                        the 'train' and 'inference' folders.
                                    
        Returns: -

        """
        ## each pipeline history path 
        train_path = os.path.join(HISTORY_PATH, 'train')
        inference_path = os.path.join(HISTORY_PATH, 'inference')
        ## calculate directory size 
        def _get_folder_size(path):
            if not os.path.exists(path): 
                return float(0)
            import subprocess
            result = subprocess.check_output(['du', '-sb', path]).decode('utf-8').split()[0]
            return float(result)
        train_size = _get_folder_size(train_path)
        inference_size = _get_folder_size(inference_path)
        total_size = train_size + inference_size
        ## nothing happens within size limit 
        if total_size <= folder_size_limit:
            PROC_LOGGER.process_message(f"[backup_history] Current total size is within the limit. No deletion required - (current history size: {total_size} B / size limit: {folder_size_limit} B)")
            return
        ## size tobe deleted
        total_to_delete = total_size - folder_size_limit
        ## calculate size tobe deleted proportionally 
        train_to_delete = (train_size / total_size) * total_to_delete
        inference_to_delete = (inference_size / total_size) * total_to_delete
        def _delete_from_folder(folder_path, target_size):
            ## [NOTE] folder existence check for single pipeline
            if not os.path.exists(folder_path): 
                PROC_LOGGER.process_message(f"< {folder_path} > does not exist. Skip deleting the path while history backup size limit checking.")
                return 
            folders = []
            for item in os.listdir(folder_path):
                full_path = os.path.join(folder_path, item)
                if os.path.isdir(full_path):
                    try:
                        utc_time_str = item.split('-')[0]
                        utc_time = datetime.strptime(utc_time_str, TIME_FORMAT)
                        folders.append((full_path, utc_time))
                    except ValueError:
                        PROC_LOGGER.process_warning("Time parsing error during history backup.") ## FIXME 
                        continue
            folders.sort(key=lambda x: x[1])
            current_size = _get_folder_size(folder_path)
            for folder, _ in folders:
                if current_size <= target_size:
                    break
                folder_size = _get_folder_size(folder)
                PROC_LOGGER.process_message(f"[backup_history] Backup size limit exceeded. Delete history folder: {folder}")  
                shutil.rmtree(folder)
                ## update current size after direcotry deletion 
                current_size -= folder_size  
        ## delete considering size to keep  
        _delete_from_folder(train_path, train_size - train_to_delete)
        _delete_from_folder(inference_path, inference_size - inference_to_delete)