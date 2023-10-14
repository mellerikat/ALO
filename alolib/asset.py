# -*- coding: utf-8 -*-

import os
import json
import shutil
import pickle

import boto3
from datetime import datetime
from pytz import timezone
from boto3.session import Session

import subprocess 
from collections import defaultdict
# [FIXME] # DeprecationWarning: pkg_resources is deprecated as an API. 해결 필요? 
import pkg_resources 
import yaml
import importlib
import sys 
import re
#pip install GitPython
import git

from alolib.common import * 
from alolib.exception import print_color

from alolib.s3downloader import S3Downloader
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
COLOR_RED = '\033[91m'
COLOR_END = '\033[0m'

ARG_NAME_MAX_LENGTH = 30

#--------------------------------------------------------------------------------------------------------------------------
#    CLASS
#--------------------------------------------------------------------------------------------------------------------------
# TODO 참고로 코드 상에 '/' 같은 경로를 쓰는건 docker 기반이고 linux 환경만 감안하기 때문. (윈도우의 '\\' 같은건 비허용)
class Asset:
    def __init__(self, envs, argv, version='None'):
        self.asset = self
        self.asset_envs = {}
        self.asset_args = {}
        self.asset_config = {}
        self.context = {}
        self.asset_version = version
        self.debug_mode = False
        ##########################
        # [FIXME] input 폴더는 external_path 데이터 가져올 때 초기화 돼야한다. 
        self.artifacts_structure = {
            'input': {}, 
            '.train_artifacts': {
                'score': {},
                'output': {},
                'log': {},
                'report': {},
                'models': {}
            },
            '.inference_artifacts': {
                'score': {},
                'output': {},
                'log': {},
                'report': {}
            },
            '.asset_interface': {},
            '.history': {}
        }
        #self.supported_extension = [".joblib", ".pkl", ".pt", ".json", ".h5"] #지원되는 확장자 관리 
        ##########################
        # 1. set envs
        ##########################
        self.asset_envs = envs
        # 현재 PROJECT PATH 보다 한 층 위 folder 
        self.project_home = self.asset_envs['project_home']
        # FIXME  사용자 api 에서 envs 를 arguments로 안받기 위해 artifacts 변수 생성 
        self.asset_envs["artifacts"] = self.set_artifacts()
        # input 데이터 경로 
        self.input_data_home = self.project_home + "input/"
        # asset 코드들의 위치
        self.asset_home = self.project_home + "assets/"
        # 2. METADATA : NOTE 위치 중요(envs 를 활용한다.)

        # 3. set context properties
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        os.environ['INFTIME'] = current_time

        try:
            # 4. set argv
            self.asset_args = argv#self._set_arguments(argv)
            # 5. check arg
            # 개발 필요 230913 swj
            # self._check_arguments(self.asset_args)

            # 6. update envs : NOTE 위치 중요 (self.context 와 self.metadata를 활용한다.)

            # 6. update asset information : version, args
            # 개발 필요 230913 swj
            # self._set_asset_information()

            # 8. Tfrecord

            # 9. 처음실행되는 step 에서 확인
            # 폴더 생성 개발 필요
            # if self.context['system']['last_step'] == 'none':
            #     check_path(self.asset_envs['input_path'])
            #     check_path(self.asset_envs['metadata_path'])
            #     check_path(self.asset_envs['output_path'])
            #     check_path(self.asset_envs['train_path'])
            #     check_path(self.asset_envs['inference_path'])
            #     check_path(self.asset_envs['interface_path'])
                
            #     check_path(self.asset_envs['temp_path'])
            #     check_path(self.asset_envs['storage_path'])
            #     check_path(self.asset_envs['model_path'])

            # self._asset_info()
        except Exception as e:
            self._asset_error(str(e))
    
