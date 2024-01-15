import os
import boto3
from src.constants import *
from urllib.parse import urlparse
import csv 
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