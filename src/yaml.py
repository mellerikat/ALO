import os
import shutil
import yaml
from src.constants import *
from src.logger import ProcessLogger
from src.redisqueue import RedisQueue
from copy import deepcopy 
# from src.compare_yamls import compare_yaml

PROC_LOGGER = ProcessLogger(PROJECT_HOME)

class ExperimentalPlan:
    def __init__(self, exp_plan_file, sol_meta):
        self.exp_plan_file = exp_plan_file
        self.sol_meta = sol_meta

    def get_yaml(self, _yaml_file):
        yaml_dict = dict()
        try:
            with open(_yaml_file, encoding='UTF-8') as f:
                yaml_dict  = yaml.load(f, Loader=yaml.FullLoader)
        except FileNotFoundError:
            PROC_LOGGER.process_error(f"Not Found : {_yaml_file}")
        except:
            PROC_LOGGER.process_error(f"Check yaml format : {_yaml_file}")

        return yaml_dict 


    def read_yaml(self, system_envs):
        # exp_plan_file은 config 폴더로 복사해서 가져옴. 단, 외부 exp plan 파일 경로는 로컬 절대 경로만 지원 
        try:
            exp_plan_file = self.load_experimental_plan(self.exp_plan_file) 
            PROC_LOGGER.process_info(f"Successfully loaded << experimental_plan.yaml >> from: \n {exp_plan_file}") 
            
            self.exp_plan = self.get_yaml(exp_plan_file)  ## from compare_yamls.py
            # self.exp_plan = compare_yaml(self.exp_plan) # plan yaml을 최신 compare yaml 버전으로 업그레이드  ## from compare_yamls.py

            # solution metadata yaml --> exp plan yaml overwrite 
            if self.sol_meta is not None:
                self._update_yaml(system_envs=system_envs) 
                PROC_LOGGER.process_info("Finish updating solution_metadata.yaml --> experimental_plan.yaml")
            
            def get_yaml_data(key): # inner func.
                data_dict = {}
                for data in self.exp_plan[key]:
                    data_dict.update(data)
                return data_dict

            # 각 key 별 value 클래스 self 변수화 
            values = {}
            for key, value in self.exp_plan.items():
                setattr(self, key, get_yaml_data(key))
        except:
            PROC_LOGGER.process_error("Failed to read experimental plan yaml.")

        # experimental yaml에 사용자 파라미터와 asset git 주소가 매칭 (from src.utils)
        self._match_steps()

        return exp_plan_file, system_envs

    def load_experimental_plan(self, exp_plan_file_path): # called at preset func.
        if exp_plan_file_path == None: 
            if os.path.exists(EXP_PLAN):
                return EXP_PLAN
            else: 
                PROC_LOGGER.process_error(f"<< {EXP_PLAN} >> not found.")
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
                if os.path.samefile(_path, PROJECT_HOME + 'config/'): 
                    PROC_LOGGER.process_info(f"Successfully loaded experimental plan yaml: \n {PROJECT_HOME + 'config/' + _file}")
                    return  PROJECT_HOME + 'config/' + _file 
                
                # 경로가 config랑 동일하지 않으면 
                # 외부 exp plan yaml을 config/ 밑으로 복사 
                if _file in os.listdir(PROJECT_HOME + 'config/'):
                    PROC_LOGGER.process_warning(f"<< {_file} >> already exists in config directory. The file is overwritten.")
                try: 
                    shutil.copy(exp_plan_file_path, PROJECT_HOME + 'config/')
                except: 
                    PROC_LOGGER.process_error(f"Failed to copy << {exp_plan_file_path} >> into << {PROJECT_HOME + 'config/'} >>")
                # self.exp_plan_file 변수에 config/ 경로로 대입하여 return 
                PROC_LOGGER.process_info(f"Successfully loaded experimental plan yaml: \n {PROJECT_HOME + 'config/' + _file}")
                return  PROJECT_HOME + 'config/' + _file 
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
        # [중요] SOLUTION_PIPELINE_MODE라는 환경 변수는 ecr build 시 생성하게 되며 (ex. train, inference, all) 이를 ALO mode에 덮어쓰기 한다. 
        sol_pipe_mode = os.getenv('SOLUTION_PIPELINE_MODE')
        if sol_pipe_mode is not None: 
            system_envs['pipeline_mode'] = sol_pipe_mode
        else:   
            raise OSError("Environmental variable << SOLUTION_PIPELINE_MODE >> is not set.")
        # solution metadata version 가져오기 --> inference summary yaml의 version도 이걸로 통일 
        system_envs['solution_metadata_version'] = self.sol_meta['version']
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
                PROC_LOGGER.process_error(f"Unsupported pipeline type for solution metadata yaml: {pipe_type}")

            # if self.external_path[f"save_inference_artifacts_path"] is None:  
            #     PROC_LOGGER.process_error(f"You did not enter the << save_inference_artifacts_path >> in the experimental_plan.yaml") 

        # [중요] system 인자가 존재해서 _update_yaml이 실행될 때는 항상 get_external_data를 every로한다. every로 하면 항상 input/train (or input/inference)를 비우고 새로 데이터 가져온다.
        self.exp_plan['control'][0]['get_external_data'] = 'every'

        return system_envs