##################################################################################################################################################################
    #                                                                           Slave API
    ##################################################################################################################################################################
    def save_summary(self, result, score, note="AI Advisor", probability=None):
        
        """ Description
            -----------
                - train_summary.yaml (train 시에도 학습을 진행할 시) 혹은 inference_summary.yaml을 저장합니다. 
                - 참고 CLM: http://collab.lge.com/main/display/LGEPROD/AI+Advisor+Data+Flow#Architecture--1257299622
                - 숫자 형은 모두 소수점 둘째 자리까지 표시합니다.  
            Parameters
            -----------
                - result: Inference result summarized info. (str, length limit: 12) 
                - score: model performance score to be used for model retraining (float, 0 ~ 1.0)
                - note: optional & additional info. for inference result (str, length limit: 100) (optional)
                - probability: Classification Solution의 경우 라벨 별로 확률 값을 제공합니다. (dict - key:str, value:float) (optional)
                            >> (ex) {'OK': 0.6, 'NG':0.4}
            Return
            -----------
                - summaray_data: summary yaml 파일에 저장될 데이터 (dict) 
            Example
            -----------
                - summary_data = save_summary(result='OK', score=0.613, note='aloalo.csv', probability={'OK':0.715, 'NG':0.135, 'NG1':0.15})
        """
        # result는 문자열 12자 이내인지 확인
        if not isinstance(result, str) or len(result) > 12:
            self._asset_error("The length of string argument << result >>  must be within 12 ")
        
        # score는 0 ~ 1.0 사이의 값인지 확인
        if not isinstance(score, (int, float)) or not 0 <= score <= 1.0:
            self._asset_error("The value of float (or int) argument << score >> must be between 0.0 and 1.0 ")

        # note는 문자열 100자 이내인지 확인
        if not isinstance(result, str) or len(note) > 100:
            self._asset_error("The length of string argument << note >>  must be within 100 ")
                    
        # probability가 존재하는 경우 dict인지 확인
        if (probability is not None) and (not isinstance(probability, dict)):
            self._asset_error("The type of argument << probability >> must be << dict >>")
        # probability key는 string이고 value는 float or int인지 확인 
        key_chk_str_set = set([isinstance(k, str) for k in probability.keys()])
        value_type_set = set([type(v) for v in probability.values()])
        if key_chk_str_set != {True}: 
            self._asset_error("The key of dict argument << probability >> must have the type of << str >> ")
        if not value_type_set.issubset({float, int}): 
            self._asset_error("The value of dict argument << probability >> must have the type of << int >> or << float >> ")
        # probability value 합이 1인지 확인 
        if sum(probability.values()) != 1: 
            self._asset_error("The sum of probability dict values must be << 1.0 >>")
        
        # FIXME 가령 0.50001, 0.49999 같은건 대응이 안됨 
        # FIXME 처음에 사용자가 입력한 dict가 합 1인지도 체크필요 > 부동소수 에러 예상
        def make_addup_1(prob): #inner func. / probability 합산이 1이되도록 가공, 소수 둘째 자리까지 표시 
            max_value_key = max(prob, key=prob.get) 
            proc_prob_dict = dict()  
            for k, v in prob.items(): 
                if k == max_value_key: 
                    proc_prob_dict[k] = 0 
                    continue
                proc_prob_dict[k] = round(v, 2) # 소수 둘째자리
            proc_prob_dict[max_value_key] = round(1 - sum(proc_prob_dict.values()), 2)
            return proc_prob_dict
                    
        
        # FIXME 배포 테스트 시 probability의 key 값 (클래스)도 정확히 모든 값 기입 됐는지 체크 필요     
        # dict type data to be saved in summary yaml 
        summary_data = {
            'result': result,
            'score': round(score, 2), # 소수 둘째자리
            'date': os.environ['INFTIME'], # UTC TIME 
            # FIXME note에 input file 명 전달할 방법 고안 필요 
            'note': note,
            'probability': make_addup_1(probability)
        }
        # self.asset_envs['pipeline'] 는 main.py에서 설정 
        if self.asset_envs['pipeline']  == "train_pipeline":
            file_path = self.asset_envs["artifacts"][".train_artifacts"] + "score/" + "train_summary.yaml" 
        elif self.asset_envs['pipeline'] == "inference_pipeline":
            file_path = self.asset_envs["artifacts"][".inference_artifacts"] + "score/" + "inference_summary.yaml" 
        else: 
            self._asset_error(f"You have written wrong value for << asset_source  >> in the config yaml file. - { self.asset_envs['pipeline']} \n Only << train_pipeline >> and << inference_pipeline >> are permitted")
        
        # save summary yaml 
        try:      
            with open(file_path, 'w') as file:
                yaml.dump(summary_data, file, default_flow_style=False)
        except: 
            self._asset_error(f"Failed to save summary yaml file \n @ << {file_path} >>")
             
        return summary_data

    # FIXME 만약 inference pipeline 여러개인 경우 model 파일이름을 사용자가 잘 분리해서 사용해야함 > pipline name 인자 관련 생각필요 
    # FIXME multi train, inference pipeline 일 때 pipeline name (yaml에 추가될 예정)으로 subfloder 분리해서 저장해야한다. (step이름 중복 가능성 존재하므로)
    # >> os.envrion 변수에 저장하면 되므로 사용자 파라미터 추가할 필욘 없을 듯
    # FIXME  step명은 같은걸로 pair, train-inference만 예외 pair / 단, cascaded train같은경우는 train1-inference1, train2-inference2가 pair  식으로
    def get_model_path(self, use_inference_path=False): # get_model_path 는 inference 시에 train artifacts 접근할 경우도 있으므로 pipeline_mode랑 step_name 인자로 받아야함 
        """ Description
            -----------
                - model save 혹은 load 시 필요한 model path를 반환한다. 
            Parameters
            -----------
                - use_inference_path: default는 False여서, train pipeline이던 inference pipline이던 train model path 반환하고,
                                      예외적으로 True로 설정하면 inference pipeline이 자기 자신 pipeline name의 subfolder를 반환한다. (bool)
            Return
            -----------
                - model_path: model 경로 
            Example
            -----------
                - model_path = get_model_path(use_inference_path=False)
        """
        # use_inference_path type check 
        if not isinstance(use_inference_path, bool):
            self._asset_error("The type of argument << use_inference_path >>  must be << boolean >> ")
        
        # yaml에 잘 "train_pipeline" or "inference_pipeline" 라고 잘 입력했는지 체크
        allowed_pipeline_mode_list = ["train_pipeline",  "inference_pipeline"]
        current_pipe_mode = self.asset_envs['pipeline']
        if current_pipe_mode not in allowed_pipeline_mode_list: 
            self._asset_error(f"You entered the wrong parameter for << user_parameters >> in your config yaml file : << {current_pipe_mode} >>. \n L ""You can select the pipeline_mode among << {allowed_pipeline_mode_list} >>"" ")
        
        # create step path 
        # default로는 step name은 train-inference 혹은 inference1-inference2 (추후 pipeline_name 추가 시) 간의 step 명이 같은 것 끼리 pair 
        # self.asset_envs['step']는 main.py에서 설정 
        current_step_name = self.asset_envs['step'] 
        model_path = self.asset_envs["artifacts"][".train_artifacts"] + f"models/{current_step_name}/"

        # inference pipeline 때 train artifacts에 같은 step 이름 없으면 에러 
        if current_pipe_mode  == "inference_pipeline":
            if not os.path.exists(model_path):
                self._asset_error(f"You must execute train pipeline first. There is no model path : \n {model_path}") 
        
        # FIXME pipeline name 관련해서 추가 yaml 인자 받아서 추가 개발 필요 
        if (current_pipe_mode  == "inference_pipeline") and (current_step_name == "inference"):
            model_path = self.asset_envs["artifacts"][".train_artifacts"] + f"models/train/"
            if not os.path.exists(model_path): 
                self._asset_error(f"You must execute train pipeline first. There is no model path : \n {model_path}") 
            elif (os.path.exists(model_path)) and (len(os.listdir(model_path)) == 0): 
                self._asset_error(f"You must generate train model first. There is no model in the train model path : \n {model_path}") 
                    
        # trian 땐 없으면 폴더 생성 
        os.makedirs(model_path, exist_ok=True) # exist_ok =True : 이미 존재하면 그대로 둠 
        print_color(f">> Successfully got model path for saving or loading your AI model: \n {model_path}", "green")
        
        return model_path

    # FIXME multi train, inference pipeline 일 때 pipeline name (yaml에 추가될 예정)으로 subfloder 분리해서 저장해야한다. 파일이름이 output.csv, output.jpg로 고정이므로 
    # >> os.envrion 변수에 저장하면 되므로 사용자 파라미터 추가할 필욘 없을 듯 
    def get_output_path(self):
        """ Description
            -----------
                - train 혹은 inference artifacts output을 저장할 경로 반환 
                - 이름은 output.csv, output.jpg 로 고정 (정책)
            Parameters
            -----------
            Return
            -----------
                - output_path: 산출물을 저장할 output 경로 
            Example
            -----------
                - output_path = get_output_path("csv")
        """
        # yaml에 잘 "train_pipeline" or "inference_pipeline" 라고 잘 입력했는지 체크
        # self.asset_envs['pipeline'] check 
        # self.asset_envs['pipeline']은 main.py에서 설정
        allowed_pipeline_mode_list = ["train_pipeline",  "inference_pipeline"]
        current_pipe_mode = self.asset_envs['pipeline']
        if current_pipe_mode  not in allowed_pipeline_mode_list: 
            self._asset_error(f"You entered the wrong parameter for << user_parameters >> in your config yaml file : << {current_pipe_mode} >>. \n L ""You can select the pipeline_mode among << {allowed_pipeline_mode_list} >>"" ")
        
        # create output path 
        output_path = ""
        if  current_pipe_mode == "train_pipeline":
            output_path = self.asset_envs["artifacts"][".train_artifacts"] + f"output/"
            os.makedirs(output_path, exist_ok=True) # exist_ok =True : 이미 존재하면 그대로 둠 
        elif current_pipe_mode == 'inference_pipeline': 
            output_path = self.asset_envs["artifacts"][".inference_artifacts"] + f"output/"
            os.makedirs(output_path, exist_ok=True)
            
        print_color(f">> Successfully got << output path >> for saving your data into csv or jpg file: \n {output_path} \n L [NOTE] ""The names of output file must be fixed as << output.csv, output.jpg >>"" ", "green")
        
        return output_path

    def get_report_path(self):
        """ Description
            -----------
                - report 를 저장할 path 반환. report는 train pipeline에서만 생성 (정책)
                
            Parameters
            -----------

            Return
            -----------
                - report_path: report.html을 저장할 output 경로 
            Example
            -----------
                - report_path = get_report_path()
        """
        
        # self.asset_envs['pipeline'] check >> train pipeline만 허용! 
       # self.asset_envs['pipeline']은 main.py에서 설정
        allowed_pipeline_mode_list = ["train_pipeline"]
        current_pipe_mode = self.asset_envs['pipeline']
        if current_pipe_mode  not in allowed_pipeline_mode_list: 
            self._asset_error(f"You entered the wrong parameter for << user_parameters >> in your config yaml file : << {current_pipe_mode} >>. \n L ""You can select the pipeline_mode among << {allowed_pipeline_mode_list} >>"" ")
            
        # create report path 
        report_path = self.asset_envs["artifacts"][".train_artifacts"] + f"report/"
        os.makedirs(report_path, exist_ok=True) # exist_ok =True : 이미 존재하면 그대로 둠 

        report_path  = report_path
        print_color(f">> Successfully got << report path >> for saving your << report.html >> file: \n {report_path}", "green")
        
        return report_path
    
    
    ##################################################################################################################################################################
    
    ##################################################################################################################################################################

    def release(self, _path):
        all_files = os.listdir(_path)
        # .py 확장자를 가진 파일만 필터링하여 리스트에 추가하고 확장자를 제거
        python_files = [file[:-3] for file in all_files if file.endswith(".py")]
        try:
            for module_name in python_files:
                if module_name in sys.modules:
                    del sys.modules[module_name]
        except:
            self._asset_error("An issue occurred while deleting the module")

    def get_toss(self, _pipe_num, envs):
        try:
            file_path = envs['artifacts']['.asset_interface'] + _pipe_num + "/" + envs['step'] + ".pkl"
            data = self.load_file(file_path)
            config = data.pop('config')

            return data, config

        except Exception as e:
            self._asset_error(str(e))
    
    def toss(self, data, config, pipe_num, envs):
        try:
            data['config'] = config
            folder_path = envs['artifacts']['.asset_interface'] + pipe_num + "/"
            # if os.path.exists(folder_path):
            #     shutil.rmtree(folder_path)
            #     print(f"{folder_path} 폴더를 제거했습니다.")

            # 폴더 생성
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                print(f"{folder_path} 폴더가 생성되었습니다.")
            else:
                print(f"{folder_path} 폴더는 이미 존재합니다.")
            
            # os.makedirs(folder_path)
            # print(f"{folder_path} 폴더가 생성되었습니다.")

            data_file = folder_path + envs['step']
            if type(data) == dict:
                data_file = data_file + ".pkl"
            else:
                self._asset_error("아직 지원하지 않는 기능입니다")
            # if type(data) == pd.DataFrame:
            #     data_file = data_file + ".csv"
            self.save_file(data, data_file)
        except Exception as e:
            self._asset_error(str(e))


    def fetch_data(self, external_path, external_path_permission): 
        ## [FIXME] 진짜 input 데이터 지우고 시작하는게 맞을지 검토필요 
        # fetch_data 할 때는 항상 input 폴더 비우고 시작한다 
        if os.path.exists(self.input_data_home):
            for file in os.scandir(self.input_data_home):
                print_color(f">> Start removing pre-existing input data before fetching external data: {file}", "yellow")
                shutil.rmtree(file.path)
     
            
        # 대전제 : 중복 이름의 데이터 폴더명은 복사 허용 x 
        load_train_data_path =  external_path['load_train_data_path'] # 0개 일수도(None), 한 개 일수도(str), 두 개 이상 일수도 있음(list) 
        load_inference_data_path =  external_path['load_inference_data_path']

        # FIXME ws external_path_permission으로 받아 오는 수정 코드 작성
        try:
            load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
            print_color(f'>> s3 private key file << load_s3_key_path >> loaded successfully.', 'green')   
        except:
            print_color('>> You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment.' , 'yellow')
            load_s3_key_path = None
            
        # external path가 존재 안하는 경우 
        if (load_train_data_path is None) and (load_inference_data_path is None): 
            # 이미 input 폴더는 무조건 만들어져 있는 상태임 
            # [FIXME] input 폴더가 비어있으면 프로세스 종료, 뭔가 서브폴더가 있으면 사용자한테 존재하는 서브폴더 notify 후 yaml의 input_path에는 그 서브폴더들만 활용 가능하다고 notify
            # 만약 input 폴더에 존재하지 않는 서브폴더 명을 yaml의 input_path에 작성 시 input asset에서 에러날 것임   
            if len(os.listdir(self.project_home + 'input/')) == 0: # input 폴더 빈 경우 
                self._asset_error(f'External path (load_train_data_path, load_inference_data_path) in experimental_plan.yaml are not written & << input >> folder is empty.') 
            else: 
                print_color('[NOTICE] You can write only one of the << {} >> at << input_path >> parameter in your experimental_plan.yaml'.format(os.listdir(self.project_home + 'input/')), 'yellow')
            return 
        # None일 시 type을 list로 통일 
        if load_train_data_path is None:
            load_train_data_path = []
        if load_inference_data_path is None:
            load_inference_data_path = []
            
        # external path가 존재하는 경우 
        def _get_ext_path_type(_ext_path): # inner function 
            if 's3:/' in _ext_path: 
                return 's3'
            elif '/nas' in _ext_path: 
                return 'nas'
            else: 
                self._asset_error(f'{_ext_path} is unsupported type of external load data path.')
        
        # 1개여서 str인 경우도 list로 바꾸고, 여러개인 경우는 그냥 그대로 list로 
        # None (미입력) 일 땐 별도처리 필요 
        load_train_data_path = [load_train_data_path] if type(load_train_data_path) == str else load_train_data_path
        load_inference_data_path =  [load_inference_data_path] if type(load_inference_data_path) == str else load_inference_data_path

        for ext_path in load_train_data_path + load_inference_data_path: 
            # ext_path는 무조건 nas 폴더 (파일말고) 혹은 s3내 폴더 URI
            print_color(f'>> Start fetching external data from << {ext_path} >> into << input >> folder.', 'yellow')
            ext_type = _get_ext_path_type(ext_path) # None / nas / s3
            
            if ext_type  == 'nas':
                # 해당 nas 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
                # nas 접근권한 없으면 에러 발생 
                # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
                try: 
                    # 사용자가 실수로 yaml external path에 마지막에 '/' 쓰든 안쓰든, (즉 아래 코드에서 '/'이든 '//' 이든 동작엔 이상X)
                    # [참고] https://stackoverflow.com/questions/3925096/how-to-get-only-the-last-part-of-a-path-in-python
                    mother_path = os.path.basename(os.path.normpath(ext_path)) # 가령 /nas001/test/ 면 test가 mother_path 
                    if mother_path in os.listdir( self.project_home + 'input/'): 
                        self._asset_error(f"You already have duplicated sub-folder name << {mother_path} >> in the << input >> folder. Please rename your sub-folder name if you use multiple data sources.")
                    shutil.copytree(ext_path, self.project_home + f"input/{mother_path}", dirs_exist_ok=True) # 중복 시 덮어쓰기 됨 

                except: 
                    self._asset_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong NAS path (must be directory!) / or You do not have permission to access / or You used duplicated sub-folder names for multiple data sources.')
            elif ext_type  == 's3':  
                # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
                # 해당 s3 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
                # s3 접근권한 없으면 에러 발생 
                # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
                s3_downloader = S3Downloader(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
                try: 
                    s3_downloader.download_folder()
                except:
                    self._asset_error(f'Failed to download s3 data folder from << {ext_path} >>')
            else: 
                # 미지원 external data storage type
                self._asset_error(f'{ext_path} is unsupported type of external data path.') 
                
        return 
    
    def extract_requirements_txt(self, step_name): 
        """ Description
            -----------
                - master 혹은 각 asset (=slave) 내의 requirements.txt가 존재 시 내부에 작성된 패키지들을 list로 추출 
            Parameters
            -----------
                - step_name: master 혹은 scripts 밑에 설치될 asset 이름 
            Return
            -----------
                - 
            Example
            -----------
                - extract_req_txt(step_name)
        """
        fixed_txt_name  = 'requirements.txt'
        packages_in_txt = []
        # ALO master 종속 패키지 리스트업 
        if step_name == 'master': 
            try: 
                with open(self.project_home + fixed_txt_name, 'r') as req_txt:  
                    for pkg in req_txt: 
                        pkg = pkg.strip() # Remove the newline character at the end of the line (=package)
                        packages_in_txt.append(pkg)
                return packages_in_txt        
            except: 
                self._asset_error(f'Failed to install basic dependency. You may have removed requirements.txt in project home.')
        # step (=asset) 종속  패키지 리스트업 
        if fixed_txt_name in os.listdir(self.asset_home + step_name):
            with open(self.asset_home + step_name + '/' + fixed_txt_name, 'r') as req_txt:  
                for pkg in req_txt: 
                    pkg = pkg.strip() # Remove the newline character at the end of the line (=package)
                    packages_in_txt.append(pkg)
            return packages_in_txt
        else: 
            self._asset_error(f"<< {fixed_txt_name} >> dose not exist in << scripts/{step_name} folder >>. However, you have written {fixed_txt_name} at that step in << config/experimental_plan.yaml >>. Please remove {fixed_txt_name} in the yaml file.")
            
    ## [FIXME] 사용자 환경의 패키지 설치 여부를 매 실행마다 체크하는 것을 on, off 하는 기능이 필요할 지?   
    # [FIXME] aiplib @ git+http://mod.lge.com/hub/smartdata/aiplatform/module/aip.lib.git@ver2 같은 이름은 아예 미허용 
    def check_install_requirements(self, requirements_dict):
        """ Description
            -----------
                - 각 step에서 필요한 package (requirements.txt에 작성됐든 yaml에 직접 작성됐든)가 현재 사용자의 가상환경에 설치 돼 있는지 설치여부 체크 후, 없으면 설치 시도
                - experimental_plan.yaml의 asset_source의 code 모드가 local 이든 git이든 일단 항상 실행 시 마다 사용자 가상환경에 모든 package 깔려있는지는 체크한다 
            Parameters
            -----------
                - requirements_dict: 각 step에서 필요한 requirements dict <dict: key=step name, value=requirements list>
            Return
            -----------
                - 
            Example
            -----------
                - check_install_requirements( requirements_dict)
        """
        # 0. asset_source_code가 local이든 git이든, check_asset_source가 once든 every든 모두 동일하게 항상 모듈의 설치여부는 패키지명, 버전 check 후 없으면 설치 (ver 다르면 notify 후 설치) 
        # 1. 한 pipline 내의 각 step을 루프 돌면서 직접 작성된 패키지 (ex. pandas==3.4)는 직접 설치하고
        # 2. experimental_plan.yaml에 requirements.txt가 기입 돼 있다면 먼저 scripts 폴더 내 해당 asset 폴더 밑에 requirements.txt가 존재하는 지 확인 (없으면 에러)
        # 3. 만약 이미 설치돼 있는 패키지 중 버전이 달라서 재설치 하는 경우는 (pandas==3.4 & pandas==3.2) print_color로 사용자 notify  
        fixed_txt_name = 'requirements.txt'
    
        # 어떤 step에 requirements.txt가 존재하면, scripts/asset폴더 내에 txt파일 존재유무 확인 후 그 내부에 기술된 패키지들을 추출  
        extracted_requirements_dict = dict() 
        for step_name, requirements_list in requirements_dict.items(): 
            # yaml의 requirements에 requirements.txt를 적었다면, 해당 step 폴더에 requirements.txt가 존재하는 지 확인하고 존재한다면 내부에 작성된 패키지 명들을 추출하여 아래 loop에서 check & install 수행 
            if fixed_txt_name in requirements_list:
                requirements_txt_list = self.extract_requirements_txt(step_name)
                requirements_txt_list = sorted(set(requirements_txt_list), key = lambda x: requirements_txt_list.index(x)) 
                yaml_written_list = sorted(set(requirements_list), key = lambda x: requirements_list.index(x)) 
                fixed_txt_index = yaml_written_list.index(fixed_txt_name)                
                extracted_requirements_dict[step_name] = yaml_written_list[ : fixed_txt_index] + requirements_txt_list + yaml_written_list[fixed_txt_index + 1 : ]
            else: #requirements.txt 를 해당 step에 미기입한 경우 (yaml에서)
                extracted_requirements_dict[step_name] = sorted(set(requirements_list), key = lambda x: requirements_list.index(x)) 

        # yaml 수동작성과 requirements.txt 간, 혹은 서로다른 asset 간에 같은 패키지인데 version이 다른 중복일 경우 아래 우선순위에 따라 한번만 설치하도록 지정         
        # 우선순위 : 1. ALO master 종속 패키지 / 2. 이번 파이프라인의 먼저 오는 step (ex. input asset) / 3. 같은 step이라면 requirements.txt보다는 yaml에 직접 작성한 패키지 우선 
        # 위 우선순위는 이미 main.py에서 requirements_dict 만들 때 부터 반영돼 있음 
        dup_checked_requirements_dict = defaultdict(list) # --force-reinstall 인자 붙은 건 중복 패키지여도 별도로 마지막에 재설치 
        dup_chk_set = set() 
        force_reinstall_list = [] 
        for step_name, requirements_list in extracted_requirements_dict.items(): 
            for pkg in requirements_list: 
                pkg_name = pkg.replace(" ", "") # 모든 공백 제거후, 비교 연산자, version 말고 패키지의 base name를 아래 조건문에서 구할 것임
                # force reinstall은 별도 저장 
                if "--force-reinstall" in pkg_name: 
                    force_reinstall_list.append(pkg) # force reinstall 은 numpy==1.25.2--force-reinstall 처럼 붙여서 쓰면 인식못하므로 pkg_name이 아닌 pkg로 기입 
                    dup_chk_set.add(pkg)
                    continue 
                # 버전 및 주석 등을 제외한, 패키지의 base 이름 추출 
                base_pkg_name = "" 
                if pkg_name.startswith("#") or pkg_name == "": # requirements.txt에도 주석 작성했거나 빈 줄을 첨가한 경우는 패스 
                    continue 
                # [FIXME] 이외의 특수문자 있으면 에러 띄워야할지? 그냥 강제로 무조건 한번 설치 시도하는게 나을수도 있을 듯 한데..  
                # 비교연산자 이외에는 지원안함 
                if '<' in pkg_name: # <, <=  케이스 
                    base_pkg_name = pkg_name[ : pkg_name.index('<')]
                elif '>' in pkg_name: # >, >=  케이스 
                    base_pkg_name = pkg_name[ : pkg_name.index('>')]
                elif ('=' in pkg_name) and ('<' not in pkg_name) and ('>' not in pkg_name): # == 케이스 
                    base_pkg_name = pkg_name[ : pkg_name.index('=')]
                else: # version 명시 안한 케이스 
                    base_pkg_name = pkg_name  
                    
                # package명 위가 아니라 옆 쪽에 주석 달은 경우, 제거  
                if '#' in base_pkg_name: 
                    base_pkg_name = base_pkg_name[ : base_pkg_name.index('#')]
                if '#' in pkg_name: 
                    pkg_name = pkg_name[ : pkg_name.index('#')]
                                    
                # ALO master 및 모든 asset들의 종속 패키지를 취합했을 때 버전 다른 중복 패키지 존재 시 먼저 진행되는 step(=asset)의 종속 패키지만 설치  
                if base_pkg_name in dup_chk_set: 
                    print_color(f'>> Ignored installing << {pkg_name} >>. Another version will be installed in the previous step.', 'yellow')
                else: 
                    dup_chk_set.add(base_pkg_name)
                    dup_checked_requirements_dict[step_name].append(pkg_name)
        
        # force reinstall은 마지막에 한번 다시 설치 하기 위해 추가 
        dup_checked_requirements_dict['force-reinstall'] = force_reinstall_list
        
        # 패키지 설치 
        self._install_packages(dup_checked_requirements_dict, dup_chk_set)

        return     
    
    def _install_packages(self, dup_checked_requirements_dict, dup_chk_set): 
        total_num_install = len(dup_chk_set)
        count = 1
        # 사용자 환경에 priority_sorted_pkg_list의 각 패키지 존재 여부 체크 및 없으면 설치
        for step_name, package_list in dup_checked_requirements_dict.items(): # 마지막 step_name 은 force-reinstall 
            print_color(f"======================================== Start dependency installation : << {step_name} >> ========================================", 'green')
            for package in package_list:
                print_color(f'>> Start checking existence & installing package - {package} | Progress: ( {count} / {total_num_install} total packages )', 'yellow')
                count += 1
                
                if "--force-reinstall" in package: 
                    try: 
                        print_color(f'- Start installing package - {package}', 'yellow')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package.replace('--force-reinstall', '').strip(), '--force-reinstall'])            
                    except OSError as e:
                        self._asset_error(f"Error occurs while --force-reinstalling {package} ~ " + e)  
                    continue 
                        
                try: # 이미 같은 버전 설치 돼 있는지 
                    # [pkg_resources 관련 참고] https://stackoverflow.com/questions/44210656/how-to-check-if-a-module-is-installed-in-python-and-if-not-install-it-within-t 
                    # 가령 aiplib @ git+http://mod.lge.com/hub/smartdata/aiplatform/module/aip.lib.git@ver2  같은 version 표기가 requirements.txt에 존재해도 conflict 안나는 것 확인 완료 
                    # [FIXME] 사용자가 가령 pandas 처럼 (==version 없이) 작성하여도 아래 코드는 통과함 
                    pkg_resources.get_distribution(package) # get_distribution tact-time 테스트: 약 0.001s
                    print_color(f'- << {package} >> already exists', 'green')
                except pkg_resources.DistributionNotFound: # 사용자 가상환경에 해당 package 설치가 아예 안 돼있는 경우 
                    try: # nested try/except 
                        print_color(f'- Start installing package - {package}', 'yellow')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                    except OSError as e:
                        # 가령 asset을 만든 사람은 abc.txt라는 파일 기반으로 pip install -r abc.txt 하고 싶었는데, 우리는 requirements.txt 라는 이름만 허용하므로 관련 안내문구 추가  
                        self._asset_error(f"Error occurs while installing {package}. If you want to install from packages written file, make sure that your file name is << {fixed_txt_name} >> ~ " + e)
                except pkg_resources.VersionConflict: # 설치 돼 있지만 버전이 다른 경우 재설치 
                    try: # nested try/except 
                        print_color(f'- VersionConflict occurs. Start re-installing package << {package} >>. You should check the dependency for the package among assets.', 'yellow')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                    except OSError as e:
                        self._asset_error(f"Error occurs while re-installing {package} ~ " + e)  
                # [FIXME] 그 밖의 에러는 아래에서 그냥 에러 띄우고 프로세스 kill 
                # pkg_resources의 exception 참고 코드 : https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
                except pkg_resources.ResolutionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                    self._asset_error(f'ResolutionError occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')
                except pkg_resources.ExtractionError: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                    self._asset_error(f'ExtractionError occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')
                # [FIXME] 왜 unrechable 이지? https://github.com/pypa/pkg_resources/blob/main/pkg_resources/__init__.py#L315
                except pkg_resources.UnknownExtra: # 위 두 가지 exception에 안걸리면 핸들링 안하겠다 
                    self._asset_error(f'UnknownExtra occurs while installing package {package} @ {step_name} step. Please check the package name or dependency with other asset.')   
                
        print_color(f"======================================== Finish dependency installation ======================================== \n", 'green')
        
        return 
    
    # [FIXME] 23.09.27 기준 scripts 폴더 내의 asset (subfolders) 유무 여부로만 check_asset_source 판단    
    def setup_asset(self, asset_config, check_asset_source='once'): 
        """ Description
            -----------
                - scripts 폴더 내의 asset들을 code가 local인지 git인지, check_asset_source가 once인지 every인지에 따라 setup  
            Parameters
            -----------
                - asset_config: 현재 step의 asset config (dict 형) 
                - check_asset_source: git을 매번 당겨올지 최초 1회만 당겨올지 ('once', 'every')
            Return
            -----------
                - 
            Example
            -----------
                - setup_asset(asset_config, check_asset_source='once')
        """
        asset_source_code = asset_config['source']['code'] # local, git url
        step_name = asset_config['step']
        git_branch = asset_config['source']['branch']
        step_path = os.path.join(self.asset_home, asset_config['step'])
        
        # 현재 yaml의 source_code가 git일 땐 control의 check_asset_source가 once이면 한번만 requirements 설치, every면 매번 설치하게 끔 돼 있음 
        ## [FIXME] ALOv2에서 기본으로 필요한 requirements.txt는 사용자가 알아서 설치 (git clone alov2 후 pip install로 직접) 
        ## asset 배치 (@ scripts 폴더)
        # local 일때는 check_asset_source 가 local인지 git url인지 상관 없음 
        if asset_source_code == "local":
            if step_name in os.listdir(self.asset_home): 
                print_color(f"@ local asset_source_code mode: <{step_name}> asset exists.", "green") 
                pass 
            else: 
                self._asset_error(f'@ local asset_source_code mode: <{step_name}> asset folder \n does not exist in <assets> folder.')
        else: # git url & branch 
            # git url 확인
            if self.is_git_url(asset_source_code):
                # _renew_asset(): 다시 asset 당길지 말지 여부 (bool)
                if (check_asset_source == "every") or (check_asset_source == "once" and self._renew_asset(step_path)): 
                    print_color(f">> Start renewing asset : {step_path}", "blue") 
                    # git으로 또 새로 받는다면 현재 존재 하는 폴더를 제거 한다
                    if os.path.exists(step_path):
                        shutil.rmtree(step_path)  # 폴더 제거
                    os.makedirs(step_path)
                    os.chdir(self.project_home)
                    repo = git.Repo.clone_from(asset_source_code, step_path)
                    try: 
                        repo.git.checkout(git_branch)
                        print_color(f"{step_path} successfully pulled.", "green") 
                    except: 
                        raise ValueError(f"Your have written incorrect git branch: {git_branch}")
                # 이미 scripts내에 asset 폴더들 존재하고, requirements.txt도 설치된 상태 
                elif (check_asset_source == "once" and not self._renew_asset(step_path)):
                    modification_time = os.path.getmtime(step_path)
                    modification_time = datetime.fromtimestamp(modification_time) # 마지막 수정시간 
                    print_color(f"{step_name} asset has already been created at {modification_time}", "blue") 
                    pass  
                else: 
                    self._asset_error(f'You have written incorrect check_asset_source: {check_asset_source}')
            else: 
                self._asset_error(f'You have written incorrect git url: {asset_source_code}')
        
        return 
        
    # [FIXME] 추후 단순 폴더 존재 유무 뿐 아니라 이전 실행 yaml과 비교하여 git주소, branch 등도 체크해야함
    def _renew_asset(self, step_path): 
        """ Description
            -----------
                - asset을 git으로 부터 새로 당겨올지 말지 결정 
            Parameters
            -----------
                - step_path: scripts 폴더 내의 asset폴더 경로 
            Return
            -----------
                - whether_renew_asset: Boolean
            Example
            -----------
                - whether_to_renew_asset =_renew_asset(step_path) 
        """
        whether_renew_asset = False  
        if os.path.exists(step_path):
            pass
        else: 
            whether_renew_asset = True
        return whether_renew_asset
            
         
    def create_folders(self, dictionary, parent_path=''):
        for key, value in dictionary.items():
            folder_path = os.path.join(parent_path, key)
            os.makedirs(folder_path, exist_ok=True)
            if isinstance(value, dict):
                self.create_folders(value, folder_path)

    # yaml 및 artifacts 백업
    # [230927] train과 inference 구분하지 않으면 train ~ inference pipline 연속 실행시 초단위까지 중복돼서 에러 발생가능하므로 구분 
    def backup_artifacts(self, pipelines):
        """ Description
            -----------
                - 파이프라인 실행 종료 후 사용한 yaml과 결과 artifacts를 .history에 백업함 
            Parameters
            -----------
                - pipelines: pipeline mode (train, inference)
            Return
            -----------
                - 
            Example
            -----------
                - backup_artifacts(pipe_mode)
        """
        if self.control['backup_artifacts'] == True:
            current_pipelines = pipelines.split("_pipelines")[0]
            # artifacts_home_생성시간 폴더를 제작
            timestamp_option = True
            hms_option = True
        
            if timestamp_option == True:  
                if hms_option == True : 
                    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
                else : 
                    timestamp = datetime.now().strftime("%y%m%d")     
                # [FIXME] 추론 시간이 1초 미만일 때는 train pipeline과 .history  내 폴더 명 중복 가능성 존재. 임시로 cureent_pipelines 이름 추가하도록 대응. 수정 필요    
                backup_folder= '{}_artifacts'.format(timestamp) + f"_{current_pipelines}/"
            
            # TODO current_pipelines 는 차후에 workflow name으로 변경이 필요
            backup_artifacts_home = self.project_home + backup_folder
            os.mkdir(backup_artifacts_home)
            
            # 이전에 실행이 가능한 환경을 위해 yaml 백업
            shutil.copy(self.project_home + "config/experimental_plan.yaml", backup_artifacts_home)
            # artifacts 들을 백업
            for dir_name in list(self.artifacts_structure.keys()):
                if dir_name == ".history" or dir_name == "input":
                    continue 
                else:
                    os.mkdir(backup_artifacts_home + dir_name)
                    shutil.copytree(self.project_home + dir_name, backup_artifacts_home + dir_name, dirs_exist_ok=True)
            # backup artifacts를 .history로 이동 
            try: 
                shutil.move(backup_artifacts_home, self.project_home + ".history/")
            except: 
                self._asset_error(f"Failed to move {bakcup_artifacts_home} into {self.project_home}/.history/")
            if os.path.exists(self.project_home + ".history/" + backup_folder):
                print_color("[Done] .history backup (config yaml & artifacts) complete", "green")
    
    #def set_artifact(self, home_path, history):
    def set_artifacts(self):
        
        # artifacts_home = self.project_home
        
        # self.project_home에 각종 artifacts 폴더들 생기므로 main.py 처음 실행 시 전부 지워줘야함  
        # 지워지는 코드 제거
        # for dir_name in list(self.artifacts_structure.keys()):
        #     if dir_name == '.history':
        #         pass
        #     else:
        #         try:
        #             shutil.rmtree(artifacts_home + dir_name)
        #         except:
        #             # TODO asset_print로 변경 필요 
        #             print(f"directory {dir_name} does not exist. (Not removed)")
        
        # artifacts 폴더 생성 
        try:
            self.create_folders(self.artifacts_structure, self.project_home)
        except:
            ValueError("Artifacts folder not generated!")

        for dir_name in list(self.artifacts_structure.keys()):
            self.artifacts_structure[dir_name] = self.project_home + dir_name + "/"
        
        return self.artifacts_structure
        

    def get_external_path(self):
        self.path_dict = {}
        for external_path in self.exp_plan['external_path']:
            self.path_dict.update(external_path)
        return self.path_dict

    def get_external_path_permission(self):
        self.path_permission_dict = {}
        for external_path_permission in self.exp_plan['external_path_permission']:
            self.path_permission_dict.update(external_path_permission)
        return self.path_permission_dict
    
    def get_pipeline(self):
        self.pipelines_list = {}
        for pipeline in self.exp_plan['asset_source']:
            self.pipelines_list.update(pipeline)
        return self.pipelines_list
        
    def get_user_parameters(self):
        self.user_parameters = {}
        for params in self.exp_plan['user_parameters']:
            # for key in params.keys():
            self.user_parameters.update(params)
        return self.user_parameters

    def get_control(self):
        self.control = {}
        for params in self.exp_plan['control']:
            # for key in params.keys():
            self.control.update(params)
        return self.control

    def get_yaml(self, _yaml_file):
        self.exp_plan = dict()

        try:
            with open(_yaml_file, encoding='UTF-8') as f:
                self.exp_plan = yaml.load(f, Loader=yaml.FullLoader)
        except FileNotFoundError:
            raise ValueError(f"Not Found : {_yaml_file}")
        except:
            raise ValueError(f"Check yaml format : {_yaml_file}")

        # return exp_plan

    # git url 확인 -> lib
    def is_git_url(self, url):
        git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
        return re.match(git_url_pattern, url) is not None
        
    def import_asset(self, _path, _file):
        _user_asset = 'none'

        try:
            # Asset import
            # asset_path = 상대경로로 지정 : self.project_home/scripts/data_input
            sys.path.append(_path)
            mod = importlib.import_module(_file)
        except ModuleNotFoundError:
            raise ValueError(f'Not Found : {_path}{_file}.py')

        # UserAsset 클래스 획득
        _user_asset = getattr(mod, "UserAsset")

        return _user_asset
