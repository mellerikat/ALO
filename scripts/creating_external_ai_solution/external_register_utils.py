import boto3
import botocore
from botocore.exceptions import ClientError, NoCredentialsError
import datetime
import os
import re
import git
import sys
import shutil
import json
import requests
import yaml 
from yaml import Dumper
import subprocess
import pandas as pd 
import tarfile 
# [FIXME] 왜 쥬피터 셀에서는 sagemaker-profile로 안돼있으면 
# .git 복사할 때 권한 에러가 나는데, 여기선 괜찮지? 
# aws config 환경변수를 meerkat-profile로 지정 (이 process가 진행될 때만 일시적으로 설정되는 듯?)
os.environ["AWS_PROFILE"] = "meerkat-profile"
#----------------------------------------#
#              환경 변수                  #
#----------------------------------------#
VERSION = 1
ALODIR = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__)))) + '/'
TEMP_ARTIFACTS_DIR = ALODIR + '.temp_artifacts_dir/'
# 외부 model.tar.gz (혹은 부재 시 해당 경로 폴더 통째로)을 .train_artifacts/models 경로로 옮기기 전 임시 저장 경로 
TEMP_MODEL_DIR = ALODIR + '.temp_model_dir/'
WORKINGDIR = os.path.abspath(os.path.dirname(__file__)) + '/'

#---------------------------------------------------------
class RegisterUtils:
    #def __init__(self, workspaces, uri_scope, tag, name, pipeline):
    def __init__(self, user_input):
        self.ecr_url = "856124245140.dkr.ecr.ap-northeast-2.amazonaws.com"
        # FIXME ecr create-repsoitory 권한은 없음 
        self.ecr_repo = "ecr-repo-an2-meerkat-dev/lge/ai-solutions" + "/" + user_input['SOLUTION_NAME']
        self.ecr_tag = "latest"
        self.ecr_full_url = self.ecr_url + "/" + self.ecr_repo
        self.region = "ap-northeast-2"
        
        self.s3 = boto3.client('s3')
        self.bucket = 's3-an2-meerkat-dev-lge' 
        # FIXME s3 bucket list 조회 및 bucket 생성 권한 없음. 필요없을지? 그냥 폴더로만 구분?
        self.solution_name = user_input['SOLUTION_NAME']
        # self.s3_full_url = 's3://s3-an2-meerkat-dev-lge/' + user_input['SOLUTION_NAME'] 
        
    def set_alo(self):
        alo_path = ALODIR
        alo_src = ['main.py', 'src', 'config', 'assets', 'alolib', '.git']
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


    def set_aws_ecr(self, docker = True, tags = []):
        self.docker = docker 
        if self.docker == True:
            run = 'docker'
        else:
            run = 'buildah'

        p1 = subprocess.Popen(
            ['aws', 'ecr', 'get-login-password', '--region', f'{self.region}'], stdout=subprocess.PIPE
        )
        #print('p1: ', ['aws', 'ecr', 'get-login-password', '--region', f'{self.region}']) 
        print_color(f"[INFO] target AWS ECR url: \n{self.ecr_url}", color='blue')
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

        try: 
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print_color(f"\n[INFO] AWS ECR create-repository response: \n{result.stdout}", color='cyan')
        except subprocess.CalledProcessError as e:
            print_color(f"Failed to AWS ECR create-repository. \n If you already made the repository << {self.ecr_repo} >>, skip this step:\n Error Message: {str(e)}", color='yellow')
       


    def build_docker(self):

        subprocess.run(['docker', 'build', '.', '-t', f'{self.ecr_full_url}:{self.ecr_tag}'])

        
    def docker_push(self):
        if self.docker:
            subprocess.run(['docker', 'push', f'{self.ecr_full_url}:{self.ecr_tag}'])
        else:
            subprocess.run(['sudo', 'buildah', 'push', f'{self.ecr_full_url}:{self.ecr_tag}'])
        if self.docker:
            subprocess.run(['docker', 'logout'])
        else:
            subprocess.run(['sudo', 'buildah', 'logout', '-a'])

    

    def s3_upload_model(self):
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
        # FIXME s3 bucket 조회 및 생성 권한 없음 
        # 사용자가 설정한 이름의 s3 bucket이 없으면 create bucket   
        # bucket_list = []     
        # for bucket in self.s3.list_buckets()['Buckets']:
        #     bucket_list.append(bucket['Name'])
        # print('debug;',bucket_list) 
        # if self.bucket not in bucket_list: 
        #   location = {'LocationConstraint': self.region}
        #   self.s3.create_bucket(Bucket=self.bucket,CreateBucketConfiguration=location)
        
        # model.tar.gz을 만들어서 s3에 올리기 
        model_path = _tar_dir(".train_artifacts/models")  # model tar.gz이 저장된 local 경로 return 
        local_folder = os.path.split(model_path)[0] + '/'
        print_color(f'\n[INFO] Start uploading << model >> into S3 from local folder:\n {local_folder}', color='cyan')
        s3_process(self.s3, self.bucket, model_path, local_folder, self.solution_name, True)
        # 주의! 이미 train artifacts도 같은 경로에 업로드 했으므로 model.tar.gz올릴 땐 delete object하지 않는다. 
        #s3_process(self.s3, self.bucket_name, model_path, local_folder, train_artifacts_s3_path, 
        # raise ValueError(f"Not allowed value for << pipeline >>: {self.pipeline}")

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
    print("")
