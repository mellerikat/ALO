import git
import hashlib
import importlib
import json
import os
import random
import re
import shutil
import sys
import yaml
from collections import Counter
from datetime import datetime
from typing import Dict
from src.artifacts import Aritifacts
from src.constants import *
from src.external import ExternalHandler
from src.install import Packages
from src.logger import ProcessLogger
from src.utils import  _log_process
from src.yaml import Metadata

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
#--------------------------------------------------------------------------------------------------------------------------

class AssetStructure:
    def __init__(self):
        """ structure for storing the input/output information of an asset.
            - self.envs: information about the environment in which ALO executes the pipeline
            - self.args: user-defined variables for processing within an asset 
                        (variables defined in experimental_plan.yaml used within the asset)
                        supports string, integer, list, and dict types
            - self.data: input/output data to be used in the asset
            - self.config: Globally shared configuration values between assets 
                        (can be added by the asset constructor)
                        
        Args: -           
            
        Returns: -

        """
        self.envs = {}
        self.args = {}
        ## FIXME unused 
        self.data = {}
        self.config = {}

class Pipeline:
    def __init__(self, experimental_plan: Dict, pipeline_type: str, system_envs: Dict):
        """ initialize pipeline config 
        
        Args: 
            experimental_plan  (dict): experimental plan yaml info as dict 
            pipeline_type      (str): pipeline type (e.g. train_pipeline, inference_pipeline)
            system_envs        (dict): system environmental info (interface within ALO master)
            
        Returns: -

        """
        if not pipeline_type in ['all', 'train_pipeline', 'inference_pipeline']:
            raise Exception(f"Invalid pipeline type: {pipeline_type}")
        if not os.path.exists(ASSET_HOME):
            try:
                os.makedirs(ASSET_HOME)
            except:
                PROC_LOGGER.process_error(f"Failed to create directory: {ASSET_HOME}")
        self.pipeline_type = pipeline_type
        self.system_envs = system_envs
        ## declare instances
        self.install = Packages()
        self.external = ExternalHandler()
        self.asset_structure = AssetStructure()
        self.artifact = Aritifacts()
        def _get_yaml_data(key, pipeline_type = 'all'): 
            data_dict = {}
            if key == "name" or key == "version":
                return experimental_plan[key]
            if experimental_plan[key] == None:
                return []
            for data in experimental_plan[key]:
                data_dict.update(data)
            if 'train_pipeline' in data_dict and 'inference_pipeline' in data_dict:
                if pipeline_type == 'train_pipeline':
                    remove_key = 'inference_pipeline'
                    del data_dict[remove_key]
                else:
                    remove_key = 'train_pipeline'
                    del data_dict[remove_key]
            return data_dict
        ## converts to class self variables
        for key, value in experimental_plan.items():
            setattr(self, key, _get_yaml_data(key, pipeline_type))
        ## must exist in the initialization (init) to accommodate cases \
        ## where only pipeline.run() is executed.
        self._set_asset_structure()

    def setup(self): 
        """ setup pipeline
            - empty package list, artifacts 
            - setup assets / create package list file 
        Args: -
            
        Returns: -

        """      
        _log_process(f"<< SETUP >> {self.pipeline_type} start", highlight=True)
        ## package list setup - only remove current pipeline step{N}.txt
        self._empty_package_list(self.pipeline_type)
        ## empty artifact
        self._empty_artifacts(self.pipeline_type)
        _, packs = self._setup_asset(self.asset_source[self.pipeline_type], self.control['get_asset_source'])
        if packs is not None: 
            self._create_package(packs)
        _log_process(f"<< SETUP >> {self.pipeline_type} finish", highlight=True)

    def load(self, data_path=[]):
        """ load pipeline
            - load external model
            - load external data
        Args:
            data_path   (list): external load data path 
            
        Returns: -

        """   
        try:
            _log_process(f"<< LOAD >> {self.pipeline_type} start", highlight=True)
            ## load external model
            if self.pipeline_type == 'inference_pipeline':
                if (self.external_path['load_model_path'] != None) and (self.external_path['load_model_path'] != ""):
                    self.external.external_load_model(self.external_path, self.external_path_permission)
                    ## Remove the {train_id} from the experiment history and record a special sentence
                    self.system_envs['inference_history']['train_id'] = "load-external-model"
            ## load external data
            ptype = self.pipeline_type.split('_')[0]
            if isinstance(data_path, str):
                data_path = [data_path]
            if len(data_path) > 0:
                ## update external path 
                self.external_path[f'load_{ptype}_data_path'] = data_path
            if self.system_envs['boot_on'] == False: 
                data_checksums = self.external.external_load_data(self.pipeline_type, self.external_path, self.external_path_permission)
                ## generate a {data_id} for the experiment history
                ptype = self.pipeline_type.split('_')[0]
                self.system_envs[f'{ptype}_history'].update(data_checksums)
            ## skip when boot-on mode 
            else: 
                pass 
            _log_process(f"<< LOAD >> {self.pipeline_type} finish", highlight=True)
        except: 
            self._publish_redis_msg("alo_fail", json.dumps(self.system_envs['redis_error_table']["E141"]))
            PROC_LOGGER.process_error(f"Failed to load {self.pipeline_type}") 
            
    def run(self, steps = 'all'):
        """ run pipeline
        
        Args:
            steps   (str, list): 'all' or asset step list 
            
        Returns: -

        """  
        _log_process(f"<< RUN >> {self.pipeline_type} start", highlight=True)
        if steps == 'all':
            for step, asset_config in enumerate(self.asset_source[self.pipeline_type]):
                _log_process(f"current step: {asset_config['step']}")
                self.asset_structure.args[asset_config['step']] = self.get_parameter(asset_config['step'])
                try:
                    self.process_asset_step(asset_config, step)
                except:
                    PROC_LOGGER.process_error(f"Failed to process step: << {asset_config['step']} >>")
        else:
            if type(steps) == list:
                for step in steps:
                    _log_process(f"current step: {step}")
                    self.asset_structure.args[step] = self.get_parameter(step)
                    for i, asset_configs in enumerate(self.asset_source[self.pipeline_type]):
                        if asset_configs['step'] == step:
                            asset_config = asset_configs
                            break
                        else:
                            continue
                    try:
                        self.process_asset_step(asset_config, i)
                    except:
                        PROC_LOGGER.process_error(f"Failed to process step: << {step} >>")
                        continue
            else:
                _log_process(f"steps: {steps}")
                self.asset_structure.args[steps] = self.get_parameter(steps)
                step = 0
                for i, asset_configs in enumerate(self.asset_source[self.pipeline_type]):
                    if asset_configs['step'] == steps:
                        asset_config = asset_configs
                        step = i
                        break
                    else:
                        continue
                try:
                    self.process_asset_step(asset_config, step)
                except:
                    PROC_LOGGER.process_error(f"Failed to process step: << {steps} >>")
        ## generate params id
        params = self.user_parameters[self.pipeline_type]
        ptype = self.pipeline_type.split('_')[0]
        self.system_envs[f'{ptype}_history']['param_id'] = self._parameter_checksum(params)
        ## generate code id 
        total_checksum = hashlib.md5()
        checksum_dict = {}
        for i, asset_config in enumerate(self.asset_source[self.pipeline_type]):
            _path = ASSET_HOME + asset_config['step'] + "/"
            checksum = self._code_checksum(_path)
            checksum_dict[asset_config['step']] = checksum
            ## convert the checksum of each folder to a string and update {total_checksum}
            total_checksum.update(str(checksum).encode())
        ## convert the MD5 hash value to a hexadecimal string and \
        ## limit the length to 12 by using only the first 12 characters
        total_checksum_str = total_checksum.hexdigest()[:12]
        self.system_envs[f'{ptype}_history']['code_id_description'] = checksum_dict
        ## store the total_checksum in the form of a string, \
        ## adjusting its length to be 12 characters long
        self.system_envs[f'{ptype}_history']['code_id'] = total_checksum_str 
        _log_process(f"<< RUN >> {self.pipeline_type} finish", highlight=True)

    def save(self):
        """ save pipeline
        
        Args: -
            
        Returns: -

        """  
        _log_process(f"<< SAVE >> {self.pipeline_type} start", highlight=True)
        ## check for proper creation of summary yaml file and output
        if (self.pipeline_type == 'inference_pipeline') and (self.system_envs['boot_on'] == False):
            self._check_output()
        ## send a success message to the edge app \
        ## indicating that the creation of inference output is complete.
        if self.system_envs['loop'] and (self.system_envs['boot_on'] == False):
            self.system_envs['success_str'] = self._send_redis_summary()
        ## save artifacts
        if self.system_envs['boot_on'] == False:
            ## (Note) within save_artifacts, there is also transmission to the edge app via Redis
            self._save_artifacts()
            ## define up to backup as the final execution time
            self.system_envs['experimental_end_time'] = datetime.now().strftime(TIME_FORMAT)
            PROC_LOGGER.process_message(f"Process finish-time: {datetime.now().strftime(TIME_FORMAT_DISPLAY)}")
            ptype = self.pipeline_type.split('_')[0]
            sttime = self.system_envs['experimental_start_time']
            exp_name = self.system_envs['experimental_name']
            random_number = '{:08}'.format(random.randint(0, 99999999))
            self.system_envs[f"{ptype}_history"]['id'] = f'{sttime}-{random_number}-{exp_name}'
            self.system_envs[f"{ptype}_history"]['start_time'] = sttime
            self.system_envs[f"{ptype}_history"]['end_time'] = self.system_envs['experimental_end_time']
            ## at the end of training, save in advance to inference_history, \
            ## because the train_id may change during inference
            if self.pipeline_type == 'train_pipeline':
                try:
                    self.system_envs[f"inference_history"]['train_id'] = self.system_envs["train_history"]['id']
                ## single pipeline (only inference)
                except: 
                    self.system_envs[f"inference_history"]['train_id'] = "none"
            if self.control['backup_artifacts'] == True:
                ## data, code, param id are saved in {system_envs} 
                if ptype == 'train':
                    path = TRAIN_ARTIFACTS_PATH + EXPERIMENTAL_HISTORY_PATH
                else:
                    path = INFERENCE_ARTIFACTS_PATH + EXPERIMENTAL_HISTORY_PATH
                with open(path, 'w') as f:
                    json.dump(self.system_envs[f"{ptype}_history"], f, indent=4)    
            ## history backup artifacts 
            if (self.control['backup_artifacts'] == True): 
                try:
                    backup_exp_plan = self._make_exp_plan_dict()
                    self.artifact.backup_history(self.pipeline_type, self.system_envs, backup_exp_plan, size=self.control['backup_size'])
                except:
                    PROC_LOGGER.process_error("Failed to backup artifacts into << history >>")
        _log_process(f"<< SAVE >> {self.pipeline_type} finish", highlight=True)

    def history(self, data_id="", param_id="", code_id="", parameter_steps=[]):
        """ Deliver the experiment results stored in history as a table, 
            allowing for solution registration by history id.
            After verifying the identity between experimental_plan.yaml in the 
            history folder and each id, create a table.
       
        Args: 
            data_id         (str): data id
            param_id        (str): parameters id
            code_id         (str): source code id
            parameter_steps (list): decide which step's parameters to display when creating a table
            
        Returns: -

        """  
        _log_process(f"{self.pipeline_type} history backup start")
        ## convert the folder names from the history folder into dictionary keys
        ptype = self.pipeline_type.split('_')[0]
        base_path = HISTORY_PATH + f'{ptype}/'
        entries = os.listdir(base_path)
        ## filter only the directories from the {entries} and add them to a list
        folders = [entry for entry in entries if os.path.isdir(os.path.join(base_path, entry))]
        history_dict = {}
        empty_score_dict = {
            "date": '',
            "file_path": '',
            "note": '',
            "probability": {},
            "result": '',
            "score": "",
            "version": "",
        }
        ## TODO consider adopting SQLite if there are concerns about speed issues
        for folder in folders: 
            ## search for data / code / param id 
            file = base_path + folder + "/" + EXPERIMENTAL_HISTORY_PATH
            if os.path.exists(file):
                with open(file, 'r') as f:
                    history = json.load(f)
                    history_dict[folder] = history
            else:
                empty_dict = {
                    "data_id_description": {},
                    "data_id": "" ,
                    "param_id": "",
                    "code_id_description": {},
                    "code_id": "",
                    "id": "",
                    "start_time": "20000101T000000Z",
                    "end_time": "20000101T000000Z"
                }
                ## if experiment_history.json is missing, set {train_id} to None in the case of inference
                if ptype == "inference":
                    empty_dict["train_id"] = "none"
                history_dict[folder] = empty_dict 
            ## search for summary yaml (score)
            file_score = base_path + folder + f"/score/{ptype}_summary.yaml"
            if os.path.exists(file_score):
                try:
                    with open(file_score, 'r') as f:
                        history_score = yaml.safe_load(f)
                        history_dict[folder].update(history_score)
                except:
                    history_dict[folder].update(empty_score_dict)
            else:
                history_dict[folder].update(empty_score_dict)
            file_exp = base_path + folder + "/experimental_plan.yaml"
            ## set metadata instance 
            meta = Metadata()
            if os.path.exists(file_exp):
                ## upon read_yaml(), file_exp becomes internalized as a variable within meta
                meta.read_yaml(exp_plan_file=file_exp, update_envs=False)  
                value_empty = False
            else:
                meta.read_yaml(exp_plan_file=DEFAULT_EXP_PLAN, update_envs=False)
                value_empty = True
            for pipe, steps_dict in meta.user_parameters.items():
                if pipe == self.pipeline_type:
                    ## validates {parameter_steps}
                    exp_step_list = sorted([i['step'] for i in meta.user_parameters[pipe]])
                    if not all(iten in exp_step_list for iten in parameter_steps):
                        raise ValueError(f"parameter_steps {parameter_steps} is not valid. It should be one of {exp_step_list}")
                    ## args into {history_dict} for each step
                    for step_dict in steps_dict: 
                        step = step_dict['step']
                        if step in parameter_steps:
                            for key, value in step_dict['args'][0].items():
                                if value_empty:
                                    history_dict[folder][f"{step}.{key}"] = "none"
                                else:
                                    history_dict[folder][f"{step}.{key}"] = value
            ## search for failed experiments
            if "-error" in folder:
                history_dict[folder]['status'] = "error"
            else:
                history_dict[folder]['status'] = "success"
        ## make table
        ## list of keys we want to remove
        drop_keys = ['data_id_description', 'code_id_description', 'file_path']
        new_order = ['id', 'status', 'start_time', 'end_time', 'score', 'result', 'note', 'probability', 'version', 'data_id', 'code_id', 'param_id']
        if ptype == 'inference':
            new_order.append('train_id')
        ## new dictionary to hold our processed records
        processed_dict = {}
        for key, record in history_dict.items():
            ## exclude unwanted keys
            filtered_record = {k: v for k, v in record.items() if k not in drop_keys}
            ## reorder and select keys according to new_order, filling missing keys with None
            processed_record = {k: filtered_record.get(k, None) for k in new_order}
            ## add remaining keys in their original order
            remaining_keys = [k for k in filtered_record.keys() if k not in new_order]
            for k in remaining_keys:
                processed_record[k] = filtered_record[k]
            ## format the 'start_time' and 'end_time'
            processed_record['start_time'] = datetime.strptime(processed_record['start_time'], TIME_FORMAT).strftime(TIME_FORMAT_DISPLAY)
            processed_record['end_time'] = datetime.strptime(processed_record['end_time'], TIME_FORMAT).strftime(TIME_FORMAT_DISPLAY)
            ## add record to the new {processed_dict}
            processed_dict[key] = processed_record
        ## sort the records by end_time in descending order (not easily achievable with a dictionary, \
        ## might need to convert to a list of tuples or a list of dictionaries)
        processed_records_list = list(processed_dict.values())
        ## filtering logic based on {data_id}, {param_id}, {code_id}
        filtered_records_list = []
        for record in processed_records_list:
            if (not data_id or record.get('data_id') == data_id) and \
            (not param_id or record.get('param_id') == param_id) and \
            (not code_id or record.get('code_id') == code_id):
                filtered_records_list.append(record)
        ## now {processed_records_list} contains the list of dictionaries sorted by \
        ## 'end_time' and you can use it as you wish.
        filtered_records_list.sort(key=lambda x: datetime.strptime(x['end_time'], TIME_FORMAT_DISPLAY), reverse=True)
        return filtered_records_list

    #####################################
    ####      INTERNAL FUNCTION      #### 
    #####################################
    
    def _make_exp_plan_dict(self):
        """ Create an experimental plan. Since intermediate values may change during the experiment, 
            be sure to reconstruct and save them.
       
        Args: -
        
        Returns: 
            backup_exp_plan {dict}: backup experimental plan info 

        """  
        backup_exp_plan = {}
        backup_exp_plan['name'] = self.name
        backup_exp_plan['version'] = self.version
        backup_exp_plan['external_path'] = [{k: v} for k, v in self.external_path.items()]
        backup_exp_plan['external_path_permission'] = [self.external_path_permission]
        backup_exp_plan['user_parameters'] = [self.user_parameters]
        backup_exp_plan['asset_source'] = [self.asset_source]
        backup_exp_plan['control'] = [{k: v} for k, v in self.control.items()]
        try:
            backup_exp_plan['ui_args_detail'] = [{k: v} for k, v in self.ui_args_detail.items()]
        except:
            ## TODO deal with non-existence case ?
            pass   
        return backup_exp_plan

    def _parameter_checksum(self, params):
        """ Convert params to a string to use as the hash input value.
            Here, it is assumed that params is a string. 
            In actual use, you may need to properly convert params.
            
        Args: -
        
        Returns: 
            hexdigest_str[:12]  (str): hexadecimal hash string (length: 12)

        """  
        params_str = str(params)
        ## calculate the hash of params_str using hashlib
        checksum = hashlib.sha256(params_str.encode('utf-8'))
        ## obtain a hexadecimal hash string by calling the hexdigest() method on the hash object
        hexdigest_str = checksum.hexdigest()
        ## Truncate the hexadecimal string to the first 12 characters \
        ## to limit the length to 12 and return it
        return hexdigest_str[:12]

    def _code_checksum(self,folder_path):
        """ Calculates the checksum based on the contents of all .py files within a folder.
            
        Args: 
            folder_path (str):  folder path to calculate checksum
        
        Returns: 
            64-bit integer checksum (int)

        """
        checksum = hashlib.md5()
        ## traverse the folder and perform operations on all .py files
        for root, dirs, files in os.walk(folder_path):
            for file in sorted(files):
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    ## read the file content and update the checksum
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            checksum.update(chunk)
        ## convert the final checksum to a 64-bit integer
        return int(checksum.hexdigest(), 16) & ((1 << 64) - 1)

    def _check_output(self):
        """ Check for proper creation of inference_summary.yaml 
            and output csv / image files (jpg, png, svg).
            There must only be one csv and one image file respectively.
            
        Args: - 
        
        Returns: -

        """
        ## check inference summary
        if "inference_summary.yaml" in os.listdir(INFERENCE_SCORE_PATH):
            PROC_LOGGER.process_message(f"[Success] << inference_summary.yaml >> exists in the inference score path: << {INFERENCE_SCORE_PATH} >>")
        else:
            PROC_LOGGER.process_error(f"[Failed] << inference_summary.yaml >> does not exist in the inference score path: << {INFERENCE_SCORE_PATH} >>")
        ## check output files
        output_files = []
        for file_path in os.listdir(INFERENCE_OUTPUT_PATH):
        ## check if current file_path is a file
            if os.path.isfile(os.path.join(INFERENCE_OUTPUT_PATH, file_path)):
                ## add filename to list
                output_files.append(file_path)
        if len(output_files) == 1:
            if os.path.splitext(output_files[0])[-1] not in TABULAR_OUTPUT_FORMATS + IMAGE_OUTPUT_FORMATS:
                PROC_LOGGER.process_error(f"[Failed] output file extension must be one of << {TABULAR_OUTPUT_FORMATS + IMAGE_OUTPUT_FORMATS} >>. \n Your output: {output_files}")
        elif len(output_files) == 2:
            ## must be one of the {'.csv', '.jpg', '.png', '.svg'}
            output_extension = set([os.path.splitext(i)[-1] for i in output_files]) 
            allowed_extensions = [set(TABULAR_OUTPUT_FORMATS + [i]) for i in IMAGE_OUTPUT_FORMATS]
            if output_extension not in allowed_extensions:
                PROC_LOGGER.process_error(f"[Failed] output files extension must be one of << {allowed_extensions} >>. \n Your output: {output_files}")
        else:
            PROC_LOGGER.process_error(f"[Failed] the number of output files must be 1 or 2. \n Your output: {output_files}")

    def _send_redis_summary(self):
        """ Once save artifacts is complete, put OK into the Redis queue. 
            If a solution metadata exists (operational mode), the Redis host is not None 
            and it's not boot-on, and it's an inference_pipeline, then it's necessary to first send
            redis message at 'save_summary' channel.
            
        Args: - 
        
        Returns: 
            success_str (str): redis success message (json dumped dict string)

        """
        success_str = None
        summary_dir = INFERENCE_SCORE_PATH
        if 'inference_summary.yaml' in os.listdir(summary_dir):
            meta = Metadata()
            summary_dict = meta.get_yaml(summary_dir + 'inference_summary.yaml')
            success_str = json.dumps({'status':'success', 'message': summary_dict})
            ## redis rput 
            redis_list = self.system_envs['redis_list_instance']
            redis_key = self.system_envs['redis_key_summary']
            redis_list.rput(redis_key, success_str)
            PROC_LOGGER.process_message("Successfully completes putting inference summary into redis queue.")
            ## update {runs_state}
            self.system_envs['runs_status'] = 'summary'
        else:
            self._publish_redis_msg("alo_fail", json.dumps(self.system_envs['redis_error_table']["E161"]))  
            PROC_LOGGER.process_error("Failed to redis-put. << inference_summary.yaml >> not found.")
        return success_str

    def _save_artifacts(self):
        """ The results (artifacts) generated during pipeline execution are stored in ./{pipeline}_artifacts/.
            In loop mode, the inference_summary results are sent to the EdgeApp via Redis.
            If there is a configuration set to store the results externally, 
            then the output is saved to local storage or S3.
        Args: - 
        
        Returns: 
            ext_saved_path (str): external save artifacts path 

        """
        ## compress and transfer (copy) artifacts to external storage, such as S3 or NAS
        try:
            ext_type, ext_saved_path = self.external.external_save_artifacts(self.pipeline_type, self.external_path, self.external_path_permission, self.control['save_inference_format'])
            ## in loop mode, deliver the completion of artifacts creation to the EdgeApp via Redis.
            if self.system_envs['loop']:
                ## external inference artifact path can be local storage or s3 
                ## s3 upload file is blocking operation. Don't have to check file generation completion at s3
                if ((ext_type in ['absolute', 'relative']) and ('inference_artifacts.{}'.format(self.control["save_inference_format"]) in os.listdir(ext_saved_path))) or (ext_type == 's3'): 
                    ## resend the inference summary that was generated for {send_summary} channel 
                    redis_list = self.system_envs['redis_list_instance']
                    redis_key = self.system_envs['redis_key_artifacts']
                    ## redis rput 
                    redis_list.rput(redis_key, self.system_envs['success_str'])
                    PROC_LOGGER.process_message("Completes putting artifacts creation << success >> signal into redis queue.")
                    self.system_envs['runs_status'] = 'artifacts'
        except:
            if self.system_envs['loop']:
                self._publish_redis_msg("alo_fail", json.dumps(self.system_envs['redis_error_table']["E162"]))  
            PROC_LOGGER.process_error("Failed to save artifacts into external path. << inference_artifacts.{} >> not found.".format(self.control["save_inference_format"]))
        return ext_saved_path

    def get_parameter(self, step_name):
        """ get user parameters
        Args: 
            step_name   (str): asset step name 
        
        Returns: 
            step args dict 

        """
        for step in self.user_parameters[self.pipeline_type]:
            if step['step'] == step_name:
                if type(step['args']) == list:
                    return step['args'][0]
                else:
                    return dict()
        ## if not returned, raise error 
        PROC_LOGGER.process_error("get parameters error") 

    def get_asset_source(self, step_name, source = None):
        """ get asset source
        Args: 
            step_name   (str): asset step name 
            source      (str, None): asset source keys 
        
        Returns: 
            step asset source dict

        """
        for step in self.asset_source[self.pipeline_type]:
            if step['step'] == step_name:
                if source == None:
                    return step['source']
                else:
                    return step['source'][source]
        ## if not returned, raise error
        PROC_LOGGER.process_error("get asset source error") 

    def process_asset_step(self, asset_config, step):
        """ import and run user asset
        Args: 
            asset_config    (dict): asset config info 
            step            (int): asset step order 
        
        Returns: -

        """
        assert self.control['check_resource'] in CHECK_RESOURCE_LIST
        self._publish_redis_msg("alo_status", f"run.{asset_config['step']}")
        self.asset_structure.envs['pipeline'] = self.pipeline_type
        _path = ASSET_HOME + asset_config['step'] + "/"
        _file = "asset_" + asset_config['step']
        # convert asset{N} --> asset
        # needed for such as inference1, inference2..  
        _file = ''.join(filter(lambda x: x.isalpha() or x == '_', _file))
        user_asset = self.import_asset(_path, _file)
        ## nested dict
        meta_dict = {'artifacts': self.system_envs['artifacts'], 'pipeline': self.pipeline_type, \
                'step': step, 'step_number': step, 'step_name': self.user_parameters[self.pipeline_type][step]['step']}
        self.asset_structure.config['meta'] = meta_dict 
        if step > 0:
            ## needed for load_config, load_data at asset.py 
            self.asset_structure.envs['prev_step'] = self.user_parameters[self.pipeline_type][step - 1]['step']
        self.asset_structure.envs['step'] = self.user_parameters[self.pipeline_type][step]['step']
        self.asset_structure.envs['num_step'] = step 
        self.asset_structure.envs['asset_branch'] = asset_config['source']['branch']
        self.asset_structure.envs['check_resource'] = self.control['check_resource']
        ## set asset structure
        asset_structure = AssetStructure()
        asset_structure.config = self.asset_structure.config
        asset_structure.data = self.asset_structure.data
        asset_structure.envs = self.asset_structure.envs
        asset_structure.args = self.asset_structure.args[self.user_parameters[self.pipeline_type][step]['step']]
        ## just return if boot mode 
        if self.system_envs['boot_on'] == True:
            _log_process(f"Booting... completes importing << {_file} >>")
            return
        ## declare user asset
        try: 
            ua = user_asset(asset_structure)
        except: 
            self._publish_redis_msg("alo_fail", json.dumps(self.system_envs['redis_error_table']["E151"]))   
        ## execute run() function in user asset 
        try: 
            self.asset_structure.data, self.asset_structure.config = ua.run()
        except: 
            self._publish_redis_msg("alo_fail", json.dumps(self.system_envs['redis_error_table']["E152"]))  
            PROC_LOGGER.process_error(f"Failed to user asset run")
        # FIXME memory release : on / off needed? 
        self.memory_release(_path)
        sys.path = [item for item in sys.path if self.asset_structure.envs['step'] not in item]

    def _setup_asset(self, asset_source, get_asset_source):
        """ Clone the asset's git repository and install packages.
            Check for duplicate step names and raise an error if any exist. 
            In loop mode, the installation process is carried out only during boot-on.
            It is also possible to install only a specific asset.
            
        Args: 
            asset_source        (dict): asset source info 
            get_asset_source    (str): get asset mode - 'once' / 'every'
        
        Returns: 
            self.install_steps() (or None)
                - dup_checked_requirements_dict   (dict)
                - extracted_requirements_dict     (dict)

        """
        ## setup asset (git clone asset (or already in local) and install requirements)
        ## TODO check for duplicated steps in the current pipeline ?
        step_values = [item['step'] for item in asset_source]
        step_counts = Counter(step_values)
        for value, count in step_counts.items():
            if count > 1:
                PROC_LOGGER.process_error(f"Duplicate step exists: {value}")
        ## if loop mode, perform the installation only during boot and skip it thereafter.
        if self.system_envs['loop']:
            ## execute only once when in a loop and during boot.
            if self.system_envs['boot_on']:  
                return self._install_steps(asset_source, get_asset_source)
            else:
                return None, None
        else:
            return self._install_steps(asset_source, get_asset_source)

    def _set_asset_structure(self):
        """ Set up the environment information required to execute the pipeline.
            This is for passing the In/Out of the asset as a data structure.
        Args: -

        Returns: -

        """
        self.asset_structure.envs['project_home'] = PROJECT_HOME
        self.asset_structure.envs['solution_metadata_version'] = self.system_envs['solution_metadata_version']
        self.asset_structure.envs['artifacts'] = self.system_envs['artifacts']
        self.asset_structure.envs['alo_version'] = self.system_envs['alo_version']
        if self.control['interface_mode'] not in INTERFACE_TYPES:
            PROC_LOGGER.process_error(f"Only << file >> or << memory >> is supported for << interface_mode >>")
        self.asset_structure.envs['interface_mode'] = self.control['interface_mode']
        self.asset_structure.envs['proc_start_time'] = self.system_envs['start_time']
        self.asset_structure.envs['save_train_artifacts_path'] = self.external_path['save_train_artifacts_path']
        self.asset_structure.envs['save_inference_artifacts_path'] = self.external_path['save_inference_artifacts_path']

    def _install_steps(self, asset_source, get_asset_source='once'):
        """ install requirements of the steps
        
        Args: 
            asset_source        (dict): asset source info 
            get_asset_source    (str): get asset mode - 'once' / 'every'

        Returns: 
            dup_checked_requirements_dict   (dict)
            extracted_requirements_dict     (dict)

        """
        try: 
            requirements_dict = dict()
            for step, asset_config in enumerate(asset_source):
                self._install_asset(asset_config, get_asset_source)
                requirements_dict[asset_config['step']] = asset_config['source']['requirements']
        except: 
            self._publish_redis_msg("alo_fail", json.dumps(self.system_envs['redis_error_table']["E131"])) 
            PROC_LOGGER.process_error(f"Failed to install asset") 
        try: 
            dup_checked_requirements_dict, extracted_requirements_dict = self.install.check_install_requirements(requirements_dict)
        except: 
            self._publish_redis_msg("alo_fail", json.dumps(self.system_envs['redis_error_table']["E132"]))  
            PROC_LOGGER.process_error(f"Failed to install requirements") 
        return dup_checked_requirements_dict, extracted_requirements_dict

    def _empty_package_list(self, pipeline):
        """ package list setup - only remove current pipeline step{N}.txt
        
        Args: 
            pipeline    (str): current pipeline

        Returns: -

        """
        if not os.path.exists(ASSET_PACKAGE_PATH):
            os.makedirs(ASSET_PACKAGE_PATH) 
            PROC_LOGGER.process_message(f"{ASSET_PACKAGE_PATH} directory created")
        else: 
            for file in os.listdir(ASSET_PACKAGE_PATH):
                if pipeline in file:  
                    os.remove(ASSET_PACKAGE_PATH + file) 
                    
    def _empty_artifacts(self, pipeline):
        """ Empty artifacts. Do not delete the log folder.
        
        Args: 
            pipeline    (str): current pipeline

        Returns: -

        """
        pipe_prefix = pipeline.split('_')[0]
        dir_artifacts = PROJECT_HOME + f"{pipe_prefix}_artifacts/"
        try:
            for subdir in os.listdir(dir_artifacts):
                ## Do not delete the log folder 
                if subdir == 'log':
                    continue
                else:
                    shutil.rmtree(dir_artifacts + subdir, ignore_errors=True)
                    os.makedirs(dir_artifacts + subdir)
                    PROC_LOGGER.process_message(f"Successfully emptied << {dir_artifacts + subdir} >> ")
        except:
            PROC_LOGGER.process_error(f"Failed to empty & re-make << {pipe_prefix}_artifacts >>")

    def import_asset(self, _path, _file):
        """ import user asset 
        
        Args: 
            _path   (str): user asset path 
            _file   (str): user asset file name 
        Returns: -

        """
        _user_asset = 'none'
        try:
            sys.path.append(_path)
            ## asset_{name} import
            mod = importlib.import_module(_file)  
        except ModuleNotFoundError:
            PROC_LOGGER.process_error(f'Failed to import asset: {_path}')
        # get UserAsset class 
        _user_asset = getattr(mod, "UserAsset")
        return _user_asset
    
    def memory_release(self, _path):
        """ memory release for the modules in the {_path}
        
        Args: 
            _path   (str): path to release memory  
            
        Returns: -

        """
        all_files = os.listdir(_path)
        # .py list without extension 
        python_files = [file[:-3] for file in all_files if file.endswith(".py")]
        try:
            for module_name in python_files:
                if module_name in sys.modules:
                    del sys.modules[module_name]
        except:
            PROC_LOGGER.process_error("Failed to release the memory of module")
                      
    def _install_asset(self, asset_config, check_asset_source='once'):
        """ Set up the assets in the scripts folder based on whether the code source is local or git, 
            and whether {check_asset_source} is set to once or every.
        
        Args: 
            asset_config        (dict): The asset config for the current step.
            check_asset_source  (str): Whether to pull from git every time or just once initially 
                                       Supported values - ('once', 'every')
        Returns: -

        """
        ## TODO it may be needed to check not only the mere existence of a folder but also \
        ## the git address, branch, etc., by comparing it with the experimental_plan.yaml from the previous execution
        def _renew_asset(step_path): 
            ## determine whether to pull the asset anew from git or not
            whether_renew_asset = False
            if os.path.exists(step_path):
                pass
            else:
                whether_renew_asset = True
            return whether_renew_asset
        ## check if it is git url
        def _is_git_url(url):
            git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
            return re.match(git_url_pattern, url) is not None
        ## code: local or git url
        asset_source_code = asset_config['source']['code']
        step_name = asset_config['step']
        git_branch = asset_config['source']['branch']
        step_path = os.path.join(ASSET_HOME, asset_config['step'])
        PROC_LOGGER.process_message(f"Start setting-up << {step_name} >> asset @ << assets >> directory.")
        ## if local mode, do not consider whether {check_asset_source} is local or a git url
        ## code: local
        if asset_source_code == "local":
            if step_name in os.listdir(ASSET_HOME):
                PROC_LOGGER.process_message(f"Now << local >> asset_source_code mode: <{step_name}> asset exists.")
                pass
            else:
                PROC_LOGGER.process_error(f'Now << local >> asset_source_code mode: \n <{step_name}> asset folder does not exist in <assets> folder.')
        ## code: git url & branch specified
        else: 
            if _is_git_url(asset_source_code):
                if (check_asset_source == "every") or (check_asset_source == "once" and _renew_asset(step_path)):
                    PROC_LOGGER.process_message(f"Start renewing asset : {step_path}")
                    ## to receive new from git, remove the currently existing folder
                    if os.path.exists(step_path):
                        shutil.rmtree(step_path)  
                    os.makedirs(step_path)
                    os.chdir(PROJECT_HOME)
                    repo = git.Repo.clone_from(asset_source_code, step_path)
                    try:
                        repo.git.checkout(git_branch)
                        PROC_LOGGER.process_message(f"{step_path} successfully pulled.")
                    except:
                        PROC_LOGGER.process_error(f"Your have written incorrect git branch: {git_branch}")
                ## (Note) assets and requirements already installed 
                elif (check_asset_source == "once" and not _renew_asset(step_path)):
                    modification_time = os.path.getmtime(step_path)
                    modification_time = datetime.fromtimestamp(modification_time) 
                    PROC_LOGGER.process_message(f"<< {step_name} >> asset had already been created at {modification_time}")
                    pass
                else:
                    PROC_LOGGER.process_error(f'You have written wrong check_asset_source: {check_asset_source}')
            else:
                PROC_LOGGER.process_error(f'You have written wrong git url: {asset_source_code}')
        return

    def _create_package(self, packs):
        """ create package list written txt file 
        
        Args: 
            packs (dict): package info dict

        Returns: -

        """
        pipes_dir = ASSET_PACKAGE_PATH
        step_number = 0
        for key, values in packs.items():
            if values:
                file_name = pipes_dir + f"{self.pipeline_type}_step_{step_number}.txt"
                step_number += 1
                with open(file_name, 'w') as file:
                    for value in values:
                        if "force" in value:
                            continue
                        file.write(value + '\n')

    def _publish_redis_msg(self, channel: str, msg: str): 
        """ publish redis message if redis_pubsub object is not None 

        Args: 
            channel (str): redis publish channel 
            msg     (str): message tobe published

        Returns: -

        """
        redis_pubsub = self.system_envs["redis_pubsub_instance"]
        if redis_pubsub is not None: 
            redis_pubsub.publish(channel, msg)
        else: 
            pass