#######################################
    def load_config(self, conf):
        """ Description
            -----------
                - Asset 에 필요한 config 를 가져온다.
            Parameters
            -----------
                - conf (str) : config의 종류 ('envs', 'args', 'config')
                               envs : 모델컨덕터의 environments 설정 값
                               args : 모델컨덕터의 arguments 설정 값
                               config : 모델컨덕터 워크플로어 운영 설정 값
            Return
            -----------
                - data (dict)
            Example
            -----------
                - envs = load_config('envs')
        """

        ret_config = dict()
        if conf == 'envs':
            ret_config = self.asset_envs.copy()
        elif conf == 'args':
            ret_config = self.asset_args.copy()
        elif conf == 'config':
            ret_config = self.asset_config.copy()
        else:
            raise ValueError("지원하지 않는 config 타입입니다. (choose : 'envs', 'args', 'config')")
        return ret_config


    def load_data(self, step = None):
        """ Description
            -----------
                - Asset 의 이전 step 에서 생성한 데이터를 가져온다.
            Parameters
            -----------
                - option
                  - step (str) : 특정 Asset 에서 생성한 데이터를 가져한다.
            Return
            -----------
                - data (dict)
            Example
            -----------
                - previous_dict = load_data()
                - preprocess_dict = load_data(step='preprocess')
        """

        data_in_file = 'none'
        in_data = 'none'

        # 이전 asset 의 데이터를 가져온다.
        if step == None:
            data_in_file = self.asset_envs['data_in_file']
        # 특정 asset 의 데이터를 가져온다.
        else:
            data_in_file = self._get_data_in_file(step, self.context['system']['pipeline'])

        in_data = self.load_file(data_in_file)

 
        return in_data


    def decorator_run(func):
        def _run(self, *args, **kwargs):

            print('************************************************************')
            # print(f'\t{self.asset_envs["step_name"]} -> run')
            print('************************************************************')
            # print(self.metadata._get_artifact(self.asset_envs["step_name"], 'info')['version'])

            try:
                #METADATA
                # self.metadata._set_execution('RUNNING')
                self.output, config = func(self, *args, **kwargs)
                #METADATA
                # self.metadata._set_execution('COMPLETED')
                # self._set_context_system()
            except Exception as e:
                # self._set_context_system()
                self._asset_error(str(e))
                # print(str(e))
            return self.output, config
        return _run


    def save_config(self, data, step):
        """ Description
            -----------
                - Workflow 운영에 필요한 Asset config 를 저장한다.
            Parameters
            -----------
                - data (dict) : config 에 저장할 데이터
                - conf (str) : config의 종류 ('config')
                               config : 모델컨덕터 워크플로어 운영 설정 값
            Return
            -----------
                - None
            Example
            -----------
                - save_config(data, 'config')
        """

        if not isinstance(data, dict):
            raise TypeError("지원하지 않는 데이터 타입입니다. (only dictionary)")

        self.asset_config[step] = data

        # if conf == 'config':
        #     self._set_context(data)
        # else:
        #     raise ValueError("지원하지 않는 config 타입입니다. (choose : 'config')")


    def save_data(self, output):
        """ Description
            -----------
                - Asset 에서 생성한 데이터와 설정값을 저장한다.
            Parameters
            -----------
                - output  (dict) : 특정 Asset 에서 생성한 데이터
            Example
            -----------
                - save_data(output)
        """
        if output is None:
            output = {}
        if not isinstance(output, dict):
            raise ValueError("지원하지 않는 데이터 타입입니다. (only dictionary)")

        self.save_file(output, self.asset_envs['data_out_file'])

    def check_record_file(self):
        if self.metadata._get_artifact(self.asset_envs['step_name'], 'output')['file'] == []:
            self.save_warning('tfrecord 파일이 비었습니다')
        else:
            pass


    def save_metadata(self, filename, type):
        """ Description
            -----------
                - Asset 에서 저장한 데이터를 Artifact에 기록한다.
            Parameters
            -----------
                - filename (str) : 저장한 데이터의 파일이름(경로 포함)
                - type (str) : input 또는 output
            Example
            -----------
                - save_metadata(filename, 'output')
        """
        
        if not type in ('input', 'output'):
            raise ValueError("type 은 'input' 또는 'output' 입니다.")

        self.metadata._set_artifact(filename, type)


    def load_file(self, _data_file, _print=True):
        """ Description
            -----------
                - 파일을 로하하여 데이터로 가져온다.
            Parameters
            -----------
                - data_file (str) : 로드할 데이터의 파일이름 (경로 포함)
                                   (확장자 지원 : csv, h5, tfrecord, pkl, json, params, log)
                - option
                  - _print (bool) : 데이터 저장여부 출력
            Return
            -----------
                - data (csv) : dataframe
                       (tfreocrd, pkl, json, params, log) : dictionary
            Example
            -----------
                - data = load_file(data_file)
        """
 
        _data = 'none'

        # file != 'none'
        if _data_file != 'none':
            try:
                # if _data_file.lower().endswith('.csv'):
                #     _data = pd.read_csv(_data_file, engine='python')
                # elif _data_file.lower().endswith('.h5'):
                #     _data = tf.keras.models.load_model(_data_file)
                # elif _data_file.lower().endswith('.tfrecord'):
                #     _data = self.tfrecord.load(_data_file)
                # elif _data_file.lower().endswith('.pkl'):
                if _data_file.lower().endswith('.pkl'):
                    with open(_data_file, 'rb') as f:
                        _data = pickle.load(f)
                elif _data_file.lower().endswith('.json') or \
                     _data_file.lower().endswith('.params') or \
                     _data_file.lower().endswith('.log'):
                    with open(_data_file, 'r') as f:
                        _data = json.load(f)
                else:
                    raise TypeError('No Support file format (support : csv, h5, tfrecord, pkl, json, params, log)')
                    _print=False
                if _print == True:
                    print('Loaded : {}'.format(_data_file))
                else:
                    pass
            except FileNotFoundError: 
                raise ValueError('File Not Found : {}'.format(_data_file))
            except AttributeError:
                # tfrecord를 제작할 때 사용한 pandas 버전과 다른 경우 발생
                raise ValueError('tfrecord error : 로드하려는 tfrecord에서 사용된 pandas 버전과 설치된 pandas 버전이 다릅니다.')
            except:
                raise ValueError('File Data Error : {}'.format(_data_file))
        else:
            pass
        #  파일 로드 성공 : artifact 에 기록
        # self.metadata._set_artifact(_data_file, 'input')

        return _data

    def save_file(self, _data, _data_file, _print=True):
        """ Description
            -----------
                - 데이터를 파일로 저장한다.
            Parameters
            -----------
                - data : 파일로 저장할 데이터
                         (csv) : dataframe
                         (h5) : tensorflow.keras.Sequential
                         (tfreocrd, pkl, json, params, log) : dictionary
                - data_file (str) : 저장할 데이터의 파일이름 (경로 포함)
                                   (확장자 지원 : csv, tfrecord, pkl, json, params, log)
                - option
                  - _print (bool) : 데이터 저장여부 출력
            Example
            -----------
                - save_file(data, data_file)
        """

        # file != 'none' and data != 'none'
        if _data_file != 'none' and not (isinstance(_data, str) and _data == 'none') and len(_data) > 0:
            try:
                check_path(_data_file)
                # if _data_file.lower().endswith('.csv'):
                #     if isinstance(_data, pd.DataFrame):
                #         _data.to_csv(_data_file, index=False)
                #     else:
                #         raise TypeError(f'need DataFrame format (your data format : {type(_data)})')
                # elif _data_file.lower().endswith('.h5'):
                #     if isinstance(_data, tf.keras.Sequential):
                #         _data.save(_data_file)
                #     else:
                #         raise TypeError(f'need tensorflow.keras.Sequential format (your data format : {type(_data)})')
                # elif _data_file.lower().endswith('.tfrecord'):
                #     if isinstance(_data, dict):
                #         self.tfrecord.save(_data, _data_file)
                #     else:
                #         raise TypeError(f'need dictionary format (your data format : {type(_data)})')
                # elif _data_file.lower().endswith('.pkl'):
                if _data_file.lower().endswith('.pkl'):
                    with open(_data_file, "wb") as f:
                        pickle.dump(_data, f)
                elif _data_file.lower().endswith('.json') or \
                     _data_file.lower().endswith('.params') or \
                     _data_file.lower().endswith('.log'):
                    with open(_data_file, "w") as f:
                        # ensure_ascii=False : 한글 지원
                        json.dump(_data, f, indent=4, ensure_ascii=False)
                else:
                    raise TypeError('No Support file format (support : csv, h5, tfrecord, pkl, json, params, log)')
                    _print=False
                if _print == True:
                    _msg = f'Saved : {_data_file}'
                    #self.asset_aip_info(Type.DATASAVE, SubType.FILEMAKE,_msg)
                    print(_msg)
                else:
                    pass
            # Tfrecord Error
            except TypeError as e:
                raise TypeError(str(e))
            except:
                raise ValueError('Failed to save : {}'.format(_data_file))
            # 파일 저장 성공 : artifact 에 기록
            # self.metadata._set_artifact(_data_file, 'output')
        else:
            pass

    def save_log(self, msg):
        """ Description
            -----------
                - Asset에서 필요한 정보를 저장한다.
            Parameters
            -----------
                - msg (str) : 저장할 문자열 (max length : 255)
            Example
            -----------
                - save_log('hello')
        """

        if not isinstance(msg, str):
            raise ValueError("지원하지 않는 데이터 타입입니다. (only string)")

        self.metadata._set_log(msg, self.context['metadata_table_version']['log'], 'info')

    def save_warning(self, msg):
        """Description
            -----------
                - Asset에서 필요한 정보를 저장한다.
            Parameters
            -----------
                - msg (str) : 저장할 문자열 (max length : 255)
            Example
            -----------
                - save_warning('hello')
        """

        if not isinstance(msg, str):
            raise ValueError("지원하지 않는 데이터 타입입니다. (only string)")

        self.metadata._set_log(msg, self.context['metadata_table_version']['log'], 'warning')

    def get_catalog(self, data):
        """ Description
            -----------
                Get the catalog(summary) of dictionary
            Parameters
            -----------
                data (dict) : dictionary data
            Return
            -----------
                the catalog (dict)
    
            Example
            -----------
                catalog = get_catalog(data)
        """
     
        catalog = dict()
    
        def get_keys(_data, _key_data):
            if isinstance(_data, dict):
                for key, value in _data.items():
                    _key_data[key] = get_keys(value, dict())
            else:
                _key_data = str(type(_data))
            return _key_data
    
        if isinstance(data, dict):
            get_keys(data, catalog)
        else:
            raise TypeError('Wrong the type of data (only dictionary)')
    
        return catalog

    def check_args(self, arg_key, is_required=False, default="", chng_type="str" ):
        """ Description
            -----------
                Check user parameter. Replace value & type 

            Parameters
            -----------
                args (dict) : Asset self.args 
                arg_key (str) : 사용자 라미미터 이름 
                is_required (bool) : 필수 존재 여부 
                default (str) : 사용자 파라미터가 존재하지 않을 경우, 강제로 입력될 값
                chng_type (str): 타입 변경 list, str, int, float, bool, 

            Return
            -----------
                the replaced string

            Example
            -----------
                replace_pattern(_str, 'inference', 'train', -1)
        """
        if is_required:
            try:
                # arg_value         = self.asset_args[arg_key]
                arg_value = self.asset_args[arg_key] if self.asset_args[arg_key] is not None else ""
            except:
                raise KeyError('Not found args [{}]'.format(arg_key))
        else:
            try:
                # arg_value         = self.asset_args[arg_key]
                if type(self.asset_args[arg_key]) == type(None):
                    arg_value         = default
                else:
                    arg_value = self.asset_args[arg_key] if self.asset_args[arg_key] is not None else ""
            except:
                arg_value         = default
                

        chk_type = type(arg_value)## issue: TypeError: 'str' object is not callable
        if chk_type == list:
            pass
        else:
            arg_value = self._convert_variable_type(arg_value, chng_type)

        return arg_value

    def make_group_by(self, df, group_cnt, group_keys, keys):
        ## group단위 dataframe 인 partial_df 생성하기
        if group_cnt == 3:
            partial_df = df[(df[group_keys[0]] == keys[0]) & (df[group_keys[1]] == keys[1]) &
                        (df[group_keys[2]] == keys[2])].reset_index(drop=True)
        elif group_cnt == 2:
            partial_df = df[(df[group_keys[0]] == keys[0]) &
                            (df[group_keys[1]] == keys[1])].reset_index(drop=True)
        elif group_cnt == 1 or group_cnt == 0 :
            partial_df = df[(df[group_keys[0]] == keys[0])].reset_index(drop=True)
        else:
            ## groupby 는 최대 3개 column 까지 지원합니다. column 갯수 별로 코드가 달라져야 합니다.
            return ValueError(f'group_key: {group_keys} has a maximum value of 3. The current value is: {group_cnt}')

        return partial_df
        
