import os
import yaml
import json 
from src.constants import *
from src.logger import ProcessLogger
from copy import deepcopy 

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
#--------------------------------------------------------------------------------------------------------------------------

class Metadata:
    def _get_yaml_data(self, exp_plan, prefix='', pipeline_type='all'):
        """ Internalize the keys of the experimental plan as class variables.

        Args: 
            exp_plan        (dict): experimental plan info 
            prefix          (str): attribute prefix
            pipeline_type   (str): pipeline type (all, inference_pipeilne, train_pipeline)
            
        Returns: -

        """
        ## FIXME pipeline_type unused 
        def get_yaml_data(key, pipeline_type = 'all'): 
            data_dict = {}
            if key == "name" or key == "version":
                return exp_plan[key]
            if exp_plan[key] == None:
                return []
            for data in exp_plan[key]:
                data_dict.update(data)
            return data_dict
        for key, value in exp_plan.items():
            if not prefix=='':
                setattr(self, prefix + key, get_yaml_data(key, pipeline_type))
            else:
                setattr(self, key, get_yaml_data(key, pipeline_type))
    
    def merged_exp_plan(self, exp_plan, pipeline_type='all'):
        """ merge experimental plan 

        Args: 
            exp_plan        (dict): experimental plan info 
            pipeline_type   (str): pipeline type (all, inference_pipeilne, train_pipeline)
            
        Returns: 
            backup_exp_plan (dict): merged experimental plan

        """
        if not pipeline_type in ['train', 'inference', 'all']:
            raise ValueError("pipeline_type must be one of the < train, inference, all >")
        self._get_yaml_data(exp_plan, prefix = 'update_' )
        PROC_LOGGER.process_message(f"Successfully loaded << experimental_plan.yaml >> (file: {exp_plan})") 
        if self.name != self.update_name:
            PROC_LOGGER.process_message(f"Update name : {self.update_name}")
            self.name = self.update_name
        if self.version != self.update_version: 
            PROC_LOGGER.process_message(f"Update version : {self.update_version}")
            self.version = self.update_version
        ## external path 
        if self.external_path != self.update_external_path:
            PROC_LOGGER.process_message(f"Update external_path : {self.update_external_path}")
            self.external_path = self.update_external_path
        if self.external_path_permission != self.update_external_path_permission:
            PROC_LOGGER.process_message(f"Update external_path_permission : {self.update_external_path_permission}")
            self.external_path_permission = self.update_external_path_permission
        ## asset source & user parameters 
        if self.user_parameters != self.update_user_parameters:
            if pipeline_type != 'all':
                self.user_parameters[f'{pipeline_type}_pipeline'] = self.update_user_parameters[f'{pipeline_type}_pipeline']
            else:
                self.user_parameters = self.update_user_parameters
            PROC_LOGGER.process_message(f"Update user_parameters : {self.update_user_parameters}")
        if self.asset_source != self.update_asset_source:
            if pipeline_type != 'all':
                self.asset_source[f'{pipeline_type}_pipeline'] = self.update_asset_source[f'{pipeline_type}_pipeline']
            else:
                self.asset_source = self.update_asset_source
            PROC_LOGGER.process_message(f"Update asset_source : {self.update_asset_source}")
        if self.ui_args_detail != self.update_ui_args_detail:
            if pipeline_type != 'all':
                self.ui_args_detail[f'{pipeline_type}_pipeline'] = self.update_ui_args_detail[f'{pipeline_type}_pipeline']
            else:
                self.ui_args_detail = self.update_ui_args_detail
            PROC_LOGGER.process_message(f"Update ui_args_detail : {self.update_ui_args_detail}")
        ## control        
        if self.control != self.update_control:
            PROC_LOGGER.process_message(f"Update control : {self.update_control}")
            self.control = self.update_control
        ## make {backup_exp_plan} / values could be changed during experiments. 
        backup_exp_plan = {}
        backup_exp_plan['name'] = self.name
        backup_exp_plan['version'] = self.version
        backup_exp_plan['external_path'] = [{k: v} for k, v in self.external_path.items()]
        backup_exp_plan['external_path_permission'] = [self.external_path_permission]
        backup_exp_plan['user_parameters'] = [{k: v} for k, v in self.user_parameters.items()]
        backup_exp_plan['asset_source'] = [{k: v} for k, v in self.asset_source.items()]
        backup_exp_plan['control'] = [{k: v} for k, v in self.control.items()]
        try:
            backup_exp_plan['ui_args_detail'] = [{k: v} for k, v in self.ui_args_detail.items()]
        except:
            # FIXME need to raise error?  
            PROC_LOGGER.process_warning("Failed to parse < ui_args_detail >")
            pass
        return backup_exp_plan

    def get_yaml(self, yaml_file):
        """ Converts yaml file info into dictionary 

        Args: 
            yaml_file   (str): yaml file path
            
        Returns: 
            yaml_dict   (dict): yaml info dict
            
        """
        yaml_dict = dict()
        try:
            with open(yaml_file, encoding='UTF-8') as f:
                yaml_dict  = yaml.load(f, Loader=yaml.FullLoader)
        except FileNotFoundError:
            PROC_LOGGER.process_error(f"Not Found : {yaml_file}")
        except:
            PROC_LOGGER.process_error(f"Check yaml format : {yaml_file}")
        return yaml_dict 

    def save_yaml(self, yaml_dict, save_path):
        """ Save dictionary into yaml file

        Args: 
            yaml_dict   (dict): yaml info dict
            save_path   (str): yaml file save path
        Returns: -
        
        """
        try: 
            with open(save_path, 'w') as file:
                yaml.safe_dump(yaml_dict, file)
        except:
            PROC_LOGGER.process_error(f"Failed to save yaml into << {save_path} >>")

    def read_yaml(self, exp_plan_file, sol_meta={}, system_envs={}, update_envs=True):
        """ Read experimental plan yaml 

        Args: 
            exp_plan_file   (str): experimental plan yaml file path
            sol_meta        (dict): solution metadata info dict
            system_envs     (dict): system envs dict (for ALO internal interface)
            update_envs     (bool): whether to update system envs  
            
        Returns: -
        
        """
        try:
            PROC_LOGGER.process_message("Start to read experimental plan yaml (& update by solution meta)")
            assert type(sol_meta) == dict 
            assert type(system_envs) == dict 
            redis_pubsub = system_envs["redis_pubsub_instance"]
            exp_plan_file = self.check_copy_exp_plan(exp_plan_file) 
            PROC_LOGGER.process_message(f"Successfully loaded << experimental_plan.yaml >> (file: {exp_plan_file})") 
            try: 
                self.exp_plan = self.get_yaml(exp_plan_file)  
            except: 
                if redis_pubsub is not None:
                    redis_pubsub.publish("alo_fail", json.dumps(system_envs["redis_error_table"]["E121"]))
            self.check_exp_plan_keys(self.exp_plan) 
            ## info to class variables
            self._get_yaml_data(self.exp_plan)
            ## save name & version into {system_envs}
            if update_envs:
                system_envs["experimental_name"] = self.name
                system_envs["experimental_version"] = self.version
            ## solution metadata yaml --> exp plan yaml overwrite
            if len(sol_meta) != 0:
                self.sol_meta = sol_meta
                if update_envs:
                    try: 
                        ## (Note) {self.exp_plan} changes at _update_yaml()
                        system_envs = self._update_yaml(system_envs=system_envs)
                    except: 
                        if redis_pubsub is not None:
                            redis_pubsub.publish("alo_fail", json.dumps(system_envs["redis_error_table"]["E112"]))
                PROC_LOGGER.process_message("Finish updating solution metadata --> experimental plan")
        except:
            PROC_LOGGER.process_error("Failed to read experimental plan yaml.")
        ## match experimental plan yaml user parameters and asset git uri info.
        self._match_steps()
        return self.exp_plan

    def overwrite_solution_meta(self, exp_plan={}, sol_meta={}, system_envs={}, update_envs=True):
        """ overwrite solution metadata info. to experimental plan dict 

        Args: 
            exp_plan        (dict): experimental plan dict 
            sol_meta        (dict): solution metadata info dict
            system_envs     (dict): system envs dict (for ALO internal interface)
            update_envs     (bool): whether to update system envs  
            
        Returns: -
        
        """
        try:
            PROC_LOGGER.process_message("Start overwriting solution metadata --> experimental plan")
            assert type(sol_meta) == dict 
            assert type(system_envs) == dict 
            ## experimental plan to class variable 
            self.exp_plan = exp_plan 
            redis_pubsub = system_envs["redis_pubsub_instance"]
            self.check_exp_plan_keys(self.exp_plan) 
            ## info to class variables
            self._get_yaml_data(self.exp_plan)
            ## save name & version into {system_envs}
            if update_envs:
                system_envs["experimental_name"] = self.name
                system_envs["experimental_version"] = self.version
            ## solution metadata yaml --> exp plan yaml overwrite
            if len(sol_meta) != 0:
                self.sol_meta = sol_meta
                if update_envs:
                    try: 
                        ## (Note) {self.exp_plan} changes at _update_yaml()
                        system_envs = self._update_yaml(system_envs=system_envs)
                    except: 
                        if redis_pubsub is not None:
                            redis_pubsub.publish("alo_fail", json.dumps(system_envs["redis_error_table"]["E112"]))
                PROC_LOGGER.process_message("Finish updating solution metadata --> experimental plan")
        except:
            PROC_LOGGER.process_error("Failed to overwrite solution meta to experimental plan.")
        ## match experimental plan yaml user parameters and asset git uri info.
        self._match_steps()
        return self.exp_plan
    
    def check_exp_plan_keys(self, exp_plan: dict): 
        """ Check experimental plan keys 

        Args: 
            exp_plan    (dict): experimental plan info dict
            
        Returns: -
        
        """
        exp_plan_format = self.get_yaml(EXPERIMENTAL_PLAN_FORMAT_FILE) 
        common_error_msg = f"Format error - experimental_plan.yaml keys: \
                            \n - Please refer to this file: \n {EXPERIMENTAL_PLAN_FORMAT_FILE} \n"
        unchecked_keys = ['train_pipeline', 'inference_pipeline']
        def get_keys(dictionary):
            key_list = [] 
            for parent_k, v in dictionary.items(): 
                key_list.append(parent_k)
                if type(v) == list: 
                    for inner_dict in v:
                        if type(inner_dict) != dict: 
                            PROC_LOGGER.process_error(common_error_msg) 
                        for child_k in inner_dict.keys():
                            ## don't check {unchecked_keys}
                            if child_k not in unchecked_keys: 
                                key_list.append(parent_k + ':' + child_k)     
                elif type(v) == str: 
                    ## since name is string, only {parent_k} appended above
                    pass
                elif parent_k == 'ui_args_detail' and type(v) == type(None):
                    ## FIXME proceed for now with the execution, even if ui_args_detail is empty
                    pass 
                else:
                    PROC_LOGGER.process_error(f"experimental_plan.yaml key error: \n {parent_k}-{v} not allowed")  
            return sorted(key_list)
        exp_plan_keys, exp_plan_format_keys = get_keys(exp_plan), get_keys(exp_plan_format)
        missed_keys = [] 
        for k in exp_plan_format_keys: 
            if k not in exp_plan_keys: 
                if k.startswith("control"):
                    self._set_default_control(k)
                else: 
                    missed_keys.append(k)
        ## allow the use of optional keys that are not in the template, without affecting the missed entries
        for opt in EXPERIMENTAL_OPTIONAL_KEY_LIST:
            ## ensure both exist to allow skipping, and permit duplicates using set()
            exp_plan_format_keys.append(opt)  
            exp_plan_keys.append(opt)
        not_allowed_keys = set(exp_plan_keys)-set(exp_plan_format_keys)
        if (len(missed_keys) > 0) or (len(not_allowed_keys) > 0): 
            PROC_LOGGER.process_error(common_error_msg + f"\n - missed keys: {missed_keys} \n" + f"\n - not allowed keys: {not_allowed_keys}\n ")

    def _set_default_control(self, control_k): 
        """ default set keys under the control key

        Args: 
            control_k   (str): key pair (e.g. control:backup_size)
            
        Returns: -
        
        """
        control, k = control_k.split(":")
        default_value = None 
        if k == "get_asset_source": 
            default_value = "once"
            self.exp_plan["control"].append({"get_asset_source":default_value})
        elif k == "backup_artifacts": 
            default_value = True 
            self.exp_plan["control"].append({"backup_artifacts":default_value})
        elif k == "backup_log": 
            default_value = True 
            self.exp_plan["control"].append({"backup_log":default_value})
        elif k == "backup_size": 
            default_value = 1000
            self.exp_plan["control"].append({"backup_size":default_value})
        elif k == "interface_mode": 
            default_value = "memory"
            self.exp_plan["control"].append({"interface_mode":default_value})
        elif k == "save_inference_format": 
            default_value = "tar.gz"
            self.exp_plan["control"].append({"save_inference_format":default_value})
        elif k == "check_resource": 
            default_value = False
            self.exp_plan["control"].append({"check_resource":default_value})
        PROC_LOGGER.process_warning(f"experimental_plan.yaml control - {k} not found. Set it default value : {default_value}")

    def check_copy_exp_plan(self, exp_plan_file_path): 
        """ Check and copy experimental plan 

        Args: 
            exp_plan_file_path  (str): experimental_plan.yaml path 
            
        Returns: -
        
        """
        if exp_plan_file_path == None: 
            if os.path.exists(DEFAULT_EXP_PLAN):
                return DEFAULT_EXP_PLAN
            else: 
                PROC_LOGGER.process_error(f"<< {DEFAULT_EXP_PLAN} >> not found.")
        else: 
            try: 
                ## FIXME is reference path project home ?
                _path, _file = os.path.split(exp_plan_file_path) 
                if os.path.isabs(_path) == True:
                    pass
                else: 
                    exp_plan_file_path = _path + "/" + _file  
                    _path, _file = os.path.split(exp_plan_file_path) 
                if os.path.samefile(_path, SOLUTION_HOME): 
                    return  SOLUTION_HOME + _file 
                else:
                    if os.path.exists(exp_plan_file_path) == False:
                        PROC_LOGGER.process_error(f"<< {exp_plan_file_path} >> not found.")
                    else:
                        return  exp_plan_file_path 
            except: 
                PROC_LOGGER.process_error(f"Failed to load experimental plan. \n You entered for << --config >> : {exp_plan_file_path}")

    def _match_steps(self):
        """ Verify that the user_parameters written in experimental_plan.yaml match the steps within the asset_source.

        Args: - 
            
        Returns: 
            Boolean
        
        """
        for pipe, steps_dict in self.asset_source.items():
            param_steps = sorted([i['step'] for i in self.user_parameters[pipe]])
            source_steps = sorted([i['step'] for i in self.asset_source[pipe]])
            if param_steps != source_steps:
                PROC_LOGGER.process_error(f"@ << {pipe} >> - You have entered unmatching steps between << user_parameters >> and << asset_source >> in your experimental_plan.yaml. \n - steps in user_parameters: {param_steps} \n - steps in asset_source: {source_steps}")
        return True
    
    def _update_yaml(self, system_envs):  
        """ solution_meta's << dataset_uri, artifact_uri, selected_user_parameters ... >> into exp_plan 

        Args: 
            system_envs (dict): system envs for alo internal interface
            
        Returns: 
            system_envs (dict): updated system envs by solution metadata 
        
        """
        ## Obtain the solution metadata version 
        ## Unify the version in the inference summary YAML with this version as well
        if 'metadata_version' in self.sol_meta:
            system_envs['solution_metadata_version'] = self.sol_meta['metadata_version']
        else:
            PROC_LOGGER.process_warning("< metadata_version > not found in solution metadata. Try to set it - None") 
            system_envs['solution_metadata_version'] = None
        ## EdgeConductor interface
        if 'edgeconductor_interface' in self.sol_meta:
            system_envs['inference_result_datatype'] = self.sol_meta['edgeconductor_interface']['inference_result_datatype']
            system_envs['train_datatype'] =  self.sol_meta['edgeconductor_interface']['train_datatype']
            if (system_envs['inference_result_datatype'] not in ['image', 'table']) or (system_envs['train_datatype'] not in ['image', 'table']):
                PROC_LOGGER.process_error(f"Only << image >> or << table >> is supported for \n \
                    train_datatype & inference_result_datatype of edge-conductor interface.")
        else:
            PROC_LOGGER.process_warning("< edgeconductor_interface > not found in solution metadata. Try to set inference_result_datatype & train_datatype - None") 
            system_envs['inference_result_datatype'] = None
            system_envs['train_datatype'] = None
            
        if 'edgeapp_interface' in self.sol_meta:
            ## get redis server host, port, db num 
            try:
                system_envs['redis_host'], _redis_port = self.sol_meta['edgeapp_interface']['redis_server_uri'].split(':')
                system_envs['redis_port'] = int(_redis_port)
                if 'redis_db_number' in self.sol_meta['edgeapp_interface']:
                    system_envs['redis_db_number'] = int(self.sol_meta['edgeapp_interface']['redis_db_number'])
                else: 
                    system_envs['redis_db_number'] = int(0) 
            except:
                system_envs['redis_host'] = '0.0.0.0'
                _redis_port = '8080'
                system_envs['redis_port'] = int(_redis_port)
                system_envs['redis_db_number'] = int(0)  
                PROC_LOGGER.process_warning(f"Failed to parse < redis_server_uri > Try to set it - {system_envs['redis_host']}:{_redis_port} and redis DB number 0")
        else:
            system_envs['redis_host'] = '0.0.0.0'
            _redis_port = '8080'
            system_envs['redis_port'] = int(_redis_port)
            system_envs['redis_db_number'] = int(0)  
            PROC_LOGGER.process_warning(f"< redis_server_uri > not found in solution metadata. Try to set it - {system_envs['redis_host']}:{_redis_port} and redis DB number 0")
        assert type(system_envs['redis_port']) == int and type(system_envs['redis_db_number']) == int 
        ## set redis list key 
        system_envs['redis_key_summary'] = 'inference_summary'
        system_envs['redis_key_artifacts'] = 'inference_artifacts'
        system_envs['redis_key_request'] = 'request_inference'
        ## check user parameters 
        if 'pipeline' in self.sol_meta:  
            ## TODO Accommodate the possibility that a pipeline existing in solution_metadata \
            ## may not be present in the experimental plan.
            exp_pipe_list = []
            for params in self.exp_plan['user_parameters']:
                exp_pipe_list.append(list(params.keys())[0].replace('_pipeline',''))
            for sol_pipe in self.sol_meta['pipeline']: 
                ## e.g. train, inference 
                pipe_type = sol_pipe['type'] 
                if pipe_type in exp_pipe_list:
                    ## update parameters
                    if 'parameters' in sol_pipe:
                        selected_params = sol_pipe['parameters']['selected_user_parameters']  
                        ## find the index of the current sol meta pipe type in the experimental plan YAML
                        cur_pipe_idx = None 
                        for idx, plan_pipe in enumerate(self.exp_plan['user_parameters']):
                            ## when there is only one pipeline key and there is a corresponding plan YAML pipe for that pipeline
                            if (len(plan_pipe.keys()) == 1) and (f'{pipe_type}_pipeline' in plan_pipe.keys()): 
                                cur_pipe_idx = idx 
                        ## overwrite the experimental plan with the selected parameters
                        init_exp_plan = self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'].copy()
                        for sol_step_dict in selected_params: 
                            sol_step = sol_step_dict['step']
                            sol_args = sol_step_dict['args'] 
                            ## Pass if {sol_args} is None or an empty list 
                            ## When attaching a custom step at the end, if the step does not require args and is expressed as - args: null, \
                            ## attempting to update is incorrect, and it is appropriate that it is skipped.
                            ## Remove and return any arg that has an empty value
                            sol_args = _convert_sol_args(sol_args)  
                            if sol_args == {}: 
                                continue 
                            for idx, plan_step_dict in enumerate(init_exp_plan):  
                                if sol_step == plan_step_dict['step']:
                                    ## handle exceptions when a user leaves args blank in experimental_plan.yaml, \
                                    ## as it will cause an error during solution metadata update
                                    if self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'][idx]['args'] != None: 
                                        ## update dictionary 
                                        self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'][idx]['args'][0].update(sol_args) 
                    else: 
                        PROC_LOGGER.process_warning("< parameters > not found in solution metadata.")
                    ## update {dataset_uri}
                    if 'dataset_uri' in sol_pipe:
                        dataset_uri = sol_pipe['dataset_uri']
                        if pipe_type == 'train': 
                            for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                                if 'load_train_data_path' in ext_dict.keys(): 
                                    self.exp_plan['external_path'][idx]['load_train_data_path'] = dataset_uri
                        elif pipe_type == 'inference':
                            ## if there is no inference dataset URI during inference in the edge app, publish a Redis error.
                            if dataset_uri == None or dataset_uri == "": 
                                if system_envs["redis_pubsub_instance"] is not None:
                                    system_envs["redis_pubsub_instance"].publish("alo_fail", json.dumps(system_envs["redis_error_table"]["E122"]))    
                            for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                                if 'load_inference_data_path' in ext_dict.keys():
                                    self.exp_plan['external_path'][idx]['load_inference_data_path'] = dataset_uri  
                        else: 
                            PROC_LOGGER.process_error(f"Unsupported pipeline type for solution metadata yaml: {pipe_type}")
                    else: 
                        PROC_LOGGER.process_warning("< dataset_uri > not found in solution metadata.")
                    ## update {artifacts_uri}
                    if 'artifact_uri' in sol_pipe:
                        artifact_uri = sol_pipe['artifact_uri']
                        if pipe_type == 'train': 
                            for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                                if 'save_train_artifacts_path' in ext_dict.keys(): 
                                    self.exp_plan['external_path'][idx]['save_train_artifacts_path'] = artifact_uri   
                        elif pipe_type == 'inference':
                            for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                                if 'save_inference_artifacts_path' in ext_dict.keys():  
                                    self.exp_plan['external_path'][idx]['save_inference_artifacts_path'] = artifact_uri 
                        else: 
                            PROC_LOGGER.process_error(f"Unsupported pipeline type for solution metadata yaml: {pipe_type}")
                    else: 
                        PROC_LOGGER.process_warning("< artifact_uri > not found in solution metadata.")
                    ## update {model_uri}
                    if 'model_uri' in sol_pipe:
                        model_uri = sol_pipe['model_uri']
                        if pipe_type == 'train':
                            pass
                        elif pipe_type == 'inference':
                            for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                                if 'load_model_path' in ext_dict.keys():
                                    self.exp_plan['external_path'][idx]['load_model_path'] = model_uri
                        else: 
                            PROC_LOGGER.process_error(f"Unsupported pipeline type for solution metadata yaml: {pipe_type}")
                    else: 
                        PROC_LOGGER.process_warning("< model_uri > not found in solution metadata.")
        else:
            PROC_LOGGER.process_error("< pipeline > key not found in solution metadata. This key is mandatory")
        return system_envs

