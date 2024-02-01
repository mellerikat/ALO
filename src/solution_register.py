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

        self.api_uri = {
            'STATIC_LOGIN': 'api/v1/auth/static/login',  # POST
            'LDAP_LOGIN': 'api/v1/auth/ldap/login',
            'SYSTEM_INFO': 'api/v1/workspaces/info',  # GET, 1. 시스템 정보 획득
            'SOLUTION_LIST': 'api/v1/solutions/workspace', # 이름 설정 시 GET, 등록 시 POST, 2. AI Solution 이름 설정 / 3. AI Solution 등록
            'REGISTER_SOLUTION': 'api/v1/solutions', # 등록 시 POST, AI Solution 등록
            'SOLUTION_INSTANCE': 'api/v1/instances', # POST, AI Solution Instance 등록
            'STREAMS': 'api/v1/streams', # POST,  Stream 등록
            'STREAM_RUN': 'api/v1/streamhistories' # POST,  Stream 실행 
            }

        if not solution_info:
            raise ValueError("solution infomation 을 입력해야 합니다.")
        else:
            self.solution_info = solution_info

        ## TODO: 임시 (version 개발 전까지 ) 
        self.infra_setup["ECR_TAG"] = 'latest'

        ####################################
        ########### Configuration ##########
        ####################################

        # solution instance 등록을 위한 interface 폴더 
        self.sm_yaml_path_file = SOLUTION_META
        self.exp_yaml_path_file = EXP_PLAN
        self.wrangler_path_file = REGISTER_WRANGLER_PATH
        self.icon_path = REGISTER_ICON_PATH

        self.interface_path = REGISTER_INTERFACE_PATH


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

        ## name 
        self.prefix_name = "alo-test-"

        self.aws_access_key_path = self.infra_setup["AWS_KEY_FILE"]
        print_color(f"[SYSTEM] S3 key 파일을 로드 합니다. (file: {self.aws_access_key_path})", color="green")
        self.update_aws_credentials(self.aws_access_key_path)

        ## internal variables
        self.sm_yaml = {}  ## core
        self.exp_yaml = {} ## core
        self._read_experimentalplan_yaml(self.exp_yaml_path_file, type='experimental_plan')  ## set exp_yaml

        self.pipeline = None 
        self.aic_cookie = None
        self.solution_name = None
        self.icon_filenames = []
        self.sm_pipe_pointer = -1  ## 0 부터 시작
        self.resource_list = []

        self.bucket_name = None
        self.bucket_name_icon = None 
        self.ecr_name= None

        self.candidate_params = dict()
        self.candidate_params_df = pd.DataFrame()

        ## debugging 용 변수
        self.debugging = False 
        self.skip_generation_docker = False
            
    ################################################
    ################################################
    def update_aws_credentials(self, aws_access_key_path, profile_name='default'):
        """ AWS CLI 설정에 액세스 키와 비밀 키를 업데이트합니다. """
        try:
            f = open(aws_access_key_path, "r")
            keys = []
            values = []
            for line in f:
                key = line.split(":")[0]
                value = line.split(":")[1].rstrip()
                keys.append(key)
                values.append(value)
            access_key = values[0]
            secret_key = values[1]
        except:
            print_color("[SYSTEM] AWS 액세스 키 파일을 찾을 수 없습니다.", color="yellow")
            return False

        # AWS credentials 파일 경로
        aws_credentials_file_path = os.path.expanduser('~/.aws/credentials')

        # configparser 객체 생성 및 파일 읽기
        config = configparser.ConfigParser()
        config.read(aws_credentials_file_path)

        # 지정된 프로필에 자격 증명 설정
        if not config.has_section(profile_name):
            config.add_section(profile_name)
        config.set(profile_name, 'aws_access_key_id', access_key)
        config.set(profile_name, 'aws_secret_access_key', secret_key)

        # 변경사항 파일에 저장
        with open(aws_credentials_file_path, 'w') as configfile:
            config.write(configfile)
        
        print_color(f"[SYSTEM] AWS credentials 설정을 완료 하였습니다. (profile: {profile_name})", color="green")
        print(f"- access_key:{access_key}")
        print(f"- secret_key:{secret_key}")
    
    def run(self, username, password):

        #############################
        ###  Login 입력
        #############################
        self.login(username, password)

        #############################
        ###  Solution Name 입력
        #############################
        self.check_solution_name()

        self.load_system_resource()   ## ECR, S3 정보 받아오기
        self._init_solution_metadata()

        #############################
        ### description & wranlger 추가 
        #############################
        self.set_description()
        self.set_wrangler()

        #############################
        ### contents type 추가 
        #############################
        self.set_edge()

        #############################
        ### icon 설명
        #############################
        html_content = self.s3_upload_icon_display()  ## pre-define 된 icon 들 보여주기
        # display(HTML(html_content))  ##  icon 고정됨으로 spec 변경 됨으로 주석 처리 됨
        self.s3_upload_icon(name='ic_artificial_intelligence')

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
                self.make_docker_container()
        
        ############################
        ### Inference pipeline 설정
        ############################
        self._sm_append_pipeline(pipeline_name='inference')
        self.set_resource(resource='standard')  ## resource 선택은 spec-out 됨
        self.set_user_parameters(display_table=False)
        self.s3_upload_data()
        self.s3_upload_artifacts()  ## inference 시, upload model 도 진행
        if (not self.debugging) and (not self.skip_generation_docker):
            self.make_docker_container()

        if not self.debugging:
            self.register_solution()


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

    def delete_solution(self):
        self.delete_solution()




    def print_step(self, step_name):
        print_color("\n######################################################", color='blue')
        print_color(f'#######    {step_name}', color='blue')
        print_color("########################################################\n", color='blue')


    def login(self, id, pw): 
        # 로그인 (관련 self 변수들은 set_user_input 에서 setting 됨)

        self.print_step("Login to AI Conductor")

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
            print(f"[INFO] Login response: \n {response_login}")

            response_workspaces = []
            for ws in response_login["workspace"]:
                response_workspaces.append(ws["name"])
            pprint(f"해당 계정으로 접근 가능한 workspace list: {response_workspaces}")

            # TODO : case1~4 에 대해 사용자가 가이드 받을 수 있도록 하기 
            ## 로그인 접속은  계정 존재 / 권한 존재 의 경우로 나뉨
            ##   - case1: 계정 O / 권한 X 
            ##   - case2: 계정 O / 권한 single (ex cism-ws) 
            ##   - case3: 계정 O / 권한 multi (ex cism-ws, magna-ws) -- 권한은 workspace 단위로 부여 
            ##   - case4: 계정 X  ()
            if response_login['account_id']:
                if self.debugging:
                    print_color(f'[SYSTEM] Success getting cookie from AI Conductor:\n {self.aic_cookie}', color='green')
                    print_color(f'[SYSTEM] Success Login: {response_login}', color='green')
                if self.infra_setup["WORKSPACE_NAME"] in response_workspaces:
                    msg = f'[SYSTEM] 접근 요청하신 workspace ({self.infra_setup["WORKSPACE_NAME"]}) 은 해당 계정으로 접근 가능합니다.'
                    print_color(msg, color='green')
                else:
                    msg = f'[SYSTEM] 접근 요청하신 workspace ({self.infra_setup["WORKSPACE_NAME"]}) 은 해당 계정으로 접근 불가능 합니다.'
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
        만약, 동일 이름 존재하면 업데이트 모드로 전환하여 솔루션 업데이트를 실행한다. (TBD) 

        Attributes:
            - name (str): solution name

        Return:
            - solution_name (str): 내부 처리로 변경된 이름 
        """
        ## TODO : public, private 의 솔루션 이름은 별도로 관리 하는가? 
        self.print_step("Solution Name Creation")

        if not name:
            name = self.solution_info['solution_name']

        # 231207 임현수C: 사용자는 public 사용못하게 해달라 
        ONLY_PUBLIC = 1 #1 --> 1로 해야 public, private 다 받아옴 

        solution_data = {
            "workspace_name": self.infra_setup["WORKSPACE_NAME"], 
            "only_public": ONLY_PUBLIC,
            "page_size": 100
        }
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SOLUTION_LIST"]

        # print("data: ", solution_data)
        # print("cooki:", self.kaic_cookie)
        solution_name = requests.get(aic+api, params=solution_data, cookies=self.aic_cookie)
        print(solution_name)
        solution_name_json = solution_name.json()

        if 'solutions' in solution_name_json.keys(): 
            solution_list = [sol['name'] for sol in solution_name_json['solutions']]
            # 기존 solution 존재하면 에러 나게 하기 
            ## TODO: 업데이트가 되도록 하기 
            ## TODO: 특수기호가 사용되면 에러나게 하기
            if name in solution_list: 
                txt = f"[SYSTEM] The name ({name}) already exists in the AI solution list. Please enter another name !!"
                print_color(txt, color='red')
                raise ValueError("Not allowed solution name.")
            else:  ## NEW solutions
                txt = f"[SUCCESS] 입력하신 Solution Name ({name})은 사용 가능합니다. " 
                self.solution_name = name
                print_color(txt, color='green')

        else: 
            msg = f" 'solutions' key not found in AI Solution data. API_URI={aic+api}"
            raise ValueError(msg)

        msg = f"[SYSTEM] Solution Name List (in-use):"
        print_color(msg, color='green')
        # 이미 존재하는 solutino list 리스트업 
        pre_existences = pd.DataFrame(solution_list, columns=["AI solutions"])
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
        description['title'] = self.solution_info['solution_name']  ## name 을 title default 로 설정함

        try: 
            self.sm_yaml['description'].update(description)
            self.sm_yaml['description']['title'] = description['title'].replace(" ", "-")
            self._save_yaml()

            print_color(f"[SUCCESS] Update solution_metadata.yaml.", color='green')
            print(f"description: {self.sm_yaml['description']}")
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << description >> in the solution_metadata.yaml \n{e}")


    def set_wrangler(self):
        """wrangler.py 를 solution_metadata 의 code-to-string 으로 반영합니다. 
        ./wrangler/wrangler.py 만 지원 합니다. 

        """

        self.print_step("Set Wrangler")


        try: 
            with open(self.wrangler_path_file, 'r') as file:
                python_content = file.read()

            self.sm_yaml['wrangler_code_uri'] = python_content
            self.sm_yaml['wrangler_dataset_uri'] = ''
            self._save_yaml()
        except:
            msg = f"[WARNING] wrangler.py 가 해당 위치에 존재해야 합니다. (path: {self.wrangler_path_file})"
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

        self.print_step("Set Contents Type (for retrain & relabeling)")
        
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
        version = str(int(self.infra_setup['VERSION']))
        if mode == "artifact":
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{version}/" + self.pipeline  + "/artifacts/"
            uri = {'artifact_uri': "s3://" + self.bucket_name + "/" + prefix_uri}
        elif mode == "data":
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{version}/" + self.pipeline  + "/data/"
            if len(data_paths) ==0 :
                uri = {'dataset_uri': ["s3://" + self.bucket_name + "/" + prefix_uri]}
            else:
                uri = {'dataset_uri': []}
                data_path_base = "s3://" + self.bucket_name + "/" + prefix_uri
                for data_path_sub in data_paths:
                    uri['dataset_uri'].append(data_path_base + data_path_sub)

        elif mode == "model":  ## model
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{version}/" + 'train'  + "/artifacts/"
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

        self.print_step("Register AI solution")

        try: 
            # 등록을 위한 형태 변경
            data = {
            "scope_ws": self.infra_setup["WORKSPACE_NAME"],
            "metadata_json": self.sm_yaml
            }
            data =json.dumps(data)
            solution_params = {
                "workspace_name": self.infra_setup["WORKSPACE_NAME"]

            }
            # AI 솔루션 등록
            aic = self.infra_setup["AIC_URI"]
            api = self.api_uri["REGISTER_SOLUTION"]
            response = requests.post(aic+api, params=solution_params, data=data, cookies=self.aic_cookie)
            self.response_solution = response.json()
        except Exception as e: 
            raise NotImplementedError(f"Failed to register AI solution: \n {e}")

        if response.status_code == 200:
            print_color("[SUCCESS] AI Solution 등록을 성공하였습니다. ", color='cyan')
            print(f"[INFO] AI solution register response: \n {self.response_solution}")

            # interface 용 폴더 생성.
            try:
                if os.path.exists(self.interface_path):
                    shutil.rmtree(self.interface_path)
                os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory while registering solution instance: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.solution_file
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
    

    

    ################################
    ######    STEP2. S3 Control
    ################################

    
            
    def s3_upload_icon_display(self):
        """ 가지고 있는 icon 들을 디스플레이하고 파일명을 선택하게 한다. 
        """
        self.print_step("Display icon list")

        # 폴더 내의 모든 SVG 파일을 리스트로 가져오기
        svg_files = [os.path.join(self.icon_path, file) for file in os.listdir(self.icon_path) if file.endswith('.svg')]

        # HTML과 CSS를 사용하여 SVG 파일과 파일명을 그리드 형태로 표시
        html_content = '<div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px;">'
        icon_filenames = []
        for file in svg_files:
            file_name = os.path.basename(file)  # 파일 이름만 추출
            file_name = file_name.replace(f"{self.icon_path}/", "")
            icon_filenames.append(file_name)
            file_name = file_name.replace(f".svg", "")
            html_content += f'''<div>
                                    <img src="{file}" style="width: 100px; height: 100px;">
                                    <div style="word-wrap: break-word; word-break: break-all; width: 100px;">{file_name}</div>
                                </div>'''
        html_content += '</div>'

        self.icon_filenames = icon_filenames

        return html_content

    def s3_upload_icon(self, name):
        """ icon 업로드는 추후 제공 
        현재는 icon name 을 solution_metadata 에 업데이트 하는 것으로 마무리 
        """
        self.print_step("Upload icon")

        # 신규 icon 파일을 업로드 하는 경우 (추후 지원)
        # def s3_process(s3, bucket_name, data_path, s3_path):
        #     objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)
        #     print(objects_to_delete)
        #     if 'Contents' in objects_to_delete:
        #         for obj in objects_to_delete['Contents']:
        #             self.s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
        #             print_color(f'[INFO] Deleted pre-existing S3 object: {obj["Key"]}', color = 'yellow')
        #     s3.delete_object(Bucket=bucket_name, Key=s3_path)
        #     #s3.put_object(Bucket=bucket_name, Key=(s3_path +'/'))
        #     try:    
        #         response = s3.upload_file(data_path, bucket_name, s3_path)
        #     except NoCredentialsError as e:
        #         raise NoCredentialsError(f"NoCredentialsError: \n{e}")
        #     except ClientError as e:
        #         print(f"ClientError: ", e)
        #         return False
        #     print_color(f"Success uploading into S3 path: {bucket_name + '/' + s3_path}", color='green')
        #     return True
        # # FIXME hardcoding icon.png 솔루션 이름등으로 변경 필요 
        # data_path = f'./image/{self.ICON_FILE}'
        # s3_process(self.s3, self.bucket_name, data_path, s3_file_path)

        if not ".svg" in name:
            name = name+".svg"
        if name in self.icon_filenames:

            icon_s3_uri = "s3://" + self.bucket_name_icon + '/icons/' + name   # 값을 리스트로 감싸줍니다
            self.sm_yaml['description']['icon'] = icon_s3_uri
            self._save_yaml()

            print_color(f'[SUCCESS] update solution_metadata.yaml:', color='green')
            print(f'description: -icon: {icon_s3_uri} ')
        else:
            raise ValueError(f"[ERROR] Wrong icon name: {name}. \n(icon_list={self.icon_filenames}) ")
        
    def _s3_access_check(self):
        """ S3 에 접속 가능한지를 확인합니다.  s3_client instance 생성을 합니다.

        1) s3_access_key_path 가 존재하면, 파일에서 key 를 확인하고,
          - TODO file format 공유하기 (프로세스화)
        2) TODO aws configure가 설정되어 있으면 이를 자동으로 해석한다. 
        3) key 없이 권한 설정으로 접속 가능한지도 확인한다. 

        """
        self.print_step("Check to access S3")

        try:
            f = open(self.aws_access_key_path, "r")
            keys = []
            values = []
            for line in f:
                key = line.split(":")[0]
                value = line.split(":")[1].rstrip()
                keys.append(key)
                values.append(value)
            ACCESS_KEY = values[0]
            SECRET_KEY = values[1]
            self.s3_client = boto3.client('s3',
                                aws_access_key_id=ACCESS_KEY,
                                aws_secret_access_key=SECRET_KEY)
        except:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            self.s3_client = boto3.client('s3')

        # # FIXME 아래 region이 none으로 나옴 
        # my_session = boto3.session.Session()
        # self.region = my_session.region_name
        print(f"[INFO] AWS region: {self.infra_setup['REGION']}")
        if isinstance(boto3.client('s3'), botocore.client.BaseClient) == True:       
            print_color(f"[INFO] AWS S3 access check: OK", color="green")
        else: 
            raise ValueError(f"[ERROR] AWS S3 access check: Fail")

        return isinstance(boto3.client('s3'), botocore.client.BaseClient)

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
            version = str(int(self.infra_setup['VERSION']))
            train_artifacts_s3_path = s3_prefix_uri.replace(f'v{version}/inference', f'v{version}/train')
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

    def make_docker_container(self):
        """ECR 에 업로드 할 docker 를 제작 한다. 
        1) experimental_plan 에 사용된 source code 를 임시 폴더로 copy 한다. 
        2) Dockerfile 을 작성 한다. 
        3) Dockerfile 을 컴파일 한다. 
        4) 컴파일 된 도커 파일을 ECR 에 업로드 한다. 
        5) 컨테이너 uri 를 solution_metadata.yaml 에 저장 한다. 
        
        """

        self._set_alo()  # copy alo folders
        ##TODO : ARM/AMD 에 따라 다른 dockerfile 설정
        self._set_docker_contatiner()  ## set docerfile

        self.print_step("Set AWS ECR")
        if self.infra_setup["BUILD_METHOD"] == 'docker':
            ## docker login 실행 
            self._set_aws_ecr(docker=True)
        else:  ##buildah
            self._set_aws_ecr(docker=False, tags=self.infra_setup["REPOSITORY_TAGS"]) 

        self.print_step("Upload Docker Container")

        self._build_docker()
        self._docker_push()
        self._set_container_uri()


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
        try:
            f = open(self.aws_access_key_path, "r")
            keys = []
            values = []
            for line in f:
                key = line.split(":")[0]
                value = line.split(":")[1].rstrip()
                keys.append(key)
                values.append(value)
            ACCESS_KEY = values[0]
            SECRET_KEY = values[1]
            ecr_client = boto3.client('ecr',
                                aws_access_key_id=ACCESS_KEY,
                                aws_secret_access_key=SECRET_KEY,
                                region_name=self.infra_setup['REGION'])
        except:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            ecr_client = boto3.client('ecr')
        
        self.ecr_clinet = ecr_client


        ## Spec-out : 고객지수는 모든 ecr 를 불러 올 수 있는 권한이 없다. 
        # repos = ecr_client.describe_repositories(
        #     maxResults=600  ## 갯수가 작아서 찾지 못하는 Issue 있었음 (24.01)
        #     )
        # for repo in repos['repositories']:
        #     # print(repo['repositoryName'])
        #     if repo['repositoryName'] == self.ecr_repo:
        #         print_color(f"[SYSTEM] Repository {self.ecr_repo} already exists. Deleting...", color='yellow')
        #         ecr_client.delete_repository(repositoryName=self.ecr_repo, force=True)

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
                resp = ecr_client.create_repository(repositoryName=self.ecr_repo, tags=tags)
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
            subprocess.run(['docker', 'build', '.', '-t', f'{self.ecr_full_url}:{self.infra_setup["ECR_TAG"]}'])
        else:
            subprocess.run(['sudo', 'buildah', 'build', '--isolation', 'chroot', '-t', f'{self.ecr_full_url}:{self.infra_setup["ECR_TAG"]}'])


    def _docker_push(self):
        if self.infra_setup['BUILD_METHOD'] == 'docker':
            subprocess.run(['docker', 'push', f'{self.ecr_full_url}:{self.infra_setup["ECR_TAG"]}'])
        else:
            subprocess.run(['sudo', 'buildah', 'push', f'{self.ecr_full_url}:{self.infra_setup["ECR_TAG"]}'])

        if self.infra_setup['BUILD_METHOD'] == 'docker':
            subprocess.run(['docker', 'logout'])
        else:
            subprocess.run(['sudo', 'buildah', 'logout', '-a'])

    def _set_container_uri(self):
        try: 
            data = {'container_uri': self.ecr_full_url} # full url 는 tag 정보까지 포함 
            data = {'container_uri': self.ecr_full_url}
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

        self.candidate_params_df = df

        return self.candidate_format
    
    #####################################
    ##### For Debug 
    #####################################
    def get_contents(self, url):
        def _is_git_url(url):
            git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
            return re.match(git_url_pattern, url) is not None

        contents_path = "./contents"
        if(_is_git_url(url)):
        
            if os.path.exists(contents_path):
                shutil.rmtree(contents_path)  # 폴더 제거
            repo = git.Repo.clone_from(url, "./contents")


    # FIXME [임시] amd docker ecr 등록 실험용 
    def rename_docker(self, pre_existing_docker: str): 
        try: 
            if self.docker:
                subprocess.run(['docker', 'tag', pre_existing_docker, f'{self.ecr_full_url}:{self.ECR_TAG}'])
                print_color(f"[Success] done renaming docker: \n {pre_existing_docker} --> {self.ecr_full_url}:{self.ECR_TAG}", color='green')
            ## FIXME buildah도 tag 명령어 있는지? 
            # else:
            #     subprocess.run(['sudo', 'buildah', 'tag', pre_existing_docker, f'{self.ecr_full_url}:{self.ECR_TAG}'])
            
        except: 
            raise NotImplementedError("Failed to rename docker.")
        
    def register_solution_instance(self): 

        self.print_step("Register AI solution instance")

        ## file load 한다. 
        try:
            path = self.interface_path + self.solution_file
            with open(path) as f:
                response_solution = json.load(f)

            print_color(f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_solution)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

        self.solution_instance_params = {
            "workspace_name": response_solution['scope_ws']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.solution_instance_params}", color='blue')

        # solution_metadata 를 읽어서 json 화 
        with open(self.sm_yaml_path_file, 'r') as file:
            yaml_data = yaml.safe_load(file)
        data = {
            "name": self.prefix_name + response_solution['name'],
            "solution_version_id": response_solution['versions'][0]['id'],
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
                if not os.path.exists(self.interface_path):
                    os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.solution_instance_file
            with open(path, 'w') as f:
              json.dump(self.response_solution_instance, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_solution_instance["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_solution_instance["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')

    
    def register_stream(self): 

        self.print_step("Register AI solution stream")

        ## file load 한다. 
        try:
            path = self.interface_path + self.solution_instance_file
            with open(path) as f:
                response_solution_instance = json.load(f)

            print_color(f"[SYSTEM] AI solution instance 등록 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_solution_instance)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

        # stream 등록 
        stream_params = {
            "workspace_name": response_solution_instance['workspace_name']
        }

        data = {
            "instance_id": response_solution_instance['id'],
            "name": response_solution_instance['name']  ## prefix name 이 instance 에서 추가 되었으므로 두번 하지 않음
        }
        data =json.dumps(data) # json 화
        # pprint(stream_params)
        # pprint(data)

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAMS"]
        response = requests.post(aic+api, 
                                 params=stream_params, 
                                 data=data,
                                 cookies=self.aic_cookie)
        self.response_stream = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream 등록을 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {self.response_stream}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(self.interface_path):
                    os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.stream_file
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
        try:
            path = self.interface_path + self.stream_file
            with open(path) as f:
                response_stream = json.load(f)

            print_color(f"[SYSTEM] Stream 등록 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_stream)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")


        # stream 등록 
        stream_params = {
            "stream_id": response_stream['id'],
            "workspace_name": response_stream['workspace_name']
        }
        pprint(stream_params)

        # solution_metadata 를 읽어서 json 화 
        with open(self.sm_yaml_path_file, 'r') as file:
            yaml_data = yaml.safe_load(file)
        data = {
            "metadata_json": yaml_data,
            "config_path": "" # FIXME config_path는 일단 뭐넣을지 몰라서 비워둠 
        }
        data =json.dumps(data) # json 화



        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAM_RUN"] + f"/{response_stream['id']}"
        response = requests.post(aic+api, params=stream_params, data=data, cookies=self.aic_cookie)
        self.response_stream_run = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream Run 요청을 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {self.response_stream_run}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(self.interface_path):
                    os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.stream_run_file
            with open(path, 'w') as f:
              json.dump(self.response_stream_run, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] Stream Run 요청을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_stream_run["detail"])
            raise ValueError("Error message: ", self.response_stream_run["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] Stream Run 요청을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_stream_run["detail"])
            raise ValueError("Error message: ", self.response_stream_run["detail"])
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
        try:
            path = self.interface_path + self.stream_run_file
            with open(path) as f:
                response_stream_run = json.load(f)

            print_color(f"[SYSTEM] Stream 실행 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_stream_run)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

        stream_history_params = {
            "stream_history_id": response_stream_run['id'],
            "workspace_name": response_stream_run['workspace_name']
        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAM_RUN"] + f"/{response_stream_run['id']}/info"

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
                    path = self.interface_path + self.stream_status_file
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
        try:
            f = open(self.aws_access_key_path, "r")
            keys = []
            values = []
            for line in f:
                key = line.split(":")[0]
                value = line.split(":")[1].rstrip()
                keys.append(key)
                values.append(value)
            ACCESS_KEY = values[0]
            SECRET_KEY = values[1]
            s3_client = boto3.client('s3',
                                aws_access_key_id=ACCESS_KEY,
                                aws_secret_access_key=SECRET_KEY,
                                region_name=self.infra_setup['REGION'])
        except:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            s3_client = boto3.client('s3')


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
        try:
            path = self.interface_path + self.stream_run_file
            with open(path) as f:
                response_stream_run = json.load(f)

            print_color(f"[SYSTEM] Strema 등록 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_solution_instance)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

        # stream 등록 
        stream_params = {
            "stream_history_id": response_stream_run['id'],
            "workspace_name": response_stream_run['workspace_name']
        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAMS"] + f"/{response_stream_run['id']}"
        response = requests.delete(aic+api, 
                                 params=stream_params, 
                                 cookies=self.aic_cookie)
        response_delete_stream_history = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream history 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_stream_history}")

            # # interface 용 폴더 생성.
            # try:
            #     if not os.path.exists(self.interface_path):
            #         os.mkdir(self.interface_path)
            # except Exception as e:
            #     raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            # path = self.interface_path + self.stream_file
            # with open(path, 'w') as f:
            #   json.dump(response_delete_stream, f, indent=4)
            #   print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
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



    def delete_stream(self): 

        self.print_step("Delete stream")

        ## file load 한다. 
        try:
            path = self.interface_path + self.stream_file
            with open(path) as f:
                response_stream = json.load(f)

            print_color(f"[SYSTEM] Strema 등록 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_solution_instance)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

        # stream 등록 
        stream_params = {
            "stream_id": response_stream['id'],
            "workspace_name": response_stream['workspace_name']
        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAMS"] + f"/{response_stream['id']}"
        response = requests.delete(aic+api, 
                                 params=stream_params, 
                                 cookies=self.aic_cookie)
        response_delete_stream = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_stream}")

            # # interface 용 폴더 생성.
            # try:
            #     if not os.path.exists(self.interface_path):
            #         os.mkdir(self.interface_path)
            # except Exception as e:
            #     raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            # path = self.interface_path + self.stream_file
            # with open(path, 'w') as f:
            #   json.dump(response_delete_stream, f, indent=4)
            #   print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
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

    def delete_solution_instance(self): 

        self.print_step("Delete AI solution instance")

        ## file load 한다. 
        try:
            path = self.interface_path + self.solution_instance_file
            with open(path) as f:
                response_instance = json.load(f)

            print_color(f"[SYSTEM] AI solution instance 등록 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_solution_instance)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

        # stream 등록 
        stream_params = {
            "instance_id": response_instance['id'],
            "workspace_name": response_instance['workspace_name']
        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["SOLUTION_INSTANCE"] + f"/{response_instance['id']}"
        response = requests.delete(aic+api, 
                                 params=stream_params, 
                                 cookies=self.aic_cookie)
        response_delete_instance = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] AI solution instance 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_instance}")

            # # interface 용 폴더 생성.
            # try:
            #     if not os.path.exists(self.interface_path):
            #         os.mkdir(self.interface_path)
            # except Exception as e:
            #     raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            # path = self.interface_path + self.stream_file
            # with open(path, 'w') as f:
            #   json.dump(response_delete_instance, f, indent=4)
            #   print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
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

    def delete_solution(self): 

        self.print_step("Delete AI solution")

        ## file load 한다. 
        try:
            path = self.interface_path + self.solution_file
            with open(path) as f:
                response_solution = json.load(f)

            print_color(f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다.", color='green')
            # pprint(response_solution_instance)
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

        # stream 등록 
        solutin_params = {
            "solution_id": response_solution['id'],
            "workspace_name": response_solution['scope_ws']
        }

        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["REGISTER_SOLUTION"] + f"/{response_solution['id']}"
        response = requests.delete(aic+api, 
                                 params=solutin_params, 
                                 cookies=self.aic_cookie)
        response_delete_solution = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] AI solution 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_solution}")

            # # interface 용 폴더 생성.
            # try:
            #     if not os.path.exists(self.interface_path):
            #         os.mkdir(self.interface_path)
            # except Exception as e:
            #     raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            # path = self.interface_path + self.stream_file
            # with open(path, 'w') as f:
            #   json.dump(response_delete_solution, f, indent=4)
            #   print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] AI solution 삭제를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", response_delete_solution["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI solution 삭제를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_delete_solution["detail"])
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_solution}")
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_solution}")

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
                if not os.path.exists(self.interface_path):
                    os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.stream_list_file
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
                if not os.path.exists(self.interface_path):
                    os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.stream_history_list_file
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

        ## file load 한다. 
        # try:
        #     path = self.interface_path + self.solution_file
        #     with open(path) as f:
        #         response_solution = json.load(f)

        #     print_color(f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다.", color='green')
        #     # pprint(response_solution)
        # except:
        #     raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

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
                if not os.path.exists(self.interface_path):
                    os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.instance_list_file
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

        ## file load 한다. 
        # try:
        #     path = self.interface_path + self.solution_file
        #     with open(path) as f:
        #         response_solution = json.load(f)

        #     print_color(f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다.", color='green')
        #     # pprint(response_solution)
        # except:
        #     raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")

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

                max_name_len = len(max(name, key=len))
                print(f"(idx: {cnt:{max_name_len}}), solution_name: {name:{max_name_len}}, solution_id: {id}")

            # interface 용 폴더 생성.
            try:
                if not os.path.exists(self.interface_path):
                    os.mkdir(self.interface_path)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")

            # JSON 데이터를 파일에 저장
            path = self.interface_path + self.solution_list_file
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

    def _init_solution_metadata(self):
        """ Solution Metadata 를 생성합니다. 

        """

        if not type(self.infra_setup['VERSION']) == float:
            raise ValueError("solution_metadata 의 VERSION 은 float 타입이어야 합니다.")

        self.sm_yaml['version'] = self.infra_setup['VERSION']
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

        self.print_step("Set alo source code for docker container")

        alo_src = ['main.py', 'src', 'solution', 'assets', 'alolib', '.git', 'requirements.txt', 'solution_requirements.txt']

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
            

        ## Experimental_plan 에서 필수적으로 변경되어야 할 부분을 수정 합니다. 
        try:
            with open(REGISTER_EXPERIMENTAL_PLAN, 'r') as yaml_file:
                exp_plan_dict = yaml.safe_load(yaml_file)
        except FileNotFoundError:
            print(f'File {REGISTER_EXPERIMENTAL_PLAN} not found.')

        if exp_plan_dict['control'][0]['get_asset_source'] == 'every':
            exp_plan_dict['control'][0]['get_asset_source'] = 'once'
        with open(REGISTER_EXPERIMENTAL_PLAN, 'w') as file:
            yaml.safe_dump(self.exp_yaml, file)

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

            # ## root 로 copy 된 Dcokerfile 에서 train -> train, inference 로 변경 (Legacy 방식) 
            # spm = 'ENV SOLUTION_PIPELINE_MODE='
            # file_path = PROJECT_HOME + dockerfile
            # d_file = []
            # with open(file_path, 'r') as file:
            #     for line in file:
            #         if line.startswith(spm):
            #             if line.find(self.pipeline) > 0:
            #                 # 현재 파이프라인으로 구동
            #                 pass
            #             else:
            #                 # 다른 파이프라인으로 dockerfile을 수정 후 구동
            #                 line = line.replace('train', self.pipeline)
            #         d_file.append(line)
            # data = ''.join(d_file)
            # with open(file_path, 'w') as file:
            #     file.write(data)
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
        