# --------------------------------------------------------------------------------------------------------------------------
#    COMMON FUNCTION
# --------------------------------------------------------------------------------------------------------------------------

    def _convert_variable_type(self, variable, target_type):
        if not isinstance(target_type, str) or target_type.lower() not in ["str", "int", "float", "list", "bool"]:
            raise ValueError("Invalid target_type. Allowed values are 'str', 'int', 'float', and 'list'.")

        if target_type.lower() == "str" and not isinstance(variable, str):
            return str(variable)
        elif target_type.lower() == "int" and not isinstance(variable, int):
            return int(variable)
        elif target_type.lower() == "float" and not isinstance(variable, float):
            return float(variable)
        elif target_type.lower() == "list" and not isinstance(variable, list):
            return [variable]
        elif target_type.lower() == "bool" and not isinstance(variable, bool):
            if variable == "false" or variable == "False":
                return False
            else:
                return True
        else:
            return variable

    def _get_data_in_file(self, step, pipeline):
        data_in_file = 'none'

        if not isinstance(step, str):
            raise TypeError(f"only str, Wrong Type !! : {type(step)}")
        
        if not step in pipeline:
            raise ValueError(f"There is no asset({step}), (choice : {pipeline}")

        data_in_file = self._get_output_tfrecord(step)
        return data_in_file


    def _get_output_tfrecord(self, step):
        tfrecord_file = 'none'

        # get output artifact
        asset_info = self.metadata._get_artifact(step, 'output')

        # find tfrecord
        tfrecord_file_list = [t for t in asset_info['file'] if t.endswith('.tfrecord')]

        # 이 전에 출력한 데이터가 있다.
        if len(tfrecord_file_list) > 0:
            # 0 : 가장 처음 tfrecord 저장한 파일
            tfrecord_file = tfrecord_file_list[0]

        return tfrecord_file


    def _set_context(self, _context):
        saved_context = self.metadata._get_context()
     
        # global, 변수는 업데이트 할 수 없다.
        for key, value in saved_context['user'].items():
            if 'global' in key:
                if saved_context['user'][key] != _context[key]:
                    raise ValueError(f"config 에서 'global' 이포함된 {key} 는 수정할 수 없습니다.")
        
        saved_context['user'] = _context

        if saved_context['system']['last_step'] == 'none':
            saved_context['user']['aiplib_version'] = self.asset_envs['aiplib_version']
        
        self.metadata._set_context(saved_context)


    def _set_context_system(self):
        saved_context = self.metadata._get_context()
      
        #################################  system 업데이트 ####################################
        # update : pipeline 연결 정보
        saved_context['system']['pipeline'].append(self.asset_envs['step_name'])
        saved_context['system']['last_step'] = self.asset_envs['step_name']

        self.metadata._set_context(saved_context)


    def _set_asset_information(self):
        # 추가 개발 필요 230913 swj
        asset_info = dict()

        ###################################  version 추가 #####################################
        asset_info['version'] = dict()
        asset_info['version']['aiplib'] = self.asset_envs['aiplib_version']
        asset_info['version']['aiptfx'] = self.asset_envs['aiptfx_version']
        asset_info['version']['asset']  = self.asset_envs['asset_version']

        ###################################  args 추가 #####################################
        asset_info['args'] = dict()
        asset_info['args'] = self.asset_args