#####################################
####      INTERNAL FUNCTION      #### 
#####################################

def _convert_sol_args(_args): 
    """ - Delete any args in the selected user parameters that have empty values.
        - Convert string type comma splits into a list.

    Args: 
        _args   (dict): args tobe converted 
        
    Returns: 
        _args   (dict): converted args  
    """
    ## TODO Should we check the types of user parameters to ensure all selected_user_parameters types are validated?
    if type(_args) != dict: 
        PROC_LOGGER.process_error(f"selected_user_parameters args. in solution_medata must have << dict >> type.") 
    if _args == {}:
        return _args
    ## when a multi-selection comes in empty, the key is still sent \
    ## e.g. args : { "key" : [] }
    _args_copy = deepcopy(_args)
    for k, v in _args_copy.items():
        ## single(multi) selection 
        ## FIXME Although a dict type might not exist, just in case... \
        ## (perhaps if a dict needs to be represented as a str, it might be possible?)
        if (type(v) == list) or (type(v) == dict): 
            if len(v) == 0: 
                del _args[k]
        elif isinstance(v, str):
            if (v == None) or (v == ""): 
                del _args[k]
            else:  
                ## 'a, b' --> ['a', 'b']
                converted_string = [i.strip() for i in v.split(',')] 
                if len(converted_string) == 1: 
                    ## ['a'] --> 'a'
                    _args[k] = converted_string[0] 
                elif len(converted_string) > 1:
                    ## ['a', 'b']
                    _args[k] = converted_string 
        ## int, float 
        else: 
            if v == None: 
                del _args[k]
    return _args