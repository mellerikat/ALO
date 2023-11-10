import os
import boto3
from boto3.session import Session
from botocore.client import Config
from botocore.handlers import set_list_objects_encoding_type_url
from src.constants import *
from boto3.s3.transfer import S3Transfer
from urllib.parse import urlparse
from alolib import logger 
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = logger.ProcessLogger(PROJECT_HOME)

#--------------------------------------------------------------------------------------------------------------------------

class S3Handler:
    def __init__(self, s3_uri, load_s3_key_path):
        # url : (ex) 's3://aicontents-marketplace/cad/inference/' 
        # S3 VARIABLES
        # TODO 파일 기반으로 key 로드할 거면 무조건 파일은 access_key 먼저 넣고, 그 다음 줄에 secret_key 넣는 구조로 만들게 가이드한다.
        self.access_key, self.secret_key = self.init_s3_key(load_s3_key_path) 
        self.s3_uri = s3_uri 
        self.bucket, self.s3_folder =  self.parse_s3_url(s3_uri) # (ex) aicontents-marketplace, cad/inference/
        
    def init_s3_key(self, s3_key_path): 
        if s3_key_path != None: 
            try: 
                keys = [] 
                with open (s3_key_path, 'r') as f: 
                    for key in f:
                        keys.append(key.strip())
                return tuple(keys)
            except: 
                PROC_LOGGER.process_error(f'Failed to get s3 key from {s3_key_path}. The shape of contents in the S3 key file may be incorrect.')
        else: # yaml에 s3 key path 입력 안한 경우는 한 번 시스템 환경변수에 사용자가 key export 해둔게 있는지 확인 후 있으면 반환 없으면 에러  
            access_key, secret_key = os.getenv("AWS_ACCESS_KEY_ID"), os.getenv("AWS_SECRET_ACCESS_KEY")
            if (access_key != None) and (secret_key != None):
                return access_key, secret_key 
            else: # 둘 중 하나라도 None 이거나 둘 다 None 이면 에러 
                PROC_LOGGER.process_error('<< AWS_ACCESS_KEY_ID >> or << AWS_SECRET_ACCESS_KEY >> is not defined on your system environment.')  

    def parse_s3_url(self, uri):
        parts = urlparse(uri)
        bucket = parts.netloc
        key = parts.path.lstrip('/')
        return bucket, key
    
    def create_s3_session(self):
        try:
            if self.access_key and self.access_key.startswith('GOOG'):
                session = Session(aws_access_key_id=self.access_key,aws_secret_access_key=self.secret_key)
                session.events.unregister('before-parameter-build.s3.ListObjects',set_list_objects_encoding_type_url)
                return session.client('s3', endpoint_url='https://storage.googleapis.com',config=Config(signature_version='s3v4'))
            else:
                if (not self.access_key or self.access_key == 'None' or self.access_key == 'none'):
#                    self.logger.info('not existed access key')
                    return boto3.client('s3')
                else:
                    session = boto3.session.Session()
                    return session.client('s3', aws_access_key_id=self.access_key, aws_secret_access_key=self.secret_key)
        except Exception as e:
            PROC_LOGGER.process_error("S3 CONNECTION ERROR %s" % e)

    def create_s3_session_resource(self):
        try:
            if self.access_key and self.access_key.startswith('GOOG'):
                session = Session(aws_access_key_id=self.access_key,aws_secret_access_key=self.secret_key)
                session.events.unregister('before-parameter-build.s3.ListObjects',set_list_objects_encoding_type_url)
                return session.resource('s3', endpoint_url='https://storage.googleapis.com',config=Config(signature_version='s3v4'))
            else:
                return boto3.resource('s3', aws_access_key_id=self.access_key, aws_secret_access_key=self.secret_key)
        except Exception as e:
            PROC_LOGGER.process_error("S3 CONNECTION ERROR %s" % e)
    
    def download_file_from_s3(self, _from, _to):
        PROC_LOGGER.process_info(f"    >> Start downloading file from s3 << {_from} >> into \n       local << {_to} >>")
        if not os.path.exists(_to):
            self.s3.download_file(self.bucket, _from, _to)
            
    # recursive download from s3
    def download_folder(self, input_path):
        # https://saturncloud.io/blog/downloading-a-folder-from-s3-using-boto3-a-comprehensive-guide-for-data-scientists/
        # https://qkqhxla1.tistory.com/992
        self.s3 = self.create_s3_session() 
        #bucket = s3.Bucket(self.bucket)
        s3_basename = os.path.basename(os.path.normpath(self.s3_folder)) #.partition('/')[-1] 
  
        target = os.path.join(input_path, s3_basename)
        if os.path.exists(target):
            PROC_LOGGER.process_error(f"{s3_basename} already exists in the << input >> folder.")
            
        def download_folder_from_s3_recursively(s3_dir_path):
            paginator = self.s3.get_paginator('list_objects_v2')
            for dir_list in paginator.paginate(Bucket=self.bucket, Delimiter='/', Prefix=s3_dir_path):
                if 'CommonPrefixes' in dir_list:  # 폴더가 있으면
                    for i, each_dir in enumerate(dir_list['CommonPrefixes']):  # 폴더를 iteration한다.
                        PROC_LOGGER.process_info('>> Start downloading s3 directory << {} >> | Progress: ( {} / {} total directories )'.format(each_dir['Prefix'], i+1, len(dir_list['CommonPrefixes'])))
                        # 폴더들의 Prefix를 이용하여 다시 recursive하게 함수를 호출한다.
                        download_folder_from_s3_recursively(each_dir['Prefix'])  
            
                if 'Contents' in dir_list:  # 폴더가 아니라 파일이 있으면
                    for i, each_file in enumerate(dir_list['Contents']):  # 파일을 iteration한다.
                        sub_folder, filename = each_file['Key'].split('/')[-2:]  # 내 로컬에 저장할 폴더 이름은 s3의 폴더 이름과 같게 한다. 파일 이름도 그대로.
                        if i % 10 == 0: # 파일 10개마다 progress logging
                            print('  >> S3 downloading file << {} >> | Progress: ( {} / {} total file )'.format(filename, i+1, len(dir_list['Contents'])))
                        if sub_folder == s3_basename: # 가령 s3_basename이 data인데 sub_folder이름도 data이면 굳이 data/data 만들지 않고 data/ 밑에 .csv들 가져온다. 
                            target = os.path.join(input_path, s3_basename)
                        else: 
                            target = os.path.join(input_path + s3_basename + '/', sub_folder)
                        # target directory 생성 
                        os.makedirs(target, exist_ok=True)
                        self.download_file_from_s3(each_file['Key'], target + '/' + filename)  # .csv 파일 다운로드 
                        
        download_folder_from_s3_recursively(self.s3_folder)


    def upload_file(self, file_path):
        s3 = self.create_s3_session_resource() # session resource 만들어야함 
        bucket = s3.Bucket(self.bucket)
        base_name = os.path.basename(os.path.normpath(file_path))
        bucket_upload_path = self.s3_folder + base_name 
        try:
            with open(f'{file_path}', 'rb') as tar_file:  
                bucket.put_object(Key=bucket_upload_path, Body=tar_file, ContentType='artifacts/gzip')
        except: 
            PROC_LOGGER.process_error(f"Failed to upload << {file_path} >> onto << {self.s3_uri} >>.")
        
        
