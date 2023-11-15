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

# yaml = YAML()
# yaml.preserve_quotes = True

VERSION = 1.0

class SMC:
    def __init__(self, bucket, ecr):
        self.sm_yaml = {}
        self.ex_yaml = {}
        self.bucket_name = bucket
        self.ecr = ecr


    def save_yaml(self):
        # YAML 파일로 데이터 저장
        class NoAliasDumper(Dumper):
            def ignore_aliases(self, data):
                return True

        with open('solution_metadata.yaml', 'w', encoding='utf-8') as yaml_file:
            yaml.dump(self.sm_yaml, yaml_file, allow_unicode=True, default_flow_style=False, Dumper=NoAliasDumper)
            

    def set_yaml(self, version=VERSION):
        self.sm_yaml['version'] = version
        self.sm_yaml['name'] = ''
        self.sm_yaml['description'] = {}
        self.sm_yaml['pipeline'] = []
        self.sm_yaml['pipeline'].append({'type': 'train'})
        self.sm_yaml['pipeline'].append({'type': 'inference'})

        self.save_yaml()
        print(f"solution metadata 작성을 시작합니다. 현재 {version} 입니다.")
        

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
            self.ex_yaml = data
        else:
            pass

    def set_sm_name(self, name):
        self.name = name.replace(" ", "-")
        self.sm_yaml['name'] = self.name

    # {'title': '', 'overview': '', 'input_data': '', 'output_data': '', 'user_parameters': '', 'algorithm': '', 'icon': None}

    def set_sm_description(self, title, overview, input_data, output_data, user_parameters, algorithm, icon):
        self.sm_yaml['description']['title'] = self._check_parammeter(title)
        self.set_sm_name(self._check_parammeter(title))
        self.sm_yaml['description']['overview'] = self._check_parammeter(overview)
        self.sm_yaml['description']['input_data'] = self._check_parammeter(input_data)
        self.sm_yaml['description']['output_data'] = self._check_parammeter(output_data)
        self.sm_yaml['description']['user_parameters'] = self._check_parammeter(user_parameters)
        self.sm_yaml['description']['algorithm'] = self._check_parammeter(algorithm)
        self.sm_yaml['description']['icon'] = self._check_parammeter(icon)
        self.save_yaml()
        print("solution metadata description이 작성되었습니다")

    def set_wrangler(self):
        self.sm_yaml['wrangler_code_uri'] = ''
        self.sm_yaml['wrangler_dataset_uri'] = ''
        self.save_yaml()

    def set_container_uri(self, type):
        if type == 'train':
            data = {'container_uri': self.ecr + "train/" + self.name}
            self.sm_yaml['pipeline'][0].update(data)
            print(f"container uri is {data['container_uri']}")
        elif type == 'inf' or type == 'inference':
            data = {'container_uri': self.ecr + "inference/" + self.name}
            self.sm_yaml['pipeline'][1].update(data)
            print(f"container uri is {data['container_uri']}")
        self.save_yaml()

    #s3://s3-an2-cism-dev-aic/artifacts/bolt_fastening_table_classification/train/artifacts/2023/11/06/162000/
    def set_artifacts_uri(self, pipeline):
        data = {'artifact_uri': "s3://" + self.bucket_name + "/artifact/" + self.name + "/" + pipeline + "/" + "artifacts/"}
        if pipeline == 'train':
            self.sm_yaml['pipeline'][0].update(data)
        if pipeline == 'inf' or 'inference':
            self.sm_yaml['pipeline'][1].update(data)
        self.save_yaml()
        print(f"{data['artifact_uri']} were stored")

    def set_model_uri(self, pipeline):
        data = {'model_uri': "s3://" + self.bucket_name + "/artifact/" + self.name + "/" + pipeline + "/" + "artifacts/"}
        if pipeline == 'train':
            print("not support this type")
        if pipeline == 'inf' or 'inference':
            self.sm_yaml['pipeline'][1].update(data)
        self.save_yaml()
        print(f"{data['model_uri']} were stored")

    def set_edge(self):
        self.sm_yaml['edgeapp_interface'] = {'redis_server_uri': ""}
        self.save_yaml()


    def set_train_dataset_uri(self, uri):
        pass

    def set_train_artifact_uri(self, uri):
        pass

    def set_cadidate_param(self, pipeline):
        yaml_path = "../../config/experimental_plan.yaml"
        self.read_yaml(yaml_path)

        def rename_key(d, old_key, new_key):
            if old_key in d:
                d[new_key] = d.pop(old_key)
        
        if "train" in pipeline:
            temp_dict = self.ex_yaml['user_parameters'][0]
            rename_key(temp_dict, 'train_pipeline', 'candidate_parameters')
            self.sm_yaml['pipeline'][0].update({'parameters' : temp_dict})
        elif "inference" in pipeline:
            temp_dict = self.ex_yaml['user_parameters'][1]
            rename_key(temp_dict, 'inference_pipeline', 'candidate_parameters')
            self.sm_yaml['pipeline'][1].update({'parameters' : temp_dict})
    
        subkeys = {}
        output_datas = []
        for step in temp_dict['candidate_parameters']:
            output_data = {'step': step['step'], 'args': []}
            output_datas.append(output_data)
        
        subkeys['user_parameters'] = output_datas
        subkeys['selected_user_parameters'] = output_datas
        
        if "train" in pipeline:
            self.sm_yaml['pipeline'][0]['parameters'].update(subkeys)
        elif "inference" in pipeline:
            self.sm_yaml['pipeline'][1]['parameters'].update(subkeys)

        print("candidate_parameters were stored")
        
        self.save_yaml()

    def set_resource(self, pipeline, resource = 'standard'):
        if "train" in pipeline:
            self.sm_yaml['pipeline'][0]["resource"] = {"default": resource}
        elif "inference" in pipeline:
            self.sm_yaml['pipeline'][1]["resource"] = {"default": resource}

        print(f"cloud resource was {resource}")
        self.save_yaml()

    def s3_access_check(self):
        
        f = open("/nas001/users/ruci.sung/aws.key", "r")
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

        try:
            self.s3.list_buckets()
            print("S3 접근 성공")
        except Exception as e:
            print("S3 접근 실패")
            print(e)

    # def s3_upload(self, pipeline, local_folder = './input/train/'):
    def s3_upload(self, pipeline):

        def s3_process(s3, bucket_name, data_path, local_folder, s3_path):
            objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=s3_path)

            if 'Contents' in objects_to_delete:
                for obj in objects_to_delete['Contents']:
                    self.s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
                    print(f'Deleted object: {obj["Key"]}')

            s3.delete_object(Bucket=bucket_name, Key=s3_path)
            
            s3.put_object(Bucket=bucket_name, Key=(s3_path +'/'))

            s3.upload_file(data_path, bucket_name, s3_path + "/" + data_path[len(local_folder):])
            print("S3 upload 완료")

        if "train" in pipeline:
            # local_folder = '../../input/train/'
            local_folder = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))+"/input/train/"
            for root, dirs, files in os.walk(local_folder):
                for file in files:
                    data_path = os.path.join(root, file)

            s3_path = f'/solution/{self.name}/train/data'
            s3_process(self.s3, self.bucket_name, data_path, local_folder, s3_path)
            # self.sm_yaml['pipeline'].append({'dataset_uri': 'train'})

            data = {'dataset_uri': ["s3://" + self.bucket_name + s3_path + "/"]}  # 값을 리스트로 감싸줍니다
            self.sm_yaml['pipeline'][0].update(data)
            
            # data = {'dataset_uri': "s3://" + self.bucket_name + s3_path + "/"}
            # self.sm_yaml['pipeline'][0].update(data)
            self.save_yaml()
            
        elif "inf" in pipeline:
            local_folder = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))+"/input/inference/"
            for root, dirs, files in os.walk(local_folder):
                for file in files:
                    data_path = os.path.join(root, file)
            
            s3_path = f'/solution/{self.name}/inference/data/'
            s3_process(self.s3, self.bucket_name, data_path, local_folder, s3_path)
            
            data = {'dataset_uri': ["s3://" + self.bucket_name + s3_path + "/"]}  # 값을 리스트로 감싸줍니다
            self.sm_yaml['pipeline'][1].update(data)
            
            # data = {'dataset_uri': "s3://" + self.bucket_name + s3_path + "/"}
            # self.sm_yaml['pipeline'][1].update(data)
            self.save_yaml()
        else:
            print(f"{pipeline}은 지원하지 않는 pipeline 구조 입니다")

    def get_contents(self, url):
        def _is_git_url(url):
            git_url_pattern = r'^(https?|git)://[^\s/$.?#].[^\s]*$'
            return re.match(git_url_pattern, url) is not None

        contents_path = "./contents"
        if(_is_git_url(url)):
        
            if os.path.exists(contents_path):
                shutil.rmtree(contents_path)  # 폴더 제거
            repo = git.Repo.clone_from(url, "./contents")

    def copy_alo(self):
        alo_src = ['../../main.py', '../../src/', '../../config/', '../../assets/']

        dst = './'

        for item in alo_src:
            src_path = os.path.relpath(item)
            print(src_path)
            if os.path.isfile(src_path):
                shutil.copy2(src_path, dst)
            elif os.path.isdir(src_path):
                shutil.copytree(src_path, dst)
        
    def _check_parammeter(self, param):
        if self._check_str(param):
            return param
        else:
            print("입력하신 내용이 str이 아닙니다. 해당 내용은 빈칸이 들어 갑니다")
            return ""

    def _check_str(self, data):
        return isinstance(data, str)

if __name__ == "__main__":
    s3_bucket = 'acp-kubeflow-lhs-s3'
    ecr = "ecr-repo-an2-cism-dev-aic"

    new_directory = '/home/ruci.sung/0.repo/release/docker_test/contents/alo/scripts/creating_ai_solution'

    sm = SMC(s3_bucket, ecr)

    # sm.copy_alo()

    os.chdir(new_directory)


    sm.set_yaml()
    sm.set_sm_description("solution meta test ingda", "테스트중이다", "s3://하하하", "s3://호호호", "params", "alo", "s3://icon")

    sm.s3_access_check()
    
    pipeline = 'train'
    sm.s3_upload(pipeline)
    sm.set_container_uri(pipeline) # uri도 그냥 입력되게 수정
    sm.set_cadidate_param(pipeline)
    sm.set_artifacts_uri(pipeline)
    sm.set_resource(pipeline)
    
    pipeline = 'inference'
    sm.s3_upload(pipeline)
    sm.set_container_uri(pipeline)
    sm.set_cadidate_param(pipeline)
    sm.set_artifacts_uri(pipeline)
    sm.set_resource(pipeline)

    sm.set_wrangler()