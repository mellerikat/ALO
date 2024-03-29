import os
import yaml
from src.constants import *
from src.logger import ProcessLogger
from src.redisqueue import RedisQueue
from copy import deepcopy 

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
#--------------------------------------------------------------------------------------------------------------------------
class Metadata:
    def _get_yaml_data(self, exp_plan, prefix='', pipeline_type='all'):
        """ exp_plan 의 key 를 내부 변수화 하기 """
        def get_yaml_data(key, pipeline_type = 'all'): # inner func.
            data_dict = {}
            if key == "name" or key == "version":
                return exp_plan[key]
            if exp_plan[key] == None:
                return []
            for data in exp_plan[key]:
                data_dict.update(data)
            return data_dict
        # 각 key 별 value 클래스 self 변수화 --> ALO init() 함수에서 ALO 내부변수로 넘김
        values = {}
        for key, value in exp_plan.items():
            if not prefix=='':
                setattr(self, prefix + key, get_yaml_data(key, pipeline_type))
            else:
                setattr(self, key, get_yaml_data(key, pipeline_type))
    
    def merged_exp_plan(self, exp_plan, pipeline_type='all'):
        if not pipeline_type in ['train', 'inference', 'all']:
            raise ValueError("pipeline_type must be 'all', 'train' or 'inference'")
        self._get_yaml_data(exp_plan, prefix = 'update_' )
        PROC_LOGGER.process_message(f"Successfully loaded << experimental_plan.yaml >> (file: {exp_plan})") 
        if self.name != self.update_name:
            PROC_LOGGER.process_message(f"Update name : {self.update_name}")
            self.name = self.update_name
        if self.version != self.update_version: 
            PROC_LOGGER.process_message(f"Update version : {self.update_version}")
            self.version = self.update_version
        ##### external path 
        if self.external_path != self.update_external_path:
            PROC_LOGGER.process_message(f"Update external_path : {self.update_external_path}")
            self.external_path = self.update_external_path
        if self.external_path_permission != self.update_external_path_permission:
            PROC_LOGGER.process_message(f"Update external_path_permission : {self.update_external_path_permission}")
            self.external_path_permission = self.update_external_path_permission
        ##### asset source 와 user parameters 
        if self.user_parameters != self.update_user_parameters:
            if pipeline_type == 'train':
                self.user_parameters['train_pipeline'] = self.update_user_parameters['train_pipeline']
            elif pipeline_type == 'inference':
                self.user_parameters['inference_pipeline'] = self.update_user_parameters['inference_pipeline']
            else:
                self.user_parameters = self.update_user_parameters
            PROC_LOGGER.process_message(f"Update user_parameters : {self.update_user_parameters}")
        if self.asset_source != self.update_asset_source:
            if pipeline_type == 'train':
                self.asset_source['train_pipeline'] = self.update_asset_source['train_pipeline']
            elif pipeline_type == 'inference':
                self.asset_source['inference_pipeline'] = self.update_asset_source['inference_pipeline']
            else:
                self.asset_source = self.update_asset_source
            PROC_LOGGER.process_message(f"Update asset_source : {self.update_asset_source}")
        if self.ui_args_detail != self.update_ui_args_detail:
            if pipeline_type == 'train':
                self.ui_args_detail['train_pipeline'] = self.update_ui_args_detail['train_pipeline']
            elif pipeline_type == 'inference':
                self.ui_args_detail['inference_pipeline'] = self.update_ui_args_detail['inference_pipeline']
            else:
                self.ui_args_detail = self.update_ui_args_detail
            PROC_LOGGER.process_message(f"Update ui_args_detail : {self.update_ui_args_detail}")
        ##### asset source 와 user parameters 
        ##### control        
        if self.control != self.update_control:
            PROC_LOGGER.process_message(f"Update control : {self.update_control}")
            self.control = self.update_control
        ## exp_plan 만들기. 실험 중에 중간 값들이 변경되어 있으므로, 꼭 ~ 재구성하여 저장한다.
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
            pass   ## 존재하지 않는 경우 대응
        return backup_exp_plan

    def get_yaml(self, yaml_file):
        """yaml file을 읽어서 dict화 합니다.
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
        """dict를 yaml file화 시킵니다. 
        - yaml_dict: dict화 된 yaml 
        - save_path: yaml file 경로 
        """
        try: 
            with open(save_path, 'w') as file:
                yaml.safe_dump(yaml_dict, file)
        except:
            PROC_LOGGER.process_error(f"Failed to save yaml into << {save_path} >>")

    def read_yaml(self, exp_plan_file,  sol_me_file=None, system_envs={}, update_envs=True):
        # exp_plan_file은 config 폴더로 복사해서 가져옴. 단, 외부 exp plan 파일 경로는 로컬 절대 경로만 지원 
        try:
            exp_plan_file = self.check_and_copy_expplan(exp_plan_file) 
            if update_envs:  
                PROC_LOGGER.process_message(f"Successfully loaded << experimental_plan.yaml >> (file: {exp_plan_file})") 
            self.exp_plan = self.get_yaml(exp_plan_file)  ## from compare_yamls.py
            # self.exp_plan = compare_yaml(self.exp_plan) # plan yaml을 최신 compare yaml 버전으로 업그레이드  ## from compare_yamls.py
            self.check_exp_plan_keys(self.exp_plan) 
            # 각 key 별 value 클래스 self 변수화 --> ALO init() 함수에서 ALO 내부변수로 넘김
            self._get_yaml_data(self.exp_plan)
            ## v2.3.0 NEW : name, version 을 system_envs 에 저장한다. 
            if update_envs:
                system_envs["experimental_name"] = self.name
                system_envs["experimental_version"] = self.version
            # solution metadata yaml --> exp plan yaml overwrite
            if sol_me_file is not None:
                self.sol_meta = sol_me_file
                if update_envs:
                    # 주의: _update_yaml에서 self.exp_plan의 내용이 바뀜
                    system_envs = self._update_yaml(system_envs=system_envs)
                PROC_LOGGER.process_message("Finish updating solution_metadata.yaml --> experimental_plan.yaml")
        except:
            PROC_LOGGER.process_error("Failed to read experimental plan yaml.")
        # experimental yaml에 사용자 파라미터와 asset git 주소가 매칭 (from src.utils)
        self._match_steps()
        return self.exp_plan

    # TODO rel 2.2 --> 2.2.1 added 
    def check_exp_plan_keys(self, exp_plan: dict): 
        exp_plan_format = self.get_yaml(EXPERIMENTAL_PLAN_FORMAT_FILE) ## dict 
        common_error_msg = f"experimental_plan.yaml key error: \
                            \n - ! Please refer to this file: \n {EXPERIMENTAL_PLAN_FORMAT_FILE} \n"
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
                            if child_k not in unchecked_keys: # unchecked_keys는 check 대상에서 제외 
                                key_list.append(parent_k + ':' + child_k)     
                elif type(v) == str: 
                    pass # name 은 str 이므로 parent_k만 위에서 추가
                elif parent_k == 'ui_args_detail' and type(v) == type(None):
                    pass # ui_args_detail는 비어 있어도 실행이 되게 일단 진행
                else:
                    PROC_LOGGER.process_error(f"experimental_plan.yaml key error: \n {parent_k}-{v} not allowed")  
            return sorted(key_list)
        exp_plan_keys, exp_plan_format_keys = get_keys(exp_plan), get_keys(exp_plan_format)
        missed_keys = [] 
        for k in exp_plan_format_keys: 
            if k not in exp_plan_keys: 
                missed_keys.append(k)
        ## optional key 는 template 에는 없지만, 사용 허용 하도록 함. (missed 에는 영향 없음) 
        for opt in EXPERIMENTAL_OPTIONAL_KEY_LIST:
            exp_plan_format_keys.append(opt)  ## 둘다 존재 하도록해서 skip 되도록 함. set() 으로 중복도 허용
            exp_plan_keys.append(opt)
        not_allowed_keys = set(exp_plan_keys)-set(exp_plan_format_keys)
        if (len(missed_keys) > 0) or (len(not_allowed_keys) > 0): 
            PROC_LOGGER.process_error(common_error_msg + f"\n - missed keys: {missed_keys} \n" + f"\n - not allowed keys: {not_allowed_keys}\n ")
         
    def check_and_copy_expplan(self, exp_plan_file_path): # called at preset func.
        if exp_plan_file_path == None: 
            if os.path.exists(DEFAULT_EXP_PLAN):
                return DEFAULT_EXP_PLAN
            else: 
                PROC_LOGGER.process_error(f"<< {DEFAULT_EXP_PLAN} >> not found.")
        else: 
            try: 
                # 입력한 경로가 상대 경로이면 config 기준으로 경로 변환  
                _path, _file = os.path.split(exp_plan_file_path) 
                if os.path.isabs(_path) == True:
                    pass
                else: 
                    exp_plan_file_path = _path + "/" + _file  
                    _path, _file = os.path.split(exp_plan_file_path) 
                # 경로가 config랑 동일하면 (samefile은 dir, file 다 비교가능) 그냥 바로 return 
                if os.path.samefile(_path, SOLUTION_HOME): 
                    return  SOLUTION_HOME + _file 
                else:
                    if os.path.exists(exp_plan_file_path) == False:
                        PROC_LOGGER.process_error(f"<< {exp_plan_file_path} >> not found.")
                    else:
                        return  exp_plan_file_path 
            except: 
                PROC_LOGGER.process_error(f"Failed to load experimental plan. \n You entered for << --config >> : {exp_plan_file_path}")

    # FIXME pipeline name 추가 시 추가 고려 필요 
    def _match_steps(self):
        """ Description
            -----------
                - experimental_plan.yaml에 적힌 user_parameters와 asset_source 내의 steps들이 일치하는 지 확인 
            Parameters
            -----------
                - user_parameters: (dict)
                - asset_source: (dict)
            Return
            -----------

            Example
            -----------
                - match_steps(user_parameters, asset_source)
        """
        for pipe, steps_dict in self.asset_source.items():
            param_steps = sorted([i['step'] for i in self.user_parameters[pipe]])
            source_steps = sorted([i['step'] for i in self.asset_source[pipe]])
            if param_steps != source_steps:
                PROC_LOGGER.process_error(f"@ << {pipe} >> - You have entered unmatching steps between << user_parameters >> and << asset_source >> in your experimental_plan.yaml. \n - steps in user_parameters: {param_steps} \n - steps in asset_source: {source_steps}")
        return True
    
    def _update_yaml(self, system_envs):  
        '''
        sol_meta's << dataset_uri, artifact_uri, selected_user_parameters ... >> into exp_plan 
        '''
        # solution metadata version 가져오기 --> inference summary yaml의 version도 이걸로 통일 
        # key 명 바뀜 version -> metadata_version (24.02.02)
        system_envs['solution_metadata_version'] = self.sol_meta['metadata_version']
        # solution metadata yaml에 pipeline key 있는지 체크 
        if 'pipeline' not in self.sol_meta.keys(): # key check 
            PROC_LOGGER.process_error("Not found key << pipeline >> in the solution metadata yaml file.") 
        # EdgeConductor Interface
        system_envs['inference_result_datatype'] = self.sol_meta['edgeconductor_interface']['inference_result_datatype']
        system_envs['train_datatype'] =  self.sol_meta['edgeconductor_interface']['train_datatype']
        if (system_envs['inference_result_datatype'] not in ['image', 'table']) or (system_envs['train_datatype'] not in ['image', 'table']):
            PROC_LOGGER.process_error(f"Only << image >> or << table >> is supported for \n \
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
                system_envs['redis_host'], _redis_port = self.sol_meta['edgeapp_interface']['redis_server_uri'].split(':')
                system_envs['redis_port'] = int(_redis_port)
                if (system_envs['redis_host'] == None) or (system_envs['redis_port'] == None): 
                    PROC_LOGGER.process_error("Missing host or port of << redis_server_uri >> in solution metadata.")
                # set redis queues
                system_envs['q_inference_summary'] = RedisQueue('inference_summary', host=system_envs['redis_host'], port=system_envs['redis_port'], db=0)
                system_envs['q_inference_artifacts'] = RedisQueue('inference_artifacts', host=system_envs['redis_host'], port=system_envs['redis_port'], db=0)
            except: 
                PROC_LOGGER.process_error(f"Failed to parse << redis_server_uri >>") 
        def _convert_sol_args(_args): # inner func.
            # TODO user parameters 의 type check 해서 selected_user_paramters type 다 체크할 것인가? 
            '''
            # _args: dict 
            # selected user parameters args 중 값이 비어있는 arg는 delete  
            # string type의 comma split은 list로 변환 * 
            '''
            if type(_args) != dict: 
                PROC_LOGGER.process_error(f"selected_user_parameters args. in solution_medata must have << dict >> type.") 
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
        # TODO: solution_metadata 에 존재하는 pipeline 이 experimental 에는 존재 하지 않을 수 있음을 대응
        exp_pipe_list = []
        for params in self.exp_plan['user_parameters']:
            exp_pipe_list.append(list(params.keys())[0].replace('_pipeline',''))
        for sol_pipe in self.sol_meta['pipeline']: 
            pipe_type = sol_pipe['type'] # train, inference 
            if pipe_type in exp_pipe_list:
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
                            # 사용자가 experimental_plan.yaml에 args: 빈칸으로 두면 solution metadata update 시 에러가나므로 예외처리 
                            if self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'][idx]['args'] != None: 
                                self.exp_plan['user_parameters'][cur_pipe_idx][f'{pipe_type}_pipeline'][idx]['args'][0].update(sol_args) #dict update
                # external path 덮어 쓰기 
                if pipe_type == 'train': 
                    check_train_keys = []
                    for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                        if 'load_train_data_path' in ext_dict.keys(): 
                            self.exp_plan['external_path'][idx]['load_train_data_path'] = dataset_uri
                            check_train_keys.append('load_train_data_path') 
                        if 'save_train_artifacts_path' in ext_dict.keys(): 
                            self.exp_plan['external_path'][idx]['save_train_artifacts_path'] = artifact_uri   
                            check_train_keys.append('save_train_artifacts_path') 
                    diff_keys = set(['load_train_data_path', 'save_train_artifacts_path']) - set(check_train_keys)
                    if len(diff_keys) != 0:
                        PROC_LOGGER.process_error(f"<< {diff_keys} >> key does not exist in experimental plan yaml.")
                elif pipe_type == 'inference':
                    check_inference_keys = []
                    for idx, ext_dict in enumerate(self.exp_plan['external_path']):
                        if 'load_inference_data_path' in ext_dict.keys():
                            self.exp_plan['external_path'][idx]['load_inference_data_path'] = dataset_uri  
                            check_inference_keys.append('load_inference_data_path')
                        if 'save_inference_artifacts_path' in ext_dict.keys():  
                            self.exp_plan['external_path'][idx]['save_inference_artifacts_path'] = artifact_uri 
                            check_inference_keys.append('save_inference_artifacts_path')
                        # inference type인 경우 model_uri를 plan yaml의 external_path의 load_model_path로 덮어쓰기
                        if 'load_model_path' in ext_dict.keys():
                            self.exp_plan['external_path'][idx]['load_model_path'] = sol_pipe['model_uri']
                            check_inference_keys.append('load_model_path')
                    diff_keys = set(['load_inference_data_path', 'save_inference_artifacts_path', 'load_model_path']) - set(check_inference_keys)
                    if len(diff_keys) != 0:
                        PROC_LOGGER.process_error(f"<< {diff_keys} >> key does not exist in experimental plan yaml.")
                else: 
                    PROC_LOGGER.process_error(f"Unsupported pipeline type for solution metadata yaml: {pipe_type}")
        return system_envs