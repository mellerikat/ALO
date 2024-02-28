import sys
import time
import boto3
import os
import re
import git
import shutil
import datetime
import yaml 
from yaml import Dumper
import botocore
from botocore.exceptions import ClientError, NoCredentialsError
import subprocess
# 모듈 import 
import os
import json
import requests
import pandas as pd 
import shutil
import tarfile 
from copy import deepcopy 
from pprint import pprint
import configparser

### internal package 
from src.constants import *
from src.external import S3Handler

#----------------------------------------#
#              REST API                  #
#----------------------------------------#

KUBEFLOW_STATUS = ("pending", "running", "succeeded", "skipped", "failed", "error")
#---------------------------------------------------------

class SolutionRegister:
    #def __init__(self, workspaces, uri_scope, tag, name, pipeline):
    def __init__(self, infra_setup=None, solution_info=None, api_uri=None,):
        
        self.print_step("Initiate ALO operation mode")
        print_color("[SYSTEM] Solutoin 등록에 필요한 setup file 들을 load 합니다. ", color="green")

        if infra_setup == None :
            print(f"Infra setup 파일이 존재 하지 않으므로, Default 파일을 load 합니다. (path: {infra_setup})")
            infra_setup = INFRA_CONFIG
        else:
            print(f"Infra setup 파일을 load 합니다. (path: {infra_setup})")
            try:    
                with open(infra_setup) as f:
                    self.infra_setup = yaml.safe_load(f)
            except Exception as e : 
                raise ValueError(e)
        print_color("[SYSTEM] infra_setup (max display: 5 line): ", color='green')
        pprint(self.infra_setup, depth=5)

        ####################################
        ########### Setup aws key ##########
        ####################################
        s3_client = S3Handler(s3_uri=None, aws_key_profile=self.infra_setup["AWS_KEY_PROFILE"])
        self.aws_access_key = s3_client.access_key
        self.aws_secret_key = s3_client.secret_key


        ####################################
        ########### Setup AIC api ##########
        ####################################
        self.api_uri = {
            'VERSION': 'api/v1/versions', # GET, 버전 확인
            'STATIC_LOGIN': 'api/v1/auth/login',  # POST
            'LDAP_LOGIN': 'api/v1/auth/ldap/login',
            'SYSTEM_INFO': 'api/v1/workspaces/info',  # GET, 1. 시스템 정보 획득
            'SOLUTION_LIST': 'api/v1/solutions/workspace', # 이름 설정 시 GET, 등록 시 POST, 2. AI Solution 이름 설정 / 3. AI Solution 등록
            'REGISTER_SOLUTION': 'api/v1/solutions', # 등록 시 POST, AI Solution 등록
            'SOLUTION_INSTANCE': 'api/v1/instances', # POST, AI Solution Instance 등록
            'STREAMS': 'api/v1/streams', # POST,  Stream 등록
            'STREAM_RUN': 'api/v1/streamhistories' # POST,  Stream 실행 
            }

        self.api_uri_legacy = {
            'STATIC_LOGIN': 'api/v1/auth/static/login',  # POST
        }
        ## legacy 버전 보다 낮을 경우, API 변경
        self.api_uri_legacy_version = 1.5
        self.check_version()

        if not solution_info:
            raise ValueError("solution infomation 을 입력해야 합니다.")
        else:
            self.solution_info = solution_info


        ####################################
        ########### Configuration ##########
        ####################################

        ## interface_path 와 연동됨
        self.solution_file = '.response_solution.json'
        self.solution_instance_file = '.response_solution_instance.json'
        self.stream_file = '.response_stream.json'
        self.stream_run_file = '.response_stream_run.json'
        self.stream_status_file = '.response_stream_status.json'

        self.stream_history_list_file = '.response_stream_history_list.json'
        self.stream_list_file = '.response_stream_list.json'
        self.instance_list_file = '.response_instance_list.json'
        self.solution_list_file = '.response_solution_list.json'

        ## internal variables
        self.sm_yaml = {}  ## core
        self.exp_yaml = {} ## core
        self._read_experimentalplan_yaml(EXP_PLAN, type='experimental_plan')  ## set exp_yaml

        self.pipeline = None 
        self.aic_cookie = None
        self.solution_name = None
        self.icon_filenames = []
        self.sm_pipe_pointer = -1  ## 0 부터 시작
        self.resource_list = []

        self.bucket_name = None
        self.bucket_name_icon = None 
        self.ecr_name= None
        self.solution_version_new = 1   # New 가 1 부터 이다. 
        self.solution_version_id = None  # solution update 에서만 사용

        ## debugging 용 변수
        self.debugging = False 
        self.skip_generation_docker = False
            
    ################################################
    ################################################
    def run(self, username, password):

        #############################
        ###  Solution Name 입력
        #############################
        self.check_solution_name()

        self.load_system_resource()   ## ECR, S3 정보 받아오기
        self._init_solution_metadata()

        #############################
        ### description & wranlger 추가 
        #############################
        self._set_alo()  ## contents_name 확인용
        self.set_description()
        # html_content = self.s3_upload_icon_display()  ## pre-define 된 icon 들 보여주기
        # display(HTML(html_content))  ##  icon 고정됨으로 spec 변경 됨으로 주석 처리 됨
        self.select_icon(name='ic_artificial_intelligence')
        self.set_wrangler()
        self.set_edge()

        #############################
        ### contents type 추가 
        #############################

        ## common
        self._s3_access_check()  ## s3 instnace 생성 
        self.set_resource_list()   
        ############################
        ### Train pipeline 설정
        ############################
        if self.solution_info['inference_only']:
            pass
        else:
            self._sm_append_pipeline(pipeline_name='train')
            self.set_resource(resource='standard')  ## resource 선택은 spec-out 됨
            self.set_user_parameters()
            self.s3_upload_data()
            self.s3_upload_artifacts()
            if (not self.debugging) and (not self.skip_generation_docker):
                skip_build=False
            else:
                skip_build=True

            self.make_docker_container(skip_build)
        
        ############################
        ### Inference pipeline 설정
        ############################
        self._sm_append_pipeline(pipeline_name='inference')
        self.set_resource(resource='standard')  ## resource 선택은 spec-out 됨
        self.set_user_parameters(display_table=False)
        self.s3_upload_data()
        self.s3_upload_artifacts()  ## inference 시, upload model 도 진행
        if (not self.debugging) and (not self.skip_generation_docker):
            skip_build=False
        else:
            skip_build=True

        self.make_docker_container(skip_build)

        if not self.debugging:
            self.register_solution()
            self.register_solution_instance()   ## AIC, Solution Storage 모두에서 instance 까지 항상 생성한다. 



    def run_train(self, status_period=5, delete_instance=True, delete_solution=False):
        if self.solution_info['inference_only']:
            raise ValueError("inference_only=False 여야 합니다.")
        else:
            self.register_solution_instance()
            self.register_stream()
            self.request_run_stream()
            self.get_stream_status(status_period=status_period)

        if delete_instance:
            self.delete_stream_history()
            self.delete_stream()
            self.delete_solution_instance()

        if delete_solution:
            if delete_instance:
                self.delete_solution()
            else:
                raise Exception("delete_instance 옵션을 켜야 solution 삭제가 가능합니다.")


    def print_step(self, step_name, sub_title=False):
        if not sub_title:
            print_color("\n######################################################", color='blue')
            print_color(f'#######    {step_name}', color='blue')
            print_color("######################################################\n", color='blue')
        else:
            print_color(f'\n#######  {step_name}', color='blue')



    def check_version(self):
        """ AI Conductor 의 버전을 확인하여 API 를 변경함
        """
        self.print_step("Check Version", sub_title=True)


        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["VERSION"]
        response = requests.get(aic+api)
        if response.status_code == 200:
            response_json = response.json()
            version_str = response_json['versions'][0]['ver_str']
            print_color(f"[SUCCESS] Version 을 확인 하였습니다. (current_version: {version_str}). ", color='cyan')

            match = re.match(r'(\d+\.\d+)', version_str)
            if match:
                version = float(match.group(1))
            else:
                version = float(version_str)

            if self.api_uri_legacy_version >= version:
                self.api_uri.update(self.api_uri_legacy)

                print_color(f"[INFO] API 의 uri 가 변경되었습니다.", color='yellow')
                pprint(f"changed_uri:{self.api_uri_legacy}")


        elif response.status_code == 400:
            raise ValueError("[ERROR] version 을 확인할 수 없습니다.  ")

        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')


    def login(self, id, pw): 
        # 로그인 (관련 self 변수들은 set_user_input 에서 setting 됨)

        self.print_step("Login to AI Conductor", sub_title=True)

        login_data = json.dumps({
            "login_id": id,
            "login_pw": pw
        })
        try:
            if self.infra_setup["LOGIN_MODE"] == 'ldap':
                response = requests.post(self.infra_setup["AIC_URI"] + self.api_uri["LDAP_LOGIN"], data = login_data)
                print(response)
            else:
                response = requests.post(self.infra_setup["AIC_URI"] + self.api_uri["STATIC_LOGIN"], data = login_data)
        except Exception as e:
            print(e)

        response_login = response.json()

        cookies = response.cookies.get_dict()
        access_token = cookies.get('access-token', None)
        self.aic_cookie = {
        'access-token' : access_token 
        }

        if response.status_code == 200:
            print_color("[SUCCESS] Login 접속을 성공하였습니다. ", color='cyan')
            # print(f"[INFO] Login response:")
            # pprint(response_login)

            ws_list = []
            for ws in response_login["workspace"]:
                ws_list.append(ws["name"])
            print(f"해당 계정으로 접근 가능한 workspace list: {ws_list}")

            ## 로그인 접속은  계정 존재 / 권한 존재 의 경우로 나뉨
            ##   - case1: 계정 O / 권한 X 
            ##   - case2: 계정 O / 권한 single (ex cism-ws) 
            ##   - case3: 계정 O / 권한 multi (ex cism-ws, magna-ws) -- 권한은 workspace 단위로 부여 
            ##   - case4: 계정 X  ()
            if response_login['account_id']:
                if self.debugging:
                    print_color(f'[SYSTEM] Success getting cookie from AI Conductor:\n {self.aic_cookie}', color='green')
                    print_color(f'[SYSTEM] Success Login: {response_login}', color='green')
                if self.infra_setup["WORKSPACE_NAME"] in ws_list:
                    msg = f'[SYSTEM] 접근 요청하신 workspace ({self.infra_setup["WORKSPACE_NAME"]}) 은 해당 계정으로 접근 가능합니다.'
                    print_color(msg, color='green')
                else:
                    msg = f' List of workspaces accessible by the account: {self.infra_setup["WORKSPACE_NAME"]}) 은 해당 계정으로 접근 불가능 합니다.'
                    raise ValueError()
            else: 
                print_color(f'\n>> Failed Login: {response_login}', color='red')   
        elif response.status_code == 401:
            print_color("[ERROR] login 실패. 잘못된 아이디 또는 비밀번호입니다.", color='red')
            print("Error message: ", self.response_solution)
        elif response.status_code == 400:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_solution["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_solution["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')


    def check_solution_name(self, name=None): 
        """사용자가 등록할 솔루션 이름이 사용가능한지를 체크 한다. 

        중복된 이름이 존재 하지 않으면, 신규 솔루션으로 인식한다. 
        만약, 동일 이름 존재하면 업데이트 모드로 전환하여 솔루션 업데이트를 실행한다. 

        Attributes:
            - name (str): solution name

        Return:
            - solution_name (str): 내부 처리로 변경된 이름 
        """
        self.print_step("Solution Name Creation")

        if not name:
            name = self.solution_info['solution_name']
        
        ########## name-rule ###########
        ## 1) 중복 제거를 위해 workspace 이름 추가
        name = name +  "-" + self.infra_setup["WORKSPACE_NAME"]

        # 2) 문자열의 바이트 길이가 100바이트를 넘지 않는지 확인
        if len(name.encode('utf-8')) > 100:
            raise ValueError("The solution name must be less than 50 bytes.")   
        
        # 3) 스페이스, 특수 문자, 한글 제외한 영문자와 숫자만 허용하는 정규 표현식 패턴
        pattern = re.compile('^[a-zA-Z0-9-]+$')
        # 정규 표현식으로 입력 문자열 검사
        if not pattern.match(name):
            raise ValueError("The solution name can only contain alphanumeric characters and underscores.")

        ########## name-unique #########
        solution_data = {
            "workspace_name": self.infra_setup["WORKSPACE_NAME"], 
            "only_public": 0,  # 1: public, private 다 받아옴, 0: ws 것만
            "page_size": 100
        }
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SOLUTION_LIST"]
        response = requests.get(aic+api, params=solution_data, cookies=self.aic_cookie)
        response_json = response.json()

        solution_list = []
        if 'solutions' in response_json.keys(): 
            for sol in response_json['solutions']: 
                solution_list.append(sol['name'])

                ### 솔루션 업데이트 
                if self.solution_info['solution_update']:
                    if name in sol['name']: 
                        txt = f"[SUCCESS] The solution name ({name}) already exists and can be upgraded. " 
                        self.solution_name = name
                        self.solution_version_new = int(sol['versions'][0]['version']) + 1  ## latest 확인 때문에 [0] 번째 확인
                        self.solution_version_id = sol['id']
                        print_color(txt, color='green')
        else: 
            msg = f" 'solutions' key not found in AI Solution data. API_URI={aic+api}"
            raise ValueError(msg)

        ## 업데이트  에러 처리 및 신규 등록 처리 (모든 solution list 검수 후 진행 가능)
        if self.solution_info['solution_update']:
            if not name in solution_list:
                txt = f"[ERROR] if solution_update is True, the same solution name cannot exist.(name: {name})"
                print_color(txt, color='red')
                raise ValueError("Not find solution name.")
        else:
            # 기존 solution 존재하면 에러 나게 하기 
            if name in solution_list:
                txt = f"[SYSTEM] the solution name ({name}) already exists in the AI solution list. Please enter another name !!"
                print_color(txt, color='red')
                raise ValueError("Not allowed solution name.")
            else:  ## NEW solutions
                txt = f"[SUCCESS] the solution name ({name}) is available." 
                self.solution_name = name
                self.solution_version_new = 1
                self.solution_version_id = None
                print_color(txt, color='green')

        msg = f'[INFO] solution name list (workspace: {self.infra_setup["WORKSPACE_NAME"]}):'
        print(msg)
        # 이미 존재하는 solutino list 리스트업 
        pre_existences = pd.DataFrame(solution_list, columns=["AI solutions"])
        pre_existences = pre_existences.head(100)
        print_color(pre_existences.to_markdown(tablefmt='fancy_grid'), color='cyan')

        return self.solution_name

    def set_description(self, description={}):
        """솔루션 설명을 solution_metadata 에 삽입합니다. 

        Attributes:
          - desc (dict): title, overview, input_data (format descr.), output_data (format descr.),
          user_parameters, algorithm 에 대한 설명문을 작성한다. 
          추후 mark-up 지원여부 
        """

        self.print_step("Set AI Solution Description")

        if len(description)==0:
            description = self.solution_info["description"]

        def validate_dict(d):
            required_keys = ['title', 'input_data', 'output_data', 'user_parameters', 'algorithm']

            if 'overview' not in d:
              raise KeyError("overview key is required") 

            for key in required_keys:
              if key not in d:
                d[key] = ""
        
        validate_dict(description)
        description['title'] = self.solution_name  ## name 을 title default 로 설정함
        description['contents_name'] = self.exp_yaml['name']

        try: 
            self.sm_yaml['description'].update(description)
            self._save_yaml()

            print_color(f"[SUCCESS] Update solution_metadata.yaml.", color='green')
            print(f"description:")
            pprint(description)
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << description >> in the solution_metadata.yaml \n{e}")


    def set_wrangler(self):
        """wrangler.py 를 solution_metadata 의 code-to-string 으로 반영합니다. 
        ./wrangler/wrangler.py 만 지원 합니다. 

        """

        self.print_step("Set Wrangler", sub_title=True)


        try: 
            with open(REGISTER_WRANGLER_PATH, 'r') as file:
                python_content = file.read()

            self.sm_yaml['wrangler_code_uri'] = python_content
            self.sm_yaml['wrangler_dataset_uri'] = ''
            self._save_yaml()
        except:
            msg = f"[WARNING] wrangler.py 가 해당 위치에 존재해야 합니다. (path: {REGISTER_WRANGLER_PATH})"
            print_color(msg, color="yellow")

            self.sm_yaml['wrangler_code_uri'] = ''
            self.sm_yaml['wrangler_dataset_uri'] = ''
            self._save_yaml()
        
    def set_edge(self, metadata_value={}):
        """Edge Conductor 에서 처리해야 할 key 를 사용자로 부터 입력 받습니다. 
        이를 soluton_metadata 에 반영합니다. 

        Attributes:
          - metadata_value (dict): 'support_labeling', 'inference_result_datatype', 'train_datatype' key 지원

          사용자가 정상적으로 metadata_value 를 설정하였는지를 체크하고, 이를 solution_metadata 에 반영합니다. 
          - support_labeling : True / False (bool)
          - inference_result_datatype: table / image (str) --> inference reult 를 csv, image 로 display 할지
          - train_datatype: table / image (str) --> inference output 의 형태가 csv, image 인지를 선택
        """

        self.print_step("Set Edge Condcutor & Edge App", sub_title=True)
        
        if len(metadata_value) == 0:
            metadata_value = self.solution_info['contents_type']

        def _check_edgeconductor_interface(user_dict):
            check_keys = ['support_labeling', 'inference_result_datatype', 'train_datatype']
            allowed_datatypes = ['table', 'image']
            for k in user_dict.keys(): ## 엉뚱한 keys 존재 하는지 확인
                self._check_parammeter(k)
                if k not in check_keys: 
                    raise ValueError(f"[ERROR] << {k} >> is not allowed for contents_type key. \
                                     (keys: support_labeling, inference_result_datatype, train_datatype) ")
            for k in check_keys: ## 필수 keys 가 누락되었는지 확인
                if k not in user_dict.keys(): 
                    raise ValueError(f"[ERROR] << {k} >> must be in the edgeconductor_interface key list.")

            ## type 체크 및 key 존재 확인
            if isinstance(user_dict['support_labeling'], bool):
                pass
            else: 
                raise ValueError("[ERRPR] << support_labeling >> parameter must have boolean type.")

            if user_dict['inference_result_datatype'] not in allowed_datatypes:
                raise ValueError(f"[ERROR] << inference_result_datatype >> parameter must have the value among these: \n{allowed_datatypes}")

            if user_dict['train_datatype'] not in allowed_datatypes:
                raise ValueError(f"[ERROR] << train_datatype >> parameter must have the value among these: \n{allowed_datatypes}")                  

        # edgeconductor interface 
        _check_edgeconductor_interface(metadata_value)

        self.sm_yaml['edgeconductor_interface'] = metadata_value
        
        ### EdgeAPP 관련 부분도 업데이트 함.
        self.sm_yaml['edgeapp_interface'] = {'redis_server_uri': ""}
        self._save_yaml()

        msg = "[SUCCESS] contents_type 을 solution_metadata 에 성공적으로 업데이트 하였습니다."
        print_color(msg, color="green")
        print(f"edgeconductor_interfance: {metadata_value}")

    def set_resource_list(self):
        """AI Conductor 에서 학습에 사용될 resource 를 선택 하도록, 리스트를 보여 줍니다. (필수 실행)
        """
        self.print_step(f"Display {self.pipeline} Resource List")

        params = {
            "workspace_name": self.infra_setup["WORKSPACE_NAME"],
            "page_size": 100

        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SYSTEM_INFO"]
        try: 
            response = requests.get(aic+api, params=params, cookies=self.aic_cookie)
            response_json = response.json()
        except: 
            raise NotImplementedError("[ERROR] Failed to get workspaces info.")


        resource_list = []
        try: 
            df = pd.DataFrame(response_json["specs"])
            for spec in response_json["specs"]:
                resource_list.append(spec["name"])
        except: 
            raise ValueError("Got wrong workspace info.")

        print(f"{self.pipeline} 에 사용될 resource 를 선택해주세요(type{resource_list}):")
        print_color(df.to_markdown(tablefmt='fancy_grid'), color='cyan')

        ## 해당 함수는 두번 call 될 수 있기 때문에, global 변수로 관리함
        self.resource_list = resource_list
        return resource_list
        

    def set_resource(self, resource= ''):
        """AI Conductor 에서 학습에 사용될 resource 를 선택 합니다. 
        사용자에게 선택 하도록 해야 하며, low, standard, high 과 같은 추상적 선택을 하도록 합니다.

        Attributes:
          - resource (str): 
        """
        self.print_step(f"Set {self.pipeline} Resource")


        if len(self.resource_list) == 0: # Empty List
            msg = f"[ERROR] set_resource_list 함수를 먼저 실행 해야 합니다."
            raise ValueError(msg)
        
        if resource == '': # erorr when input is empty 
            msg = f"[ERROR] 입력된 {self.pipeline}_resource 가 empty 입니다. Spec 을 선택해주세요. (type={self.resource_list})"
            raise ValueError(msg)

        if not resource in self.resource_list:
            msg = f"[ERROR] 입력된 {self.pipeline}_resource 가 '{resource}' 입니다. 미지원 값입니다. (type={self.resource_list})"
            raise ValueError(msg)

        self.sm_yaml['pipeline'][self.sm_pipe_pointer]["resource"] = {"default": resource}

        ## inference 의 resource 를 선택하는 시나리오가 없음. standard 로 강제 고정 (24.01.17)
        if self.pipeline == "inference":
            self.sm_yaml['pipeline'][self.sm_pipe_pointer]["resource"] = {"default": 'standard'}
            resource = 'standard'
            msg = f"EdgeApp 에 대한 resource 설정은 현재 미지원 입니다. resource=standard 로 고정 됩니다."
            print_color(msg, color="yellow")

        print_color(f"[SUCCESS] Update solution_metadat.yaml:", color='green')
        print(f"pipeline[{self.sm_pipe_pointer}]: -resource: {resource}")
        self._save_yaml()

    def load_system_resource(self): 
        """ 사용가능한 ECR, S3 주소를 반환한다. 
        """
        self.print_step("Check ECR & S3 Resource")

        params = {
            "workspace_name": self.infra_setup["WORKSPACE_NAME"],
            "page_size": 100

        }
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SYSTEM_INFO"]

        try: 
            response = requests.get(aic+api, params=params, cookies=self.aic_cookie)
            response_json = response.json()
        except: 
            raise NotImplementedError("Failed to get workspaces info.")

        # workspace로부터 받아온 ecr, s3 정보를 내부 변수화 
        try:
            solution_type = self.solution_info["solution_type"]
            self.bucket_name = response_json["s3_bucket_name"][solution_type] # bucket_scope: private, public
            self.bucket_name_icon = response_json["s3_bucket_name"]["public"] # icon 은 공용 저장소에만 존재. = public
            self.ecr_name = response_json["ecr_base_path"][solution_type]
        except Exception as e:
            raise ValueError(f"Wrong format of << workspaces >> received from REST API:\n {e}")

        if self.debugging:
            print_color(f"\n[INFO] S3_BUCUKET_URI:", color='green') 
            print_color(f'- public: {response_json["s3_bucket_name"]["public"]}', color='cyan') 
            print_color(f'- private: {response_json["s3_bucket_name"]["public"]}', color='cyan') 

            print_color(f"\n[INFO] ECR_URI:", color='green') 
            print_color(f'- public: {response_json["ecr_base_path"]["public"]}', color='cyan') 
            print_color(f'- private: {response_json["ecr_base_path"]["public"]}', color='cyan') 

            
        print_color(f"[SYSTEM] AWS ECR:  ", color='green') 
        print(f"{self.ecr_name}") 
        print_color(f"[SYSTEM] AWS S3 buckeet:  ", color='green') 
        print(f"{self.bucket_name}") 


    #s3://s3-an2-cism-dev-aic/artifacts/bolt_fastening_table_classification/train/artifacts/2023/11/06/162000/
    def set_pipeline_uri(self, mode, data_paths = [], skip_update=False):
        """ dataset, artifacts, model 중에 하나를 선택하면 이에 맞느 s3 uri 를 생성하고, 이를 solution_metadata 에 반영한다.

        Attributes:
          - mode (str): dataset, artifacts, model 중에 하나 선택

        Returns:
          - uri (str): s3 uri 를 string 타입으로 반환 함 
        """
        if mode == "artifact":
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{self.solution_version_new}/" + self.pipeline  + "/artifacts/"
            uri = {'artifact_uri': "s3://" + self.bucket_name + "/" + prefix_uri}
        elif mode == "data":
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{self.solution_version_new}/" + self.pipeline  + "/data/"
            if len(data_paths) ==0 :
                uri = {'dataset_uri': ["s3://" + self.bucket_name + "/" + prefix_uri]}
            else:
                uri = {'dataset_uri': []}
                data_path_base = "s3://" + self.bucket_name + "/" + prefix_uri
                for data_path_sub in data_paths:
                    uri['dataset_uri'].append(data_path_base + data_path_sub)

        elif mode == "model":  ## model
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{self.solution_version_new}/" + 'train'  + "/artifacts/"
            uri = {'model_uri': "s3://" + self.bucket_name + "/" + prefix_uri}
        else:
            raise ValueError("mode must be one of [dataset, artifacts, model]")

        try: 
            if self.pipeline == 'train':
                if not self.sm_yaml['pipeline'][self.sm_pipe_pointer]['type'] == 'train':
                    raise ValueError("Setting << artifact_uri >> in the solution_metadata.yaml is only allowed for << train >> pipeline. \n - current pipeline: {self.pipeline}")
                ## train pipelne 시에는 model uri 미지원
                if mode == "model":
                    raise ValueError("Setting << model_uri >> in the solution_metadata.yaml is only allowed for << inference >> pipeline. \n - current pipeline: {self.pipeline}")
            else: ## inference
                if not self.sm_yaml['pipeline'][self.sm_pipe_pointer]['type'] == 'inference':
                    raise ValueError("Setting << artifact_uri >> in the solution_metadata.yaml is only allowed for << inference >> pipeline. \n - current pipeline: {self.pipeline}")

            if skip_update:
                pass
            else:
                self.sm_yaml['pipeline'][self.sm_pipe_pointer].update(uri)
                self._save_yaml()

                print_color(f'[SUCCESS] Update solution_metadata.yaml:', color='green')
                if mode == "artifacts":
                    print(f'pipeline: type: {self.pipeline}, artifact_uri: {uri} ')
                elif mode == "data":
                    print(f'pipeline: type: {self.pipeline}, dataset_uri: {uri} ')
                else: ## model
                    print(f'pipeline: type:{self.pipeline}, model_uri: {uri} ')
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << artifact_uri >> in the solution_metadata.yaml \n{e}")
        
            

        return prefix_uri


    def register_solution(self): 
        ''' 일반 등록과 솔루션 업데이트 으로 구분 됨 
        solution_info["solution_update]=True 이면, 업데이트 과정을 진행함
        '''

        self.print_step("Register AI solution")

        try: 
            # 등록을 위한 형태 변경
            data = {
            "scope_ws": self.infra_setup["WORKSPACE_NAME"],
            "metadata_json": self.sm_yaml
            }
            data =json.dumps(data)

            aic = self.infra_setup["AIC_URI"]
            if self.solution_info["solution_update"]:
                solution_params = {
                    "solution_id": self.solution_version_id,
                    "workspace_name": self.infra_setup["WORKSPACE_NAME"]
                }
                api = self.api_uri["REGISTER_SOLUTION"] + f"/{self.solution_version_id}/version"
            else:
                solution_params = {
                    "workspace_name": self.infra_setup["WORKSPACE_NAME"]
                }
                api = self.api_uri["REGISTER_SOLUTION"]

            # AI 솔루션 등록
            response = requests.post(aic+api, params=solution_params, data=data, cookies=self.aic_cookie)
            self.response_solution = response.json()
        except Exception as e: 
            raise NotImplementedError(f"Failed to register AI solution: \n {e}")

        if response.status_code == 200:
            print_color("[SUCCESS] AI Solution 등록을 성공하였습니다. ", color='cyan')
            print(f"[INFO] AI solution register response: \n {self.response_solution}")

            # interface 용 폴더 생성.
            try:
                if os.path.exists(REGISTER_INTERFACE_PATH):
                    shutil.rmtree(REGISTER_INTERFACE_PATH)
                os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory while registering solution instance: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.solution_file
            with open(path, 'w') as f:
              json.dump(response.json(), f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_solution["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_solution["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            print(aic+api)
    

    

    ################################
    ######    STEP2. S3 Control
    ################################

    
            
    # def s3_upload_icon_display(self):
    #     """ 가지고 있는 icon 들을 디스플레이하고 파일명을 선택하게 한다. 
    #     """
    #     self.print_step("Display icon list")

    #     # 폴더 내의 모든 SVG 파일을 리스트로 가져오기
    #     svg_files = [os.path.join(REGISTER_ICON_PATH, file) for file in os.listdir(REGISTER_ICON_PATH) if file.endswith('.svg')]

    #     # HTML과 CSS를 사용하여 SVG 파일과 파일명을 그리드 형태로 표시
    #     html_content = '<div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px;">'
    #     icon_filenames = []
    #     for file in svg_files:
    #         file_name = os.path.basename(file)  # 파일 이름만 추출
    #         file_name = file_name.replace(f"{REGISTER_ICON_PATH}/", "")
    #         icon_filenames.append(file_name)
    #         file_name = file_name.replace(f".svg", "")
    #         html_content += f'''<div>
    #                                 <img src="{file}" style="width: 100px; height: 100px;">
    #                                 <div style="word-wrap: break-word; word-break: break-all; width: 100px;">{file_name}</div>
    #                             </div>'''
    #     html_content += '</div>'

    #     self.icon_filenames = icon_filenames

    #     return html_content

    def select_icon(self, name):
        """ icon 업로드는 추후 제공 
        현재는 icon name 을 solution_metadata 에 업데이트 하는 것으로 마무리 
        """
        # self.print_step("select solution icon", sub_title=True )

        if not ".svg" in name:
            name = name+".svg"
        icon_s3_uri = "s3://" + self.bucket_name_icon + '/icons/' + name   # 값을 리스트로 감싸줍니다
        self.sm_yaml['description']['icon'] = icon_s3_uri
        self._save_yaml()

        # if not ".svg" in name:
        #     name = name+".svg"
        # if name in self.icon_filenames:

        #     icon_s3_uri = "s3://" + self.bucket_name_icon + '/icons/' + name   # 값을 리스트로 감싸줍니다
        #     self.sm_yaml['description']['icon'] = icon_s3_uri
        #     self._save_yaml()

        #     print_color(f'[SUCCESS] update solution_metadata.yaml:', color='green')
        #     print(f'description: -icon: {icon_s3_uri} ')
        # else:
        #     raise ValueError(f"[ERROR] Wrong icon name: {name}. \n(icon_list={self.icon_filenames}) ")
        
    def _s3_access_check(self):
        """ S3 에 접속 가능한지를 확인합니다.  s3_client instance 생성을 합니다.

        1) s3_access_key_path 가 존재하면, 파일에서 key 를 확인하고,
          - TODO file format 공유하기 (프로세스화)
        2) TODO aws configure가 설정되어 있으면 이를 자동으로 해석한다. 
        3) key 없이 권한 설정으로 접속 가능한지도 확인한다. 

        """
        self.print_step("Check to access S3")

        if not self.aws_access_key:
            self.s3_client = boto3.client('s3',
                                aws_access_key_id=self.aws_access_key,
                                aws_secret_access_key=self.aws_secret_key,
                                region_name=self.infra_setup['REGION'])
        else:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            self.s3_client = boto3.client('s3', region_name=self.infra_setup['REGION'])

        print(f"[INFO] AWS region: {self.infra_setup['REGION']}")
        if isinstance(boto3.client('s3', region_name=self.infra_setup['REGION']), botocore.client.BaseClient) == True:       
            print_color(f"[INFO] AWS S3 access check: OK", color="green")
        else: 
            raise ValueError(f"[ERROR] AWS S3 access check: Fail")

        return isinstance(boto3.client('s3', region_name=self.infra_setup['REGION']), botocore.client.BaseClient)

    def s3_upload_data(self):
        """input 폴더에 존재하는 데이터를 s3 에 업로드 합니다. 
        """
        self.print_step(f"Upload {self.pipeline} data to S3")

        # inner func.
        def s3_process(s3, bucket_name, data_path, local_folder, s3_path, delete=True):
            if delete == True: 
                objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)
                if 'Contents' in objects_to_delete:
                    for obj in objects_to_delete['Contents']:
                        self.s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                        print_color(f'[SYSTEM] Deleted pre-existing S3 object: {obj["Key"]}', color = 'yellow')
                s3.delete_object(Bucket=bucket_name, Key=s3_path)
            s3.put_object(Bucket=bucket_name, Key=(s3_path))

            ## s3 생성
            try:    
                response = s3.upload_file(data_path, bucket_name, s3_path + data_path[len(local_folder):])
            except NoCredentialsError as e:
                raise NoCredentialsError("NoCredentialsError: \n{e}")
            except ClientError as e:
                print(f"ClientError: ", e)
                return False
            # temp = s3_path + "/" + data_path[len(local_folder):]
            uploaded_path = bucket_name + '/' + s3_path + data_path[len(local_folder):]
            # print(data_path)
            print_color(f"[SUCCESS] update train_data to S3:", color='green')
            print(f"{uploaded_path }")
            return True

        if "train" in self.pipeline:
            local_folder = INPUT_DATA_HOME + "train/"
            print_color(f'[SYSTEM] Start uploading data into S3 from local folder:', color='cyan')
            print(f'{local_folder}')

            try: 
                ## sol_metadata 업데이트 
                data_uri_list = []
                for item in os.listdir(local_folder):
                    sub_folder = os.path.join(local_folder, item)
                    if os.path.isdir(sub_folder):
                        data_uri_list.append(item+"/")
                s3_prefix_uri = self.set_pipeline_uri(mode="data", data_paths=data_uri_list)

                ### upload data to S3
                for root, dirs, files in os.walk(local_folder):
                    for idx, file in enumerate(files):
                        data_path = os.path.join(root, file)
                        if idx == 0: #최초 1회만 delete s3
                            s3_process(self.s3_client, self.bucket_name, data_path, local_folder, s3_prefix_uri, True) 
                        else: 
                            s3_process(self.s3_client, self.bucket_name, data_path, local_folder, s3_prefix_uri, False)
            except Exception as e: 
                raise NotImplementedError(f'[ERROR] Failed to upload local data into S3') 

        elif "inference" in self.pipeline:
            local_folder = INPUT_DATA_HOME + "inference/"
            print_color(f'[INFO] Start uploading data into S3 from local folder:', color='cyan')
            print(f'{local_folder}')

            try: 
                ## sol_metadata 업데이트 
                data_uri_list = []
                for item in os.listdir(local_folder):
                    sub_folder = os.path.join(local_folder, item)
                    if os.path.isdir(sub_folder):
                        data_uri_list.append(item+"/")
                s3_prefix_uri = self.set_pipeline_uri(mode="data", data_paths=data_uri_list)

                ### upload data to S3
                for root, dirs, files in os.walk(local_folder):
                    for idx, file in enumerate(files):
                        data_path = os.path.join(root, file)
                        if idx == 0: #최초 1회만 delete s3
                            s3_process(self.s3_client, self.bucket_name, data_path, local_folder, s3_prefix_uri, True) 
                        else: 
                            s3_process(self.s3_client, self.bucket_name, data_path, local_folder, s3_prefix_uri, False)
            except Exception as e: 
                raise NotImplementedError(f'[ERROR] Failed to upload local data into S3') 
        else:
            raise ValueError(f"[ERROR] Not allowed value for << pipeline >>: {self.pipeline}")


    def s3_upload_artifacts(self):
        """ 최종 실험결과물 (train & inference) 를 s3 에 업로드 한다. 
        테스트 용으로 활용한다. 
        """

        self.print_step(f"Upload {self.pipeline} artifacts to S3")


        # inner func.
        def s3_process(s3, bucket_name, data_path, local_folder, s3_path, delete=True):
            if delete == True: 
                objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)
                if 'Contents' in objects_to_delete:
                    for obj in objects_to_delete['Contents']:
                        self.s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                        print_color(f'[INFO] Deleted pre-existing S3 object:', color = 'yellow')
                        print(f'{obj["Key"]}')
                s3.delete_object(Bucket=bucket_name, Key=s3_path)
            s3.put_object(Bucket=bucket_name, Key=(s3_path +'/'))
            try:    
                response = s3.upload_file(data_path, bucket_name, s3_path + data_path[len(local_folder):])
            except NoCredentialsError as e:
                raise NoCredentialsError("NoCredentialsError: \n{e}")
            except ClientError as e:
                print(f"ClientError: ", e)
                return False
            # temp = s3_path + "/" + data_path[len(local_folder):]
            uploaded_path = bucket_name + s3_path + data_path[len(local_folder):]
            print_color(f"[SUSTEM] S3 object key (new): ", color='green')
            print(f"{uploaded_path }")
            return True

        try: 
            s3_prefix_uri = self.set_pipeline_uri(mode="artifact")
        except Exception as e: 
            raise NotImplementedError(f'Failed updating solution_metadata.yaml - << artifact_uri >> info / pipeline: {self.pipeline} \n{e}')
        
        if "train" in self.pipeline:
            artifacts_path = _tar_dir(".train_artifacts")  # artifacts tar.gz이 저장된 local 경로 return
            local_folder = os.path.split(artifacts_path)[0] + '/'
            print_color(f'[SYSTEM] Start uploading train artifacts into S3 from local folder:', color='cyan')
            print(f'{local_folder}')

            s3_process(self.s3_client, self.bucket_name, artifacts_path, local_folder, s3_prefix_uri) 
            shutil.rmtree(REGISTER_ARTIFACT_PATH , ignore_errors=True)

        elif "inference" in self.pipeline:
            ## inference artifacts tar gz 업로드 
            artifacts_path = _tar_dir(".inference_artifacts")  # artifacts tar.gz이 저장된 local 경로 
            local_folder = os.path.split(artifacts_path)[0] + '/'
            print_color(f'[INFO] Start uploading inference artifacts into S3 from local folder:', color='cyan')
            print(f'{local_folder}')

            s3_process(self.s3_client, self.bucket_name, artifacts_path, local_folder, s3_prefix_uri)
            shutil.rmtree(REGISTER_ARTIFACT_PATH , ignore_errors=True)


            ## model tar gz 업로드 
            # [중요] model_uri는 inference type 밑에 넣어야되는데, 경로는 inference 대신 train이라고 pipeline 들어가야함 (train artifacts 경로에 저장)
            train_artifacts_s3_path = s3_prefix_uri.replace(f'v{self.solution_version_new}/inference', f'v{self.solution_version_new}/train')
            model_path = _tar_dir(".train_artifacts/models")  # model tar.gz이 저장된 local 경로 return 
            local_folder = os.path.split(model_path)[0] + '/'
            print_color(f'\n[SYSTEM] Start uploading << model >> into S3 from local folder:', color='cyan')
            print(f'{local_folder}')
            # 주의! 이미 train artifacts도 같은 경로에 업로드 했으므로 model.tar.gz올릴 땐 delete object하지 않는다. 
            s3_process(self.s3_client, self.bucket_name, model_path, local_folder, train_artifacts_s3_path, delete=False) 

            ## model uri 기록
            try: 
                self.set_pipeline_uri(mode="model")
            except Exception as e: 
                raise NotImplementedError(f'[ERROR] Failed updating solution_metadata.yaml - << model_uri >> info / pipeline: {self.pipeline} \n{e}')
            finally:
                shutil.rmtree(REGISTER_MODEL_PATH, ignore_errors=True)

        else:
            raise ValueError(f"Not allowed value for << pipeline >>: {self.pipeline}")

    ################################
    ######    STEP3. Dcoker Container Control
    ################################

    def make_docker_container(self, skip_build=False):
        """ECR 에 업로드 할 docker 를 제작 한다. 
        1) experimental_plan 에 사용된 source code 를 임시 폴더로 copy 한다. 
        2) Dockerfile 을 작성 한다. 
        3) Dockerfile 을 컴파일 한다. 
        4) 컴파일 된 도커 파일을 ECR 에 업로드 한다. 
        5) 컨테이너 uri 를 solution_metadata.yaml 에 저장 한다. 
        
        """
        if not skip_build:
            self._reset_alo_solution()  # copy alo folders
            ##TODO : ARM/AMD 에 따라 다른 dockerfile 설정
            self._set_docker_contatiner()  ## set docerfile

            self.print_step("Set AWS ECR")
            if self.infra_setup["BUILD_METHOD"] == 'docker':
                ## docker login 실행 
                self._set_aws_ecr(docker=True, tags=self.infra_setup["REPOSITORY_TAGS"])
            else:  ##buildah
                self._set_aws_ecr(docker=False, tags=self.infra_setup["REPOSITORY_TAGS"]) 

            self.print_step("Upload Docker Container", sub_title=True)

            self._build_docker()
            self._docker_push()
        else:
            if self.infra_setup["BUILD_METHOD"] == 'docker':
                self._set_aws_ecr_skipbuild(docker=True, tags=self.infra_setup["REPOSITORY_TAGS"])
            else:  ##buildah
                self._set_aws_ecr_skipbuild(docker=False, tags=self.infra_setup["REPOSITORY_TAGS"]) 

        self._set_container_uri()


    def _set_aws_ecr_skipbuild(self, docker = True, tags = []):
        self.docker = docker
        self.ecr_url = self.ecr_name.split("/")[0]
        # FIXME 마지막에 붙는 container 이름은 solution_name 과 같게 
        # http://collab.lge.com/main/pages/viewpage.action?pageId=2126915782
        # [중요] container uri 는 magna-ws 말고 magna 같은 식으로 쓴다 (231207 임현수C)
        ecr_scope = self.infra_setup["WORKSPACE_NAME"].split('-')[0] # magna-ws --> magna
        self.ecr_repo = self.ecr_name.split("/")[1] + '/' + ecr_scope + "/ai-solutions/" + self.solution_name + "/" + self.pipeline + "/"  + self.solution_name  
        self.ecr_full_url = self.ecr_url + '/' + self.ecr_repo 

        print_color(f"[SYSTEM] Target AWS ECR repository:", color='cyan')
        print(f"{self.ecr_repo}")


    def _set_aws_ecr(self, docker = True, tags = []):


        self.docker = docker
        self.ecr_url = self.ecr_name.split("/")[0]
        # FIXME 마지막에 붙는 container 이름은 solution_name 과 같게 
        # http://collab.lge.com/main/pages/viewpage.action?pageId=2126915782
        # [중요] container uri 는 magna-ws 말고 magna 같은 식으로 쓴다 (231207 임현수C)
        ecr_scope = self.infra_setup["WORKSPACE_NAME"].split('-')[0] # magna-ws --> magna
        self.ecr_repo = self.ecr_name.split("/")[1] + '/' + ecr_scope + "/ai-solutions/" + self.solution_name + "/" + self.pipeline + "/"  + self.solution_name  
        self.ecr_full_url = self.ecr_url + '/' + self.ecr_repo 

        ## 동일 이름의 ECR 존재 시, 삭제하고 다시 생성한다. 
        if not self.aws_access_key:
            ecr_client = boto3.client('ecr',
                                aws_access_key_id=self.aws_access_key,
                                aws_secret_access_key=self.aws_secret_key,
                                region_name=self.infra_setup['REGION'])
        else:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            ecr_client = boto3.client('ecr', region_name=self.infra_setup['REGION'])

        try:
            ecr_client.delete_repository(repositoryName=self.ecr_repo, force=True)
            print_color(f"[SYSTEM] Repository {self.ecr_repo} already exists. Deleting...", color='yellow')
        except:
            pass

        if self.docker == True:
            run = 'docker'
        else:
            run = 'buildah'

        print_color(f"[SYSTEM] target AWS ECR url: ", color='blue')
        print(f"{self.ecr_url}",)

        p1 = subprocess.Popen(
            ['aws', 'ecr', 'get-login-password', '--region', f'{self.infra_setup["REGION"]}'], stdout=subprocess.PIPE
        )
        if self.docker == True:
            p2 = subprocess.Popen(
                [f'{run}', 'login', '--username', 'AWS','--password-stdin', f'{self.ecr_url}' + "/" + self.ecr_repo], stdin=p1.stdout, stdout=subprocess.PIPE
            )
        else:
            p2 = subprocess.Popen(
                ['sudo', f'{run}', 'login', '--username', 'AWS','--password-stdin', f'{self.ecr_url}' + "/" + self.ecr_repo], stdin=p1.stdout, stdout=subprocess.PIPE
            )

        p1.stdout.close()
        output = p2.communicate()[0]

        print_color(f"[SYSTEM] AWS ECR | docker login result:", color='cyan')
        print(f"{output.decode()}")

        print_color(f"[SYSTEM] Target AWS ECR repository:", color='cyan')
        print(f"{self.ecr_repo}")

        # print(tags)

        if len(tags) > 0:
            command = [
            "aws",
            "ecr",
            "create-repository",
            "--region", self.infra_setup["REGION"],
            "--repository-name", self.ecr_repo,
            "--image-scanning-configuration", "scanOnPush=true",
            "--tags"
            ] + tags  # 전달된 태그들을 명령어에 추가합니다.
        else:
            command = [
            "aws",
            "ecr",
            "create-repository",
            "--region", self.infra_setup["REGION"],
            "--repository-name", self.ecr_repo,
            "--image-scanning-configuration", "scanOnPush=true",
            ]
        # subprocess.run() 함수를 사용하여 명령을 실행합니다.
        try:
            if self.docker: 
                create_resp = ecr_client.create_repository(repositoryName=self.ecr_repo)
                repository_arn = create_resp['repository']['repositoryArn']
                tags_new = []
                for tag in tags:
                        key, value = tag.split(',')
                        tag_dict = {'Key': key.split('=')[1], 'Value': value.split('=')[1]}
                        tags_new.append(tag_dict)
                

                resp = ecr_client.tag_resource(
                    resourceArn=repository_arn,
                    tags=tags_new
                    )

                print_color(f"[SYSTEM] AWS ECR create-repository response: ", color='cyan')
                print(f"{resp}")
            else:
                resp = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                print_color(f"[INFO] AWS ECR create-repository response: \n{resp.stdout}", color='cyan')
        except subprocess.CalledProcessError as e:
            raise NotImplementedError(f"Failed to AWS ECR create-repository:\n + {e}")

    # FIXME 그냥 무조건 latest로 박히나? 
    def _build_docker(self):

        if self.docker:
            subprocess.run(['docker', 'build', '.', '-t', f'{self.ecr_full_url}:v{self.solution_version_new}'])
        else:
            subprocess.run(['sudo', 'buildah', 'build', '--isolation', 'chroot', '-t', f'{self.ecr_full_url}:v{self.solution_version_new}'])


    def _docker_push(self):
        if self.infra_setup['BUILD_METHOD'] == 'docker':
            subprocess.run(['docker', 'push', f'{self.ecr_full_url}:v{self.solution_version_new}'])
        else:
            subprocess.run(['sudo', 'buildah', 'push', f'{self.ecr_full_url}:v{self.solution_version_new}'])

        if self.infra_setup['BUILD_METHOD'] == 'docker':
            subprocess.run(['docker', 'logout'])
        else:
            subprocess.run(['sudo', 'buildah', 'logout', '-a'])

    def _set_container_uri(self):
        try: 
            data = {'container_uri': f'{self.ecr_full_url}:v{self.solution_version_new}'} # full url 는 tag 정보까지 포함 
            self.sm_yaml['pipeline'][self.sm_pipe_pointer].update(data)
            print_color(f"[SYSTEM] Completes setting << container_uri >> in solution_metadata.yaml:", color='green')
            print(f"pipeline: -container_uri: {data['container_uri']}")
            self._save_yaml()
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << container_uri >> in the solution_metadata.yaml \n{e}")

    ################################
    ######    STEP4. Set User Parameters
    ################################

    def set_user_parameters(self, display_table=False):
        """experimental_plan.yaml 에서 제작한 parameter 들으 보여주고, 기능 정의 하도록 한다.
        """
 
        self.print_step(f"Set {self.pipeline} user parameters:")
 
        def rename_key(d, old_key, new_key): #inner func.
            if old_key in d:
                d[new_key] = d.pop(old_key)
       
        ### candidate parameters setting

        params = deepcopy(self.exp_yaml['user_parameters'])
        for pipe_dict in params:
            pipe_name = None # init
            if 'train_pipeline' in list(pipe_dict.keys()):
                pipe_name = 'train'
            elif 'inference_pipeline' in list(pipe_dict.keys()):
                pipe_name = 'inference'
            else:
                pipe_name = None
 
            ## single pipeline 이 지원되도록 하기
            rename_key(pipe_dict, f'{pipe_name}_pipeline', 'candidate_parameters')
            sm_pipe_type = self.sm_yaml['pipeline'][self.sm_pipe_pointer]['type']
 
            if sm_pipe_type == pipe_name:
 
                subkeys = {}
                subkeys.update(pipe_dict)  ## candidate
 
                # 빈 user_parameters 생성
                selected_user_parameters = []
                user_parameters = []
                step_list = []
                for step in pipe_dict['candidate_parameters']:
                    output_data = {'step': step['step'], 'args': {}} # solution metadata v9 기준 args가 dict
                    selected_user_parameters.append(output_data.copy())
                    output_data = {'step': step['step'], 'args': []} # solution metadata v9 기준 args가 list
                    user_parameters.append(output_data.copy())
                    step_list.append(step['step'])
 
 
                subkeys['selected_user_parameters'] = selected_user_parameters
                subkeys['user_parameters'] = user_parameters
 
                ## ui 로 표현할 parameter 존재하는지 확인
                try:
                    ui_dict = deepcopy(self.exp_yaml['ui_args_detail'])
                    enable_ui_args = True
                    new_dict = {'user_parameters': {}}
                    for ui_args_step in ui_dict:
                        if f'{pipe_name}_pipeline' in list(ui_args_step.keys()):
                            new_dict['user_parameters'] = ui_args_step[f'{pipe_name}_pipeline']
                except:
                    enable_ui_args = False
 
                ## ui 로 표현할 parameter 존재 시 진행 됨
                if enable_ui_args:
                    ## step name 추가
                    for new_step in new_dict['user_parameters']:
                        for cnt, steps in enumerate(subkeys['user_parameters']):
                            if steps['step'] == new_step['step']:
                                subkeys['user_parameters'][cnt]['args'] = new_step['args']
 
 
                    ## ui_args_detail 존재 여부 체크
                    print_color("[SYSTEM] experimental_plan.yaml 에 ui_args_detail 이 정상 기록 되었는지 체크 합니다.", color='green')
                    for candi_step_dict in pipe_dict['candidate_parameters']:
                        if 'ui_args' in candi_step_dict:
                            # print(step)
                            for ui_arg in candi_step_dict['ui_args']:
                                flag = False
 
                                ## 존재 여부 검색 시작
                                ui_dict = deepcopy(self.exp_yaml['ui_args_detail'])
                                for ui_pipe_dict in ui_dict:
                                    if f'{pipe_name}_pipeline' in list(ui_pipe_dict.keys()):
                                        for ui_step_dict in ui_pipe_dict[f'{pipe_name}_pipeline']:
                                            if candi_step_dict['step'] == ui_step_dict['step']:
                                                for arg in ui_step_dict['args']:
                                                    if ui_arg == arg['name']:
                                                        flag = True
                                                        print(f"ui_arg_detail: 에 [{candi_step_dict['step']}]({ui_arg}) 이 기록됨을 확인. ")
                                if not flag :
                                    raise ValueError (f"[ERROR] ui_arg_detail: 에서 [{candi_step_dict['step']}]({ui_arg}) 를 찾을 수 없습니다. ! ")
       
                self.sm_yaml['pipeline'][self.sm_pipe_pointer].update({'parameters':subkeys})
                # print(subkeys)
                self._save_yaml()


            
        ## display
        params2 = deepcopy(self.exp_yaml['user_parameters'])
        columns = ['pipeline', 'step', 'parmeter', 'value']
        df = pd.DataFrame(columns=columns)
        table_idx = 0
        self.candidate_format = {} ## return format 만들기 
        for pipe_dict in params2:
            if 'train_pipeline' in list(pipe_dict.keys()):
                pipe_name = 'train'
                self.candidate_format.update({'train_pipeline':[]})
            elif 'inference_pipeline' in list(pipe_dict.keys()):
                pipe_name = 'inference'
                self.candidate_format.update({'inference_pipeline':[]})
            else:
                pipe_name = None

            step_idx = 0
            for step_dict in pipe_dict[f'{pipe_name}_pipeline']:
                step_name = step_dict['step']
                new_dict = {'step': step_name, 
                            'args': []}
                self.candidate_format[f'{pipe_name}_pipeline'].append(new_dict)

                try: 
                    for key, value in step_dict['args'][0].items():
                        item = [pipe_name, step_name, key, value]
                        df.loc[table_idx] = item

                        new_dict2 = {
                            'name': key,
                            'description': '',
                            'type': '',
                        }
                        self.candidate_format[f'{pipe_name}_pipeline'][step_idx]['args'].append(new_dict2)
                        table_idx += 1
                except:
                    self.candidate_format[f'{pipe_name}_pipeline'][step_idx]['args'].append({})
                    table_idx += 1
                step_idx += 1

        ## 길이 제한
        # 'text' 컬럼 값을 미리 10글자로 제한
        MAX_LEN = 40
        df['value'] = df['value'].astype(str)
        df['value'] = df['value'].apply(lambda x: x[:MAX_LEN] + '...' if len(x) > MAX_LEN else x)

        if display_table:
            print_color(df.to_markdown(tablefmt='fancy_grid'), color='cyan')

        return self.candidate_format
    
    #####################################
    ##### For Debug 
    #####################################
    def register_solution_instance(self): 

        self.print_step("Register AI solution instance")

        if os.path.exists(REGISTER_INTERFACE_PATH + self.solution_instance_file):
            path = REGISTER_INTERFACE_PATH + self.solution_instance_file
            print(f'[SYSTEM] AI solution instance 가 등록되어 있어 과정을 생략합니다. (등록정보: {path})')
            return 
        else:
            path = REGISTER_INTERFACE_PATH + self.solution_file
            msg = f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다."
            load_response = self._load_response_yaml(path, msg)

        ########################
        ### instance name      -- spec 변경 시, 수정 필요 (fix date: 24.02.23)
        name = load_response['name'] + \
            "-" + f'v{load_response["versions"][0]["version"]}'
        ########################


        self.solution_instance_params = {
            "workspace_name": load_response['scope_ws']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.solution_instance_params}", color='blue')

        # solution_metadata 를 읽어서 json 화 
        with open(SOLUTION_META, 'r') as file:
            yaml_data = yaml.safe_load(file)
        data = {
            "name": name,
            "solution_version_id": load_response['versions'][0]['id'],  ## latest 만 봐야 하기 때문에 [0] 번째로 고정
            "metadata_json": yaml_data,
        }
        data =json.dumps(data) # json 화

        # solution instance 등록
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SOLUTION_INSTANCE"]
        response = requests.post(aic+api, 
                                 params=self.solution_instance_params, 
                                 data=data,
                                 cookies=self.aic_cookie)
        self.response_solution_instance = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] AI solution instance 등록을 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {self.response_solution_instance}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.solution_instance_file
            with open(path, 'w') as f:
              json.dump(self.response_solution_instance, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            raise ValueError("Error message: ", self.response_solution_instance["detail"])

        elif response.status_code == 422:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            raise ValueError("Error message: ", self.response_solution_instance["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')

    
    def register_stream(self): 

        self.print_step("Register AI solution stream")

        ## file load 한다. 
        if os.path.exists(REGISTER_INTERFACE_PATH + self.stream_file):
            path = REGISTER_INTERFACE_PATH + self.stream_file
            print(f'[SYSTEM] AI solution instance 가 등록되어 있어 과정을 생략합니다. (등록정보: {path})')
            return 
        else:
            path = REGISTER_INTERFACE_PATH + self.solution_instance_file
            msg = f"[SYSTEM] AI solution instance 등록 정보를 {path} 에서 확인합니다."
            load_response = self._load_response_yaml(path, msg)

        # stream 등록 
        params = {
            "workspace_name": load_response['workspace_name']
        }

        data = {
            "instance_id": load_response['id'],
            "name": load_response['name']  ## prefix name 이 instance 에서 추가 되었으므로 두번 하지 않음
        }
        data =json.dumps(data) # json 화

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAMS"]
        response = requests.post(aic+api, 
                                 params=params, 
                                 data=data,
                                 cookies=self.aic_cookie)
        self.response_stream = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream 등록을 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {self.response_stream}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.stream_file
            with open(path, 'w') as f:
              json.dump(self.response_stream, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] Stream 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_stream["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] Stream 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_stream["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')


    def request_run_stream(self): 

        self.print_step("Request AI solution stream run")


        ## stream file load 한다. 
        path = REGISTER_INTERFACE_PATH + self.stream_file
        msg = f"[SYSTEM] Stream 등록 정보를 {path} 에서 확인합니다."
        load_response = self._load_response_yaml(path, msg)

        # stream 등록 
        stream_params = {
            "stream_id": load_response['id'],
            "workspace_name": load_response['workspace_name']
        }
        pprint(stream_params)

        # solution_metadata 를 읽어서 json 화 
        with open(SOLUTION_META, 'r') as file:
            yaml_data = yaml.safe_load(file)
        data = {
            "metadata_json": yaml_data,
            "config_path": "" # FIXME config_path는 일단 뭐넣을지 몰라서 비워둠 
        }
        data =json.dumps(data) # json 화



        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAM_RUN"] + f"/{load_response['id']}"
        response = requests.post(aic+api, params=stream_params, data=data, cookies=self.aic_cookie)
        response_json = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream Run 요청을 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_json}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.stream_run_file
            with open(path, 'w') as f:
              json.dump(response_json, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] Stream Run 요청을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", response_json["detail"])
            raise ValueError("Error message: ", response_json["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] Stream Run 요청을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_json["detail"])
            raise ValueError("Error message: ", response_json["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise ValueError(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})")


    def get_stream_status(self, status_period):
        """ KUBEFLOW_STATUS 에서 지원하는 status 별 action 처리를 진행 함. 
            KUBEFLOW_STATUS = ("Pending", "Running", "Succeeded", "Skipped", "Failed", "Error")
            https://www.kubeflow.org/docs/components/pipelines/v2/reference/api/kubeflow-pipeline-api-spec/

          - Pending : docker container 가 실행되기 전 임을 알림.
          - Running : 실행 중 임을 알림.
          - Succeeded : 성공 상태 
          - Skipped : Entity has been skipped. For example, due to caching
          - STOPPED : 중지 상태 
          - FAILED : 실패 상태 

        """

        self.print_step("Get AI solution stream status")

        ## stream file load 한다. 
        path = REGISTER_INTERFACE_PATH + self.stream_run_file
        msg = f"[SYSTEM] Stream 실행 정보를 {path} 에서 확인합니다."
        load_response = self._load_response_yaml(path, msg)

        stream_history_params = {
            "stream_history_id": load_response['id'],
            "workspace_name": load_response['workspace_name']
        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAM_RUN"] + f"/{load_response['id']}/info"

        start_time = time.time()
        time_format = "%Y-%m-%d %H:%M:%S"
        start_time_str = time.strftime(time_format, time.localtime(start_time))
        while True: 
            time.sleep(status_period)

            response = requests.get(aic+api, 
                                    params=stream_history_params, 
                                    cookies=self.aic_cookie)
            self.response_stream_status = response.json()

            if response.status_code == 200:
                # print_color("[SUCCESS] Stream Status 요청을 성공하였습니다. ", color='cyan')
                # print(f"[INFO] response: \n {self.response_stream_status}")

                status = self.response_stream_status["status"]
                status = status.lower()
                if not status in KUBEFLOW_STATUS:
                    raise ValueError(f"[ERROR] 지원하지 않는 status 입니다. (status: {status})")

                end_time = time.time()
                elapsed_time = end_time - start_time
                elapsed_time_str = time.strftime(time_format, time.localtime(elapsed_time))
                ## KUBEFLOW_STATUS = ("Pending", "Running", "Succeeded", "Skipped", "Failed", "Error")
                if status == "succeeded":
                    print_color(f"[SUCCESS] (run_time: {elapsed_time_str}) Train pipeline (status:{status}) 정상적으로 실행 하였습니다. ", color='green')

                    # JSON 데이터를 파일에 저장
                    path = REGISTER_INTERFACE_PATH + self.stream_status_file
                    with open(path, 'w') as f:
                      json.dump(self.response_stream_status, f, indent=4)
                      print_color(f"[SYSTEM] status 확인 결과를 {path} 에 저장합니다.",  color='green')

                    return status 
                
                elif status == "failed":
                    print_color(f"[ERROR] (start: {start_time_str}, run: {elapsed_time_str}) Train pipeline (status:{status}) 실패 하였습니다. ", color='red')
                    return status 
                elif status == "pending":
                    print_color(f"[INFO] (start: {start_time_str}, run: {elapsed_time_str}) Train pipeline (status:{status}) 준비 중입니다. ", color='yellow')
                    continue
                elif status == "running":
                    print_color(f"[INFO] (start: {start_time_str}, run: {elapsed_time_str}) Train pipeline (status:{status}) 실행 중입니다. ", color='yellow')
                    continue
                elif status == "skipped":
                    print_color(f"[INFO] (start: {start_time_str}, run: {elapsed_time_str}) Train pipeline (status:{status}) 스킵 되었습니다. ", color='yellow')
                    return status 
                elif status == "error":
                    print_color(f"[ERROR] (start: {start_time_str}, run: {elapsed_time_str}) Train pipeline (status:{status}) 에러 발생 하였습니다. ", color='red')
                    return status 
                else:
                    raise ValueError(f"[ERROR] 지원하지 않는 status 입니다. (status: {status})")
                 
            elif response.status_code == 400:
                # print_color("[ERROR] Stream status 요청을 실패하였습니다. 잘못된 요청입니다. ", color='red')
                # print("Error message: ", self.response_stream_status["detail"])
                raise ValueError(f"[ERROR] Stream status 요청을 실패하였습니다. 잘못된 요청입니다. ")
            elif response.status_code == 422:
                print_color("[ERROR] Stream status 요청을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
                print("Error message: ", self.response_stream_status["detail"])
                raise ValueError(f"[ERROR] Stream status 요청을 실패하였습니다. 유효성 검사를 실패 하였습니다.")
            else:
                print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
                raise ValueError(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})")
            



    def download_artifacts(self): 

        self.print_step("Download train artifacts ")

        def split_s3_path(s3_path): #inner func.
            # 's3://'를 제거하고 '/'를 기준으로 첫 부분을 분리하여 bucket과 나머지 경로를 얻습니다.
            path_parts = s3_path.replace('s3://', '').split('/', 1)
            bucket = path_parts[0]
            rest_of_the_path = path_parts[1]
            return bucket, rest_of_the_path

        ## s3_client 생성
 
        if not self.aws_access_key:
            s3_client = boto3.client('s3',
                                aws_access_key_id=self.aws_access_key,
                                aws_secret_access_key=self.aws_secret_key,
                                region_name=self.infra_setup['REGION'])
        else:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            s3_client = boto3.client('s3', region_name=self.infra_setup['REGION'])


        try: 
            s3_bucket = split_s3_path(self.stream_history['train_artifact_uri'])[0]
            s3_prefix = split_s3_path(self.stream_history['train_artifact_uri'])[1]
            # S3 버킷에서 파일 목록 가져오기
            objects = s3_client.list_objects(Bucket=s3_bucket, Prefix=s3_prefix)
            # 파일 다운로드
            for obj in objects.get('Contents', []):
                key = obj['Key']
                filename = key.split('/')[-1]  # 파일 이름 추출
                s3_client.download_file(s3_bucket, key, filename)
                print_color(f'Downloaded: {filename}', color='cyan')
        except: 
            raise NotImplementedError("Failed to download train artifacts.")



    #####################################
    ######    Delete
    #####################################

    def delete_stream_history(self): 

        self.print_step("Delete stream history")

        ## file load 한다. 
        path = REGISTER_INTERFACE_PATH + self.stream_run_file
        msg = f"[SYSTEM] stream 등록 정보를 {path} 에서 확인합니다."
        load_response = self._load_response_yaml(path, msg)

        # stream 등록 
        stream_params = {
            "stream_history_id": load_response['id'],
            "workspace_name": load_response['workspace_name']
        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAMS"] + f"/{load_response['id']}"
        response = requests.delete(aic+api, 
                                 params=stream_params, 
                                 cookies=self.aic_cookie)
        response_delete_stream_history = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream history 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_stream_history}")

            ## 삭제 성공 시, path 파일 삭제
            if os.path.exists(path):
                os.remove(path)
                print(f'File removed successfully! (file: {path})')
            else:
                print(f'File does not exist! (file: {path})')

        elif response.status_code == 400:
            print_color("[WARNING] Stream history 삭제를 실패하였습니다. 잘못된 요청입니다. ", color='yellow')
            print("Error message: ", response_delete_stream_history["detail"])
            ## 실패하더라도 stream 삭제로 넘어가게 하기
        elif response.status_code == 422:
            print_color("[ERROR] Stream history 삭제를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_delete_stream_history["detail"])
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_stream_history}")
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_stream_history}")



    def delete_stream(self,solution_id=None): 

        self.print_step("Delete stream")

        if not solution_id:  ## id=none
            ## file load 한다. 
            path = REGISTER_INTERFACE_PATH + self.stream_file
            msg = f"[SYSTEM] stream 등록 정보를 {path} 에서 확인합니다."
            load_response = self._load_response_yaml(path, msg)

            params = {
                "stream_id": load_response['id'],
                "workspace_name": load_response['workspace_name']
            }
            api = self.api_uri["STREAMS"] + f"/{load_response['id']}"
        else:
            params = {
                "instance_id": solution_id,
                "workspace_name": self.infra_setup['WORKSPACE_NAME']
            }
            api = self.api_uri["STREAMS"] + f"/{solution_id}"
        # stream 등록 

        aic = self.infra_setup["AIC_URI"]
        response = requests.delete(aic+api, 
                                 params=params, 
                                 cookies=self.aic_cookie)
        response_delete_stream = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_stream}")

            if not solution_id:  ## id=none
                ## 삭제 성공 시, path 파일 삭제
                if os.path.exists(path):
                    os.remove(path)
                    print(f'File removed successfully! (file: {path})')
                else:
                    print(f'File does not exist! (file: {path})')

        elif response.status_code == 400:
            print_color("[ERROR] Stream 삭제를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", response_delete_stream["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] Stream 삭제를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_delete_stream["detail"])
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_stream}")
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_stream}")

    def delete_solution_instance(self, solution_id=None): 

        self.print_step("Delete AI solution instance")

        # stream 등록 
        if not solution_id:  ## id=none
            ## file load 한다. 
            path = REGISTER_INTERFACE_PATH + self.solution_instance_file
            msg = f"[SYSTEM] AI solution instance 등록 정보를 {path} 에서 확인합니다."
            load_response = self._load_response_yaml(path, msg)

            params = {
                "instance_id": load_response['id'],
                "workspace_name": load_response['workspace_name']
            }
            api = self.api_uri["SOLUTION_INSTANCE"] + f"/{load_response['id']}"
        else:
            params = {
                "instance_id": solution_id,
                "workspace_name": self.infra_setup['WORKSPACE_NAME']
            }
            api = self.api_uri["SOLUTION_INSTANCE"] + f"/{solution_id}"

        aic = self.infra_setup["AIC_URI"]
        response = requests.delete(aic+api, 
                                 params=params, 
                                 cookies=self.aic_cookie)
        response_delete_instance = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] AI solution instance 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_instance}")

            if not solution_id:  ## id=none
                ## 삭제 성공 시, path 파일 삭제
                if os.path.exists(path):
                    os.remove(path)
                    print(f'File removed successfully! (file: {path})')
                else:
                    print(f'File does not exist! (file: {path})')

        elif response.status_code == 400:
            print_color("[ERROR] AI solution insatnce 삭제를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", response_delete_instance["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI solution instance 삭제를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_delete_instance["detail"])
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_instance}")
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_instance}")

    def delete_solution(self, delete_all=False, solution_id=None): 

        self.print_step("Delete AI solution")


        if self.solution_info["solution_update"]:
            ## file load 한다. 
            path = REGISTER_INTERFACE_PATH + self.solution_file
            msg = f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다."
            load_response = self._load_response_yaml(path, msg)

            version_id = load_response['versions'][0]['id']
            params = {
                "solution_version_id": version_id,
                "workspace_name": load_response['scope_ws']
            }
            api = self.api_uri["REGISTER_SOLUTION"] + f"/{version_id}/version"
        else:
            if not solution_id:
                ## file load 한다. 
                path = REGISTER_INTERFACE_PATH + self.solution_file
                msg = f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다."
                load_response = self._load_response_yaml(path, msg)

                params = {
                    "solution_id": load_response['id'],
                    "workspace_name": load_response['scope_ws']
                }
                api = self.api_uri["REGISTER_SOLUTION"] + f"/{load_response['id']}"
            else:
                params = {
                    "solution_id": solution_id,
                    "workspace_name": self.infra_setup["WORKSPACE_NAME"]
                }
                api = self.api_uri["REGISTER_SOLUTION"] + f"/{solution_id}"
        aic = self.infra_setup["AIC_URI"]
        response = requests.delete(aic+api, 
                                 params=params, 
                                 cookies=self.aic_cookie)

        if response.status_code == 200:
            response_delete_solution = response.json()
            print_color("[SUCCESS] AI solution 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_solution}")

            if not solution_id:  ## id=none
                ## 삭제 성공 시, path 파일 삭제
                if os.path.exists(path):
                    os.remove(path)
                    print(f'File removed successfully! (file: {path})')
                else:
                    print(f'File does not exist! (file: {path})')


        elif response.status_code == 400:
            response_delete_solution = response.json()
            print_color("[ERROR] AI solution 삭제를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", response_delete_solution["detail"])
        elif response.status_code == 422:
            response_delete_solution = response.json()
            print_color("[ERROR] AI solution 삭제를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_delete_solution["detail"])
            raise NotImplementedError(f"Failed to delete solution: \n {response_delete_solution}")
        elif response.status_code == 500:
            print_color("[ERROR] AI solution 삭제를 실패하였습니다. 잘못된 요청입니다. ", color='red')
        else:
            response_delete_solution = response.json()
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise NotImplementedError(f"Failed to delete solution: \n {response_delete_solution}")

    #####################################
    ######    List Solution & Instance & Stream
    #####################################

    def list_stream(self): 

        self.print_step("List stream ")

        self.stream_params = {
            "workspace_name": self.infra_setup['WORKSPACE_NAME']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.stream_params}", color='blue')

        # solution instance 등록
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAMS"]
        response = requests.get(aic+api, 
                                 params=self.stream_params, 
                                 cookies=self.aic_cookie)
        self.stream_list = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] stream list 조회를 성공하였습니다. ", color='cyan')
            pprint("[INFO] response: ")
            for cnt, instance in enumerate(self.stream_list["streams"]):
                id = instance["id"]
                name = instance["name"]

                max_name_len = len(max(name, key=len))
                print(f"(idx: {cnt:{max_name_len}}), stream_name: {name:{max_name_len}}, stream_id: {id}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.stream_list_file
            with open(path, 'w') as f:
              json.dump(self.stream_list, f, indent=4)
              print_color(f"[SYSTEM] list 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] stream list 조회를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.stream_list["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] stream list 조회를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.stream_list["detail"])
        else:

            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')

    def list_stream_history(self, id=''): 

        self.print_step("List stream history")

        self.stream_run_params = {
            "stream_id": id,
            "workspace_name": self.infra_setup['WORKSPACE_NAME']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.stream_run_params}", color='blue')

        # solution instance 등록
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAM_RUN"]
        response = requests.get(aic+api, 
                                 params=self.stream_run_params, 
                                 cookies=self.aic_cookie)
        self.stream_history_list = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] AI solution instance 등록을 성공하였습니다. ", color='cyan')
            pprint("[INFO] response: ")
            for cnt, instance in enumerate(self.stream_history_list["stream_histories"]):
                id = instance["id"]
                name = instance["name"]

                max_name_len = len(max(name, key=len))
                print(f"(idx: {cnt:{max_name_len}}), history_name: {name:{max_name_len}}, history_id: {id}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.stream_history_list_file
            with open(path, 'w') as f:
              json.dump(self.stream_history_list, f, indent=4)
              print_color(f"[SYSTEM] list 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] stream history 조회를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.stream_history_list["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] stream history 조회를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.stream_history_list["detail"])
        else:

            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')

    def list_solution_instance(self): 

        self.print_step("Load AI solution instance list")

        self.solution_instance_params = {
            "workspace_name": self.infra_setup['WORKSPACE_NAME']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.solution_instance_params}", color='blue')

        # solution instance 등록
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SOLUTION_INSTANCE"]
        response = requests.get(aic+api, 
                                 params=self.solution_instance_params, 
                                 cookies=self.aic_cookie)
        self.response_instance_list = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] AI solution instance 등록을 성공하였습니다. ", color='cyan')
            pprint("[INFO] response: ")
            for cnt, instance in enumerate(self.response_instance_list["instances"]):
                id = instance["id"]
                name = instance["name"]

                max_name_len = len(max(name, key=len))
                print(f"(idx: {cnt:{max_name_len}}), instance_name: {name:{max_name_len}}, instance_id: {id}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.instance_list_file
            with open(path, 'w') as f:
              json.dump(self.response_instance_list, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_instance_list["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_instance_list["detail"])
        else:

            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')

    def list_solution(self): 

        self.print_step("Load AI solution instance list")

        params = {
            "workspace_name": self.infra_setup['WORKSPACE_NAME'],
            "with_pulic": 1, 
            "page_size": 100
        }
        print_color(f"\n[INFO] AI solution interface information: \n {params}", color='blue')

        # solution instance 등록
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SOLUTION_LIST"]
        response = requests.get(aic+api, 
                                 params=params, 
                                 cookies=self.aic_cookie)
        response_json = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] solution list 조회를 성공하였습니다. ", color='cyan')
            pprint("[INFO] response: ")
            for cnt, instance in enumerate(response_json["solutions"]):
                id = instance["id"]
                name = instance["name"]
                latest_version = instance["versions"][0]["version"]

                max_name_len = len(max(name, key=len))
                print(f"(idx: {cnt:{max_name_len}}), solution_name: {name:{max_name_len}}, solution_id: {id}, latest_version: {latest_version}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = REGISTER_INTERFACE_PATH + self.solution_list_file
            with open(path, 'w') as f:
              json.dump(response_json, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] solution list 조회를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", response_json["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] solution list 조회를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_json["detail"])
        else:

            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')


    #####################################
    ######    Internal Functions
    #####################################
    def _load_response_yaml(self, path, msg):
        try:
            with open(path) as f:
                data = json.load(f)
                print_color(msg, color='green')
            return data
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")


    def _init_solution_metadata(self):
        """ Solution Metadata 를 생성합니다. 

        """

        # 각 디렉토리를 반복하며 존재하면 삭제
        for dir_path in [REGISTER_ARTIFACT_PATH, REGISTER_SOURCE_PATH, REGISTER_INTERFACE_PATH]:
            if os.path.isdir(dir_path):
                print(f"Removing directory: {dir_path}")
                shutil.rmtree(dir_path, ignore_errors=False)
                print(f"Directory {dir_path} has been removed successfully.")
            else:
                print(f"Directory {dir_path} does not exist, no action taken.")



        if not type(self.infra_setup['VERSION']) == float:
            raise ValueError("solution_metadata 의 VERSION 은 float 타입이어야 합니다.")

        self.sm_yaml['metadata_version'] = self.infra_setup['VERSION']
        self.sm_yaml['name'] = self.solution_name
        self.sm_yaml['description'] = {}
        self.sm_yaml['pipeline'] = []
        # self.sm_yaml['pipeline'].append({'type': 'inference'})
        try: 
            self._save_yaml()
            if self.debugging:
                print_color(f"\n << solution_metadata.yaml >> generated. - current version: v{self.infra_setup['VERSION']}", color='green')
        except: 
            raise NotImplementedError("Failed to generate << solution_metadata.yaml >>")

    def _sm_append_pipeline(self, pipeline_name): 
        if not pipeline_name in ['train', 'inference']:
            raise ValueError(f"Invalid value ({pipeline_name}). Only one of 'train' or 'inference' is allowed as input.")
        self.sm_yaml['pipeline'].append({'type': pipeline_name})
        self.pipeline = pipeline_name # 가령 inference 파이프라인 추가 시 인스턴스의 pipeline을 inference 로 변경 
        self.sm_pipe_pointer += 1 # 파이프라인 포인터 증가 1
        try: 
            self._save_yaml()
        except: 
            raise NotImplementedError("Failed to update << solution_metadata.yaml >>")
    
    def _save_yaml(self):
        # YAML 파일로 데이터 저장
        class NoAliasDumper(Dumper):
            def ignore_aliases(self, data):
                return True
        with open('solution_metadata.yaml', 'w', encoding='utf-8') as yaml_file:
            yaml.dump(self.sm_yaml, yaml_file, allow_unicode=True, default_flow_style=False, Dumper=NoAliasDumper)


    def _set_alo(self):

        self.print_step("Set alo source code for docker container", sub_title=True)

        alo_src = ['main.py', 'src', 'assets', 'solution', 'alolib', '.git', 'requirements.txt', 'solution_requirements.txt']

        ## 폴더 초기화
        if os.path.isdir(REGISTER_SOURCE_PATH):
            shutil.rmtree(REGISTER_SOURCE_PATH)
        os.mkdir(REGISTER_SOURCE_PATH)

        ## 실행 할 상황 복사
        for item in alo_src:
            src_path = PROJECT_HOME + item
            if os.path.isfile(src_path):
                shutil.copy2(src_path, REGISTER_SOURCE_PATH)
                print_color(f'[INFO] copy from " {src_path} "  -->  " {REGISTER_SOURCE_PATH} " ', color='blue')
            elif os.path.isdir(src_path):
                dst_path = REGISTER_SOURCE_PATH  + os.path.basename(src_path)
                shutil.copytree(src_path, dst_path)
                print_color(f'[INFO] copy from " {src_path} "  -->  " {REGISTER_SOURCE_PATH} " ', color='blue')
    
    def _reset_alo_solution(self):
        """ select = all, train, inference 를 지원. experimental 에서 삭제할 사항 선택
        """
        shutil.copy2(EXP_PLAN, REGISTER_EXPPLAN)
        print_color(f'[INFO] copy from " {EXP_PLAN} " to "{REGISTER_EXPPLAN}" ', color='blue')

        ## Experimental_plan 에서 필수적으로 변경되어야 할 부분을 수정 합니다. 
        try:
            with open(REGISTER_EXPPLAN, 'r') as yaml_file:
                exp_plan_dict = yaml.safe_load(yaml_file)
        except FileNotFoundError:
            print(f'File {REGISTER_EXPPLAN} not found.')
     
        for idx, _dict in enumerate(exp_plan_dict['control']):
            if list(map(str, _dict.keys()))[0] == 'get_asset_source':
                if list(map(str, _dict.values()))[0] =='every':
                    exp_plan_dict['control'][idx]['get_asset_source'] = 'once'
            if list(map(str, _dict.keys()))[0] == 'get_external_data':
                if list(map(str, _dict.values()))[0] == 'once':
                    exp_plan_dict['control'][idx]['get_external_data'] = 'every'

        ## 선택한 사항 삭제
        if self.pipeline == 'train':
            delete_pipeline = 'inference'
        else:
            delete_pipeline = 'train'

        exp_plan_dict['user_parameters'] = [
            item for item in exp_plan_dict['user_parameters']
            if f'{delete_pipeline}_pipeline' not in item
        ]
        exp_plan_dict['asset_source'] = [
            item for item in exp_plan_dict['asset_source']
            if f'{delete_pipeline}_pipeline' not in item
        ]

        ## 다시 저장
        with open(REGISTER_EXPPLAN, 'w') as file:
            yaml.safe_dump(exp_plan_dict, file)

        print_color("[SUCCESS] Success ALO directory setting.", color='green')

    def _set_docker_contatiner(self):
        try: 
            ## Dockerfile 준비
            if self.pipeline == 'train':
                dockerfile = "TrainDockerfile"
            elif self.pipeline == 'inference':
                dockerfile = "InferenceDockerfile"
            else:
                raise ValueError(f"Invalid value ({self.pipeline}). Only one of 'train' or 'inference' is allowed as input.")
            if os.path.isfile(PROJECT_HOME + dockerfile):
                os.remove(PROJECT_HOME + dockerfile)
            shutil.copy(REGISTER_DOCKER_PATH + dockerfile, PROJECT_HOME)
            os.rename(PROJECT_HOME+dockerfile, PROJECT_HOME + 'Dockerfile')

            print_color(f"[SUCESS] set DOCKERFILE for ({self.pipeline}) pipeline", color='green')
        except Exception as e: 
            raise NotImplementedError(f"Failed DOCKERFILE setting. \n - pipeline: {self.pipeline} \n {e}")


    def _read_experimentalplan_yaml(self, yaml_file_path, type):
        try:
        # YAML 파일을 읽어옵니다.
            with open(yaml_file_path, 'r') as yaml_file:
                data = yaml.safe_load(yaml_file)


        # 파싱된 YAML 데이터를 사용합니다.
        except FileNotFoundError:
            print(f'File {yaml_file_path} not found.')
        
        if type == "experimental_plan" :
            self.exp_yaml = data
        elif type == "solution_metada":
            self.sm_yaml = data
        else:
            raise ValueError("Invalid type. Only 'experimental_plan' or 'solution_metadata' is allowed as input.")


    def _check_parammeter(self, param):
        if self._check_str(param):
            return param
        else:
            raise ValueError("You should enter only string value for parameter.")


    def _check_str(self, data):
        return isinstance(data, str)




#----------------------------------------#
#              Common Function           #
#----------------------------------------#
COLOR_RED = '\033[91m'
COLOR_END = '\033[0m'
ARG_NAME_MAX_LENGTH = 30
COLOR_DICT = {
   'PURPLE':'\033[95m',
   'CYAN':'\033[96m',
   'DARKCYAN':'\033[36m',
   'BLUE':'\033[94m',
   'GREEN':'\033[92m',
   'YELLOW':'\033[93m',
   'RED':'\033[91m',
   'BOLD':'\033[1m',
   'UNDERLINE':'\033[4m',
}
COLOR_END = '\033[0m'

def print_color(msg, color):
    """ Description
        -----------
            Display text with color 

        Parameters
        -----------
            msg (str) : text
            _color (str) : PURPLE, CYAN, DARKCYAN, BLUE, GREEN, YELLOW, RED, BOLD, UNDERLINE

        example
        -----------
            print_color('Display color text', 'BLUE')
    """
    if color.upper() in COLOR_DICT.keys():
        print(COLOR_DICT[color.upper()] + msg + COLOR_END)
    else:
        raise ValueError('[ERROR] print_color() function call error. - selected color : {}'.format(COLOR_DICT.keys()))
    
def _tar_dir(_path): 
    ## _path: .train_artifacts / .inference_artifacts     
    os.makedirs(REGISTER_ARTIFACT_PATH , exist_ok=True)
    os.makedirs(REGISTER_MODEL_PATH, exist_ok=True)
    last_dir = None
    if 'models' in _path: 
        _save_path = REGISTER_MODEL_PATH + 'model.tar.gz'
        last_dir = 'models/'
    else: 
        _save_file_name = _path.strip('.') 
        _save_path = REGISTER_ARTIFACT_PATH +  f'{_save_file_name}.tar.gz' 
        last_dir = _path # ex. .train_artifacts/

    tar = tarfile.open(_save_path, 'w:gz')
    for root, dirs, files in os.walk(PROJECT_HOME  + _path):
        base_dir = root.split(last_dir)[-1] + '/'
        for file_name in files:
            # print("SSH@@@@@@@@@@@", file_name, base_dir, file_name)
            #https://stackoverflow.com/questions/2239655/how-can-files-be-added-to-a-tarfile-with-python-without-adding-the-directory-hi
            tar.add(os.path.join(root, file_name), arcname = base_dir + file_name) # /home부터 시작하는 절대 경로가 아니라 .train_artifacts/ 혹은 moddels/부터 시작해서 압축해야하므로 
    tar.close()
    
    return _save_path

def is_float(string):
    try:
        float(string)
        return True 
    except ValueError:
        return False 

def is_int(string):
    try:
        int(string)
        return True 
    except ValueError:
        return False 

# FIXME bool check 어렵 (0이나 1로 입력하면?)
def is_bool(string):
    bool_list = ['True', 'False']
    if string in bool_list: 
        return True 
    else: 
        return False 
    
def is_str(string):
    return isinstance(string, str)

def split_comma(string):
    return [i.strip() for i in string.split(',')]

def convert_string(string_list: list): 
    # string list 내 string들을 float 혹은 int 타입일 경우 해당 타입으로 바꿔줌 
    output_list = [] 
    for string in string_list: 
        if is_int(string): 
            output_list.append(int(string))
        elif is_float(string):
            output_list.append(float(string))
        elif is_bool(string):
            # FIXME 주의: bool(string)이 아니라 eval(string) 으로 해야 정상 작동 
            output_list.append(eval(string)) 
        else: # 무조건 string 
            output_list.append(string)
    return output_list 


def convert_args_type(values: dict):
    '''
    << values smaple >> 
    
    {'name': 'num_hpo',
    'description': 'test3',
    'type': 'int',
    'default': '2',
    'range': '2,5'}
    '''
    output = deepcopy(values) # dict 
    
    arg_type = values['type']
    for k, v in values.items(): 
        if k in ['name', 'description', 'type']: 
            assert type(v) == str 
        elif k == 'selectable': # 전제: selectable은 2개이상 (ex. "1, 2")
            # single 이든 multi 이든 yaml 에 list 형태로 표현  
            assert type(v) == str 
            string_list = split_comma(v)
            assert len(string_list) > 1
            # FIXME 각각의 value들은 type이 제각기 다를 수 있으므로 완벽한 type check는 어려움 
            output[k] = convert_string(string_list) 
        elif k == 'default':
            # 주의: default 는 None이 될수도 있음 (혹은 사용자가 그냥 ""로 입력할 수도 있을듯)
            if (v == None) or (v==""): 
                output[k] = []
                ## FIXME string 일땐 [""] 로 해야하나? 
                if arg_type == 'string': 
                    output[k] = [""] # 주의: EdgeCondcutor UI 에서 null 이 아닌 공백으로 표기 원하면 None 이 아닌 ""로 올려줘야함 
                else: 
                    # FIXME 일단 single(multi)-selection, int, float 일땐 default value가 무조건 있어야 한다고 판단했음 
                    raise ValueError(f"Default value needed for arg. type: << {arg_type} >>")
            else:  
                # FIXME selection 일 때 float, str 같은거 섞여있으면..? 사용자가 1을 의도한건지 '1'을 의도한건지? 
                string_list = split_comma(v)
                if arg_type == 'single_selection': 
                    assert len(string_list) == 1
                elif arg_type == 'multi_selection':
                    assert len(string_list) > 1
                output[k] = convert_string(string_list) # list type     
        elif k == 'range':
            string_list = split_comma(v)
            assert len(string_list) == 2 # range 이므로 [처음, 끝] 2개 
            converted = convert_string(string_list)
            if (arg_type == 'string') or (arg_type == 'int'):
                for i in converted:
                    if not is_int(i): # string type 일 땐 글자 수 range 의미 
                        raise ValueError("<< range >> value must be int")
            elif arg_type == 'float':
                for i in converted:
                    if not is_float(i): # string 글자 수 range 의미 
                        raise ValueError("<< range >> value must be float")
            output[k] = converted 
            
    return output
        