import os
import boto3
from src.constants import *
from urllib.parse import urlparse
import csv 
import tarfile 
import shutil
from src.logger import ProcessLogger
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)

#--------------------------------------------------------------------------------------------------------------------------

class AWSHandler:
    def __init__(self, s3_uri='', load_s3_key_path=None, region=''):
        # url : (ex) 's3://aicontents-marketplace/cad/inference/' 
        # S3 VARIABLES
        # TODO 파일 기반으로 key 로드할 거면 무조건 파일은 access_key 먼저 넣고, 그 다음 줄에 secret_key 넣는 구조로 만들게 가이드한다.
        self.access_key, self.secret_key = self.init_s3_key(load_s3_key_path) 
        self.s3_uri = s3_uri 
        self.bucket, self.s3_folder =  self.parse_s3_url(s3_uri) # (ex) aicontents-marketplace, cad/inference/
        self.region = region 
        self.temp_model_extract_dir = PROJECT_HOME + '.temp_sagemaker_model/'
        
    def init_s3_key(self, s3_key_path): 
        if s3_key_path != None: 
            _, ext = os.path.splitext(s3_key_path)
            if ext != '.csv': 
                PROC_LOGGER.process_error(f"AWS key file extension must be << csv >>. \n You entered: << {s3_key_path} >>")
            try: 
                with open(s3_key_path, newline='') as csvfile: 
                    csv_reader = csv.reader(csvfile, delimiter=',')
                    reader_list = [] 
                    for row in csv_reader: 
                        reader_list.append(row) 
                        if len(row) != 2: # 컬럼 수 2가 아니면 에러 
                            PROC_LOGGER.process_error(f"AWS key file must have regular format \n - first row: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY \n - second row: << access key value >>, << secret access key value >>")
                    if len(reader_list) != 2: # 행 수 2가 아니면 에러 
                        PROC_LOGGER.process_error(f"AWS key file must have regular format \n - first row: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY \n - second row: << access key value >>, << secret access key value >>")
                PROC_LOGGER.process_info(f"Successfully read AWS key file from << {s3_key_path} >>")
                return tuple((reader_list[1][0].strip(), reader_list[1][1].strip()))
            except: 
                PROC_LOGGER.process_error(f'Failed to get s3 key from {s3_key_path}. The shape of contents in the S3 key file may be incorrect.')
        else: # yaml에 s3 key path 입력 안한 경우는 한 번 시스템 환경변수에 사용자가 key export 해둔게 있는지 확인 후 있으면 반환 없으면 경고   
            access_key, secret_key = os.getenv("AWS_ACCESS_KEY_ID"), os.getenv("AWS_SECRET_ACCESS_KEY")
            if (access_key != None) and (secret_key != None):
                PROC_LOGGER.process_info('Successfully got << AWS_ACCESS_KEY_ID >> or << AWS_SECRET_ACCESS_KEY >> from os environmental variables.') 
                return access_key, secret_key 
            else: # 둘 중 하나라도 None 이거나 둘 다 None 이면 warning (key 필요 없는 SA 방식일 수 있으므로?)
                PROC_LOGGER.process_warning('<< AWS_ACCESS_KEY_ID >> or << AWS_SECRET_ACCESS_KEY >> is not defined on your system environment.')  
                return access_key, secret_key 
                
                
    def parse_s3_url(self, uri):
        parts = urlparse(uri)
        bucket = parts.netloc
        key = parts.path.lstrip('/')
        return bucket, key
    
    
    def create_bucket(self):
        # S3 클라이언트 생성
        s3 = boto3.client('s3', region_name=self.region) #, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
        # 버킷 목록 가져오기
        response = s3.list_buckets()
        # 버킷 이름 출력
        bucket_list_log = "Pre-existing S3 Bucket list: \n"
        bucket_list = list()
        for existing_bucket in response['Buckets']:
            bucket_list_log += f"{existing_bucket['Name']} \n"
            bucket_list.append(existing_bucket['Name'])
        PROC_LOGGER.process_info(bucket_list_log)
        
        if not self.bucket in bucket_list: 
            # 버킷 생성
            s3.create_bucket(Bucket=self.bucket,
                        CreateBucketConfiguration={'LocationConstraint': self.region})
            PROC_LOGGER.process_info(f"Complete creating S3 bucket (bucket name:{self.bucket})")
        else:
            PROC_LOGGER.process_info(f"S3 Bucket already exists. (bucket name:{self.bucket})")
        

    def create_ecr_repository(self, ecr_repository):
        # aws ecr repo create 
        # ECR 클라이언트 생성
        # 참고: http://mod.lge.com/hub/ai_contents_marketplace/aia-ml-marketplace/-/blob/main/aia-pad-notebook/aia-pad-algo-for-market/UPAD-Test-SamgeMaker-Make-Algorithm-ARN.ipynb
        ecr = boto3.client('ecr', region_name=self.region)

        def repository_exists(ecr_client, repository_name): #inner func.
            try:
                response = ecr_client.describe_repositories(repositoryNames=[repository_name])
                return True
            except ecr_client.exceptions.RepositoryNotFoundException:
                return False
            
        # 리포지토리 존재 여부 확인
        if repository_exists(ecr, ecr_repository):

            response = ecr.describe_repositories()
            uri_list = response['repositories']
            for uri in uri_list:
                if ecr_repository == uri['repositoryUri'].split('/')[1]:
                    #FIXME sagemaker 학습 시 일단 ecr tag 미지원 
                    # repository_uri = uri['repositoryUri'] + ":" + ecr_tag
                    repository_uri_without_tag = uri['repositoryUri']
                    PROC_LOGGER.process_info(f"The ECR repository << {ecr_repository} >> already exists - repository_uri: {repository_uri_without_tag}")
        else:
            PROC_LOGGER.process_info(f"The repository << {ecr_repository} >> does not exist.")
            # 리포지토리 생성
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecr/client/create_repository.html
            response = ecr.create_repository(repositoryName=ecr_repository, imageScanningConfiguration={'scanOnPush': True})
            #FIXME sagemaker 학습 시 일단 ecr tag 미지원 
            #repository_uri = response['repository']['repositoryUri']  + ":" + ecr_tag
            repository_uri_without_tag = response['repository']['repositoryUri']

            PROC_LOGGER.process_info(f"Created repository URI: {repository_uri_without_tag}")
    
    
    def download_latest_model(self):
        try: 
            # S3 클라이언트 생성
            s3 = boto3.resource('s3', region_name=self.region) #, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
            # 버킷 목록 가져오기
            bucket = s3.Bucket(self.bucket)
            model_path_list = list()
            for object_summary in bucket.objects.filter(Prefix=self.s3_folder):
                ## object_summary.Object().key 예시 
                # train-artifacts/sagemaker-test-240115-v2-2024-01-15-10-05-05-244/debug-output/training_job_end.ts
                # train-artifacts/sagemaker-test-240115-v2-2024-01-15-10-05-05-244/output/model.tar.gz
                if 'model.tar.gz' in object_summary.Object().key:
                    model_path_list.append(object_summary.Object().key)
            # model.tar.gz 있는 것 중 최신날짜 포함하는 것만 다운로드 
            # 예시. train-artifacts/sagemaker-test-240115-v2-2024-01-15-10-05-05-244/output/model.tar.gz
            latest_model_path = sorted(model_path_list, reverse=True)[0]
            client = boto3.client('s3', region_name=self.region)
            # from, to / PROJECT HOME 에 model.tar.gz 를 s3에서 로컬로 다운로드
            client.download_file(self.bucket, latest_model_path, PROJECT_HOME)  
            # model.tar.gz을 PROJECT HOME 에 바로 압축해제 후 삭제 
            def _create_dir(_dir):
                # temp model dir 생성 
                if os.path.exists(_dir):
                    shutil.rmtree(_dir, ignore_errors=True)
                    os.makedirs(_dir)
                else: 
                    os.makedirs(_dir)
            # model.tar.gz 압축 해제 할 임시 폴더 생성 
            _create_dir(self.temp_model_extract_dir)
            # 압축 해제 
            if 'model.tar.gz' in os.listdir(PROJECT_HOME):
                # model.tar.gz은 train_artifacts 및 models 폴더를 통째로 압축한것들을 포함 (sagemaker에서 만드는 이름)
                # [주의] 즉 alo에서 만드는 model.tar.gz이랑 다르다 (이름 중복)
                tar = tarfile.open(PROJECT_HOME + 'model.tar.gz') 
                tar.extractall(self.temp_model_extract_dir) # 본인경로에 풀면안되는듯 
                tar.close() 
            # alo에서 생성했던 'train_artifacts.tar.gz'과 'model.tar.gz' 중 train_artifacts 만 PROJECT HOME에 압축해제 (--> .train_artifacts)
            # FIXME 이미 .train_artifacts 존재해도 에러 안나고 덮어쓰기 되는지 ? 
            if 'train_artifacts.tar.gz' in os.listdir(self.temp_model_extract_dir): 
                tar = tarfile.open(self.temp_model_extract_dir + 'train_artifacts.tar.gz')
                tar.extractall(PROJECT_HOME)
                tar.close() 
        except: 
            PROC_LOGGER.process_error(f"Failed to download latest sagemaker created model from s3 : \n << {self.s3_uri} >>")
        finally: 
            # PROJECT_HOME 상의 model.tar.gz (s3로 부터 받은) 제거 및 temp dir 제거 
            if os.path.exists(PROJECT_HOME + 'model.tar.gz'): 
                os.remove(PROJECT_HOME + 'model.tar.gz')
            shutil.rmtree(self.temp_model_extract_dir, ignore_errors=True)
                