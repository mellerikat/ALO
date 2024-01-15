import os
import shutil
import yaml
from src.constants import *
from src.logger import ProcessLogger
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


    def read_yaml(self):
        # exp_plan_file은 config 폴더로 복사해서 가져옴. 단, 외부 exp plan 파일 경로는 로컬 절대 경로만 지원 
        try:
            exp_plan_file = self.load_experimental_plan(self.exp_plan_file) 
            PROC_LOGGER.process_info(f"Successfully loaded << experimental_plan.yaml >> from: \n {exp_plan_file}") 
            
            self.exp_plan = self.get_yaml(exp_plan_file)  ## from compare_yamls.py
            # self.exp_plan = compare_yaml(self.exp_plan) # plan yaml을 최신 compare yaml 버전으로 업그레이드  ## from compare_yamls.py

            # solution metadata yaml --> exp plan yaml overwrite 
            if self.sol_meta is not None:
                self._update_yaml() 
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

        return exp_plan_file

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
                    exp_plan_file_path = PROJECT_HOME + 'config/' + exp_plan_file_path  
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