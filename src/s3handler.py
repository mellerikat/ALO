import os
import boto3
from boto3.session import Session
from botocore.client import Config
from botocore.handlers import set_list_objects_encoding_type_url
import tarfile
from urllib.parse import urlparse

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
                raise ValueError(f'Failed to get s3 key from {s3_key_path}. The shape of contents in the S3 key file may be incorrect.')
        else: # yaml에 s3 key path 입력 안한 경우는 한 번 시스템 환경변수에 사용자가 key export 해둔게 있는지 확인 후 있으면 반환 없으면 에러  
            access_key, secret_key = os.getenv("ACCESS_KEY"), os.getenv("SECRET_KEY")
            if (access_key != None) and (secret_key != None):
                return access_key, secret_key 
            else: # 둘 중 하나라도 None 이거나 둘 다 None 이면 에러 
                raise ValueError('<< ACCESS_KEY >> or << SECRET_KEY >> is not defined on your system environment.')  

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
            raise Exception("S3 CONNECTION ERROR %s" % e)

    def create_s3_session_resource(self):
        try:
            if self.access_key and self.access_key.startswith('GOOG'):
                session = Session(aws_access_key_id=self.access_key,aws_secret_access_key=self.secret_key)
                session.events.unregister('before-parameter-build.s3.ListObjects',set_list_objects_encoding_type_url)
                return session.resource('s3', endpoint_url='https://storage.googleapis.com',config=Config(signature_version='s3v4'))
            else:
                return boto3.resource('s3', aws_access_key_id=self.access_key, aws_secret_access_key=self.secret_key)
        except Exception as e:
            raise Exception("S3 CONNECTION ERROR %s" % e)
        
    # https://saturncloud.io/blog/downloading-a-folder-from-s3-using-boto3-a-comprehensive-guide-for-data-scientists/
    def download_folder(self, input_path):
        s3 = self.create_s3_session_resource() # session resource 만들어야함 
        bucket = s3.Bucket(self.bucket)
        mother_folder = self.s3_folder.partition('/')[-1] 
        if os.path.exists(input_path + mother_folder):
            raise ValueError(f"{mother_folder} already exists in the << input >> folder.")
        for obj in bucket.objects.filter(Prefix=self.s3_folder):
            # 아래처럼 쓰면 해당 폴더 아래에 있는 것 전부 input 폴더로 복사 (폴더든, 파일이든) 
            # 따라서 single external path일 때 사용 가능 
            # multi s3인 경우 input 폴더 밑에 여러 폴더들 배치될 수 있으므로 mother 폴더로 한번 감싸서 서로 구분한다             
            target = os.path.join(input_path + mother_folder, os.path.relpath(obj.key, self.s3_folder)) 
            # FIXME 일단 중복 폴더 이름 허용했음 
            os.makedirs(os.path.dirname(target), exist_ok=True)
            bucket.download_file(obj.key, target)

    def upload_file(self, file_path):
        s3 = self.create_s3_session_resource() # session resource 만들어야함 
        bucket = s3.Bucket(self.bucket)
        base_name = os.path.basename(os.path.normpath(file_path))
        bucket_upload_path = self.s3_folder + base_name 
        try:
            with open(f'{file_path}', 'rb') as tar_file:  
                bucket.put_object(Key=bucket_upload_path, Body=tar_file, ContentType='artifacts/gzip')
        except: 
            raise NotImplementedError(f"Failed to upload << {file_path} >> onto << {self.s3_uri} >>.")
        
        
