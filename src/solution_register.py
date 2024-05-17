import boto3
import botocore
import docker
import io
import json
import os
import pyfiglet
import re
import requests
import shutil
import subprocess
import sys
import tarfile
import time
import yaml 
from copy import deepcopy 
from botocore.exceptions import ProfileNotFound, ClientError, NoCredentialsError
from docker.errors import APIError
from pprint import pprint
from yaml import Dumper
from src.constants import *
from src.utils import print_color

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
KUBEFLOW_STATUS = ("pending", "running", "succeeded", "skipped", "failed", "error")
#--------------------------------------------------------------------------------------------------------------------------

class SolutionRegister:
    ## class const. variables
    SOLUTION_FILE = '.response_solution.json'
    SOLUTION_INSTANCE_FILE = '.response_solution_instance.json'
    STREAM_FILE = '.response_stream.json'
    STREAM_RUN_FILE = '.response_stream_run.json'
    STREAM_STATUS_FILE = '.response_stream_status.json'
    STREAM_HISTORY_LIST_FILE = '.response_stream_history_list.json'
    STREAM_LIST_FILE = '.response_stream_list.json'
    INSTANCE_LIST_FILE = '.response_instance_list.json'
    SOLUTION_LIST_FILE = '.response_solution_list.json'
    
    def __init__(self, infra_setup=None, solution_info=None, experimental_plan=None):
        """ initialize info. for solution registration.
            If each arg. is a string, recognize it as a path, load the file, and convert it to a dictionary.

        Args: 
            - infra_setup (str or dict): infra setup yaml file info. 
            - solution_info (str or dict): solution info. user entered
            - experimental_plan (str or dict): experimental_plan yaml info.   
            
        Returns: -

        """
        self.print_step("Initiate ALO operation mode")
        print_color("[SYSTEM] Solutoin 등록에 필요한 setup file 들을 load 합니다. ", color="green")
        self.infra_setup = check_and_load_yaml(infra_setup, mode='infra_setup')
        self.solution_info = check_and_load_yaml(solution_info, mode='solution_info')
        self.exp_yaml = check_and_load_yaml(experimental_plan, mode='experimental_plan')
        print_color("[SYSTEM] infra_setup (max display: 5 line): ", color='green')
        pprint(self.infra_setup, depth=5)
        ## Setup AIConductor API
        file_name = SOURCE_HOME + 'config/ai_conductor_api.json'
        ## read json from file 
        with open(file_name, 'r') as file:
            data = json.load(file)
        self.api_uri = data['API']
        ## If the version is lower than the legacy version, change the API.
        self.api_uri_legacy_version = 1.5
        version = self.check_version()
        max_val = find_max_value(list(data.keys()))
        if version >max_val:
            version = max_val
        self.register_solution_api = data[f'{version}']['REGISTER_SOLUTION']
        self.register_solution_instance_api = data[f'{version}']['REGISTER_SOLUTION_INSTANCE']
        self.register_stream_api = data[f'{version}']['REGISTER_STREAM']
        self.request_run_stream_api = data[f'{version}']['REQUEST_RUN_STREAM']
        self.api_uri_legacy = {
            'STATIC_LOGIN': 'api/v1/auth/static/login',  
        }
        ## Configuration 
        self.sm_yaml = {}  
        self.pipeline = None 
        self.aic_cookie = None
        self.solution_name = None
        self.icon_filenames = []
        self.sm_pipe_pointer = -1  
        self.resource_list = []
        self.bucket_name = None
        self.bucket_name_icon = None 
        self.ecr_name= None
        self.solution_version_new = 1   
        ## used in solution update
        self.solution_version_id = None  
        ## for debugging 
        self.debugging = False 
        self.skip_generation_docker = False        
        make_art("Register AI Solution!!!")
        self._s3_access_check()

    def set_solution_settings(self):
        """ check solution name, load s3 / ecr info.

        Args: -
        
        Returns: -

        """
        self.login()
        self.check_solution_name()
        ## load s3, ecr info 
        self.load_system_resource()   

    def set_solution_metadata(self):
        """ initialize soluiton metadata 
        Args: -
        
        Returns: -

        """
        self.login()
        ## init solution metadata
        self._init_solution_metadata()
        self._set_alo()  
        self.set_description()
        ## FIXME icon out of spec
        self.select_icon(name='ic_artificial_intelligence')
        self.set_wrangler()
        self.set_edge()
    
    def run_pipeline(self, pipe):
        """ upload data to s3, docker push to ecr ..
        
        Args: 
            pipe    (str): pipeline name 
        
        Returns: 
            codebuild_client    (object): aws codebuild client 
            build_id            (str): codebuild id 

        """
        self.login()
        self._sm_append_pipeline(pipeline_name=pipe) 
        ## FIXME resource selection spec-out
        self.set_resource(resource='high')  
        ## solution metadata
        self.set_user_parameters() 
        ## aws s3 upload data, artifacts
        self.s3_upload_data() 
        self.s3_upload_artifacts()
        skip_build = (self.debugging or self.skip_generation_docker)
        codebuild_client, build_id = self.make_docker(skip_build)
        self.docker_push()
        self._set_container_uri()
        return codebuild_client, build_id

    def run(self):
        """ run solution registraion flow API 
        
        Args: -
        
        Returns: -

        """
        ## set solution name
        self.set_solution_settings()
        ## FIXME set description & wrangler (spec-out)
        self.set_solution_metadata()
        ## set resource list to upload 
        self.set_resource_list()
        ## run solution registration pipeline 
        pipelines = ["train", "inference"]
        codebuild_run_meta = {} 
        for pipe in pipelines:
            if self.solution_info['inference_only'] and pipe == 'train':
                continue
            codebuild_client, build_id = self.run_pipeline(pipe)
            codebuild_run_meta[pipe] = (codebuild_client, build_id)
        ## wait until codebuild finish for each pipeline 
        for pipe in codebuild_run_meta:
            if codebuild_run_meta[pipe][0] != None and codebuild_run_meta[pipe][1] != None: 
                self._batch_get_builds(codebuild_run_meta[pipe][0], codebuild_run_meta[pipe][1], status_period=20)
        if not self.debugging:
            ## Since it is before solution registration, code to delete the solution cannot be included.
            self.register_solution()
            ## Since it is before solution registration, code to delete the solution instance cannot be included.
            ## If registration fails, delete the solution.
            self.register_solution_instance()  

    def run_train(self, status_period=5, delete_solution=False):
        """ request running train docker in AI conductor infra
        
        Args: 
            status_period   (int): check train status period
            delete_solution (bool): whether to delete solution after train
        
        Returns: -

        """
        if self.solution_info['inference_only']:
            raise ValueError("학습 요청은 inference_only=False 일 때만 가능합니다.")
        else:
            try: 
                self.login()
                self.register_stream()
                self.register_solution_instance()
                self.request_run_stream()
                self.get_stream_status(status_period=status_period)
                ## artifacts download before stream deletion  
                self.download_artifacts()
                ## FIXME self.delete_stream_history() not called: if stream removed, history also removed
            finally: 
                ## Regardless of whether the training is successful or not, the stream is deleted anyway.
                self.delete_stream()
                if delete_solution:
                    self.delete_solution_instance()
                    self.delete_solution()

    def print_step(self, step_name, sub_title=False):
        """ print registration step info
        
        Args: 
            step_name   (str): registration step name 
            sub_title   (bool): whether to sub-title
        
        Returns: -

        """
        if not sub_title:
            print_color("\n######################################################", color='blue')
            print_color(f'#######    {step_name}', color='blue')
            print_color("######################################################\n", color='blue')
        else:
            print_color(f'\n#######  {step_name}', color='blue')

    def check_version(self):
        """ Check AIC version and convert API 
        
        Args: -
        
        Returns: 
            version (float): AIP version

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
        return version

    def login(self, id = None, pw = None): 
        """ login to AIC (get session).
            Login access is divided into cases where an account exists and where permissions exist.
            - case1: account O / authority X 
            - case2: accoun O / authority single (ex cism-ws) 
            - case3: accoun O / authority multi (ex cism-ws, magna-ws) - authority is depended on workspace 
            - case4: accoun X  ()
        
        Args: 
            id  (str): user entered id  
            pw  (str): user entered password
        
        Returns: -

        """
        self.print_step("Connect to AI Conductor..", sub_title=True)
        try:
            if id != None and pw != None:
                self.login_data = json.dumps({
                    "login_id": id,
                    "login_pw": pw
                })
        except Exception as e:
            print(e)
        try:
            if self.infra_setup["LOGIN_MODE"] == 'ldap':
                response = requests.post(self.infra_setup["AIC_URI"] + self.api_uri["LDAP_LOGIN"], data = self.login_data)
            else:
                response = requests.post(self.infra_setup["AIC_URI"] + self.api_uri["STATIC_LOGIN"], data = self.login_data)
        except Exception as e:
            print(e)
        response_login = response.json()
        cookies = response.cookies.get_dict()
        access_token = cookies.get('access-token', None)
        self.aic_cookie = {
        'access-token' : access_token 
        }
        if response.status_code == 200:
            print_color("[SUCCESS] login OK", color='cyan')
            ws_list = []
            for ws in response_login["workspace"]:
                ws_list.append(ws["name"])
            print(f"Workspace list: {ws_list}")
            if response_login['account_id']:
                if self.debugging:
                    print_color(f'[SYSTEM] Success getting cookie from AI Conductor:\n {self.aic_cookie}', color='green')
                    print_color(f'[SYSTEM] Success Login: {response_login}', color='green')
                if self.infra_setup["WORKSPACE_NAME"] in ws_list:
                    msg = f'[SYSTEM] 접근 요청하신 workspace ({self.infra_setup["WORKSPACE_NAME"]}) 은 해당 계정으로 접근 가능합니다.'
                    print_color(msg, color='green')
                else:
                    ws_name = self.infra_setup["WORKSPACE_NAME"]
                    msg = f'{ws_name} workspace는 해당 계정으로 접근 불가능 합니다.'
                    raise ValueError(msg)
            else: 
                print_color(f'\n>> Failed Login: {response_login}', color='red')   
        elif response.status_code == 401:
            print_color("[ERROR] login 실패. 잘못된 아이디 또는 비밀번호입니다.", color='red')
            if response_login['detail']['error_code'] == 'USER.LOGIN.000':
                pass
            if response_login['detail']['error_code'] == 'USER.LOGIN.001':
                if 'login_fail_count' in list(response_login['detail'].keys()):
                    count = response_login['detail']['login_fail_count']
                    print(f"Password를 오기입하셨습니다 {count} / 5 번 남았습니다.")
                else:
                    print(f"{id}를 오기입 하셨습니다") 
            if response_login['detail']['error_code'] == 'USER.LOGIN.002':
                if 'login_fail_count' in list(response_login['detail'].keys()):
                    if int(response_login['detail']['login_fail_count']) == 5:
                        print(f"5번 잘못 입력하셨습니다. 계정이 잠겼으니 관리자에게 문의 하세요.")
            if response_login['detail']['error_code'] == 'USER.LOGIN.003':
                if 'unused_period' in list(response_login['detail'].keys()):
                    up = response_login['detail']['unused_period']
                    print(f'{up} 만큼 접속하지 않으셔서 계정이 잠겼습니다.')
                    print(f'관리자에게 문의하세요.')
        elif response.status_code == 400:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_solution["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_solution["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
    
    def check_solution_name(self, name=None): 
        """ Check if the solution name the user intends to register is available for use. 
            If there is no duplicate name, it is recognized as a new solution. 
            If the same name exists, switch to update mode and execute a solution update.
        
        Args: 
            name (str): solution name
        
        Returns: -

        """
        self.print_step("Solution Name Creation")
        if not name:
            name = self.solution_info['solution_name']
        ## solution name rule 
        name = name
        ## check name length limit 100  
        if len(name.encode('utf-8')) > 100:
            raise ValueError("The solution name must be less than 50 bytes.")   
        ## only lower case, number allowed 
        pattern = re.compile('^[a-zA-Z0-9-]+$')
        if not pattern.match(name):
            raise ValueError("The solution name can only contain lowercase letters / dash / number (ex. my-solution-v0)")
        ## solution name uniqueness check 
        ## {only_public} - 1: public, private / 0: only workspace 
        solution_data = {
            "workspace_name": self.infra_setup["WORKSPACE_NAME"], 
            "only_public": 0,  
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
                ## solution update
                if self.solution_info['solution_update']:
                    if name == sol['name']: 
                        txt = f"[SUCCESS] The solution name ({name}) already exists and can be upgraded. " 
                        self.solution_name = name
                        ## latest check ([0])
                        self.solution_version_new = int(sol['versions'][0]['version']) + 1  
                        self.solution_version_id = sol['id']
                        print_color(txt, color='green')
        else: 
            msg = f"<< solutions >> key not found in AI Solution data. API_URI={aic+api}"
            raise ValueError(msg)
        ## handle update error
        if self.solution_info['solution_update']:
            if not name in solution_list:
                txt = f"[ERROR] if solution_update is True, the same solution name cannot exist.(name: {name})"
                print_color(txt, color='red')
                raise ValueError("Not found solution name.")
        ## handle new solution name 
        else:
            ## check pre-existence of name 
            if name in solution_list:
                txt = f"[SYSTEM] the solution name ({name}) already exists in the AI solution list. Please enter another name !!"
                print_color(txt, color='red')
                msg = f'[INFO] solution name list (workspace: {self.infra_setup["WORKSPACE_NAME"]}):'
                print(msg)
                raise ValueError("Not allowed solution name.")
            ## new solution name 
            else:  
                txt = f"[SUCCESS] the solution name ({name}) is available." 
                self.solution_name = name
                self.solution_version_new = 1
                self.solution_version_id = None
                print_color(txt, color='green')
        print_color('< Pre-existing AI Solutions >', color='cyan')
        for idx, sol in enumerate(solution_list): 
            print_color(f'{idx}. {sol}', color='cyan')

    def _get_alo_version(self):
        """ get alo version 
        
        Args: - 
        
        Returns: 
            __version__ (str): alo version 

        """
        with open(PROJECT_HOME + '.git/HEAD', 'r') as f:
            ref = f.readline().strip()
        ## Since the format of ref is 'ref: refs/heads/branch_name', only the last part is taken.
        if ref.startswith('ref:'):
            __version__ = ref.split('/')[-1]
        else:
            ## Detached HEAD state (commit hash instead of branch name)
            __version__ = ref  
        return __version__
    
    def set_description(self, description={}):
        """ insert solution description into solution metadata
        
        Args: 
            description (dict): solution description (title, overview ..)
        
        Returns: -

        """
        self.print_step("Set AI Solution Description")
        ##  Automatically fetch contents_name and contents_version from the experimental plan.
        def _add_descr_keys(d):
            required_keys = ['title', 'problem', 'data', 'key_feature', 'value', 'note_and_contact']

            for key in required_keys:
              if key not in d:
                d[key] = ""
        _add_descr_keys(description)
        ## title default: solution name  
        description['title'] = self.solution_name  
        description['contents_name'] = self.exp_yaml['name']
        description['contents_version'] = str(self.exp_yaml['version'])
        description['alo_version'] = self._get_alo_version()
        description['inference_build_type'] =  'arm64' if self.solution_info['inference_arm'] == True  else 'amd64'
        try: 
            self.sm_yaml['description'].update(description)
            self._save_yaml()

            print_color(f"[SUCCESS] Update solution_metadata.yaml.", color='green')
            print(f"description:")
            pprint(description)
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << description >> in the solution_metadata.yaml \n{str(e)}")

    def set_wrangler(self):
        ## FIXME wrangler spec-out 
        """ Reflect wrangler.py in the solution_metadata's code-to-string. 
            Only ./wrangler/wrangler.py is supported.
        
        Args: -
        
        Returns: -

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
        """ setup edge conductor, edge app related info to solution metadata 
        
        Args: 
            metadata_value (dict): edge related info from user
            
        Returns: -

        """
        self.print_step("Set Edge Condcutor & Edge App", sub_title=True)
        if len(metadata_value) == 0:
            metadata_value = self.solution_info['contents_type']
        ## check edgeconductor related keys 
        def _check_edgeconductor_interface(user_dict):
            check_keys = ['support_labeling', 'inference_result_datatype', 'train_datatype', 'labeling_column_name']
            allowed_datatypes = ['table', 'image']
            ## check wrong keys
            for k in user_dict.keys():
                self._check_parammeter(k)
                if k not in check_keys: 
                    raise ValueError(f"[ERROR] << {k} >> is not allowed for contents_type key. \
                                     (keys: support_labeling, inference_result_datatype, train_datatype) ")
            ## check necessary keys
            for k in check_keys:
                if k not in user_dict.keys(): 
                    raise ValueError(f"[ERROR] << {k} >> must be in the edgeconductor_interface key list.")
            ## check type and key existence 
            if isinstance(user_dict['support_labeling'], bool):
                pass
            else: 
                raise ValueError("[ERROR] << support_labeling >> parameter must have boolean type.")
            if user_dict['inference_result_datatype'] not in allowed_datatypes:
                raise ValueError(f"[ERROR] << inference_result_datatype >> parameter must have the value among these: \n{allowed_datatypes}")
            if user_dict['train_datatype'] not in allowed_datatypes:
                raise ValueError(f"[ERROR] << train_datatype >> parameter must have the value among these: \n{allowed_datatypes}")                  
        ## edgeconductor interface 
        _check_edgeconductor_interface(metadata_value)
        self.sm_yaml['edgeconductor_interface'] = metadata_value
        ## update edgeapp related info. 
        self.sm_yaml['edgeapp_interface'] = {'single_pipeline': self.check_single_pipeline(), 'redis_server_uri': "", 'redis_db_number': 0}
        self._save_yaml()
        msg = "[SUCCESS] contents_type 을 solution_metadata 에 성공적으로 업데이트 하였습니다."
        print_color(msg, color="green")
        print(f"edgeconductor_interfance: {metadata_value}")

    def set_resource_list(self):
        """ list up AIC train resource 
        
        Args: -
            
        Returns: -

        """
        self.print_step(f"Display {self.pipeline} Resource List")
        self.login()
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
            for spec in response_json["specs"]:
                resource_list.append(spec["name"])
        except: 
            raise ValueError("Got wrong workspace info.")
        print(f"{self.pipeline} Available resource list (type{resource_list}):")
        print_color(f"< Allowed Specs >", color='cyan')
        print(response_json["specs"])
        ## as self variable
        self.resource_list = resource_list
        return resource_list
        

    def set_resource(self, resource= ''):
        ## FIXME sepc-out ?
        """ Select the resources to be used for training in AI Conductor. 
            Allow the user to make the choice, providing abstract options like low, standard, high.
        
        Args: 
            resource (str): low, standard, high
            
        Returns: -

        """
        self.print_step(f"Set {self.pipeline} Resource")
        if len(self.resource_list) == 0: 
            msg = f"[ERROR] set_resource_list 함수를 먼저 실행 해야 합니다."
            raise ValueError(msg)
        ## erorr when input is empty 
        if resource == '':
            msg = f"[ERROR] 입력된 {self.pipeline}_resource 가 empty 입니다. Spec 을 선택해주세요. (type={self.resource_list})"
            raise ValueError(msg)
        if not resource in self.resource_list:
            msg = f"[ERROR] 입력된 {self.pipeline}_resource 가 '{resource}' 입니다. 미지원 값입니다. (type={self.resource_list})"
            raise ValueError(msg)
        self.sm_yaml['pipeline'][self.sm_pipe_pointer]["resource"] = {"default": resource}
        ## There is no scenario for selecting resources for inference. It is forcibly fixed to standard.
        if self.pipeline == "inference":
            self.sm_yaml['pipeline'][self.sm_pipe_pointer]["resource"] = {"default": 'standard'}
            resource = 'standard'
            msg = f"EdgeApp 에 대한 resource 설정은 현재 미지원 입니다. resource=standard 로 고정 됩니다."
            print_color(msg, color="yellow")
        print_color(f"[SUCCESS] Update solution_metadat.yaml:", color='green')
        print(f"pipeline[{self.sm_pipe_pointer}]: -resource: {resource}")
        self._save_yaml()

    def load_system_resource(self): 
        """ return available ecr, s3 uri 
        
        Args: -
            
        Returns: -

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
        ## workspace ecr, s3 info as self variables
        try:
            solution_type = self.solution_info["solution_type"]
            ## bucket_scope: private, public
            self.bucket_name = response_json["s3_bucket_name"][solution_type] 
            ## FIXME icon is only in public
            self.bucket_name_icon = response_json["s3_bucket_name"]["public"] 
            self.ecr_name = response_json["ecr_base_path"][solution_type]
        except Exception as e:
            raise ValueError(f"Wrong format of << workspaces >> received from REST API:\n {e}")
        ## debugging mode 
        if self.debugging:
            print_color(f"\n[INFO] S3_BUCUKET_URI:", color='green') 
            print_color(f'- public: {response_json["s3_bucket_name"]["public"]}', color='cyan') 
            print_color(f'- private: {response_json["s3_bucket_name"]["public"]}', color='cyan') 

            print_color(f"\n[INFO] ECR_URI:", color='green') 
            print_color(f'- public: {response_json["ecr_base_path"]["public"]}', color='cyan') 
            print_color(f'- private: {response_json["ecr_base_path"]["public"]}', color='cyan') 
        print_color(f"[SYSTEM] AWS ECR: \n {self.ecr_name}", color='green') 
        print_color(f"[SYSTEM] AWS S3 bucket: \n {self.bucket_name}", color='green') 
    
    def set_pipeline_uri(self, mode, data_paths = [], skip_update=False):
        """ If one of the dataset, artifacts, or model is selected, 
            generate the corresponding s3 uri and reflect this in the solution_metadata
        
        Args: 
            mode        (str): dataset, artifacts, model 
            data_paths  (list): data paths
            skip_update (bool): whether to skip solution update
            
        Returns: 
            prefix_uri (str): prefix uri 

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
        elif mode == "model":  
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{self.solution_version_new}/" + 'train'  + "/artifacts/"
            if not self.check_single_pipeline():
                uri = {'model_uri': "s3://" + self.bucket_name + "/" + prefix_uri}
            else: 
                uri = {'model_uri': None}
        else:
            raise ValueError("mode must be one of [data, artifact, model]")
        try: 
            if self.pipeline == 'train':
                if not self.sm_yaml['pipeline'][self.sm_pipe_pointer]['type'] == 'train':
                    raise ValueError("Setting << artifact_uri >> in the solution_metadata.yaml is only allowed for << train >> pipeline. \n - current pipeline: {self.pipeline}")
                ## model uri only in inference pipeine 
                if mode == "model":
                    raise ValueError("Setting << model_uri >> in the solution_metadata.yaml is only allowed for << inference >> pipeline. \n - current pipeline: {self.pipeline}")
            ## inference
            else: 
                if not self.sm_yaml['pipeline'][self.sm_pipe_pointer]['type'] == 'inference':
                    raise ValueError("Setting << artifact_uri >> in the solution_metadata.yaml is only allowed for << inference >> pipeline. \n - current pipeline: {self.pipeline}")
            if skip_update:
                pass
            else:
                self.sm_yaml['pipeline'][self.sm_pipe_pointer].update(uri)
                self._save_yaml()
                print_color(f'[SUCCESS] Update solution_metadata.yaml:', color='green')
                if mode == "artifact":
                    print(f'pipeline type: {self.pipeline}, artifact_uri: {uri} ')
                elif mode == "data":
                    print(f'pipeline type: {self.pipeline}, dataset_uri: {uri} ')
                ## model
                else: 
                    print(f'pipeline type:{self.pipeline}, model_uri: {uri} ')
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << artifact_uri >> in the solution_metadata.yaml \n{str(e)}")
        return prefix_uri
    
    def register_solution(self): 
        """ Differentiated into regular registration and solution update. 
            If solution_info["solution_update"] is True, proceed with the update process.
        
        Args: -
            
        Returns: -

        """
        self.print_step("Register AI solution")
        self.login()
        try: 
            ## change status for registration 
            self.register_solution_api["scope_ws"] = self.infra_setup["WORKSPACE_NAME"]
            self.register_solution_api["metadata_json"] = self.sm_yaml
            data =json.dumps(self.register_solution_api)
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
            ## register request
            response = requests.post(aic+api, params=solution_params, data=data, cookies=self.aic_cookie)
            self.response_solution = response.json()
        except Exception as e: 
            raise NotImplementedError(f"Failed to register AI solution: \n {str(e)}")
        if response.status_code == 200:
            print_color("[SUCCESS] AI Solution 등록을 성공하였습니다. ", color='cyan')
            print(f"[INFO] AI solution register response: \n {self.response_solution}")
            ## create interface directory
            try:
                if os.path.exists(REGISTER_INTERFACE_PATH):
                    shutil.rmtree(REGISTER_INTERFACE_PATH)
                os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory while registering solution instance: \n {str(e)}")
            ## json data file save 
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_FILE
            with open(path, 'w') as f:
              json.dump(response.json(), f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            raise ValueError("Error message: {}".format(self.response_solution["detail"]))
        elif response.status_code == 422:
            print_color("[ERROR] AI Solution 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다..", color='red')
            raise ValueError("Error message: {}".format(self.response_solution["detail"]))
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise ValueError("Error message: {}".format(self.response_solution["detail"]))
 
    def select_icon(self, name):
        # FIXME spec-out  
        """ select icon 
        
        Args: -
            
        Returns: -

        """
        if not ".svg" in name:
            name = name+".svg"
        icon_s3_uri = "s3://" + self.bucket_name_icon + '/icons/' + name  
        self.sm_yaml['description']['icon'] = icon_s3_uri
        self._save_yaml()
        
    def _s3_access_check(self):
        """ check aws s3 access, generate s3 client instance
        
        Args: -
            
        Returns: 
            access_check    (bool): s3 access availability

        """
        self.print_step("Check to access S3")
        print("**********************************")
        profile_name = self.infra_setup["AWS_KEY_PROFILE"]
        try:
            self.session = boto3.Session(profile_name=profile_name)
            self.s3_client = self.session.client('s3', region_name=self.infra_setup['REGION'])
        except ProfileNotFound:
            print_color(f"[WARNING] AWS profile {profile_name} not found. Create session and s3 client without aws profile.", color="yellow")
            self.session = boto3.Session()
            self.s3_client = boto3.client('s3', region_name=self.infra_setup['REGION'])
        except Exception:
            raise ValueError("The aws credentials are not available.")
        print_color(f"[INFO] AWS region: {self.infra_setup['REGION']}", color='blue')
        access_check = isinstance(boto3.client('s3', region_name=self.infra_setup['REGION']), botocore.client.BaseClient)
        if access_check == True:       
            print_color(f"[INFO] AWS S3 access check: OK", color="green")
        else: 
            raise ValueError(f"[ERROR] AWS S3 access check: Fail")
        return access_check

    def _s3_delete(self, s3, bucket_name, s3_path):
        """ delete s3 path 
        
        Args: 
            bucket_name (str): s3 bucket name
            s3_path     (str): s3 prefix path 
            
        Returns: -

        """
        try: 
            objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)
            if 'Contents' in objects_to_delete:
                for obj in objects_to_delete['Contents']:
                    self.s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                    print_color(f'[SYSTEM] Deleted pre-existing S3 object: {obj["Key"]}', color = 'yellow')
            s3.delete_object(Bucket=bucket_name, Key=s3_path)
        except: 
            raise NotImplementedError("Failed to s3 delete") 
            
    def _s3_update(self, s3, bucket_name, data_path, local_folder, s3_path):
        """ upload data to s3 path 
        
        Args: 
            bucket_name     (str): s3 bucket name
            data_path       (str): local data path 
            local_folder    (str): local data directory name
            s3_path         (str): s3 path tobe uploaded
            
        Returns: -

        """
        s3.put_object(Bucket=bucket_name, Key=(s3_path))
        try:    
            response = s3.upload_file(data_path, bucket_name, s3_path + data_path[len(local_folder):])
        except NoCredentialsError as e:
            raise NoCredentialsError(f"[NoCredentialsError] Failed to create s3 bucket and file upload: \n {str(e)}")
        except Exception as e:
            raise NotImplementedError(f"Failed to create s3 bucket and file upload: \n {str(e)}")
        uploaded_path = bucket_name + '/' + s3_path + data_path[len(local_folder):]
        print_color(f"[SUCCESS] update data to S3: \n", color='green')
        print(f"{uploaded_path}")
        return 

    def s3_upload_data(self):
        """ upload data file to s3  
        
        Args: -
        
        Returns: -

        """
        self.print_step(f"Upload {self.pipeline} data to S3")
        if "train" in self.pipeline:
            local_folder = INPUT_DATA_HOME + "train/"
            print_color(f'[SYSTEM] Start uploading data into S3 from local folder:\n {local_folder}', color='cyan')
            try: 
                ## update solution metadata 
                data_uri_list = []
                for item in os.listdir(local_folder):
                    sub_folder = os.path.join(local_folder, item)
                    if os.path.isdir(sub_folder):
                        data_uri_list.append(item+"/")
                s3_prefix_uri = self.set_pipeline_uri(mode="data", data_paths=data_uri_list)
                ## delete & upload data to S3
                self._s3_delete(self.s3_client, self.bucket_name, s3_prefix_uri) 
                for root, dirs, files in os.walk(local_folder):
                    for file in files:
                        data_path = os.path.join(root, file)
                        self._s3_update(self.s3_client, self.bucket_name, data_path, local_folder, s3_prefix_uri)
            except Exception as e: 
                raise NotImplementedError(f'[ERROR] Failed to upload local data into S3: \n {str(e)}') 
        elif "inference" in self.pipeline:
            local_folder = INPUT_DATA_HOME + "inference/"
            print_color(f'[INFO] Start uploading data into S3 from local folder:\n {local_folder}', color='cyan')
            try: 
                ## update solution metadata
                data_uri_list = []
                for item in os.listdir(local_folder):
                    sub_folder = os.path.join(local_folder, item)
                    if os.path.isdir(sub_folder):
                        data_uri_list.append(item+"/")
                s3_prefix_uri = self.set_pipeline_uri(mode="data", data_paths=data_uri_list)
                ## delete & upload data to S3
                self._s3_delete(self.s3_client, self.bucket_name, s3_prefix_uri) 
                for root, dirs, files in os.walk(local_folder):
                    for file in files:
                        data_path = os.path.join(root, file)
                        self._s3_update(self.s3_client, self.bucket_name, data_path, local_folder, s3_prefix_uri)
            except Exception as e: 
                raise NotImplementedError(f'[ERROR] Failed to upload local data into S3: \n {str(e)}') 
        else:
            raise ValueError(f"[ERROR] Not allowed value for << pipeline >>: {self.pipeline}")

    def s3_upload_stream_data(self, stream_id='stream_id', instance_id='insatsnce_id'):
        """ Upload the data existing in the input folder to s3 for streaming.
        
        Args: 
            stream_id   (str): stream id
            instance_id (str): instance id
        
        Returns: 
            uri (dict): dataset uri dict 

        """
        self.print_step(f"Upload {self.pipeline} data to S3")
        ## only upload train data 
        local_folder = INPUT_DATA_HOME + "train/"
        print_color(f'[SYSTEM] Start uploading data into S3 from local folder:\n {local_folder}', color='cyan')
        try:
            s3_prefix_uri = "streams/" + f"{stream_id}/{instance_id}/train/data/"
            ## delete & upload data to S3
            self._s3_delete(self.s3_client, self.bucket_name, s3_prefix_uri) 
            for root, dirs, files in os.walk(local_folder):
                for file in files:
                    data_path = os.path.join(root, file)
                    self._s3_update(self.s3_client, self.bucket_name, data_path, local_folder, s3_prefix_uri)
        except Exception as e: 
            raise NotImplementedError(f'[ERROR] Failed to upload local data into S3') 
        ## dict for updating solution metadata 
        data_paths = []
        for item in os.listdir(local_folder):
            sub_folder = os.path.join(local_folder, item)
            if os.path.isdir(sub_folder):
                data_paths.append(item+"/")
        if len(data_paths) ==0 :
            uri = {'dataset_uri': ["s3://" + self.bucket_name + "/" + s3_prefix_uri]}
        else:
            uri = {'dataset_uri': []}
            data_path_base = "s3://" + self.bucket_name + "/" +  s3_prefix_uri
            for data_path_sub in data_paths:
                uri['dataset_uri'].append(data_path_base + data_path_sub)
        return uri

    def s3_process(self, bucket_name, data_path, local_folder, s3_path, delete=True):
        """ delete and upload data to s3 
        
        Args: 
            bucket_name     (str): s3 bucket name
            data_path       (str): local data path 
            local_folder    (str): local data directory name
            s3_path         (str): s3 path tobe uploaded
            delete          (bool): whether to delete pre-existing data in s3
        
        Returns: -

        """
        if delete == True: 
            objects_to_delete = self.s3_client.list_objects(Bucket=bucket_name, Prefix=s3_path)
            if 'Contents' in objects_to_delete:
                for obj in objects_to_delete['Contents']:
                    self.s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                    print_color(f'[INFO] Deleted pre-existing S3 object:', color = 'yellow')
                    print(f'{obj["Key"]}')
            self.s3_client.delete_object(Bucket=bucket_name, Key=s3_path)
        self.s3_client.put_object(Bucket=bucket_name, Key=(s3_path +'/'))
        try:    
            response = self.s3_client.upload_file(data_path, bucket_name, s3_path + data_path[len(local_folder):])
        except NoCredentialsError as e:
            raise NoCredentialsError(f"[NoCredentialsError] Failed to upload file onto s3: \n {str(e)}")
        except Exception as e:
            raise NotImplementedError(f"Failed to upload file onto s3: \n {str(e)}")
        uploaded_path = bucket_name + '/' + s3_path + data_path[len(local_folder):]
        print_color(f"[SYSTEM] S3 object key (new): ", color='green')
        print(f"{uploaded_path }")
        return 

    def s3_upload_artifacts(self):
        """ upload artifacts to s3
        
        Args: -
        
        Returns: -

        """
        self.print_step(f"Upload {self.pipeline} artifacts to S3")
        try: 
            s3_prefix_uri = self.set_pipeline_uri(mode="artifact")
        except Exception as e: 
            raise NotImplementedError(f'Failed updating solution_metadata.yaml - << artifact_uri >> info / pipeline: {self.pipeline} \n{e}')
        if "train" in self.pipeline:
            ## local path of artifacts compressed file
            artifacts_path = _tar_dir("train_artifacts") 
            local_folder = os.path.split(artifacts_path)[0] + '/'
            print_color(f'[SYSTEM] Start uploading train artifacts into S3 from local folder:\n {local_folder}', color='cyan')
            self.s3_process(self.bucket_name, artifacts_path, local_folder, s3_prefix_uri) 
            shutil.rmtree(REGISTER_ARTIFACT_PATH , ignore_errors=True)
        elif "inference" in self.pipeline:
            ## upload inference artifacts  
            artifacts_path = _tar_dir("inference_artifacts")  
            local_folder = os.path.split(artifacts_path)[0] + '/'
            print_color(f'[INFO] Start uploading inference artifacts into S3 from local folder:\n {local_folder}', color='cyan')
            self.s3_process(self.bucket_name, artifacts_path, local_folder, s3_prefix_uri)
            shutil.rmtree(REGISTER_ARTIFACT_PATH , ignore_errors=True)
            ## upload model.tar.gz to s3 
            ## (Note) The {model_uri} should be placed under the inference type, \
            ## but the path should enter train instead of inference for the pipeline.
            if not self.check_single_pipeline():
                train_artifacts_s3_path = s3_prefix_uri.replace(f'v{self.solution_version_new}/inference', f'v{self.solution_version_new}/train')
                ## model tar.gz saved local path 
                model_path = _tar_dir("train_artifacts/models")
                local_folder = os.path.split(model_path)[0] + '/'
                print_color(f'\n[SYSTEM] Start uploading << model >> into S3 from local folder: \n {local_folder}', color='cyan')
                ## (Note) Since the train artifacts have already been uploaded to the same path, \
                ## do not delete the object when uploading model.tar.gz.
                self.s3_process(self.bucket_name, model_path, local_folder, train_artifacts_s3_path, delete=False) 
            ## model uri into solution metadata
            try: 
                ## None (null) if single pipeline  
                self.set_pipeline_uri(mode="model")
            except Exception as e: 
                raise NotImplementedError(f'[ERROR] Failed updating solution_metadata.yaml - << model_uri >> info / pipeline: {self.pipeline} \n{e}')
            finally:
                shutil.rmtree(REGISTER_MODEL_PATH, ignore_errors=True)
        else:
            raise ValueError(f"Not allowed value for << pipeline >>: {self.pipeline}")

    def make_docker(self, skip_build=False):
        """ Create a docker for upload to ECR.
            1. Copy the source code used in the experimental_plan to a temporary folder.
            2. Write the Dockerfile.
            3. Compile the Dockerfile.
            4. Upload the compiled docker file to ECR.
            5. Save the container URI to solution_metadata.yaml.
        
        Args: 
            skip_build  (bool): whether to skip docker build
        
        Returns: -

        """
        assert self.infra_setup['BUILD_METHOD'] in ['docker', 'buildah', 'codebuild']
        if not skip_build:
            is_remote = (self.infra_setup['BUILD_METHOD'] == 'codebuild')
            is_docker = (self.infra_setup['BUILD_METHOD'] == 'docker')
            if not is_remote: 
                builder = "Docker" if is_docker else "Buildah"
            else: 
                builder = "AWS Codebuild"
            ## copy alo folders
            self._reset_alo_solution()  
            ## set docerfile
            self._set_dockerfile()  
            ## set aws ecr 
            self.print_step("Start setting AWS ECR")
            self._set_aws_ecr()
            if not is_remote: 
                self._ecr_login(is_docker=is_docker)
                self.print_step("Create ECR Repository", sub_title=True)
                self._create_ecr_repository(self.infra_setup["REPOSITORY_TAGS"])
            else: 
                pass 
            ## build docker image 
            self.print_step(f"Build {builder} image", sub_title=True)
            if is_remote:
                try: 
                    ## remote docker build & ecr push 
                    codebuild_client, build_id = self._aws_codebuild() 
                except Exception as e: 
                    raise NotImplementedError(str(e))
            else: 
                start = time.time()
                self._build_docker(is_docker=is_docker)
                end = time.time()
                print(f"{builder} build time : {end - start:.5f} sec")
        else:
            self._set_aws_ecr_skipbuild()
        if self.infra_setup["BUILD_METHOD"] == "codebuild": 
            return codebuild_client, build_id
        else: 
            return None, None

    def _set_aws_ecr_skipbuild(self):
        """ set aws ecr when skipbuild is true
        
        Args: - 
        
        Returns: -

        """
        self.ecr_url = self.ecr_name.split("/")[0]
        ## FIXME docker image name is same as solution name  
        ## {name}-ws --> {name}
        ecr_scope = self.infra_setup["WORKSPACE_NAME"].split('-')[0] 
        self.ecr_repo = self.ecr_name.split("/")[1] + '/' + ecr_scope + "/ai-solutions/" + self.solution_name + "/" + self.pipeline + "/"  + self.solution_name  
        self.ecr_full_url = self.ecr_url + '/' + self.ecr_repo 
        print_color(f"[SYSTEM] Target AWS ECR repository: \n {self.ecr_repo}", color='cyan')

    def _set_aws_ecr(self):
        """ set aws ecr 
        
        Args: - 
        
        Returns: -

        """
        self.ecr_url = self.ecr_name.split("/")[0]
        ## {name}-ws --> {name}
        ecr_scope = self.infra_setup["WORKSPACE_NAME"].split('-')[0] 
        self.ecr_repo = self.ecr_name.split("/")[1] + '/' + ecr_scope + "/ai-solutions/" + self.solution_name + "/" + self.pipeline + "/"  + self.solution_name  
        self.ecr_full_url = self.ecr_url + '/' + self.ecr_repo 
        ## get ecr client 
        try: 
            try:
                self.ecr_client = self.session.client('ecr',region_name=self.infra_setup['REGION'])
            except:
                print_color(f"[WARNING] ecr client creation with session failed. Start creating ecr client from boto3", color="yellow")
                self.ecr_client = boto3.client('ecr', region_name=self.infra_setup['REGION'])
        except Exception as e:
            raise ValueError(f"Failed to create ecr client. \n {str(e)}")
        ## if same ecr named exists, delete and re-create 
        ## During a solution update, only the own version should be deleted - deleting the entire repo would make the cache feature unusable.
        if self.solution_info['solution_update'] == False:
            try:
                self.ecr_client.delete_repository(repositoryName=self.ecr_repo, force=True)
                print_color(f"[SYSTEM] Repository {self.ecr_repo} already exists. Deleting...", color='yellow')
            except Exception as e:
                print_color(f"[WARNING] Failed to delete pre-existing ECR Repository. \n {str(e)}", color='yellow')
        else: 
            try:
                print_color(f"Now in solution update mode. Only delete current version docker image.", color='yellow')
                resp_ecr_image_list = self.ecr_client.list_images(repositoryName=self.ecr_repo)
                print(resp_ecr_image_list)
                cur_ver_image = []
                for image in resp_ecr_image_list['imageIds']:
                    if 'imageTag' in image.keys():
                        if image['imageTag'] == f'v{self.solution_version_new}':
                            cur_ver_image.append(image)
                ## In fact, during a solution update, there will likely be almost no already-created current version images.
                if len(cur_ver_image) != 0: 
                    resp_delete_cur_ver = self.ecr_client.batch_delete_image(repositoryName=self.ecr_repo, imageIds=cur_ver_image)
            except Exception as e:
                raise NotImplementedError(f'Failed to delete current versioned image \n {str(e)}') 
        print_color(f"[SYSTEM] target AWS ECR url: \n {self.ecr_full_url}", color='blue')
    
    def buildah_login(self, password):
        """ buildah login
        
        Args: 
            password    (str): aws configure password
        
        Returns: -

        """
        login_command = [
            'sudo', 'buildah', 'login',
            '--username', 'AWS',
            '--password-stdin',
            self.ecr_url
        ]
        try:
            p1 = subprocess.Popen(['echo', password], stdout=subprocess.PIPE)
            p2 = subprocess.Popen(login_command, stdin=p1.stdout, stdout=subprocess.PIPE)
            ## Allow p1 to receive a SIGPIPE if p2 exits
            p1.stdout.close()  
            output, _ = p2.communicate()
            if p2.returncode != 0:
                raise RuntimeError(output.decode('utf-8'))
            print(f"Successfully logged in to {self.ecr_url} with Buildah")
        except subprocess.CalledProcessError as e:
            print(f"An error occurred during Buildah login: {e.output.decode('utf-8')}")
        except RuntimeError as e:
            print(e)
    
    def get_user_password(self):
        """ get user and aws password 
        
        Args: -
        
        Returns: 
            user        (str): user 
            password    (str): password

        """
        try:
            ecr_client = self.session.client('ecr', region_name=self.infra_setup['REGION'])
            response = ecr_client.get_authorization_token()
            auth_data = response['authorizationData'][0]
            token = auth_data['authorizationToken']
            import base64
            user, password = base64.b64decode(token).decode('utf-8').split(':')
        except ClientError as e:
            print(f"An error occurred: {e}")
            return None
        return user, password
    
    def _ecr_login(self, is_docker):
        """ aws ecr login
        
        Args:
            is_docker   (bool): whether it is docker or buildah
        
        Returns: -

        """
        builder = "Docker" if is_docker else "Buildah"
        user, password = self.get_user_password()
        if is_docker:
            self.docker_client = docker.from_env(version='1.24')
            if not self.docker_client.ping():
                raise ValueError("Docker 연결을 실패 했습니다")
            try:
                ## aws ecr login
                login_results = self.docker_client.login(username=user, password=password, registry=self.ecr_url, reauth=True)
                print('login_results {}'.format(login_results))
                print(f"Successfully logged in to {self.ecr_url}")
            except APIError as e:
                print(f"An error occurred during {builder} login: {e}")
        else:
            self.buildah_login(password)
        print_color(f"[SYSTEM] AWS ECR | {builder} login result:", color='cyan')

    def _parse_tags(self, tags):
        """ parse tag string into dictionary list 
        
        Args:
            tags   (list): tags dictionary list 
        
        Returns: 
            parsed_tags (list): key, value parsed dictionary list 

        """
        parsed_tags = []
        for tag in tags:
            key, value = tag.split(',')
            tag_dict = {
                'Key': key.split('=')[1],
                'Value': value.split('=')[1]
            }
            parsed_tags.append(tag_dict)
        return parsed_tags
    
    def _create_ecr_repository(self, tags):
        """ create ecr repository 
        
        Args:
            tags   (list): tags dictionary list 
        
        Returns: -

        """
        if self.solution_info['solution_update'] == False:
            try:
                create_resp = self.ecr_client.create_repository(repositoryName=self.ecr_repo)
                repository_arn = create_resp.get('repository', {}).get('repositoryArn')
                ## parse tags 
                tags_new = self._parse_tags(tags)
                resp = self.ecr_client.tag_resource(resourceArn=repository_arn, tags=tags_new)
                print_color(f"[SYSTEM] AWS ECR create-repository response: ", color='cyan')
                print(f"{resp}")
            except Exception as e:
                raise NotImplementedError(f"Failed to AWS ECR create-repository:\n + {e}")

    def _aws_codebuild(self):
        """ run aws codebuild for remote docker build & push  
        
        Args: -
        
        Returns: 
            codebuild_client    (object): aws codebuild client
            build_id            (str): codebuild id 

        """
        ## 0. create boto3 session and get codebuild service role arn 
        session = boto3.Session(profile_name=self.infra_setup["AWS_KEY_PROFILE"])
        try: 
            iam_client = session.client('iam', region_name=self.infra_setup["REGION"])
            codebuild_role = iam_client.get_role(RoleName = 'CodeBuildServiceRole')['Role']['Arn']
        except: 
            raise NotImplementedError("Failed to get aws codebuild arn")
        ## 1. make buildspec.yml  
        if self.pipeline == 'train':
            buildspec = self._make_buildspec_commands()
        elif self.solution_info['inference_arm'] == False and self.pipeline == 'inference':   
            buildspec = self._make_buildspec_commands()
        ## crossbuild only supports inference  
        elif self.solution_info['inference_arm'] == True and self.pipeline == 'inference': 
            buildspec = self._make_cross_buildspec_commands()
        ## 2. make create-codebuild-project.json (trigger: s3)
        s3_prefix_uri = "ai-solutions/" + self.solution_name + \
              f"/v{self.solution_version_new}/" + self.pipeline  + "/codebuild/"
        bucket_uri = self.bucket_name + "/" + s3_prefix_uri 
        codebuild_project_json = self._make_codebuild_s3_project(bucket_uri, codebuild_role)
        ## 3. make solution.zip (including buildspec.yml)
        ## Except for the .package_list, all other files and folders are wrapped in a .register_source folder.
        ## .codebuild_solution_zip directory init.
        if os.path.isdir(AWS_CODEBUILD_ZIP_PATH):
            shutil.rmtree(AWS_CODEBUILD_ZIP_PATH)
        os.makedirs(AWS_CODEBUILD_ZIP_PATH)
        ## copy things needed for docker
        ## The .package_list/{pipe}_pipeline, Dockerfile, solution_metadata.yaml (only for inference), \
        ## and buildspec.yml files are located directly under the zip folder.
        ## copy Dockerfile 
        shutil.copy2(PROJECT_HOME + "Dockerfile", AWS_CODEBUILD_ZIP_PATH)
        ## copy solution_metdata.yaml (only when inference)
        if self.pipeline == 'inference':
            shutil.copy2(SOLUTION_META, AWS_CODEBUILD_ZIP_PATH)
        ## REGISTER_SOURCE_PATH --> AWS_CODEBUILD_BUILD_SOURCE_PATH
        shutil.copytree(REGISTER_SOURCE_PATH, AWS_CODEBUILD_BUILD_SOURCE_PATH)
        shutil.copytree(ASSET_PACKAGE_PATH, AWS_CODEBUILD_ZIP_PATH + ASSET_PACKAGE_DIR)
        ## save buildspec.yml 
        try: 
            with open(AWS_CODEBUILD_ZIP_PATH + AWS_CODEBUILD_BUILDSPEC_FILE, 'w') as file:
                yaml.safe_dump(buildspec, file)
            print_color(f"[SUCCESS] Saved {AWS_CODEBUILD_BUILDSPEC_FILE} file for aws codebuild", color='green')
        except: 
            raise NotImplementedError(f"Failed to save {AWS_CODEBUILD_BUILDSPEC_FILE} file for aws codebuild")
        ## AWS_CODEBUILD_ZIP_PATH --> .zip (AWS_CODEBUILD_S3_SOLUTION_FILE)
        try: 
            shutil.make_archive(PROJECT_HOME + AWS_CODEBUILD_S3_SOLUTION_FILE, 'zip', AWS_CODEBUILD_ZIP_PATH)
            print_color(f"[SUCCESS] Saved {AWS_CODEBUILD_S3_SOLUTION_FILE}.zip file for aws codebuild", color='green')
        except: 
            raise NotImplementedError(f"Failed to save {AWS_CODEBUILD_S3_SOLUTION_FILE}.zip file for aws codebuild")
        ## 4. s3 upload solution.zip
        local_file_path = PROJECT_HOME + AWS_CODEBUILD_S3_SOLUTION_FILE + '.zip'
        local_folder = os.path.split(local_file_path)[0] + '/'
        print_color(f'\n[SYSTEM] Start uploading << {AWS_CODEBUILD_S3_SOLUTION_FILE}.zip >> into S3 from local folder:\n {local_folder}', color='cyan')
        self.s3_process(self.bucket_name, local_file_path, local_folder, s3_prefix_uri)
        ## 5. run aws codebuild create-project
        try:
            codebuild_client = session.client('codebuild', region_name=self.infra_setup['REGION'])
        except ProfileNotFound:
            print_color(f"[INFO] Start AWS codebuild access check without key file.", color="blue")
            codebuild_client = boto3.client('codebuild', region_name=self.infra_setup['REGION'])
        except Exception as e:
            raise ValueError(f"The credentials are not available: \n {str(e)}")
        ## If a project with the same name already exists, delete it.
        ws_name = self.infra_setup["WORKSPACE_NAME"].split('-')[0]
        ## (Note) '/' not allowed in {project_name}
        project_name = f'{ws_name}_ai-solutions_{self.solution_name}_v{self.solution_version_new}'
        if project_name in codebuild_client.list_projects()['projects']: 
            resp_delete_proj = codebuild_client.delete_project(name=project_name) 
            print_color(f"[INFO] Deleted pre-existing codebuild project: {project_name} \n {resp_delete_proj}", color='yellow')
        resp_create_proj = codebuild_client.create_project(name = project_name, \
                                                source = codebuild_project_json['source'], \
                                                artifacts = codebuild_project_json['artifacts'], \
                                                cache = codebuild_project_json['cache'], \
                                                tags = codebuild_project_json['tags'], \
                                                environment = codebuild_project_json['environment'], \
                                                logsConfig = codebuild_project_json['logsConfig'], \
                                                serviceRole = codebuild_project_json['serviceRole'])
        ## 6. run aws codebuild start-build 
        if type(resp_create_proj)==dict and 'project' in resp_create_proj.keys():
            print_color(f"[SUCCESS] CodeBuild create project response: \n {resp_create_proj}", color='green')
            proj_name = resp_create_proj['project']['name']
            assert type(proj_name) == str
            try: 
                resp_start_build = codebuild_client.start_build(projectName = proj_name)
            except: 
                raise NotImplementedError(f"[FAIL] Failed to start-build CodeBuild project: {proj_name}")
            if type(resp_start_build)==dict and 'build' in resp_start_build.keys(): 
                build_id = resp_start_build['build']['id']
            else: 
                raise ValueError(f"[FAIL] << build id >> not found in response of codebuild - start_build")
        else: 
            raise NotImplementedError(f"[FAIL] Failed to create CodeBuild project \n {resp_create_proj}")           
        return codebuild_client, build_id

    def _make_codebuild_s3_project(self, bucket_uri, codebuild_role):
        """ make aws codebuild project (s3 type) 
        
        Args: 
            bucket_uri      (str): s3 bucket uri
            codebuild_role  (str): codebuiild role
        
        Returns: 
            codebuild_project_json  (dict): codebuild project info. 

        """
        with open(AWS_CODEBUILD_S3_PROJECT_FORMAT_FILE) as file:
            codebuild_project_json = json.load(file)
        codebuild_project_json['source']['location'] = bucket_uri + AWS_CODEBUILD_S3_SOLUTION_FILE + '.zip'
        codebuild_project_json['serviceRole'] = codebuild_role
        codebuild_project_json['environment']['type'] = self.infra_setup["CODEBUILD_ENV_TYPE"]
        codebuild_project_json['environment']['computeType'] = self.infra_setup["CODEBUILD_ENV_COMPUTE_TYPE"]
        codebuild_project_json['environment']['privilegedMode'] = False 
        ## FIXME use ECR tags as tags 
        def _convert_tags(tags):
            if len(tags) > 0:  
                tags_new = []
                for tag in tags:
                        key, value = tag.split(',')
                        tag_dict = {'key': key.split('=')[1], 'value': value.split('=')[1]}
                        tags_new.append(tag_dict)
                return tags_new 
            else: 
                return tags
        ## codebuild tags format - [{'key':'temp-key', 'value':'temp-value'}]
        codebuild_project_json['tags'] = _convert_tags(self.infra_setup["REPOSITORY_TAGS"])
        codebuild_project_json['cache']['location'] = bucket_uri + 'cache'
        codebuild_project_json['logsConfig']['s3Logs']['location'] = bucket_uri + 'logs'
        codebuild_project_json['logsConfig']['s3Logs']['encryptionDisabled'] = True 
        print('codebuild project json: \n', codebuild_project_json)
        return codebuild_project_json
        
    def _make_buildspec_commands(self):
        """ make buildspec for codebuild
        
        Args: -
        
        Returns: 
            buildspec   (dict): codebuild buildspec

        """
        with open(AWS_CODEBUILD_BUILDSPEC_FORMAT_FILE, 'r') as file: 
            ## {'version': 0.2, 'phases': {'pre_build': {'commands': None}, 'build': {'commands': None}, 'post_build': {'commands': None}}}
            buildspec = yaml.safe_load(file)
        pre_command = [f'aws ecr get-login-password --region {self.infra_setup["REGION"]} | docker login --username AWS --password-stdin {self.ecr_url}']  
        build_command = ['export DOCKER_BUILDKIT=1']
        if self.solution_info['solution_update'] == True: 
            ## Download the previous version of the docker and utilize the cache when building the current version.
            pre_command.append(f'docker pull {self.ecr_full_url}:v{self.solution_version_new - 1}')
            build_command.append(f'docker build --build-arg BUILDKIT_INLINE_CACHE=1 --cache-from {self.ecr_full_url}:v{self.solution_version_new - 1} -t {self.ecr_full_url}:v{self.solution_version_new} .')
        else:
            pre_command.append(f'aws ecr create-repository --repository-name {self.ecr_repo} --region {self.infra_setup["REGION"]} --image-scanning-configuration scanOnPush=true')
            build_command.append(f'docker build --build-arg BUILDKIT_INLINE_CACHE=1 -t {self.ecr_full_url}:v{self.solution_version_new} .')
        post_command = [f'docker push {self.ecr_full_url}:v{self.solution_version_new}']
        buildspec['phases']['pre_build']['commands'] = pre_command
        buildspec['phases']['build']['commands'] = build_command
        buildspec['phases']['post_build']['commands'] = post_command
        del buildspec['phases']['install']
        return buildspec

    def _make_cross_buildspec_commands(self):
        """ make buildspec for codebuild (cross-build)
        
        Args: -
        
        Returns: 
            buildspec   (dict): codebuild buildspec

        """
        ## make buildspec for amd --> arm cross build 
        with open(AWS_CODEBUILD_BUILDSPEC_FORMAT_FILE, 'r') as file: 
            ## {'version': 0.2, 'phases': {'pre_build': {'commands': None}, 'build': {'commands': None}, 'post_build': {'commands': None}}}
            buildspec = yaml.safe_load(file)
        ## runtime_docker_version = {'docker': AWS_CODEBUILD_DOCKER_RUNTIME_VERSION} ~ 19
        install_command = ['docker version', \
                'curl -JLO https://github.com/docker/buildx/releases/download/v0.4.2/buildx-v0.4.2.linux-amd64', \
                'mkdir -p ~/.docker/cli-plugins', \
                'mv buildx-v0.4.2.linux-amd64 ~/.docker/cli-plugins/docker-buildx', \
                'chmod a+rx ~/.docker/cli-plugins/docker-buildx', \
                'docker run --rm tonistiigi/binfmt --install all']
                ## 'docker run --privileged --rm tonistiigi/binfmt --install all']
        pre_command = [f'aws ecr get-login-password --region {self.infra_setup["REGION"]} | docker login --username AWS --password-stdin {self.ecr_url}']
        build_command = ['export DOCKER_BUILDKIT=1', \
                    'docker buildx create --use --name crossx']
        if self.solution_info['solution_update'] == True: 
            ## Download the previous version of the docker and utilize the cache when building the current version.
            pre_command.append(f'docker pull {self.ecr_full_url}:v{self.solution_version_new - 1}')
            build_command.append(f'docker buildx build --push --platform=linux/amd64,linux/arm64 --build-arg BUILDKIT_INLINE_CACHE=1 --cache-from {self.ecr_full_url}:v{self.solution_version_new - 1} -t {self.ecr_full_url}:v{self.solution_version_new} .')
        else: 
            pre_command.append(f'aws ecr create-repository --repository-name {self.ecr_repo} --region {self.infra_setup["REGION"]} --image-scanning-configuration scanOnPush=true')
            build_command.append(f'docker buildx build --push --platform=linux/amd64,linux/arm64 --build-arg BUILDKIT_INLINE_CACHE=1 -t {self.ecr_full_url}:v{self.solution_version_new} .')
        buildspec['phases']['install']['commands'] = install_command
        buildspec['phases']['pre_build']['commands'] = pre_command
        buildspec['phases']['build']['commands'] = build_command
        del buildspec['phases']['post_build']
        return buildspec
    
    def _batch_get_builds(self, codebuild_client, build_id, status_period=20):
        """ batch get codebuild status 
        
        Args: 
            codebuild_client    (object): codebuild client
            build_id            (str): codebuild id
            status_period       (int): check status period
        
        Returns: 
            build_status    (str): codebuild status 

        """
        ## check remote build status (1check per {status_perioud})
        build_status = None 
        while True: 
            resp_batch_get_builds = codebuild_client.batch_get_builds(ids = [build_id])  
            if type(resp_batch_get_builds)==dict and 'builds' in resp_batch_get_builds.keys():
                print_color(f'Response-batch-get-builds: ', color='blue')
                print(resp_batch_get_builds)
                print('-------------------------------------------------------------------------------- \n')
                ## assert len(resp_batch_get_builds) == 1 
                ## Since there will only be one build per pipeline, only one item is embedded in the ids list.
                build_status = resp_batch_get_builds['builds'][0]['buildStatus']
                ## 'SUCCEEDED'|'FAILED'|'FAULT'|'TIMED_OUT'|'IN_PROGRESS'|'STOPPED'
                if build_status == 'SUCCEEDED':
                    print_color(f"[SUCCESS] Completes remote build with AWS CodeBuild", color='green')
                    break 
                elif build_status == 'IN_PROGRESS': 
                    print_color(f"[IN PROGRESS] In progress.. remote building with AWS CodeBuild", color='blue')
                    time.sleep(status_period)
                else: 
                    self._download_codebuild_s3_log(resp_batch_get_builds) 
                    raise NotImplementedError(f"[FAIL] Failed to remote build with AWS CodeBuild: \n Build Status - {build_status}")
        ## TODO s3 delete .zip ? 
        return build_status

    def _download_codebuild_s3_log(self, resp_batch_get_builds): 
        """ download codebuild log from s3  
        
        Args: 
            resp_batch_get_builds   (dict): codebuild status 
        
        Returns: -

        """
        try: 
            codebuild_id = resp_batch_get_builds['builds'][0]['id']
            s3_log_path = resp_batch_get_builds['builds'][0]['logs']['s3LogsArn'].split(':::')[-1]
            s3_bucket, file_key = s3_log_path.split('/', maxsplit=1) 
            local_file_path = PROJECT_HOME + f"codebuild_fail_log_{codebuild_id}.gz".replace(':', '_')
            self.s3_client.download_file(s3_bucket, file_key, local_file_path)
            print_color(f'\n Downloaded: s3://{s3_bucket}/{file_key} \n --> {local_file_path} \n Please check the log!', color='red')
        except Exception as e: 
            raise NotImplementedError(f"Failed to download codebuild fail log \n {e}")
        
    def _build_docker(self, is_docker):
        """ build docker image
        
        Args: 
            is_docker   (bool): whether docker or buildah
        
        Returns: -

        """
        last_update_time = time.time()
        ## update interval
        update_interval = 1 
        log_file_path = f"{self.pipeline}_build.log"
        image_tag = f"{self.ecr_full_url}:v{self.solution_version_new}"
        if is_docker:
            try:
                with open(log_file_path, "w") as log_file:
                    for line in self.docker_client.api.build(path='.', tag=image_tag, decode=True):
                        if 'stream' in line:
                            log_file.write(line['stream'])
                            ## flush stdout
                            if time.time() - last_update_time > update_interval:
                                sys.stdout.write('.')
                                sys.stdout.flush()
                                last_update_time = time.time()
                    sys.stdout.write(' Done!\n')
            except Exception as e:
                print(f"An error occurred: {e}")
        else:
            with open(log_file_path, "wb") as log_file:
                command = ['sudo', 'buildah', 'bud', '--isolation', 'chroot', '-t', image_tag, '.']
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                for line in iter(process.stdout.readline, b''):
                    log_file.write(line)
                    if time.time() - last_update_time > update_interval:
                        sys.stdout.write('.')
                        sys.stdout.flush()
                        last_update_time = time.time()
                process.stdout.close()
                return_code = process.wait()
                if return_code == 0:
                    sys.stdout.write(' Done!\n')
                else:
                    raise ValueError(f"{self.pipeline}_build.log를 확인하세요")

    def docker_push(self):
        """ docker push to ecr
        
        Args: -
        
        Returns: -

        """
        image_tag = f"{self.ecr_full_url}:v{self.solution_version_new}"
        self.print_step(f"push {image_tag} Container", sub_title=True)
        if self.infra_setup['BUILD_METHOD'] == 'docker':
            try:
                response = self.docker_client.images.push(image_tag, stream=True, decode=True)
                for line in response:
                    ## processing status print (...)
                    sys.stdout.write('.')
                    sys.stdout.flush()
                print("\nDone")
            except Exception as e:
                print(f"Exception occurred: {e}")
        elif self.infra_setup['BUILD_METHOD'] == 'buildah':
            subprocess.run(['sudo', 'buildah', 'push', f'{self.ecr_full_url}:v{self.solution_version_new}'])
            subprocess.run(['sudo', 'buildah', 'logout', '-a'])
        elif self.infra_setup['BUILD_METHOD'] == 'codebuild':
            ## codebuild docker push is impelemented on cloud 
            pass  

    def _set_container_uri(self):
        """ set docker container uri 
        
        Args: -
        
        Returns: -

        """
        try: 
            ## ful url contains tags info.
            data = {'container_uri': f'{self.ecr_full_url}:v{self.solution_version_new}'} 
            self.sm_yaml['pipeline'][self.sm_pipe_pointer].update(data)
            print_color(f"[SYSTEM] Completes setting << container_uri >> in solution_metadata.yaml:", color='green')
            print(f"container_uri: {data['container_uri']}")
            self._save_yaml()
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << container_uri >> in the solution_metadata.yaml \n {str(e)}")

    def set_user_parameters(self, display_table=False):
        """ Display the parameters created in experimental_plan.yaml and define their functionality.
        
        Args:  
            display_table   (bool): whether to show as table 
        
        Returns: 
            candidate_format    (dict): candidate params format

        """
        self.print_step(f"Set {self.pipeline} user parameters:")
        def rename_key(d, old_key, new_key): 
            if old_key in d:
                d[new_key] = d.pop(old_key)
       
        ## candidate parameters setting
        params = deepcopy(self.exp_yaml['user_parameters'])
        for pipe_dict in params:
            pipe_name = None 
            if 'train_pipeline' in list(pipe_dict.keys()):
                pipe_name = 'train'
            elif 'inference_pipeline' in list(pipe_dict.keys()):
                pipe_name = 'inference'
            else:
                pipe_name = None
            ## single pipeline supports ({pipe_dict} type conversion : pipeline-->candidate_parameters) 
            rename_key(pipe_dict, f'{pipe_name}_pipeline', 'candidate_parameters')
            sm_pipe_type = self.sm_yaml['pipeline'][self.sm_pipe_pointer]['type']
            if sm_pipe_type == pipe_name:
                subkeys = {}
                ## candidate
                subkeys.update(pipe_dict)  
                ## create empty {user_parameters} 
                selected_user_parameters = []
                user_parameters = []
                step_list = []
                for step in pipe_dict['candidate_parameters']:
                    output_data = {'step': step['step'], 'args': {}} 
                    selected_user_parameters.append(output_data.copy())
                    output_data = {'step': step['step'], 'args': []} 
                    user_parameters.append(output_data.copy())
                    step_list.append(step['step'])
                subkeys['selected_user_parameters'] = selected_user_parameters
                subkeys['user_parameters'] = user_parameters
                ## check edgeconductor UI parameters
                try:
                    ui_dict = deepcopy(self.exp_yaml['ui_args_detail'])
                    enable_ui_args = True
                    new_dict = {'user_parameters': {}}
                    for ui_args_step in ui_dict:
                        if f'{pipe_name}_pipeline' in list(ui_args_step.keys()):
                            new_dict['user_parameters'] = ui_args_step[f'{pipe_name}_pipeline']
                except:
                    enable_ui_args = False
                ## run below if ui parameters exist 
                ## {ui_args_detail} should not be None
                if new_dict['user_parameters'] != None: 
                    if enable_ui_args:
                        ## add step name
                        user_names, detail_names = [], []
                        for new_step in new_dict['user_parameters']:
                            for cnt, steps in enumerate(subkeys['user_parameters']):
                                if steps['step'] == new_step['step']:
                                    filtered_new_step_args = [] 
                                    if new_step['args'] != None:
                                        assert type(new_step['args']) == list 
                                        ## Among the detailed UI arguments, only the parts that the user has written as \
                                        ## UI arguments in the user_parameters section should be entered into the solution metadata's user_parameters.
                                        for detail_step_info in new_step['args']: 
                                            detail_name = detail_step_info['name']
                                            detail_names.append(detail_name) 
                                            for user_params_step in pipe_dict[f'candidate_parameters']:
                                                if user_params_step['step'] == new_step['step']: 
                                                    if 'ui_args' in user_params_step.keys():
                                                        assert type(user_params_step['ui_args']) == list
                                                        for user_ui_arg in user_params_step['ui_args']:
                                                            if user_ui_arg not in user_names:
                                                                user_names.append(user_ui_arg)
                                                            if user_ui_arg == detail_name:
                                                                filtered_new_step_args.append(detail_step_info)
                                                    else: 
                                                        print_color(f"<< ui_args >> key not found in {step_name} step", color='yellow')
                                    subkeys['user_parameters'][cnt]['args'] = filtered_new_step_args
                        args_diff = list(set(user_names) - set(detail_names))
                        if len(args_diff) != 0: 
                            raise ValueError(f"These ui arg keys are not in ui_args_detail:\n {args_diff}")
                self.sm_yaml['pipeline'][self.sm_pipe_pointer].update({'parameters':subkeys})
                ## save yaml
                self._save_yaml()
        ## display
        params2 = deepcopy(self.exp_yaml['user_parameters'])
        columns = ['pipeline', 'step', 'parmeter', 'value']
        table_idx = 0
        ## return format
        self.candidate_format = {}  
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
            item_list = []
            for step_dict in pipe_dict[f'{pipe_name}_pipeline']:
                step_name = step_dict['step']
                new_dict = {'step': step_name, 
                            'args': []}
                self.candidate_format[f'{pipe_name}_pipeline'].append(new_dict)
                try: 
                    for key, value in step_dict['args'][0].items():
                        item = [pipe_name, step_name, key, value]
                        item_list.append(item)
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
        if display_table:
            print_color(columns, color='cyan')
            for i in item_list: 
                print_color(i, color='cyan')
        return self.candidate_format
    
    def register_solution_instance(self): 
        """ register solution instance
        
        Args: -
        
        Returns: -

        """
        self.print_step("Register AI solution instance")
        self.login()
        if os.path.exists(REGISTER_INTERFACE_PATH + self.SOLUTION_INSTANCE_FILE):
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_INSTANCE_FILE
            print(f'[SYSTEM] AI solution instance 가 등록되어 있어 과정을 생략합니다. (등록정보: {path})')
            return 
        else:
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_FILE
            msg = f"[SYSTEM] AI solution 등록 정보를 {path} 에서 확인합니다."
            load_response = self._load_response_yaml(path, msg)
        print_color('load_response: \n', color='blue')
        print(load_response)
        ## instance name
        name = load_response['name'] + \
            "-" + f'v{load_response["versions"][0]["version"]}'
        self.solution_instance_params = {
            "workspace_name": load_response['scope_ws']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.solution_instance_params}", color='blue')
        ## read solution metadata  
        with open(SOLUTION_META, 'r') as file:
            yaml_data = yaml.safe_load(file)
        
        self.register_solution_instance_api["name"] = name
        self.register_solution_instance_api["solution_version_id"] = load_response['versions'][0]['id']
        self.register_solution_instance_api["metadata_json"] = yaml_data
        ## FIXME resource
        if 'train_resource' in self.register_solution_instance_api:
            self.register_solution_instance_api['train_resource'] = "standard"
            yaml_data['pipeline'][0]["resource"]['default'] = self.register_solution_instance_api['train_resource']
        ## json dump
        data =json.dumps(self.register_solution_instance_api)
        ## register solution instance 
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
            ## create interface directory
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {str(e)}")
            ## save json to file
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_INSTANCE_FILE
            with open(path, 'w') as f:
              json.dump(self.response_solution_instance, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            self.delete_stream()
            self.delete_solution()
            raise ValueError("Error message: ", self.response_solution_instance["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] AI solution instance 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            self.delete_stream()
            self.delete_solution()
            raise ValueError("Error message: ", self.response_solution_instance["detail"])
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            self.delete_stream()
            self.delete_solution()
    
    def register_stream(self): 
        """ register solution stream
        
        Args: -
        
        Returns: -

        """
        self.print_step("Register AI solution stream")
        ## file load 
        if os.path.exists(REGISTER_INTERFACE_PATH + self.STREAM_FILE):
            path = REGISTER_INTERFACE_PATH + self.STREAM_FILE
            print(f'[SYSTEM] AI solution instance 가 등록되어 있어 과정을 생략합니다. (등록정보: {path})')
            return 
        else:
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_INSTANCE_FILE
            msg = f"[SYSTEM] AI solution instance 등록 정보를 {path} 에서 확인합니다."
            load_response = self._load_response_yaml(path, msg)
        ## register stream  
        params = {
            "workspace_name": load_response['workspace_name']
        }
        ## prefix name already added in solution instance
        data = {
            "instance_id": load_response['id'],
            "name": load_response['name']  
        }
        ## json dump
        data =json.dumps(data) 
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
            ## create interface directory
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {str(e)}")
            ## save json to file 
            path = REGISTER_INTERFACE_PATH + self.STREAM_FILE
            with open(path, 'w') as f:
              json.dump(self.response_stream, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            self.delete_solution()
            print_color("[ERROR] Stream 등록을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.response_stream["detail"])
        elif response.status_code == 422:
            self.delete_solution()
            print_color("[ERROR] Stream 등록을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.response_stream["detail"])
        else:
            self.delete_solution()
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
    
    def request_run_stream(self): 
        """ request train for stream
        
        Args: -
        
        Returns: -

        """
        self.print_step("Request AI solution stream run")
        ## stream info. file load 
        path = REGISTER_INTERFACE_PATH + self.STREAM_FILE
        msg = f"[SYSTEM] Stream 등록 정보를 {path} 에서 확인합니다."
        load_response = self._load_response_yaml(path, msg)
        ## stream params
        stream_params = {
            "stream_id": load_response['id'],
            "workspace_name": load_response['workspace_name']
        }
        pprint(stream_params)
        ## Upload train sample data to the s3 path required by the stream (similar to edge conductor).
        dataset_uri = self.s3_upload_stream_data(stream_id=load_response['id'], instance_id=load_response['instance_id'])
        ## read solution metadata  
        with open(SOLUTION_META, 'r') as file:
            yaml_data = yaml.safe_load(file)
        ## + dataset_uri update and register
        for pip in yaml_data['pipeline']:
            if pip['type'] == 'train':
                pip['dataset_uri'] = dataset_uri['dataset_uri']
        ## FIXME config_path ?
        data = {
            "metadata_json": yaml_data,
            "config_path": ""
        }
        ## json dump
        data =json.dumps(data) 
        aic = self.infra_setup["AIC_URI"]
        api = self.api_uri["STREAM_RUN"] + f"/{load_response['id']}"
        response = requests.post(aic+api, params=stream_params, data=data, cookies=self.aic_cookie)
        response_json = response.json()

        if response.status_code == 200:
            print_color("[SUCCESS] Stream Run 요청을 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_json}")
            ## create interface directory
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {str(e)}")
            ## save json to file
            path = REGISTER_INTERFACE_PATH + self.STREAM_RUN_FILE
            with open(path, 'w') as f:
              json.dump(response_json, f, indent=4)
              print_color(f"[SYSTEM] register 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            self.delete_stream()
            self.delete_solution_instance()
            self.delete_solution()
            print_color("[ERROR] Stream Run 요청을 실패하였습니다. 잘못된 요청입니다. ", color='red')
            raise ValueError("Error message: {}".format(response_json["detail"]))
        elif response.status_code == 422:
            self.delete_stream()
            self.delete_solution_instance()
            self.delete_solution()
            print_color("[ERROR] Stream Run 요청을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            raise ValueError("Error message: {}".format(response_json["detail"]))
        else:
            self.delete_stream()
            self.delete_solution_instance()
            self.delete_solution()
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise ValueError(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})")

    def get_log_error(self):
        """ get error log
        
        Args: -
        
        Returns: -

        """
        def _get_log_error(log_file_name, step = ""):
            error_started = False
            log_file = tar.extractfile(log_file_name)
            if log_file:
                for line in log_file:
                    msg = line.decode('utf-8').strip()
                    if "current step" in msg:
                        step = msg.split(":")[1].replace(" ", "")
                    if error_msg in msg:
                        print(f"error step is {step}")
                        error_started = True
                    if error_started:
                        print(msg)
            log_file.close()
        file_name = 'train_artifacts.tar.gz'
        error_msg = "[ERROR]"
        process_log = 'log/process.log'
        pipeline_log = 'log/pipeline.log'
        step = ""
        s3 = self.session.client('s3')
        ## FIXME only supports train 
        s3_tar_file_key = "ai-solutions/" + self.solution_name + f"/v{self.solution_version_new}/" + 'train'  + f"/artifacts/{file_name}"
        try:
            s3_object = s3.get_object(Bucket=self.bucket_name, Key=s3_tar_file_key)
            s3_streaming_body = s3_object['Body']

            with io.BytesIO(s3_streaming_body.read()) as tar_gz_stream:
                ## go to stream start point
                tar_gz_stream.seek(0)  
                with tarfile.open(fileobj=tar_gz_stream, mode='r:gz') as tar:
                    try:
                        _get_log_error(process_log, step)
                        _get_log_error(pipeline_log, step)
                    except KeyError:
                        print(f'log file is not exist in the tar archive')
        except Exception as e:
            raise NotImplementedError(str(e))
        
    def get_stream_status(self, status_period=20):
        """ Proceed with the action handling for each status supported by KUBEFLOW_STATUS. KUBEFLOW_STATUS options include 
            ("Pending", "Running", "Succeeded", "Skipped", "Failed", "Error"). 
                Pending: Notifies that the docker container is about to run.
                Running: Notifies that it is currently in execution.
                Succeeded: Indicates successful status.
                Skipped: Entity has been skipped. For example, due to caching.
                Stopped: Indicates stopped status.
                Failed: Indicates a failed status.

        Args: 
            status_period   (int): stream status check period
        
        Returns: -

        """
        self.print_step("Get AI solution stream status")
        ## stream file load 
        path = REGISTER_INTERFACE_PATH + self.STREAM_RUN_FILE
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
            self.login()
            response = requests.get(aic+api, 
                                    params=stream_history_params, 
                                    cookies=self.aic_cookie)
            self.response_stream_status = response.json()
            if response.status_code == 200:
                status = self.response_stream_status["status"]
                status = status.lower()
                if not status in KUBEFLOW_STATUS:
                    raise ValueError(f"[ERROR] 지원하지 않는 status 입니다. (status: {status})")
                end_time = time.time()
                elapsed_time = end_time - start_time
                elapsed_time_str = time.strftime(time_format, time.localtime(elapsed_time))
                if status == "succeeded":
                    print_color(f"[SUCCESS] (run_time: {elapsed_time_str}) Train pipeline (status:{status}) 정상적으로 실행 하였습니다. ", color='green')
                    ## save json to file 
                    path = REGISTER_INTERFACE_PATH + self.STREAM_STATUS_FILE
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
                self.delete_stream()
                self.delete_solution_instance()
                self.delete_solution()
                raise ValueError(f"[ERROR] Stream status 요청을 실패하였습니다. 잘못된 요청입니다. ")
            elif response.status_code == 422:
                self.delete_stream()
                self.delete_solution_instance()
                self.delete_solution()
                print_color("[ERROR] Stream status 요청을 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
                print("Error message: ", self.response_stream_status["detail"])
                raise ValueError(f"[ERROR] Stream status 요청을 실패하였습니다. 유효성 검사를 실패 하였습니다.")
            else:
                self.delete_stream()
                self.delete_solution_instance()
                self.delete_solution()
                print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
                raise ValueError(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})")
    
    def download_artifacts(self): 
        """ download artifacts

        Args: -
        
        Returns: -

        """
        self.print_step("\n Download train artifacts \n")
        def split_s3_path(s3_path): 
            ## Remove 's3://' and split the first part based on '/' to obtain the bucket and the remaining path.
            path_parts = s3_path.replace('s3://', '').split('/', 1)
            bucket = path_parts[0]
            rest_of_the_path = path_parts[1]
            return bucket, rest_of_the_path
        try: 
            assert self.sm_yaml['pipeline'][0]['type'] == 'train'
            train_artifact_uri = self.sm_yaml['pipeline'][0]['artifact_uri']
            s3_bucket, s3_prefix = split_s3_path(train_artifact_uri)
            ## object list in s3 bucket 
            objects = self.s3_client.list_objects(Bucket=s3_bucket, Prefix=s3_prefix)
            ## file download from s3 
            for obj in objects.get('Contents', []):
                key = obj['Key']
                filename = key.split('/')[-1] 
                if filename not in [COMPRESSED_TRAIN_ARTIFACTS_FILE, COMPRESSED_MODEL_FILE]:
                    print(f'Skip downloading: {filename}')
                    continue 
                local_file_path = PROJECT_HOME + filename
                self.s3_client.download_file(s3_bucket, key, local_file_path)
                print_color(f'\n Downloaded: {s3_bucket}/{key}{filename} --> \n {local_file_path} \n Please check the log in the artifact file', color='cyan')
        except: 
            raise NotImplementedError("Failed to download train artifacts.")

    def delete_stream_history(self): 
        """ delete stream history

        Args: -
        
        Returns: -

        """
        self.print_step("Delete stream history")
        self.login()
        ## file load 
        path = REGISTER_INTERFACE_PATH + self.STREAM_RUN_FILE
        msg = f"[SYSTEM] stream 등록 정보를 {path} 에서 확인합니다."
        load_response = self._load_response_yaml(path, msg)
        ## stream register 
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
            ## if success deletion, delete files in path  
            if os.path.exists(path):
                os.remove(path)
                print(f'File removed successfully! (file: {path})')
            else:
                print(f'File does not exist! (file: {path})')
        elif response.status_code == 400:
            print_color("[WARNING] Stream history 삭제를 실패하였습니다. 잘못된 요청입니다. ", color='yellow')
            print("Error message: ", response_delete_stream_history["detail"])
            ## althogh fails, delete stream history
        elif response.status_code == 422:
            print_color("[ERROR] Stream history 삭제를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", response_delete_stream_history["detail"])
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_stream_history}")
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')
            raise NotImplementedError(f"Failed to delete stream: \n {response_delete_stream_history}")

    def delete_stream(self,solution_id=None): 
        """ delete stream 

        Args: 
            solution_id (str): solution id 
        
        Returns: -

        """
        self.print_step("Delete stream")
        self.login()
        if not solution_id:  
            ## file load 
            path = REGISTER_INTERFACE_PATH + self.STREAM_FILE
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
        ## stream register
        aic = self.infra_setup["AIC_URI"]
        response = requests.delete(aic+api, 
                                 params=params, 
                                 cookies=self.aic_cookie)
        response_delete_stream = response.json()
        if response.status_code == 200:
            print_color("[SUCCESS] Stream 삭제를 성공하였습니다. ", color='cyan')
            print(f"[INFO] response: \n {response_delete_stream}")
            if not solution_id:  
                ## if success deletion, delete files in path 
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
        """ delete instance

        Args: 
            solution_id (str): solution id 
        
        Returns: -

        """
        self.print_step("Delete AI solution instance")
        self.login()
        if not solution_id: 
            ## file load 
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_INSTANCE_FILE
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
            if not solution_id:  
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
        ## FIXME delete_all ? 
        """ delete solution

        Args: 
            delete_all  (bool): whether to delete all the solutions
            solution_id (str): solution id 
        
        Returns: -

        """
        self.print_step("Delete AI solution")
        self.login()
        if self.solution_info["solution_update"]:
            ## file load 
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_FILE
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
                ## file load 
                path = REGISTER_INTERFACE_PATH + self.SOLUTION_FILE
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
            if not solution_id: 
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

    def list_stream(self): 
        """ list stream

        Args: -
        
        Returns: -

        """
        self.print_step("List stream ")
        self.stream_params = {
            "workspace_name": self.infra_setup['WORKSPACE_NAME']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.stream_params}", color='blue')
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
            ## create interface directory
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")
            ## save json to file 
            path = REGISTER_INTERFACE_PATH + self.STREAM_LIST_FILE
            with open(path, 'w') as f:
              json.dump(self.stream_list, f, indent=4)
              print_color(f"[SYSTEM] list 결과를 {path} 에 저장합니다.",  color='green')
        elif response.status_code == 400:
            print_color("[ERROR] stream list 조회를 실패하였습니다. 잘못된 요청입니다. ", color='red')
            print("Error message: ", self.stream_list["detail"])
        elif response.status_code == 422:
            print_color("[ERROR] stream list 조회를 실패하였습니다. 유효성 검사를 실패 하였습니다.. ", color='red')
            print("Error message: ", self.stream_list["detail"])
            raise NotImplementedError(f"Failed to delete solution: \n {response.status_code}")
        else:
            print_color(f"[ERROR] 미지원 하는 응답 코드입니다. (code: {response.status_code})", color='red')

    def list_stream_history(self, id=''): 
        """ list stream history

        Args: 
            id  (str): stream id 
        
        Returns: -

        """
        self.print_step("List stream history")
        self.stream_run_params = {
            "stream_id": id,
            "workspace_name": self.infra_setup['WORKSPACE_NAME']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.stream_run_params}", color='blue')
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
            ## create interface directory
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {e}")
            ## save json file 
            path = REGISTER_INTERFACE_PATH + self.STREAM_HISTORY_LIST_FILE
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
        """ list solution instance

        Args: -
        
        Returns: -

        """
        self.print_step("Load AI solution instance list")
        self.solution_instance_params = {
            "workspace_name": self.infra_setup['WORKSPACE_NAME']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.solution_instance_params}", color='blue')
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
            ## create interface directory
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {str(e)}")
            ## save to file
            path = REGISTER_INTERFACE_PATH + self.INSTANCE_LIST_FILE
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
        """ list solution 

        Args: -
        
        Returns: -

        """
        self.print_step("Load AI solution instance list")
        params = {
            "workspace_name": self.infra_setup['WORKSPACE_NAME'],
            "with_pulic": 1, 
            "page_size": 100
        }
        print_color(f"\n[INFO] AI solution interface information: \n {params}", color='blue')
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
            ## create interface directory
            try:
                if not os.path.exists(REGISTER_INTERFACE_PATH):
                    os.mkdir(REGISTER_INTERFACE_PATH)
            except Exception as e:
                raise NotImplementedError(f"Failed to generate interface directory: \n {str(e)}")
            ## save to file 
            path = REGISTER_INTERFACE_PATH + self.SOLUTION_LIST_FILE
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
    ######    Internal Functions   ######
    #####################################
    
    def _load_response_yaml(self, path, msg):
        """ load AIC response saved yaml 

        Args: 
            path    (str): yaml path
            msg     (msg): logging message 
        
        Returns: 
            data    (dict): json loaded yaml 

        """
        try:
            with open(path) as f:
                data = json.load(f)
                print_color(msg, color='green')
            return data
        except:
            raise ValueError(f"[ERROR] {path} 를 읽기 실패 하였습니다.")
    
    def _init_solution_metadata(self):
        """ initialize solution metadata

        Args: -
        
        Returns: -

        """
        ## Iterate over each directory and delete it if it exists.
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
        try: 
            self._save_yaml()
            if self.debugging:
                print_color(f"\n << solution_metadata.yaml >> generated. - current version: v{self.infra_setup['VERSION']}", color='green')
        except: 
            raise NotImplementedError("Failed to generate << solution_metadata.yaml >>")

    def _sm_append_pipeline(self, pipeline_name): 
        """ append pipeline to solution metadata

        Args: 
            pipeline_name   (str): pipeline tobe appended
        
        Returns: -

        """
        if not pipeline_name in ['train', 'inference']:
            raise ValueError(f"Invalid value ({pipeline_name}). Only one of 'train' or 'inference' is allowed as input.")
        self.sm_yaml['pipeline'].append({'type': pipeline_name})
        ## e.g. when adding an inference pipeline, change the pipeline attribute of the instance to 'inference'.
        self.pipeline = pipeline_name
        ## pipeline pointer increases
        self.sm_pipe_pointer += 1 
        try: 
            self._save_yaml()
        except: 
            raise NotImplementedError("Failed to update << solution_metadata.yaml >>")
    
    def _save_yaml(self):
        """ save into yaml file

        Args: -
        
        Returns: -

        """
        class NoAliasDumper(Dumper):
            def ignore_aliases(self, data):
                return True
        with open('solution_metadata.yaml', 'w', encoding='utf-8') as yaml_file:
            yaml.dump(self.sm_yaml, yaml_file, allow_unicode=True, default_flow_style=False, Dumper=NoAliasDumper)
    
    def _set_alo(self):
        """ copy alo components to register solution path 

        Args: -
        
        Returns: -

        """
        self.print_step("Set alo source code for docker container", sub_title=True)
        alo_src = ['main.py', 'src', 'assets', 'solution/experimental_plan.yaml', 'alolib', '.git', 'requirements.txt']
        ## initailize register source path 
        if os.path.isdir(REGISTER_SOURCE_PATH):
            shutil.rmtree(REGISTER_SOURCE_PATH)
        os.mkdir(REGISTER_SOURCE_PATH)
        ## copy things needed for docker 
        for item in alo_src:
            src_path = PROJECT_HOME + item
            if os.path.isfile(src_path):
                if item == 'solution/experimental_plan.yaml': 
                    register_solution_path = REGISTER_SOURCE_PATH + 'solution/'
                    os.makedirs(register_solution_path , exist_ok=True)
                    shutil.copy2(src_path, register_solution_path)
                    print_color(f'[INFO] copy from " {src_path} "  -->  " {register_solution_path} " ', color='blue')
                else: 
                    shutil.copy2(src_path, REGISTER_SOURCE_PATH)
                    print_color(f'[INFO] copy from " {src_path} "  -->  " {REGISTER_SOURCE_PATH} " ', color='blue')
            elif os.path.isdir(src_path):
                dst_path = REGISTER_SOURCE_PATH  + os.path.basename(src_path)
                shutil.copytree(src_path, dst_path)
                print_color(f'[INFO] copy from " {src_path} "  -->  " {REGISTER_SOURCE_PATH} " ', color='blue')
    
    def _reset_alo_solution(self):
        """ reset experimental plan solution info.

        Args: -
        
        Returns: -

        """
        ## When declaring an instance, self.exp_yaml has already been set (different from the original in the solution folder).
        exp_plan_dict = self.exp_yaml.copy()
        ## experimental_plan.yaml control reset
        exp_plan_dict['control'] = [{'get_asset_source': 'once'}, {'backup_artifacts': False}, \
                                    {'backup_log': False}, {'backup_size':1000}, {'interface_mode': 'memory'}, \
                                    {'save_inference_format': 'zip'}, {'check_resource': False}]
        print_color(f"[INFO] reset experimental plan control for edgeapp inference: {exp_plan_dict['control']}", color='blue')
        ## experimental_plan.yaml external_path_permission reset 
        for idx, _dict in enumerate(exp_plan_dict['external_path_permission']):
            if list(map(str, _dict.keys()))[0] == 'aws_key_profile':
                if list(map(str, _dict.values()))[0] is not None:
                    exp_plan_dict['external_path_permission'][idx]['aws_key_profile'] = None
        print_color("[INFO] reset aws key profile", color='blue')
        ## pipeline tobe deleted
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
        ## save to yaml 
        with open(REGISTER_EXPPLAN, 'w') as file:
            yaml.safe_dump(exp_plan_dict, file)
        print_color("[SUCCESS] Success ALO directory setting.", color='green')

    def _set_dockerfile(self):
        """ setup dockerfile

        Args: -
        
        Returns: -

        """
        try: 
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
            docker_location = '/framework/'
            file_list = sorted(next(os.walk(ASSET_PACKAGE_PATH))[2], key=lambda x:int(os.path.splitext(x)[0].split('_')[-1]))
            ## install inference after train 
            file_list = [i for i in file_list if i.startswith('train')] + [i for i in file_list if i.startswith('inference')]
            search_string = 'site_packages_location'
            with open(PROJECT_HOME + 'Dockerfile', 'r', encoding='utf-8') as file:
                content = file.read()
            path = ASSET_PACKAGE_PATH.replace(PROJECT_HOME, "./")
            replace_string = '\n'.join([f"COPY {path}{file} {docker_location}" for file in file_list])
            requirement_files = [file for file in file_list if file.endswith('.txt')]
            pip_install_commands = '\n'.join([f"RUN pip3 install --no-cache-dir -r {docker_location}{file}" for file in requirement_files])
            if search_string in content:
                content = content.replace(search_string, replace_string + "\n" + pip_install_commands)
                with open(PROJECT_HOME + 'Dockerfile', 'w', encoding='utf-8') as file:
                    file.write(content)
            print_color(f"[SUCESS] set DOCKERFILE for ({self.pipeline}) pipeline", color='green')
        except Exception as e: 
            raise NotImplementedError(f"Failed DOCKERFILE setting. \n - pipeline: {self.pipeline} \n {str(e)}")

    def _check_parammeter(self, param):
        """ check parameter if it is string

        Args: 
            param   (*): tobe type checked
        
        Returns: 
            whether it is string (bool)

        """
        def _check_str(data):
            return isinstance(data, str)
        if _check_str(param):
            return param
        else:
            raise ValueError("You should enter only string value for parameter.")
    
    def check_single_pipeline(self):
        """check whether it is single pipeline solution 
            single pipeline means that both train & inference occur in inference pipeline.  

        Args: -
        
        Returns: 
            Bool

        """
        exp_plan_dict = self.exp_yaml.copy()
        user_param_exist = any('train_pipeline' in d for d in exp_plan_dict['user_parameters'])
        asset_source_exist = any('train_pipeline' in d for d in exp_plan_dict['asset_source'])
        if user_param_exist and asset_source_exist:
            return False 
        elif (not user_param_exist) and (not asset_source_exist):
            return True 
        else: 
            raise ValueError("Pipelines list in user_parameters and asset_source must be same")

#####################################
######     Common Functions    ######
#####################################

def check_and_load_yaml(path_or_dict, mode=''):
    """ check and load yaml into dict 

    Args: 
        path_or_dict    (str, dict): path or dict 
        mode            (str): mode
    
    Returns: 
        result_dict (dict): converted dict

    """
    if not mode in ['infra_setup', 'solution_info', 'experimental_plan']:
        raise ValueError("The mode must be infra_setup, solution_info, or experimental_plan. (type: {})".format(type))
    if path_or_dict == None or path_or_dict == '' :
        if mode == 'infra_setup': path = DEFAULT_INFRA_SETUP
        elif mode == 'solution_info': path = DEFAULT_SOLUTION_INFO
        else: path = DEFAULT_EXP_PLAN
        print(f"{mode} 파일이 존재 하지 않으므로, Default 파일을 load 합니다. (path: {path})")
        try:    
            with open(path) as f:
                result_dict = yaml.safe_load(f)
        except Exception as e : 
            raise ValueError(str(e))
    else:
        if isinstance(path_or_dict, str):
            print(f"{mode} 파일을 load 합니다. (path: {path_or_dict})")
            try:    
                with open(path_or_dict) as f:
                    result_dict = yaml.safe_load(f)
            except Exception as e : 
                raise ValueError(str(e))
        elif isinstance(path_or_dict, dict):
            result_dict = path_or_dict
        else:
            raise ValueError(f"{mode} 파일이 유효하지 않습니다. (infra_setup: {path_or_dict})")
    return result_dict

def convert_to_float(input_str):
    """ convert string to float

    Args: 
        input_str   (str): string tobe converted
    
    Returns: 
        float_value (float): float value

    """
    try:
        float_value = float(input_str)  
        return float_value
    except ValueError:
        pass

def find_max_value(input_list):
    """ Find max value in input list. 
        If value is string, convert it into float

    Args: 
        input_list  (list): input list
    
    Returns: 
        max_value   (float): max float value 

    """
    max_value = None
    for item in input_list:
        converted_item = convert_to_float(item)
        if isinstance(converted_item, float):
            if max_value is None or converted_item > max_value:
                max_value = converted_item
    return max_value

def make_art(msg):
    """ print title

    Args: 
        msg (str): message
    
    Returns: -

    """
    ascii_art = pyfiglet.figlet_format(msg, font="slant")
    print("*" * 80)
    print(ascii_art)
    print("*" * 80)
            
def _tar_dir(_path): 
    """ compress dir into tar.gz

    Args: 
        _path   (str): path for train_artifacts / inference_artifacts   
    
    Returns: 
        _save_path  (str): saved path 

    """
    ## _path: train_artifacts / inference_artifacts     
    os.makedirs(REGISTER_ARTIFACT_PATH , exist_ok=True)
    os.makedirs(REGISTER_MODEL_PATH, exist_ok=True)
    last_dir = None
    if 'models' in _path: 
        _save_path = REGISTER_MODEL_PATH + 'model.tar.gz'
        last_dir = 'models/'
    else: 
        _save_file_name = _path.strip('.') 
        _save_path = REGISTER_ARTIFACT_PATH +  f'{_save_file_name}.tar.gz' 
        ## e.g. train_artifacts/
        last_dir = _path 
    tar = tarfile.open(_save_path, 'w:gz')
    for root, dirs, files in os.walk(PROJECT_HOME  + _path):
        base_dir = root.split(last_dir)[-1] + '/'
        for file_name in files:
            ## Since compression should start not from the absolute path \
            ## beginning with /home but from within train_artifacts/ or models/
            tar.add(os.path.join(root, file_name), arcname = base_dir + file_name)
    tar.close()
    return _save_path

def is_float(msg):
    """ check if it is float

    Args: 
       msg   (*)
       
    Returns: 
        Bool

    """
    try:
        float(msg)
        return True 
    except ValueError:
        return False 

def is_int(msg):
    """ check if it is integer

    Args: 
       msg   (*)
       
    Returns: 
        Bool

    """
    try:
        int(msg)
        return True 
    except ValueError:
        return False 

def is_bool(msg):
    """ check if it is boolean

    Args: 
       msg   (*)
       
    Returns: 
        Bool

    """
    ## FIXME It's difficult to check boolean values (what if they are entered as 0 or 1?).
    bool_list = ['True', 'False']
    if msg in bool_list: 
        return True 
    else: 
        return False 
    
def is_str(msg):
    """ check if it is string

    Args: 
       msg   (*)
       
    Returns: 
        Bool

    """
    return isinstance(msg, str)

def split_comma(string):
    """ split comma in the string and convert into list

    Args: 
       string   (str): comma split string
       
    Returns: 
        split list  (list)

    """
    return [i.strip() for i in string.split(',')]

def convert_string(value_list: list): 
    """ Convert strings within a string list to their respective float or int types if applicable.

    Args: 
        value_list  (list): value (str, int ..) list
       
    Returns: 
        output_list (list): type converted value list 

    """
    output_list = [] 
    for value in value_list: 
        if is_int(value): 
            output_list.append(int(value))
        elif is_float(value):
            output_list.append(float(value))
        elif is_bool(value):
            # FIXME It should work properly with eval(string) instead of bool(string).
            output_list.append(eval(value)) 
        ## string 
        else:
            output_list.append(value)
    return output_list 

def convert_args_type(values: dict):
    """ Convert args type

    Args: 
        values  (dict): e.g. {'name': 'my_arg',
                            'description': 'my-description',
                            'type': 'int',
                            'default': '1',
                            'range': '1,5'}
       
    Returns: 
        output  (dict): type converted values

    """
    output = deepcopy(values) 
    arg_type = values['type']
    for k, v in values.items(): 
        if k in ['name', 'description', 'type']: 
            assert type(v) == str 
        ## Assumption: Selectable options are more than one (e.g., "1, 2")
        elif k == 'selectable': 
            ## Whether single or multi, represent it as a list in the YAML.
            assert type(v) == str 
            string_list = split_comma(v)
            assert len(string_list) > 1
            ## FIXME Since each value can have a different type, it is difficult to perform a perfect type check.
            output[k] = convert_string(string_list) 
        elif k == 'default':
            ## (Note) The default could also be None (or the user could just enter "").
            if (v == None) or (v==""): 
                output[k] = []
                ## FIXME string --> [""] ?
                ## (Note) If you want the EdgeConductor UI to display a space instead of null, you need to send "" instead of None.
                if arg_type == 'string': 
                    output[k] = [""] 
                else: 
                    ## FIXME For now, we have determined that there must always be a default value for single(multi)-selection, int, and float types.
                    raise ValueError(f"Default value needed for arg. type: << {arg_type} >>")
            else:  
                ## FIXME What if a selection contains a mix of types like float and str? \
                ## Would it be clear whether the user intended the number 1 or the string '1'?
                string_list = split_comma(v)
                if arg_type == 'single_selection': 
                    assert len(string_list) == 1
                elif arg_type == 'multi_selection':
                    assert len(string_list) > 1
                ## list type
                output[k] = convert_string(string_list) 
        elif k == 'range':
            string_list = split_comma(v)
            ## range: [start, finish] ~ 2
            assert len(string_list) == 2
            converted = convert_string(string_list)
            if (arg_type == 'string') or (arg_type == 'int'):
                for i in converted:
                    ## when string type, range means for # characters
                    if not is_int(i): 
                        raise ValueError("<< range >> value must be int")
            elif arg_type == 'float':
                for i in converted:
                    if not is_float(i): 
                        raise ValueError("<< range >> value must be float")
            output[k] = converted 
    return output
        
