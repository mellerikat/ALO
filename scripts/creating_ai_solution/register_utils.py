# from ruamel.yaml import YAML
import sys
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

# yaml = YAML()
# yaml.preserve_quotes = True
#----------------------------------------#
#              REST API                  #
#----------------------------------------#
VERSION = 1
ALODIR = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__)))) + '/'
TEMP_ARTIFACTS_DIR = ALODIR + '.temp_artifacts_dir/'
# 외부 model.tar.gz (혹은 부재 시 해당 경로 폴더 통째로)을 .train_artifacts/models 경로로 옮기기 전 임시 저장 경로 
TEMP_MODEL_DIR = ALODIR + '.temp_model_dir/'
#---------------------------------------------------------
WORKINGDIR = os.path.abspath(os.path.dirname(__file__)) + '/'
# REST API Endpoints
BASE_URI = 'api/v1/'
# 0. 로그인
STATIC_LOGIN = BASE_URI + 'auth/static/login' # POST
LDAP_LOGIN = BASE_URI + 'auth/ldap/login'
# 1. 시스템 정보 획득
SYSTEM_INFO = BASE_URI + 'workspaces' # GET
# 2. AI Solution 이름 설정 / 3. AI Solution 등록
AI_SOLUTION = BASE_URI + 'solutions' # 이름 설정 시 GET, 등록 시 POST
# 4. AI Solution Instance 등록
SOLUTION_INSTANCE = BASE_URI + 'instances' # POST
# 5. Stream 등록
STREAMS = BASE_URI + 'streams' # POST
# 6. Train pipeline 요청
# STREAMS + '/{stream_id}/start # POST
# 7. Train pipeline 확인
# STREAMS + '/{stream_history_id}/info # GET
# 9.a Stream 삭제 
# STREAMS + '/{stream_id} # DELETE
# 9.b AI Solution Instance 삭제
# SOLUTION_INSTANCES + '/{instance_id}' # DELETE
# 9.c AI Solution 삭제
# AI_SOLUTION + '/{solution_id}' # DELETE 
#----------------------------------------#
#----------------------------------------#
#              URI SCOPE                 #
#----------------------------------------#
# 231207 임현수C: 사용자는 public 사용못하게 해달라 
ONLY_PUBLIC = 0 #1 --> 1로 해야 public, private 다 받아옴 
#----------------------------------------#
class RegisterUtils:
    #def __init__(self, workspaces, uri_scope, tag, name, pipeline):
    def __init__(self, user_input):
        self.user_input = user_input # dict 
        self.set_user_input() # dict 
        self.URI_SCOPE = self.WORKSPACE_NAME #'magna-ws' #'public'
        print('URI_SCOPE: ', self.URI_SCOPE)
        self.access_scope = 'private' # 'public'
        
        self.sm_yaml = {}
        self.exp_yaml = {}
        self.pipeline = None 
        self.solution_name = None
        self.workspaces = None 

        # FIXME sm.set_aws_ecr 할 때 boto3 session 생성 시 region 을 None으로 받아와서 에러나므로 일단 임시로 추가 
        self.region = "ap-northeast-2"
        self.ECR_TAG = 'latest' # 사용자 설정가능 
        # FIXME aws login 방법 고민필요
        self.s3_access_key_path = "/nas001/users/ruci.sung/aws.key"
        
        # solution instance 등록을 위한 interface 폴더 
        self.interface_dir = './interface'
        self.sm_yaml_file_path = './solution_metadata.yaml'
        # FIXME 다른 이름으로 exp plan yaml 사용하면 ?
        self.exp_yaml_path = "../../config/experimental_plan.yaml"
        

        
    def set_user_input(self): 
        # TODO user input 다 잘 작성했나 체크필요 
        # 각 key 별 value 클래스 self 변수화 
        for key, value in self.user_input.items():
            setattr(self, key, value)
        

    
    def login(self, login_way = 'ldap'): 
        # 로그인 (관련 self 변수들은 set_user_input 에서 setting 됨)
        login_data = json.dumps({
        "login_id": self.LOGIN_ID,
        "login_pw": self.LOGIN_PW
        })
        if login_way == 'ldap':
            LOGIN = LDAP_LOGIN 
        elif login_way == 'static':
            LOGIN = STATIC_LOGIN
        else: 
            raise ValueError(f'Unsupported login way: {login_way}')
        login_response = requests.post(self.URI + LOGIN, data = login_data)
        login_response_json = login_response.json()

        cookies = login_response.cookies.get_dict()
        access_token = cookies.get('access-token', None)
        self.aic_cookie = {
        'access-token' : access_token 
        }
        if login_response_json['result'] == 'OK':
            print_color(f'\n>> Success getting cookie from AI Conductor:\n {self.aic_cookie}', color='green')
            print_color(f'\n>> Success Login: {login_response_json}', color='green')
        else: 
            print_color(f'\n>> Failed Login: {login_response_json}', color='red')   
    
    
    def check_solution_name(self, user_solution_name): 
        solution_data = {
            "workspace_name": self.WORKSPACE_NAME, 
            "only_public": ONLY_PUBLIC 
        }
        solution_name = requests.get(self.URI + AI_SOLUTION, params=solution_data, cookies=self.aic_cookie)
        solution_name_json = solution_name.json()
        # FIXME AIC 초기화시 solution_name이 존재 안할 수 있음 
        if 'solutions' not in solution_name_json.keys(): 
            print_color("<< solutions >> key not found in AI Solution data.", color='yellow')
            pass
        else: 
            solution_list = [sol['name'] for sol in solution_name_json['solutions']]
            # 기존 solution 존재하면 에러 나게 하기 
            if user_solution_name in solution_list: 
                txt = f"\n[Error] Not allowed name: {user_solution_name} - The name already exists in the AI solution list. \n Please enter another name."
                print_color(txt, color='red')
                # 이미 존재하는 solutino list 리스트업 
                pre_existences = pd.DataFrame(solution_list, columns=["Pre-existing AI solutions"])
                print_color("\n\n < Reference: Pre-existing AI solutions list > \n", color='cyan')
                print_color(pre_existences.to_markdown(tablefmt='fancy_grid'), color='cyan')
                raise ValueError("Not allowed solution name.")
        txt = f"[Success] Allowed name: << {user_solution_name} >>" 
        self.solution_name = user_solution_name
        print_color(txt, color='green')


    
    def check_workspace(self): 
        ## workspaces list 확인 
        try: 
            self.workspaces = requests.get(self.URI + SYSTEM_INFO, cookies=self.aic_cookie)
        except: 
            raise NotImplementedError("Failed to get workspaces info.")
        ## workspace_name 의 ECR, S3 주소를 확인 합니다. 
        try: 
            print(self.workspaces.json())
            for ws in self.workspaces.json():
                if self.WORKSPACE_NAME in ws['name']:
                    S3_BUCKET_NAME = ws['s3_bucket_name']
                    ECR_NAME = ws['ecr_base_path']       
        except: 
            raise ValueError("Got wrong workspace info.")
        
        print_color(f"\n[INFO] S3_BUCUKET_URI:", color='green') 
        print_color(f"- public: {S3_BUCKET_NAME['public']}", color='cyan') 
        print_color(f"- private: {S3_BUCKET_NAME['private']}", color='cyan') 

        print_color(f"\n[INFO] ECR_URI:", color='green') 
        print_color(f"- public: {ECR_NAME['public']}", color='cyan') 
        print_color(f"- private: {ECR_NAME['private']}", color='cyan') 

        # workspace로부터 받아온 ecr, s3 정보를 내부 변수화 
        try:
            self.bucket_name = S3_BUCKET_NAME[self.access_scope] # bucket_scope: private, public
            self.ecr = ECR_NAME[self.access_scope]
        except Exception as e:
            raise ValueError(f"Wrong format of << workspaces >> received from REST API:\n {e}")
            
        print_color(f"\n[INFO] AWS ECR URI received: \n {self.ecr}", color='green') 
        print_color(f"\n[INFO] AWS S3 BUCKET NAME received: \n {self.bucket_name}", color='green') 
        
        
    def save_yaml(self):
        # YAML 파일로 데이터 저장
        class NoAliasDumper(Dumper):
            def ignore_aliases(self, data):
                return True
        with open('solution_metadata.yaml', 'w', encoding='utf-8') as yaml_file:
            yaml.dump(self.sm_yaml, yaml_file, allow_unicode=True, default_flow_style=False, Dumper=NoAliasDumper)
            

    def set_yaml(self, pipeline, version=VERSION):
        self.pipeline = pipeline
        self.sm_yaml['version'] = version
        self.sm_yaml['name'] = ''
        self.sm_yaml['description'] = {}
        self.sm_yaml['pipeline'] = []
        self.sm_yaml['pipeline'].append({'type': pipeline})
        # self.sm_yaml['pipeline'].append({'type': 'inference'})
        try: 
            self.save_yaml()
            print_color(f"\n << solution_metadata.yaml >> generated. - current version: v{version}", color='green')
        except: 
            raise NotImplementedError("Failed to generate << solution_metadata.yaml >>")
        
    def append_pipeline(self, pipeline): 
        self.sm_yaml['pipeline'].append({'type': 'inference'})
        self.pipeline = pipeline # 가령 inference 파이프라인 추가 시 인스턴스의 pipeline을 inference 로 변경 
        try: 
            self.save_yaml()
            print_color(f"\n<< solution_metadata.yaml >> updated. - appended pipeline: {pipeline}", color='green')
        except: 
            raise NotImplementedError("Failed to update << solution_metadata.yaml >>")
        
        
    def read_yaml(self, yaml_file_path):
        try:
        # YAML 파일을 읽어옵니다.
            with open(yaml_file_path, 'r') as yaml_file:
                data = yaml.safe_load(yaml_file)

        # 파싱된 YAML 데이터를 사용합니다.
        except FileNotFoundError:
            print(f'File {yaml_file_path} not found.')
        
        if  'solution' in yaml_file_path:
            self.sm_yaml = data
        elif 'experimental' in yaml_file_path:
            self.exp_yaml = data
            if self.exp_yaml['control'][0]['get_asset_source'] == 'every':
                self.exp_yaml['control'][0]['get_asset_source'] = 'once'
            with open(yaml_file_path, 'w') as file:
                yaml.safe_dump(self.exp_yaml, file)
        else:
            pass

    def set_sm_name(self, name):
        self.name = name.replace(" ", "-")
        self.sm_yaml['name'] = self.name


    #def set_description(self, overview, input_data, output_data, user_parameters, algorithm):
    def set_description(self, desc):
        try: 
            self.sm_yaml['description']['title'] = self._check_parammeter(self.solution_name)
            self.set_sm_name(self._check_parammeter(self.solution_name))
            self.sm_yaml['description']['overview'] = self._check_parammeter(desc['overview'])
            self.sm_yaml['description']['input_data'] = self._check_parammeter(self.bucket_name + desc['input_data'])
            self.sm_yaml['description']['output_data'] = self._check_parammeter(self.bucket_name + desc['input_data'])
            self.sm_yaml['description']['user_parameters'] = self._check_parammeter(desc['user_parameters'])
            self.sm_yaml['description']['algorithm'] = self._check_parammeter(desc['algorithm'])
            # FIXME icon 관련 하드코딩 변경필요 
            self.sm_yaml['description']['icon'] = self.icon_s3_uri  
            self.save_yaml()
            print_color(f"\n<< solution_metadata.yaml >> updated. \n- solution metadata description:\n {self.sm_yaml['description']}", color='green')
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << description >> in the solution_metadata.yaml \n{e}")
            

    def set_wrangler(self):
        self.sm_yaml['wrangler_code_uri'] = ''
        self.sm_yaml['wrangler_dataset_uri'] = ''
        self.save_yaml()


    def set_container_uri(self):
        try: 
            data = {'container_uri': self.ecr_full_url} # full url 는 tag 정보까지 포함 
            if self.pipeline == 'train':
                data = {'container_uri': self.ecr_full_url}
                self.sm_yaml['pipeline'][0].update(data)
                print_color(f"[INFO] Completes setting << container_uri >> in solution_metadata.yaml: \n{data['container_uri']}", color='green')
            elif self.pipeline == 'inference':
                data = {'container_uri': self.ecr_full_url}
                self.sm_yaml['pipeline'][1].update(data)
                print_color(f"[INFO] Completes setting << container_uri >> in solution_metadata.yaml: \n{data['container_uri']}", color='green')
            self.save_yaml()
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << container_uri >> in the solution_metadata.yaml \n{e}")


    #s3://s3-an2-cism-dev-aic/artifacts/bolt_fastening_table_classification/train/artifacts/2023/11/06/162000/
    def set_artifacts_uri(self):
        try: 
            data = {'artifact_uri': "s3://" + self.bucket_name + "/ai-solutions/" + self.solution_name + f"/v{VERSION}/" + self.pipeline  + "/artifacts/"}
            if self.pipeline == 'train':
                self.sm_yaml['pipeline'][0].update(data)
            elif self.pipeline =='inference':
                self.sm_yaml['pipeline'][1].update(data)
            self.save_yaml()
            print_color(f"[INFO] Completes setting << artifact_uri >> in solution_metadata.yaml: \n{data['artifact_uri']}", color='green')
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << artifact_uri >> in the solution_metadata.yaml \n{e}")
        
        
    def set_model_uri(self):
        try: 
            # FIXME 주의: set model uri는 추론시에만 call 하지만, artifacts 경로는 train 으로 고정 
            data = {'model_uri': "s3://" + self.bucket_name + "/ai-solutions/" + self.solution_name + f"/v{VERSION}/" + 'train' + "/artifacts/"}
            if self.pipeline == 'train':
                raise ValueError("Setting << model_uri >> in the solution_metadata.yaml is only allowed for << inference >> pipeline. \n - current pipeline: {self.pipeline}")
            elif self.pipeline == 'inference':
                self.sm_yaml['pipeline'][1].update(data)
            self.save_yaml()
            print_color(f"[INFO] Completes setting << model_uri >> in solution_metadata.yaml: \n{data['model_uri']}", color='green')
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << model_uri >> in the solution_metadata.yaml \n{e}")


    def _check_edgeconductor_interface(self, user_dict):
        check_keys = ['support_labeling', 'inference_result_datatype', 'train_datatype']
        allowed_datatypes = ['table', 'image']
        for k in user_dict.keys(): 
            self._check_parammeter(k)
            if k not in check_keys: 
                raise ValueError(f"<< {k} >> is not allowed for edgeconductor_interface key.")
        for k in check_keys: 
            if k not in user_dict.keys(): 
                raise ValueError(f"<< {k} >> must be in the edgeconductor_interface key list.")

        if isinstance(user_dict['support_labeling'], bool):
            pass
        else: 
            raise ValueError("<< support_labeling >> parameter must have boolean type.")
        if user_dict['inference_result_datatype'] not in allowed_datatypes:
            raise ValueError(f"<< inference_result_datatype >> parameter must have the value among these: \n{allowed_datatypes}")
        if user_dict['train_datatype'] not in allowed_datatypes:
            raise ValueError(f"<< train_datatype >> parameter must have the value among these: \n{allowed_datatypes}")                  
        
        
    def set_edge(self, edgeconductor_interface: dict):
        # edgeconductor interface 
        self._check_edgeconductor_interface(edgeconductor_interface)
        self.sm_yaml['edgeconductor_interface'] = edgeconductor_interface
        
        # FIXME edgeapp interface는 우리가 값 채울 필요 X? 
        self.sm_yaml['edgeapp_interface'] = {'redis_server_uri': ""}
        self.save_yaml()


    # def set_train_dataset_uri(self):
    #     pass


    # def set_train_artifact_uri(self):
    #     pass


    def set_candidate_parameters(self):
        self.read_yaml(self.exp_yaml_path)

        def rename_key(d, old_key, new_key): #inner func.
            if old_key in d:
                d[new_key] = d.pop(old_key)
        
        ### candidate parameters setting
        if "train" in self.pipeline:
            self.candidate_params = self.exp_yaml['user_parameters'][0]
            rename_key(self.candidate_params, 'train_pipeline', 'candidate_parameters')
            self.sm_yaml['pipeline'][0].update({'parameters' : self.candidate_params})
        elif "inference" in self.pipeline:
            self.candidate_params = self.exp_yaml['user_parameters'][1]
            rename_key(self.candidate_params, 'inference_pipeline', 'candidate_parameters')
            self.sm_yaml['pipeline'][1].update({'parameters' : self.candidate_params})
        #print(self.sm_yaml['pipeline'][0]['parameters'])

        return self.candidate_params['candidate_parameters']
    
    def set_user_paramters(self):
        ### user parameters setting 
        subkeys = {}
        user_parameters = []
        for step in self.candidate_params['candidate_parameters']:
            output_data = {'step': step['step'], 'args': []} # solution metadata v9 기준 args가 list
            user_parameters.append(output_data)
        subkeys['user_parameters'] = user_parameters
        
        # TODO EdgeCondcutor 인터페이스 테스트 필요
        # selected user parameters는 UI에서 선택시 채워질것 이므로 args를 빈 dict로 채워 보냄
        # 사용자가 미선택시 default로 user paramters에서 복사될 것임    
        ### selected user parameters setting 
        selected_user_parameters = []
        for step in self.candidate_dict['candidate_parameters']:
            output_data = {'step': step['step'], 'args': {}} # solution metadata v9 기준 args가 dict 
            selected_user_parameters.append(output_data)
        subkeys['selected_user_parameters'] = selected_user_parameters
    
        if self.pipeline == 'train':
            self.sm_yaml['pipeline'][0]['parameters'].update(subkeys)
        elif self.pipeline == 'inference':
            self.sm_yaml['pipeline'][1]['parameters'].update(subkeys)
            
        print_color("\n[{self.pipeline}] Success updating << candidate_parameters >> in the solution_metadata.yaml", color='green')
        self.save_yaml()
        
        
    def set_user_parameters(self):
        # user parameters setting 
        # subkeys = {}
        # user_parameters = []
        # for step in self.candidate_dict['candidate_parameters']:
        #     print(step)
        #     print('----------')
        #     output_data = {'step': step['step'], 'args': []} # solution metadata v9 기준 args가 list
        #     user_parameters.append(output_data)
        # subkeys['user_parameters'] = user_parameters
        # return subkeys 
        print(self.candidate_dict['candidate_parameters'])
        data = [] #["data1", "data2", "data3", "data4"]
        for step_info in self.candidate_dict['candidate_parameters']:
            for k in step_info['args'][0].keys(): 
                data.append(step_info['step'] + ' / ' + k)
        checkboxes = [widgets.Checkbox(value=False, description=label) for label in data]
        output = widgets.VBox(children=checkboxes)
        display(output)
        selected_data = []
        for i in range(0, len(checkboxes)):
            if checkboxes[i].value == True:
                selected_data = selected_data + [checkboxes[i].description]
        print(selected_data)
        

    def set_resource(self, resource = 'standard'):
        if "train" in self.pipeline:
            self.sm_yaml['pipeline'][0]["resource"] = {"default": resource}
        elif "inference" in self.pipeline:
            self.sm_yaml['pipeline'][1]["resource"] = {"default": resource}
        print_color(f"\n[{self.pipeline}] Success updating << resource >> in the solution_metadata.yaml", color='green')
        self.save_yaml()


    # FIXME access key file 기반으로 하는거 꼭 필요할지? 
    def s3_access_check(self, contents: str):
        # contents: 'data' or 'artifacts'
        self.s3_path = f'ai-solutions/{self.solution_name}/v{VERSION}/{self.pipeline}/{contents}'
        try:
            f = open(self.s3_access_key_path, "r")
            keys = []
            values = []
            for line in f:
                key = line.split(":")[0]
                value = line.split(":")[1].rstrip()
                keys.append(key)
                values.append(value)
            ACCESS_KEY = values[0]
            SECRET_KEY = values[1]
            self.s3 = boto3.client('s3',
                                aws_access_key_id=ACCESS_KEY,
                                aws_secret_access_key=SECRET_KEY)
        except:
            print_color(f"\n[INFO] Start s3 access check without key file.", color="blue")
            self.s3 = boto3.client('s3')

        # # FIXME 아래 region이 none으로 나옴 
        # my_session = boto3.session.Session()
        # self.region = my_session.region_name
        print_color(f"\n[INFO] AWS region: {self.region}", color="cyan")
        if isinstance(boto3.client('s3'), botocore.client.BaseClient) == True:       
            print_color(f"\n[INFO] AWS S3 access check: OK", color="green")
        else: 
            raise ValueError(f"\n[ERROR] AWS S3 access check: Fail")
          
        return isinstance(boto3.client('s3'), botocore.client.BaseClient)
    
            
    def s3_upload_icon(self):
        # inner func.
        def s3_process(s3, bucket_name, data_path, s3_path):
            objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)
            if 'Contents' in objects_to_delete:
                for obj in objects_to_delete['Contents']:
                    self.s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
                    print_color(f'[INFO] Deleted pre-existing S3 object: {obj["Key"]}', color = 'yellow')
            s3.delete_object(Bucket=bucket_name, Key=s3_path)
            s3.put_object(Bucket=bucket_name, Key=(s3_path +'/'))
            try:    
                response = s3.upload_file(data_path, bucket_name, s3_path)
            except NoCredentialsError as e:
                raise NoCredentialsError(f"NoCredentialsError: \n{e}")
            except ClientError as e:
                print(f"ClientError: ", e)
                return False
            print_color(f"Success uploading into S3 path: {bucket_name + '/' + s3_path}", color='green')
            return True

        # FIXME hardcoding icon.png 솔루션 이름등으로 변경 필요 
        data_path = f'./image/{self.ICON_FILE}'
        s3_file_path = f'icons/{self.solution_name}/{self.ICON_FILE}'
        s3_process(self.s3, self.bucket_name, data_path, s3_file_path)
        self.icon_s3_uri = "s3://" + self.bucket_name + '/' + s3_file_path   # 값을 리스트로 감싸줍니다
        self.sm_yaml['description']['icon'] = self.icon_s3_uri
        self.save_yaml()
        

    def s3_upload_data(self):
        # inner func.
        def s3_process(s3, bucket_name, data_path, local_folder, s3_path, delete=True):
            if delete == True: 
                objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)
                if 'Contents' in objects_to_delete:
                    for obj in objects_to_delete['Contents']:
                        self.s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
                        print_color(f'\n[INFO] Deleted pre-existing S3 object: {obj["Key"]}', color = 'yellow')
                s3.delete_object(Bucket=bucket_name, Key=s3_path)
            s3.put_object(Bucket=bucket_name, Key=(s3_path +'/'))
            try:    
                response = s3.upload_file(data_path, bucket_name, s3_path + "/" + data_path[len(local_folder):])
            except NoCredentialsError as e:
                raise NoCredentialsError("NoCredentialsError: \n{e}")
            except ClientError as e:
                print(f"ClientError: ", e)
                return False
            # temp = s3_path + "/" + data_path[len(local_folder):]
            uploaded_path = bucket_name + '/' + s3_path + '/' + data_path[len(local_folder):]
            print_color(f"\nSuccess uploading into S3: \n{uploaded_path }", color='green')
            return True
 
        if "train" in self.pipeline:
            local_folder = ALODIR + "input/train/"
            print_color(f'\n[INFO] Start uploading data into S3 from local folder:\n {local_folder}', color='cyan')
            try: 
                for root, dirs, files in os.walk(local_folder):
                    for idx, file in enumerate(files):
                        data_path = os.path.join(root, file)
                        if idx == 0: #최초 1회만 delete s3
                            s3_process(self.s3, self.bucket_name, data_path, local_folder, self.s3_path, True) # self.s3_path 는 s3_access_check 할때 셋팅
                        else: 
                            s3_process(self.s3, self.bucket_name, data_path, local_folder, self.s3_path, False)
            except Exception as e: 
                raise NotImplementedError(f'\nFailed to upload local data into << self.s3_path >>') 
            try:    
                data = {'dataset_uri': ["s3://" + self.bucket_name + "/" + self.s3_path + "/"]}  # 값을 리스트로 감싸줍니다
                self.sm_yaml['pipeline'][0].update(data)
                self.save_yaml()
                print_color(f'\nSuccess updating solution_metadata.yaml - << dataset_uri >> info / pipeline: {self.pipeline}', color='green')
            except Exception as e: 
                raise NotImplementedError(f'\nFailed updating solution_metadata.yaml - << dataset_uri >> info / pipeline: {self.pipeline} \n{e}')
        elif "inf" in self.pipeline:
            local_folder = ALODIR + "input/inference/"
            print_color(f'\n[INFO] Start uploading << data >> into S3 from local folder:\n {local_folder}', color='cyan')
            try: 
                for root, dirs, files in os.walk(local_folder):
                    for idx, file in enumerate(files):
                        data_path = os.path.join(root, file)
                        if idx == 0: #최초 1회만 delete s3
                            s3_process(self.s3, self.bucket_name, data_path, local_folder, self.s3_path, True) # self.s3_path 는 s3_access_check 할때 셋팅
                        else: 
                            s3_process(self.s3, self.bucket_name, data_path, local_folder, self.s3_path, False)
            except Exception as e: 
                raise NotImplementedError(f'\nFailed to upload local data into << self.s3_path >>') 
            try:
                data = {'dataset_uri': ["s3://" + self.bucket_name + "/" + self.s3_path + "/"]}  # 값을 리스트로 감싸줍니다
                self.sm_yaml['pipeline'][1].update(data)
                self.save_yaml()
                print_color(f'\nSuccess updating solution_metadata.yaml - << dataset_uri >> info. / pipeline: {self.pipeline}', color='green')
            except Exception as e: 
                raise NotImplementedError(f'\nFailed updating solution_metadata.yaml - << dataset_uri >> info / pipeline: {self.pipeline} \n{e}')
        else:
            raise ValueError(f"Not allowed value for << pipeline >>: {self.pipeline}")


    def s3_upload_artifacts(self):
        # inner func.
        def s3_process(s3, bucket_name, data_path, local_folder, s3_path, delete=True):
            if delete == True: 
                objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)
                if 'Contents' in objects_to_delete:
                    for obj in objects_to_delete['Contents']:
                        self.s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
                        print_color(f'\n[INFO] Deleted pre-existing S3 object: {obj["Key"]}', color = 'yellow')
                s3.delete_object(Bucket=bucket_name, Key=s3_path)
            s3.put_object(Bucket=bucket_name, Key=(s3_path +'/'))
            try:    
                response = s3.upload_file(data_path, bucket_name, s3_path + "/" + data_path[len(local_folder):])
            except NoCredentialsError as e:
                raise NoCredentialsError("NoCredentialsError: \n{e}")
            except ClientError as e:
                print(f"ClientError: ", e)
                return False
            # temp = s3_path + "/" + data_path[len(local_folder):]
            uploaded_path = bucket_name + '/' + s3_path + '/' + data_path[len(local_folder):]
            print_color(f"\nSuccess uploading into S3: \n{uploaded_path }", color='green')
            return True

        
        if "train" in self.pipeline:
            artifacts_path = _tar_dir(".train_artifacts")  # artifacts tar.gz이 저장된 local 경로 return
            local_folder = os.path.split(artifacts_path)[0] + '/'
            print_color(f'\n[INFO] Start uploading << train artifacts >> into S3 from local folder:\n {local_folder}', color='cyan')
            s3_process(self.s3, self.bucket_name, artifacts_path, local_folder, self.s3_path) # self.s3_path 는 s3_access_check 할때 셋팅
            try: 
                artifact_uri = {'artifact_uri': ["s3://" + self.bucket_name + "/" + self.s3_path + "/"]}  # 값을 리스트로 감싸줍니다
                self.sm_yaml['pipeline'][0].update(artifact_uri)
                self.save_yaml()
                print_color(f'\nSuccess updating solution_metadata.yaml - << artifact_uri >> info. / pipeline: {self.pipeline}', color='green')
            except Exception as e: 
                raise NotImplementedError(f'\nFailed updating solution_metadata.yaml - << artifact_uri >> info / pipeline: {self.pipeline} \n{e}')
            finally:
                shutil.rmtree(TEMP_ARTIFACTS_DIR , ignore_errors=True)
        elif "inf" in self.pipeline:
            ## inference artifacts tar gz 업로드 
            artifacts_path = _tar_dir(".inference_artifacts")  # artifacts tar.gz이 저장된 local 경로 
            local_folder = os.path.split(artifacts_path)[0] + '/'
            print_color(f'\n[INFO] Start uploading << inference artifacts >> into S3 from local folder:\n {local_folder}', color='cyan')
            s3_process(self.s3, self.bucket_name, artifacts_path, local_folder, self.s3_path)
            try: 
                artifact_uri = {'artifact_uri': ["s3://" + self.bucket_name + "/" + self.s3_path + "/"]}  # 값을 리스트로 감싸줍니다
                self.sm_yaml['pipeline'][1].update(artifact_uri)
                self.save_yaml()
                print_color(f'\nSuccess updating solution_metadata.yaml - << artifact_uri >> info. / pipeline: {self.pipeline}', color='green')
            except Exception as e: 
                raise NotImplementedError(f'\nFailed updating solution_metadata.yaml - << artifact_uri >> info / pipeline: {self.pipeline} \n{e}')
            finally:
                shutil.rmtree(TEMP_ARTIFACTS_DIR , ignore_errors=True)
            ## model tar gz 업로드 
            # [중요] model_uri는 inference type 밑에 넣어야되는데, 경로는 inference 대신 train이라고 pipeline 들어가야함 (train artifacts 경로에 저장)
            train_artifacts_s3_path = self.s3_path.replace(f'v{VERSION}/inference', f'v{VERSION}/train')
            model_path = _tar_dir(".train_artifacts/models")  # model tar.gz이 저장된 local 경로 return 
            local_folder = os.path.split(model_path)[0] + '/'
            print_color(f'\n[INFO] Start uploading << model >> into S3 from local folder:\n {local_folder}', color='cyan')
            # 주의! 이미 train artifacts도 같은 경로에 업로드 했으므로 model.tar.gz올릴 땐 delete object하지 않는다. 
            s3_process(self.s3, self.bucket_name, model_path, local_folder, train_artifacts_s3_path, delete=False) 
            try: 
                model_uri = {'model_uri': ["s3://" + self.bucket_name + "/" + train_artifacts_s3_path + "/"]}  # 값을 리스트로 감싸줍니다
                self.sm_yaml['pipeline'][1].update(model_uri)
                self.save_yaml()
                print_color(f'\nSuccess updating solution_metadata.yaml - << model_uri >> info. / pipeline: {self.pipeline}', color='green')
            except Exception as e: 
                raise NotImplementedError(f'\nFailed updating solution_metadata.yaml - << model_uri >> info / pipeline: {self.pipeline} \n{e}')
            finally:
                shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
        else:
            raise ValueError(f"Not allowed value for << pipeline >>: {self.pipeline}")
        
        
    def get_contents(self, url):
        def _is_git_url(url):
            git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
            return re.match(git_url_pattern, url) is not None

        contents_path = "./contents"
        if(_is_git_url(url)):
        
            if os.path.exists(contents_path):
                shutil.rmtree(contents_path)  # 폴더 제거
            repo = git.Repo.clone_from(url, "./contents")

    def set_alo(self):
        alo_path = ALODIR
        alo_src = ['main.py', 'src', 'config', 'assets', 'alolib']
        work_path = WORKINGDIR + "alo/"

        if os.path.isdir(work_path):
            shutil.rmtree(work_path)
        os.mkdir(work_path)

        for item in alo_src:
            src_path = alo_path + item
            if os.path.isfile(src_path):
                shutil.copy2(src_path, work_path)
                print_color(f'[INFO] copy from " {src_path} "  -->  " {work_path} " ', color='blue')
            elif os.path.isdir(src_path):
                dst_path = work_path  + os.path.basename(src_path)
                shutil.copytree(src_path, dst_path)
                print_color(f'[INFO] copy from " {src_path} "  -->  " {dst_path} " ', color='blue')
            
        print_color("\n Success ALO directory setting.", color='green')

    def set_docker_contatiner(self):
        try: 
            dockerfile = "Dockerfile"
            spm = 'ENV SOLUTION_PIPELINE_MODE='
            if os.path.isfile(WORKINGDIR + dockerfile):
                os.remove(WORKINGDIR + dockerfile)
            shutil.copy(WORKINGDIR + "origin/" + dockerfile, WORKINGDIR)
            file_path = WORKINGDIR + dockerfile
            d_file = []
            with open(file_path, 'r') as file:
                for line in file:
                    if line.startswith(spm):
                        if line.find(self.pipeline) > 0:
                            # 현재 파이프라인으로 구동
                            pass
                        else:
                            # 다른 파이프라인으로 dockerfile을 수정 후 구동
                            line = line.replace('train', self.pipeline)
                    d_file.append(line)
            data = ''.join(d_file)
            with open(file_path, 'w') as file:
                file.write(data)
            print_color(f"Success DOCKERFILE setting. \n - pipeline: {self.pipeline}", color='green')
        except Exception as e: 
            raise NotImplementedError(f"Failed DOCKERFILE setting. \n - pipeline: {self.pipeline} \n {e}")
        
        
    def set_aws_ecr(self, docker = True, tags = []):
        self.docker = docker
        self.ecr_url = self.ecr.split("/")[0]
        # FIXME 마지막에 붙는 container 이름은 solution_name 과 같게 
        # http://collab.lge.com/main/pages/viewpage.action?pageId=2126915782
        # [중요] container uri 는 magna-ws 말고 magna 같은 식으로 쓴다 (231207 임현수C)
        ecr_scope = self.URI_SCOPE.split('-')[0] # magna-ws --> magna
        self.ecr_repo = self.ecr.split("/")[1] + "/ai-solutions/" + ecr_scope + "/" + self.solution_name + "/" + self.pipeline + "/"  + self.solution_name  
        self.ecr_full_url = self.ecr_url + '/' + self.ecr_repo 
        if self.docker == True:
            run = 'docker'
        else:
            run = 'buildah'

        print_color(f"[INFO] target AWS ECR url: \n{self.ecr_url}", color='blue')

        p1 = subprocess.Popen(
            ['aws', 'ecr', 'get-login-password', '--region', f'{self.region}'], stdout=subprocess.PIPE
        )
        p2 = subprocess.Popen(
            [f'{run}', 'login', '--username', 'AWS','--password-stdin', f'{self.ecr_url}'], stdin=p1.stdout, stdout=subprocess.PIPE
        )
        p1.stdout.close()
        output = p2.communicate()[0]

        print_color(f"[INFO] AWS ECR | docker login result: \n {output.decode()}", color='cyan')
        print_color(f"[INFO] Target AWS ECR repository: \n{self.ecr_repo}", color='cyan')

        if len(tags) > 0:
            command = [
            "aws",
            "ecr",
            "create-repository",
            "--region", self.region,
            "--repository-name", self.ecr_repo,
            "--image-scanning-configuration", "scanOnPush=true",
            "--tags"
            ] + tags  # 전달된 태그들을 명령어에 추가합니다.
        else:
            command = [
            "aws",
            "ecr",
            "create-repository",
            "--region", self.region,
            "--repository-name", self.ecr_repo,
            "--image-scanning-configuration", "scanOnPush=true",
            ]
        # subprocess.run() 함수를 사용하여 명령을 실행합니다.
        try:
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print_color(f"\n[INFO] AWS ECR create-repository response: \n{result.stdout}", color='cyan')
        except subprocess.CalledProcessError as e:
            raise NotImplementedError(f"Failed to AWS ECR create-repository:\n + {e}")


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
        
    # FIXME 그냥 무조건 latest로 박히나? 
    def build_docker(self):
        if self.docker:
            subprocess.run(['docker', 'build', '.', '-t', f'{self.ecr_full_url}:{self.ECR_TAG}'])
        else:
            subprocess.run(['sudo', 'buildah', 'build', '--isolation', 'chroot', '-t', f'{self.ecr_full_url}:{self.ECR_TAG}'])


    def docker_push(self):
        if self.docker:
            subprocess.run(['docker', 'push', f'{self.ecr_full_url}:{self.ECR_TAG}'])
        else:
            subprocess.run(['sudo', 'buildah', 'push', f'{self.ecr_full_url}:{self.ECR_TAG}'])
        if self.docker:
            subprocess.run(['docker', 'logout'])
        else:
            subprocess.run(['sudo', 'buildah', 'logout', '-a'])

    
    def register_solution(self): 
        try: 
            # 등록을 위한 형태 변경
            data = {
            "scope_ws": self.URI_SCOPE,
            "metadata_json": self.sm_yaml
            }
            data =json.dumps(data)
            solution_params = {
                "workspace_name": self.WORKSPACE_NAME
            }
            # AI 솔루션 등록
            post_response = requests.post(self.URI + AI_SOLUTION, params=solution_params, data=data, cookies=self.aic_cookie)
            self.register_solution_response = post_response.json()
            print_color(f"[INFO] AI solution register response: \n {self.register_solution_response}", color='cyan')
        except Exception as e: 
            raise NotImplementedError(f"Failed to register AI solution: \n {e}")
        
        
    def register_solution_instance(self): 
        solution_id = self.register_solution_response['version']['id']
        save_json = {"server_uri" : self.URI,
            "name" : self.solution_name,
            "version_id": solution_id,
            "workspace_name": self.WORKSPACE_NAME}
        try:
            # 폴더가 이미 존재하는 경우 삭제합니다.
            if os.path.exists(self.interface_dir):
                shutil.rmtree(self.interface_dir)
            # 새로운 폴더를 생성합니다.
            os.mkdir(self.interface_dir)
        except Exception as e:
            raise NotImplementedError(f"Failed to generate interface directory while registering solution instance: \n {e}")

        with open(self.interface_dir + "/solution_certification.json", 'w') as outfile:
            json.dump(save_json, outfile)

        with open("./interface/solution_certification.json", 'r') as outfile:
            interface = json.load(outfile)
            
        self.solution_instance_params = {"name": interface['name'],
        "solution_version_id": interface['version_id'],
        "workspace_name": interface['workspace_name']
        }
        print_color(f"\n[INFO] AI solution interface information: \n {self.solution_instance_params}", color='blue')
        # solution instance 등록
        solution_instance = requests.post(interface['server_uri'] + SOLUTION_INSTANCE, params=self.solution_instance_params, cookies=self.aic_cookie)
        self.solution_instance = solution_instance.json()
        print_color(f"\n[INFO] AI solution instance register response: \n {self.solution_instance}", color='cyan')
    
    
    # FIXME [?] stream 요청은 무조건 train만 지원인지 현재? 
    def register_stream(self): 
        # stream 등록 
        instance_params = {
            "name": self.solution_instance['name'],
            "instance_id": self.solution_instance['id'],
            "workspace_name": self.solution_instance['workspace_name']
        }
        with open("./interface/solution_certification.json", 'r') as outfile:
            interface = json.load(outfile)
        stream = requests.post(interface['server_uri'] + STREAMS, params=instance_params, cookies=self.aic_cookie)
        self.stream = stream.json() 
        print_color(f"[INFO] AI solution stream register response: \n {self.stream}", color='cyan')
        

    def request_run_stream(self): 
        # Train pipeline 요청
        # solution_metadata.yaml을 읽어서 metadata_json에 넣기
        # [?] config path? 
        # solution_metadata.yaml 읽어오기 
        # YAML 파일 경로
        
        # YAML 파일을 읽어서 parsing
        with open(self.sm_yaml_file_path, 'r') as file:
            yaml_data = yaml.safe_load(file)
        data = {
        "metadata_json": yaml_data,
        "config_path": "" # FIXME config_path는 일단 뭐넣을지 몰라서 비워둠 
        }
        data =json.dumps(data)
        # stream 등록 
        stream_params = {
        "stream_id": self.stream['id'],
        "workspace_name": self.stream['workspace_name']
        }
        with open("./interface/solution_certification.json", 'r') as outfile:
            interface = json.load(outfile)
        stream_history = requests.post(interface['server_uri'] + f"{STREAMS}/{self.stream['id']}/start", params=stream_params, data=data, cookies=self.aic_cookie)
        self.stream_history = stream_history.json()
        print_color(f"[INFO] Run pipeline << {self.pipeline} >> response: \n {self.stream_history}", color='cyan')


    def get_stream_status(self):
        # [?] 계속 running 상태여서 artifacts 안생기는 듯 
        # Train pipeline 확인
        stream_history_parmas = {
            "stream_history_id": self.stream_history['id'],
            "workspace_name": self.stream_history['workspace_name']
        }
        with open("./interface/solution_certification.json", 'r') as outfile:
            interface = json.load(outfile)
        info = requests.get(interface['server_uri'] + f"{STREAMS}/{self.stream_history['id']}/info", params=stream_history_parmas, cookies=self.aic_cookie)
        print_color(f"Stream status: {info.json()['status']}", color="cyan") 


    def download_artifacts(self): 
        def split_s3_path(s3_path): #inner func.
            # 's3://'를 제거하고 '/'를 기준으로 첫 부분을 분리하여 bucket과 나머지 경로를 얻습니다.
            path_parts = s3_path.replace('s3://', '').split('/', 1)
            bucket = path_parts[0]
            rest_of_the_path = path_parts[1]
            return bucket, rest_of_the_path
        try: 
            s3 = boto3.client('s3')
            s3_bucket = split_s3_path(self.stream_history['train_artifact_uri'])[0]
            s3_prefix = split_s3_path(self.stream_history['train_artifact_uri'])[1]
            # S3 버킷에서 파일 목록 가져오기
            objects = s3.list_objects(Bucket=s3_bucket, Prefix=s3_prefix)
            # 파일 다운로드
            for obj in objects.get('Contents', []):
                key = obj['Key']
                filename = key.split('/')[-1]  # 파일 이름 추출
                s3.download_file(s3_bucket, key, filename)
                print_color(f'Downloaded: {filename}', color='cyan')
        except: 
            raise NotImplementedError("Failed to download train artifacts.")
    
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
    os.makedirs(TEMP_ARTIFACTS_DIR , exist_ok=True)
    os.makedirs(TEMP_MODEL_DIR, exist_ok=True)
    last_dir = None
    if 'models' in _path: 
        _save_path = TEMP_MODEL_DIR + 'model.tar.gz'
        last_dir = 'models/'
    else: 
        _save_file_name = _path.strip('.') 
        _save_path = TEMP_ARTIFACTS_DIR +  f'{_save_file_name}.tar.gz' 
        last_dir = _path # ex. .train_artifacts/
    tar = tarfile.open(_save_path, 'w:gz')
    for root, dirs, files in os.walk(ALODIR  + _path):
        base_dir = root.split(last_dir)[-1] + '/'
        for file_name in files:
            #https://stackoverflow.com/questions/2239655/how-can-files-be-added-to-a-tarfile-with-python-without-adding-the-directory-hi
            tar.add(os.path.join(root, file_name), arcname = base_dir + file_name) # /home부터 시작하는 절대 경로가 아니라 .train_artifacts/ 혹은 moddels/부터 시작해서 압축해야하므로 
    tar.close()
    
    return _save_path


if __name__ == "__main__":
    user_input ={
        # 시스템 URI
        'URI': "http://10.158.2.243:9999/", 
        
        # workspace 이름 
        'WORKSPACE_NAME': "magna-ws", # "cism-ws"
        
        # 로그인 정보 
        'LOGIN_ID': '', # "cism-dev"
        'LOGIN_PW': '', # "cism-dev@com"
        
        
        # ECR에 올라갈 컨테이너 URI TAG 
        'ECR_TAG': 'latest', 
        
        # scripts/creating_ai_solution/image/ 밑에 UI에 표시될 아이콘 이미지 파일 (ex. icon.png) 를 업로드 해주세요. 
        # 이후 해당 아이콘 파일 명을 아래에 기록 해주세요.
        'ICON_FILE': 'icon.png'
    }
    registerer = RegisterUtils(user_input)


