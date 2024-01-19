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
from copy import deepcopy 
from pprint import pprint
# yaml = YAML()
# yaml.preserve_quotes = True
#----------------------------------------#
#              REST API                  #
#----------------------------------------#
ALODIR = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__)))) + '/'
TEMP_ARTIFACTS_DIR = ALODIR + '.temp_artifacts_dir/'
# 외부 model.tar.gz (혹은 부재 시 해당 경로 폴더 통째로)을 .train_artifacts/models 경로로 옮기기 전 임시 저장 경로 
TEMP_MODEL_DIR = ALODIR + '.temp_model_dir/'
#---------------------------------------------------------
WORKINGDIR = os.path.abspath(os.path.dirname(__file__)) + '/'

class SolutionRegister:
    #def __init__(self, workspaces, uri_scope, tag, name, pipeline):
    def __init__(self, cloud_setup_path=None, api_uri_path=None):
        

        self.print_step("Initiate ALO operation mode")
        print_color("[SYSTEM] Solutoin 등록에 필요한 setup file 들을 load 합니다. ", color="green")

        if not cloud_setup_path:
            cloud_setup_path = "./infra_setup.yaml" 
            print(f"Infra setup 파일이 존재 하지 않으므로, Default 파일을 load 합니다. (path: {cloud_setup_path})")
        try:    
            with open(cloud_setup_path) as f:
                self.cloud_setup = yaml.safe_load(f)
                pprint(self.cloud_setup)
        except Exception as e : 
            raise ValueError(e)

        if not api_uri_path:
            api_uri_path = "./api_setup.yaml" 
            print(f"\nAPI setup 파일이 존재 하지 않으므로, Default 파일을 load 합니다. (path: {api_uri_path})")
        try:    
            with open(api_uri_path) as f:
                self.api_uri = yaml.safe_load(f)
                pprint(self.api_uri)
        except Exception as e : 
            raise ValueError(e)


        ####################################
        ########### Configuration ##########
        ####################################

        # solution instance 등록을 위한 interface 폴더 
        self.interface_dir = './interface'
        self.sm_yaml_file_path = './solution_metadata.yaml'
        self.exp_yaml_path = "../../config/experimental_plan.yaml"
        self.wrangler_path = "./wrangler/wrangler.py"
        self.icon_path = "./icons/"


        # TODO aws login 방법 고민필요
        if self.cloud_setup["AIC_URI"] == "https://web.aic-dev.lgebigdata.com/": ## 실계정
            self.s3_access_key_path = "/nas001/users/ruci.sung/aws.key"  ##  
        else:  ## 현수 kube
            self.s3_access_key_path = "/nas001/users/sehyun.song/aws.key"    ##
        print_color(f"[SYSTEM] S3 key 파일을 로드 합니다. (file: {self.s3_access_key_path})", color="green")


        ## internal variables
        self.sm_yaml = {}  ## core
        self.exp_yaml = {} ## core

        self.pipeline = None 
        self.workspaces = None
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
        
    
    ################################################
    ################################################
    def print_step(self, step_name):
        print_color("\n#########################################", color='blue')
        print_color(f'#######    {step_name}', color='blue')
        print_color("#########################################\n", color='blue')


    def login(self, id, pw): 
        # 로그인 (관련 self 변수들은 set_user_input 에서 setting 됨)

        self.print_step("Login to AI Conductor")

        login_data = json.dumps({
            "login_id": id,
            "login_pw": pw
        })
        try:
            if self.cloud_setup["LOGIN_MODE"] == 'ldap':
                login_response = requests.post(self.cloud_setup["AIC_URI"] + self.api_uri["LDAP_LOGIN"], data = login_data)
                print(login_response)
            else:
                login_response = requests.post(self.cloud_setup["AIC_URI"] + self.api_uri["STATIC_LOGIN"], data = login_data)
        except Exception as e:
            print(e)

        login_response_json = login_response.json()

        cookies = login_response.cookies.get_dict()
        access_token = cookies.get('access-token', None)
        self.aic_cookie = {
        'access-token' : access_token 
        }

        response_workspaces = []
        for ws in login_response_json["workspace"]:
            response_workspaces.append(ws["name"])
        print(f"해당 계정으로 접근 가능한 workspace list: {response_workspaces}")

        # TODO : case1~4 에 대해 사용자가 가이드 받을 수 있도록 하기 
        ## 로그인 접속은  계정 존재 / 권한 존재 의 경우로 나뉨
        ##   - case1: 계정 O / 권한 X 
        ##   - case2: 계정 O / 권한 single (ex cism-ws) 
        ##   - case3: 계정 O / 권한 multi (ex cism-ws, magna-ws) -- 권한은 workspace 단위로 부여 
        ##   - case4: 계정 X  ()
        if login_response_json['account_id']:
            if self.debugging:
                print_color(f'[SYSTEM] Success getting cookie from AI Conductor:\n {self.aic_cookie}', color='green')
                print_color(f'[SYSTEM] Success Login: {login_response_json}', color='green')
            if self.cloud_setup["WORKSPACE_NAME"] in response_workspaces:
                msg = f'[SYSTEM] 접근 요청하신 workspace ({self.cloud_setup["WORKSPACE_NAME"]}) 은 해당 계정으로 접근 가능합니다.'
                print_color(msg, color='green')
            else:
                msg = f'[SYSTEM] 접근 요청하신 workspace ({self.cloud_setup["WORKSPACE_NAME"]}) 은 해당 계정으로 접근 불가능 합니다.'
                raise ValueError()
        else: 
            print_color(f'\n>> Failed Login: {login_response_json}', color='red')   


    def check_solution_name(self, name): 
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


        # 231207 임현수C: 사용자는 public 사용못하게 해달라 
        ONLY_PUBLIC = 1 #1 --> 1로 해야 public, private 다 받아옴 

        solution_data = {
            "workspace_name": self.cloud_setup["WORKSPACE_NAME"], 
            "only_public": ONLY_PUBLIC,
            "page_size": 100
        }
        aic = self.cloud_setup["AIC_URI"]
        api = self.api_uri["AI_SOLUTION"]

        solution_name = requests.get(aic+api, params=solution_data, cookies=self.aic_cookie)
        # print(solution_name)
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

    def set_description(self, description):
        """솔루션 설명을 solution_metadata 에 삽입합니다. 

        Attributes:
          - desc (dict): title, overview, input_data (format descr.), output_data (format descr.),
          user_parameters, algorithm 에 대한 설명문을 작성한다. 
          추후 mark-up 지원여부 
        """

        self.print_step("Set AI Solution Description")

        try: 
            self.sm_yaml['description'].update(description)
            self.sm_yaml['description']['title'] = description['title'].replace(" ", "-")

            # self.sm_yaml['description']['title'] = self._check_parammeter(desc['title'])
            # set_sm_name(self._check_parammeter(self.solution_name))
            # self.sm_yaml['description']['overview'] = self._check_parammeter(desc['overview'])
            # self.sm_yaml['description']['input_data'] = self._check_parammeter(self.bucket_name + desc['input_data'])
            # self.sm_yaml['description']['output_data'] = self._check_parammeter(self.bucket_name + desc['input_data'])
            # self.sm_yaml['description']['user_parameters'] = self._check_parammeter(desc['user_parameters'])
            # self.sm_yaml['description']['algorithm'] = self._check_parammeter(desc['algorithm'])
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
            with open(self.wrangler_path, 'r') as file:
                python_content = file.read()

            self.sm_yaml['wrangler_code_uri'] = python_content
            self.sm_yaml['wrangler_dataset_uri'] = ''
            self._save_yaml()
        except:
            msg = f"[WARNING] wrangler.py 가 해당 위치에 존재해야 합니다. (path: {self.wrangler_path})"
            print_color(msg, color="yellow")

            self.sm_yaml['wrangler_code_uri'] = ''
            self.sm_yaml['wrangler_dataset_uri'] = ''
            self._save_yaml()
        
    def set_edge(self, metadata_value: dict):
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

    def set_resource_display(self):
        """AI Conductor 에서 학습에 사용될 resource 를 선택 하도록, 리스트를 보여 줍니다. 
        """
        self.print_step(f"Display {self.pipeline} Resource List")

        aic = self.cloud_setup["AIC_URI"]
        api = self.api_uri["SYSTEM_INFO"]
        try: 
            self.workspaces = requests.get(aic+api, cookies=self.aic_cookie)
        except: 
            raise NotImplementedError("[ERROR] Failed to get workspaces info.")


        resource_list = []
        try: 
            for ws in self.workspaces.json()["workspaces"]:
                if self.cloud_setup["WORKSPACE_NAME"] in ws['name']:
                    df = pd.DataFrame(ws['execution_specs'])

                    for spec in ws['execution_specs']:
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

        aic = self.cloud_setup["AIC_URI"]
        api = self.api_uri["SYSTEM_INFO"]

        try: 
            self.workspaces = requests.get(aic+api, cookies=self.aic_cookie)
        except: 
            raise NotImplementedError("Failed to get workspaces info.")

        ## workspace_name 의 ECR, S3 주소를 확인 합니다. 
        try: 
            # print(self.workspaces.json()['workspaces'])
            for ws in self.workspaces.json()['workspaces']:
                # print(ws.items())
                if self.cloud_setup["WORKSPACE_NAME"] in ws['name']:
                    S3_BUCKET_NAME = ws['s3_bucket_name']
                    ECR_NAME = ws['ecr_base_path']       
        except: 
            raise ValueError("Got wrong workspace info.")
        
        if self.debugging:
            print_color(f"\n[INFO] S3_BUCUKET_URI:", color='green') 
            print_color(f"- public: {S3_BUCKET_NAME['public']}", color='cyan') 
            print_color(f"- private: {S3_BUCKET_NAME['private']}", color='cyan') 

            print_color(f"\n[INFO] ECR_URI:", color='green') 
            print_color(f"- public: {ECR_NAME['public']}", color='cyan') 
            print_color(f"- private: {ECR_NAME['private']}", color='cyan') 

        # workspace로부터 받아온 ecr, s3 정보를 내부 변수화 
        try:
            self.bucket_name = S3_BUCKET_NAME[self.cloud_setup["SOLUTION_TYPE"]] # bucket_scope: private, public
            self.bucket_name_icon = S3_BUCKET_NAME["public"] # icon 은 공용 저장소에만 존재. = public
            self.ecr_name = ECR_NAME[self.cloud_setup["SOLUTION_TYPE"]]
        except Exception as e:
            raise ValueError(f"Wrong format of << workspaces >> received from REST API:\n {e}")
            
        print_color(f"[SYSTEM] AWS ECR:  ", color='green') 
        print(f"{self.ecr_name}") 
        print_color(f"[SYSTEM] AWS S3 buckeet:  ", color='green') 
        print(f"{self.bucket_name}") 


    #s3://s3-an2-cism-dev-aic/artifacts/bolt_fastening_table_classification/train/artifacts/2023/11/06/162000/
    def set_pipeline_uri(self, mode):
        """ dataset, artifacts, model 중에 하나를 선택하면 이에 맞느 s3 uri 를 생성하고, 이를 solution_metadata 에 반영한다.

        Attributes:
          - mode (str): dataset, artifacts, model 중에 하나 선택

        Returns:
          - uri (str): s3 uri 를 string 타입으로 반환 함 
        """
        version = str(int(self.cloud_setup['VERSION']))
        if mode == "artifact":
            prefix_uri = "/ai-solutions/" + self.solution_name + f"/v{version}/" + self.pipeline  + "/artifacts/"
            uri = {'artifact_uri': "s3://" + self.bucket_name + "/" + prefix_uri}
        elif mode == "data":
            prefix_uri = "ai-solutions/" + self.solution_name + f"/v{version}/" + self.pipeline  + "/data/"
            uri = {'dataset_uri': ["s3://" + self.bucket_name + "/" + prefix_uri]}
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

            self.sm_yaml['pipeline'][self.sm_pipe_pointer].update(uri)
            self._save_yaml()
        except Exception as e: 
            raise NotImplementedError(f"Failed to set << artifact_uri >> in the solution_metadata.yaml \n{e}")
        
        print_color(f'[SUCCESS] Update solution_metadata.yaml:', color='green')
        if mode == "artifacts":
            print(f'pipeline: type: {self.pipeline}, artifact_uri: {uri} ')
        elif mode == "data":
            print(f'pipeline: type: {self.pipeline}, dataset_uri: {uri} ')
        else: ## model
            print(f'pipeline: type:{self.pipeline}, model_uri: {uri} ')
            

        return prefix_uri


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
            self.s3_client = boto3.client('s3',
                                aws_access_key_id=ACCESS_KEY,
                                aws_secret_access_key=SECRET_KEY)
        except:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            self.s3_client = boto3.client('s3')

        # # FIXME 아래 region이 none으로 나옴 
        # my_session = boto3.session.Session()
        # self.region = my_session.region_name
        print(f"[INFO] AWS region: {self.cloud_setup['REGION']}")
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
            print_color(f"[SUCCESS] update train_data to S3:", color='green')
            print(f"{uploaded_path }")
            return True


        try:
            s3_prefix_uri = self.set_pipeline_uri(mode="data")
        except Exception as e: 
            raise NotImplementedError(f'[ERROR] Failed updating solution_metadata.yaml - << dataset_uri >> info / pipeline: {self.pipeline} \n{e}')
 
        if "train" in self.pipeline:
            local_folder = ALODIR + "input/train/"
            print_color(f'[SYSTEM] Start uploading data into S3 from local folder:', color='cyan')
            print(f'{local_folder}')

            try: 
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
            local_folder = ALODIR + "input/inference/"
            print_color(f'[INFO] Start uploading data into S3 from local folder:', color='cyan')
            print(f'{local_folder}')

            try: 
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
                response = s3.upload_file(data_path, bucket_name, s3_path + "/" + data_path[len(local_folder):])
            except NoCredentialsError as e:
                raise NoCredentialsError("NoCredentialsError: \n{e}")
            except ClientError as e:
                print(f"ClientError: ", e)
                return False
            # temp = s3_path + "/" + data_path[len(local_folder):]
            uploaded_path = bucket_name + '/' + s3_path + '/' + data_path[len(local_folder):]
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
            shutil.rmtree(TEMP_ARTIFACTS_DIR , ignore_errors=True)

        elif "inference" in self.pipeline:
            ## inference artifacts tar gz 업로드 
            artifacts_path = _tar_dir(".inference_artifacts")  # artifacts tar.gz이 저장된 local 경로 
            local_folder = os.path.split(artifacts_path)[0] + '/'
            print_color(f'[INFO] Start uploading inference artifacts into S3 from local folder:', color='cyan')
            print(f'{local_folder}')

            s3_process(self.s3_client, self.bucket_name, artifacts_path, local_folder, s3_prefix_uri)
            shutil.rmtree(TEMP_ARTIFACTS_DIR , ignore_errors=True)


            ## model tar gz 업로드 
            # [중요] model_uri는 inference type 밑에 넣어야되는데, 경로는 inference 대신 train이라고 pipeline 들어가야함 (train artifacts 경로에 저장)
            version = str(int(self.cloud_setup['VERSION']))
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
                shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)

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

        self.print_step("Set AWS ECR")
        self._set_alo()  # copy alo folders
        ##TODO : ARM/AMD 에 따라 다른 dockerfile 설정
        self._set_docker_contatiner()  ## set docerfile

        if self.cloud_setup["BUILD_METHOD"] == 'docker':
            ## docker login 실행 
            self._set_aws_ecr(docker=True)
        else:  ##buildah
            self._set_aws_ecr(docker=False, tags=self.cloud_setup["BUILDAH_TAGS"]) 

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
        ecr_scope = self.cloud_setup["WORKSPACE_NAME"].split('-')[0] # magna-ws --> magna
        self.ecr_repo = self.ecr_name.split("/")[1] + '/' + ecr_scope + "/ai-solutions/" + self.solution_name + "/" + self.pipeline + "/"  + self.solution_name  
        self.ecr_full_url = self.ecr_url + '/' + self.ecr_repo 

        ## 동일 이름의 ECR 존재 시, 삭제하고 다시 생성한다. 
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
            ecr_client = boto3.client('ecr',
                                aws_access_key_id=ACCESS_KEY,
                                aws_secret_access_key=SECRET_KEY,
                                region_name=self.cloud_setup['REGION'])
        except:
            print_color(f"[INFO] Start s3 access check without key file.", color="blue")
            ecr_client = boto3.client('ecr')

        ### TEST 
        # resp = ecr_client.describe_repositories(repositoryNames=['086558720570'])
        # print("SSH!!!!:   ", resp['repositories'])

        repos = ecr_client.describe_repositories(
            maxResults=600  ## 갯수가 작아서 찾지 못하는 Issue 있었음 (24.01)
            )
        for repo in repos['repositories']:
            # print(repo['repositoryName'])
            if repo['repositoryName'] == self.ecr_repo:
                print_color(f"[SYSTEM] Repository {self.ecr_repo} already exists. Deleting...", color='yellow')
                ecr_client.delete_repository(repositoryName=self.ecr_repo, force=True)

        # print(f"Creating new repository {repository_name}") 
        # ecr_client.create_repository(repositoryName=repository_name)


        if self.docker == True:
            run = 'docker'
        else:
            run = 'buildah'

        print_color(f"[SYSTEM] target AWS ECR url: ", color='blue')
        print(f"{self.ecr_url}",)

        p1 = subprocess.Popen(
            ['aws', 'ecr', 'get-login-password', '--region', f'{self.cloud_setup["REGION"]}'], stdout=subprocess.PIPE
        )
        p2 = subprocess.Popen(
            [f'{run}', 'login', '--username', 'AWS','--password-stdin', f'{self.ecr_url}'], stdin=p1.stdout, stdout=subprocess.PIPE
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
            "--region", self.cloud_setup["REGION"],
            "--repository-name", self.ecr_repo,
            "--image-scanning-configuration", "scanOnPush=true",
            "--tags"
            ] + tags  # 전달된 태그들을 명령어에 추가합니다.
        else:
            command = [
            "aws",
            "ecr",
            "create-repository",
            "--region", self.cloud_setup["REGION"],
            "--repository-name", self.ecr_repo,
            "--image-scanning-configuration", "scanOnPush=true",
            ]
        # subprocess.run() 함수를 사용하여 명령을 실행합니다.
        try:
            # result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # print_color(f"[INFO] AWS ECR create-repository response: \n{result.stdout}", color='cyan')
            resp = ecr_client.create_repository(repositoryName=self.ecr_repo, tags=tags)
            print_color(f"[SYSTEM] AWS ECR create-repository response: ", color='cyan')
            print(f"{resp}")
        except subprocess.CalledProcessError as e:
            raise NotImplementedError(f"Failed to AWS ECR create-repository:\n + {e}")

    # FIXME 그냥 무조건 latest로 박히나? 
    def _build_docker(self):
        build_command = []

        # CPU/GPU 선택
        if self.use_gpu:
            build_command.extend(['--build-arg', 'USE_GPU=true'])
        else:
            build_command.extend(['--build-arg', 'USE_CPU=true'])

        # ARM/AMD 아키텍처 선택
        if self.architecture == 'ARM':
            build_command.extend(['--build-arg', 'ARCHITECTURE=arm'])
        elif self.architecture == 'AMD':
            build_command.extend(['--build-arg', 'ARCHITECTURE=amd'])

        # Train/Inference 선택
        if self.mode == 'Train':
            build_command.extend(['--build-arg', 'MODE=train'])
        elif self.mode == 'Inference':
            build_command.extend(['--build-arg', 'MODE=inference'])

        # Docker 또는 Buildah 사용
        if self.docker:
            build_command = ['docker', 'build', '.'] + build_command + ['-t', f'{self.ecr_full_url}:{self.cloud_setup["ECR_TAG"]}']
        else:
            build_command = ['sudo', 'buildah', 'build', '--isolation', 'chroot'] + build_command + ['-t', f'{self.ecr_full_url}:{self.cloud_setup["ECR_TAG"]}']

        subprocess.run(build_command)


    def _docker_push(self):
        if self.docker:
            subprocess.run(['docker', 'push', f'{self.ecr_full_url}:{self.cloud_setup["ECR_TAG"]}'])
        else:
            subprocess.run(['sudo', 'buildah', 'push', f'{self.ecr_full_url}:{self.cloud_setup["ECR_TAG"]}'])
        if self.docker:
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

    def set_candidate_parameters(self, display_table=True):
        """experimental_plan.yaml 에서 제작한 parameter 들으 보여주고, 기능 정의 하도록 한다.
        """
        self.print_step("Display User Parameter List:")


        self._read_experimentalplan_yaml(self.exp_yaml_path)

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
                user_parameters = []
                for step in pipe_dict['candidate_parameters']:
                    output_data = {'step': step['step'], 'args': []} # solution metadata v9 기준 args가 list
                    user_parameters.append(output_data)
                subkeys['user_parameters'] = user_parameters
                subkeys['selected_user_parameters'] = user_parameters
        
                self.sm_yaml['pipeline'][self.sm_pipe_pointer].update({'parameters':subkeys})
                print(subkeys)
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
    
    def check_user_parameters():
        """ 입력한 user_parametrs 가 edge conductor 가 요구하는 format 에 맞는지 확인한다. 

        1) candidate 와 동일한 step 을 가지고 있는가? -- 없다면 내부에서 만들어냄
        2) parameter 가 candidate 와 동일 step 에 존재 하는지 확인 
        3) parameter 가 가져야 할 key 를 전부 가지고 있는가? 
        4) parameter 의 key 별 허용값을 

        """
        # - name: parameters name
        #   description: description param
        #   type: float | string | int | single_selection | multi_selection
        #   selectable:
        #     - option1
        #     - option2
        #     - option3
        #   default:
        #     - option1
        #   range: range of float or int or length of string
        # --------- float 입력 시 ---------------------
        #  - name: float_param
        #    description: this is param to input float
        #    type: float
        #    default:
        #      - 0.5
        #    range:
        #      - 0.0
        #      - 1.0
        # --------- string 입력 시 ---------------------
        #  - name: string_param
        #    description: this is param to input string
        #    type: string
        #    default:
        #      - hello  "x1, x2, x3,"
        #    range:
        #      - 5
        #      - 100
        # --------- string-selection 입력 시 ---------------------
        #  - name: single_selection_param
        #    description: this is param to input single selection
        #    type: single_selection
        #    selectable:
        #      - option1
        #      - option2
        #      - option4
        #    default:
        #      - option1
        # --------- multiple-selection 입력 시 ---------------------
        #  - name: multi_selection_param
        #    description: this is param to input multi selection
        #    type: multi_selection
        #    selected:
        #      - option1
        #      - option2
        #      - option3
        #    default:
        #      - option1
        #      - option3 
       



    def set_user_parameters(self, user_parameters={}):
        """ 사용자가 입력한 user_parameter 를 candidate_parameter 와 비교하여 이상값를 찾아낸다. 
        문제 없다면 solution_metadata 에 반영한다. 

        Attributes:
          - user_parameter (dict): UI 로 표현하고 싶은 parameter 를 선택하고, format 을 결정한다.
        """

        if len(self.candidate_params_df) == 0 : 
            raise ValueError("set_candidate_parameter() 를 호출하여 선택가능한 parameter 를 확인 합니다.")



        user_parameters = deepcopy(user_parameters) # 안하면 jupyter의 user_parameters 리스트와 메모리 공유 돼서 꼬임 
        ### user parameters setting 
        subkeys = {}
        # 빈 user_parameters 생성 
        if len(user_parameters) == 0: 
            for step in self.candidate_params['candidate_parameters']:
                output_data = {'step': step['step'], 'args': []} # solution metadata v9 기준 args가 list
                user_parameters.append(output_data)
        subkeys['user_parameters'] = user_parameters
        
        # TODO EdgeCondcutor 인터페이스 테스트 필요
        # selected user parameters는 UI에서 선택시 채워질것 이므로 args를 빈 dict로 채워 보냄
        # 사용자가 미선택시 default로 user paramters에서 복사될 것임    
        ### selected user parameters setting 
        selected_user_parameters = []
        for step in self.candidate_params['candidate_parameters']:
            output_data = {'step': step['step'], 'args': {}} # solution metadata v9 기준 args가 dict 
            selected_user_parameters.append(output_data)
        subkeys['selected_user_parameters'] = selected_user_parameters
    
        if self.pipeline == 'train':
            self.sm_yaml['pipeline'][0]['parameters'].update(subkeys)
        elif self.pipeline == 'inference':
            self.sm_yaml['pipeline'][1]['parameters'].update(subkeys)
            
        print_color("\n[{self.pipeline}] Success updating << user_parameters >> in the solution_metadata.yaml", color='green')
        self._save_yaml()

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


    #####################################
    ######    Internal Functions
    #####################################

    def _init_solution_metadata(self):
        """ Solution Metadata 를 생성합니다. 

        """

        if not type(self.cloud_setup['VERSION']) == float:
            raise ValueError("solution_metadata 의 VERSION 은 float 타입이어야 합니다.")

        self.sm_yaml['version'] = self.cloud_setup['VERSION']
        self.sm_yaml['name'] = self.solution_name
        self.sm_yaml['description'] = {}
        self.sm_yaml['pipeline'] = []
        # self.sm_yaml['pipeline'].append({'type': 'inference'})
        try: 
            self._save_yaml()
            if self.debugging:
                print_color(f"\n << solution_metadata.yaml >> generated. - current version: v{version}", color='green')
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

        self.print_step("Set alo source code")

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
            
        print_color("[SUCCESS] Success ALO directory setting.", color='green')

    def _set_docker_contatiner(self):
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
            print_color(f"[SUCESS] set DOCKERFILE for ({self.pipeline}) pipeline", color='green')
        except Exception as e: 
            raise NotImplementedError(f"Failed DOCKERFILE setting. \n - pipeline: {self.pipeline} \n {e}")


    def _read_experimentalplan_yaml(self, yaml_file_path):
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