# --------------------------------------------------------------------------------------------------------------------------
#    MODEL CONDUCTOR FUNCTION
# --------------------------------------------------------------------------------------------------------------------------
    
    def _asset_info(self):
        print('\n')
        print_color("========================== ASSET INFORMATION ==========================", 'blue')
        if self.debug_mode == True:
            print_color(f"DEBUG MODE   : TRUE", 'red')
        print_color(f"TIME(KST)    : {datetime.now(timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')}", 'blue')
        print_color(f"WORKSPACE    : {self.asset_envs['workspace_name']}", 'blue')
        print_color(f"PROJECT      : {self.asset_envs['project_name']}", 'blue')
        print_color(f"WORKFLOW     : {self.asset_envs['workflow_name']}", 'blue')
        print_color(f"WORKFLOW KEY : {self.asset_envs['workflow_key']}", 'blue')
        print_color(f"ASSET NAME   : {self.asset_envs['step_name']}", 'blue')
        print_color(f"asset ver.   : {self.asset_envs['asset_version']}", 'blue')
        print_color(f"aiplib ver.  : {self.asset_envs['aiplib_version']}", 'blue')
        print_color(f"aiptfx ver.  : {self.asset_envs['aiptfx_version']}", 'blue')
        print_color("=======================================================================", 'blue')
        print('\n')
 
    def _asset_error(self, msg):
        time_utc = datetime.now(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')
        time_kst = datetime.now(timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
        print('\n\n')
        print_color("============================= ASSET ERROR =============================", 'red')
        if self.debug_mode == True:
            print_color(f"DEBUG MODE   : TRUE", 'red')
        print_color(f"TIME(UTC)    : {time_utc} (KST : {time_kst})", 'red')
        # print_color(f"PIPELINES    : {self.asset_envs['pipeline']}", 'red')
        # print_color(f"ASSETS     : {self.asset_envs['step']}", 'red')
        print_color(f"ERROR(msg)   : {msg}", 'red')
        print_color("=======================================================================", 'red')
        print('\n\n')

        # save log at metadata
        # self.metadata._set_log(msg, self.context['metadata_table_version']['log'], 'error')

        # update execution(ERROR)
        # self.metadata._set_execution('ERROR')

        raise ValueError(msg)


    # NOTE
    # log 로 저장되는 value(key:value) 는 빈칸의 값을 가질 수 없다 -> splunk 에러
    def _check_arguments(self, args):
        for key, value in args.items():
            # key 길이를 체크한다. (모델컨덕터 기준)
            if len(key) > ARG_NAME_MAX_LENGTH:
                raise ValueError("arg의 길이는 {}이하입니다. arg [{}]".format(ARG_NAME_MAX_LENGTH, key))
      
            # 괄호를 사용했는지 확인한다.
            # ${env(project_home)} <- env 로 사용한 괄호 제외
            if 'env(' in value:
                pass
            else:
                if '(' in value:
                    raise ValueError("arg의 값에 괄호를 사용할 수 없습니다. arg [{}]".format(key))

            # ${env(project_home)} <- env 로 사용한 괄호 제외
            if ')}' in value:
                pass
            else:
                if ')' in value:
                    raise ValueError("arg의 값에 괄호를 사용할 수 없습니다. arg [{}]".format(key))

            # path 가 포함된키 : 맨 마지막에 / 가 있는지 확인한다.
            if 'path' in key:
                # list
                if isinstance(value, list):
                    values = value
                else:
                    values = [value]

                for val in values:
                    if len(val) == 0 or val[-1] != '/':
                        raise ValueError("'path'가 포함된 arg의 값 마지막은 \'/\' 이어야합니다. arg [{}]".format(key))
                    else:
                        pass
            else:
                pass
