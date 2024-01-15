from src.constants import *
import shutil
from datetime import datetime
import tarfile 
from src.logger import ProcessLogger

import os
import boto3
from boto3.session import Session
from botocore.client import Config
from botocore.handlers import set_list_objects_encoding_type_url
from src.constants import *
from boto3.s3.transfer import S3Transfer
from urllib.parse import urlparse
import csv 
# from src.logger import ProcessLogger
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
# artifacts.tar.gz  압축 파일을 외부 업로드하기 전 로컬 임시 저장 경로 
TEMP_ARTIFACTS_DIR = PROJECT_HOME + '.temp_artifacts_dir/'
# 외부 model.tar.gz (혹은 부재 시 해당 경로 폴더 통째로)을 .train_artifacts/models 경로로 옮기기 전 임시 저장 경로 
TEMP_MODEL_DIR = PROJECT_HOME + '.temp_model_dir/'
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
    
    def create_s3_session(self):
        try:
            if self.access_key and self.access_key.startswith('GOOG'):
                session = Session(aws_access_key_id=self.access_key,aws_secret_access_key=self.secret_key)
                session.events.unregister('before-parameter-build.s3.ListObjects',set_list_objects_encoding_type_url)
                return session.client('s3', endpoint_url='https://storage.googleapis.com',config=Config(signature_version='s3v4'))
            else:
                if (not self.access_key or self.access_key == 'None' or self.access_key == 'none'):
                    PROC_LOGGER.process_warning('Init boto3 client without access key.') 
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
        PROC_LOGGER.process_info(f">>>>>> Start downloading file from s3 << {_from} >> into \n local << {_to} >>")
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
                            PROC_LOGGER.process_info('>>>> S3 downloading file << {} >> | Progress: ( {} / {} total file )'.format(filename, i+1, len(dir_list['Contents'])))
                        if sub_folder == s3_basename: # 가령 s3_basename이 data인데 sub_folder이름도 data이면 굳이 data/data 만들지 않고 data/ 밑에 .csv들 가져온다. 
                            target = os.path.join(input_path, s3_basename) + '/'
                        else: 
                            target = os.path.join(input_path + s3_basename + '/', sub_folder) + '/'
                        # target directory 생성 
                        os.makedirs(target, exist_ok=True)
                        self.download_file_from_s3(each_file['Key'], target + filename)  # .csv 파일 다운로드 
                        
        download_folder_from_s3_recursively(self.s3_folder)

    def download_model(self, target):
        self.s3 = self.create_s3_session()   
        s3_basename = os.path.basename(os.path.normpath(self.s3_folder)) 

        paginator = self.s3.get_paginator('list_objects_v2')
        exist_flag = False 
        for dir_list in paginator.paginate(Bucket=self.bucket, Delimiter='/', Prefix=self.s3_folder):
            if 'Contents' in dir_list:  # 폴더가 아니라 파일이 있으면
                for i, each_file in enumerate(dir_list['Contents']):  # 파일을 iteration한다.
                    sub_folder, filename = each_file['Key'].split('/')[-2:]
                    if (sub_folder == s3_basename) and (filename == 'model.tar.gz'): 
                            self.download_file_from_s3(each_file['Key'], target + filename)
                            exist_flag = True 
        return exist_flag
                        
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

class ExteranlHandler:
    def __init__(self):
        pass

    # FIXME pipeline name까지 추후 반영해야할지? http://clm.lge.com/issue/browse/DXADVTECH-352?attachmentSortBy=dateTime&attachmentOrder=asc
    def external_load_data(self, pipe_mode, external_path, external_path_permission, get_external_data): 
        """ Description
            -----------
                - external_path로부터 데이터를 다운로드 
            Parameters
            -----------
                - pipe_mode: 호출 시의 파이프라인 (train_pipeline, inference_pipeline)
                - external_path: experimental_plan.yaml에 적힌 external_path 전체를 dict로 받아옴 
                - external_path_permission: experimental_plan.yaml에 적힌 external_path_permission 전체를 dict로 받아옴 
                - get_external_data: external data를 load하는 행위를 한 번만 할 지 여러번 할지 (once, every)
            Return
            -----------
                - 
            Example
            -----------
                - external_load_data(pipe_mode, self.external_path, self.external_path_permission, self.control['get_external_data'])
        """
        # train, inference pipeline 공통 
        # 미입력 시 every로 default 설정 
        if get_external_data is None:
            get_external_data = 'every'
            PROC_LOGGER.process_warning('You did not entered << get_external_data >> control parameter in your experimental_plan.yaml \n << every >> is automatically set as default. \n')
        # once 나 every로 입력하지 않고 이상한 값 입력 시 혹은 비워놨을 시 에러 
        if get_external_data not in ['once', 'every']:
            PROC_LOGGER.process_error(f"Check your << get_external_data >> control parameter in experimental_plan.yaml. \n You entered: {get_external_data}. Only << once >> or << every >> is allowed.")
        # s3 key 경로 가져오기 시도 (없으면 환경 변수나 aws config에 설정돼 있어야 추후 s3에서 데이터 다운로드시 에러 안남)
        load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str) or None 
        if load_s3_key_path is None: 
            PROC_LOGGER.process_warning('You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n \
                                    you have to write the s3_private_key_file path or set << AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY >> in your os environment. \n')
        else: 
            if type(load_s3_key_path) != str: 
                PROC_LOGGER.process_error(f"You entered wrong type of << s3_private_key_file >> in your expermimental_plan.yaml: << {load_s3_key_path} >>. \n Only << str >> type is allowed.")
        ################################################################################################################
        external_data_path = []  
        external_base_dirs = []
        input_data_dir = ""
        
        if pipe_mode =='train_pipeline':
            # None일 시, 혹은 str로 입력 시 type을 list로 통일하여 내부 변수화 
            ################################################################################################################
            external_data_path = [] if external_path['load_train_data_path'] is None else external_path['load_train_data_path']
            # 1개여서 str인 경우도 list로 바꾸고, 여러개인 경우는 그냥 그대로 list로 
            external_data_path = [external_data_path] if type(external_data_path) == str else external_data_path
            ################################################################################################################
            # external path 미기입 시 에러 
            if len(external_data_path) == 0: 
                # 이미 input 폴더는 무조건 만들어져 있는 상태임 
                PROC_LOGGER.process_warning(f'External path - << load_train_data_path >> in experimental_plan.yaml are not written. You must fill the path.') 
                return
            else: 
                # load_train_data_path와 load_train_data_path 내 중복  base dir (마지막 서브폴더 명) 존재 시 에러 
                external_base_dirs = self._check_duplicated_basedir(external_data_path)
            # input 폴더 내에 train sub폴더 만들기 
            input_data_dir = INPUT_DATA_HOME + "train/"
            if not os.path.exists(input_data_dir):
                os.mkdir(input_data_dir)
        elif pipe_mode == 'inference_pipeline':
            ################################################################################################################
            external_data_path = [] if external_path['load_inference_data_path'] is None else external_path['load_inference_data_path']
            external_data_path = [external_data_path] if type(external_data_path) == str else external_data_path
            ################################################################################################################
            # eexternal path 미기입 시 에러
            if len(external_data_path) == 0: 
                PROC_LOGGER.process_warning(f'External path - << load_inference_data_path >> in experimental_plan.yaml are not written. You must fill the path.') 
                return
            else: 
                external_base_dirs = self._check_duplicated_basedir(external_data_path)
            # input 폴더 내에 inference sub폴더 만들기 
            input_data_dir = INPUT_DATA_HOME + "inference/"
            if not os.path.exists(input_data_dir):
                os.mkdir(input_data_dir)
        else: 
            PROC_LOGGER.process_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")
        ################################################################################################################
        # external base 폴더 이름들과 현재 input 폴더 내 구성의 일치여부 확인 후 once, every에 따른 동작 분기 
        if get_external_data == 'once':
            if external_base_dirs == os.listdir(input_data_dir): # 외부 경로와 input 폴더 내 구성이 완전히 동등하면 데이터 새로 가져오지 않고 return 
                PROC_LOGGER.process_info(f"Skip loading external data. All the data in the external load data path already exist in << {INPUT_DATA_HOME} >> equally. \n : << external_base_dirs >>")
                return # 외부 데이터 가져오지 않고 return 
            else: 
                get_external_data = 'every' # external과 input 폴더 내 구성이 갖지 않으면 once라도 every처럼 동작
        
        # 현재 pipe mode 에 따른 설정 완료 후 실제 데이터 가져오기 시작 
        if get_external_data == 'every': 
            # copy (로컬 절대경로, 상대경로) or download (s3) data (input 폴더로)
            try: 
                shutil.rmtree(input_data_dir, ignore_errors=True) # 새로 데이터 가져오기 전 폴더 없애기 (ex. input/train) >> 어짜피 아래서 _load_data 시 새로 폴더 만들것임 
                PROC_LOGGER.process_info(f"Successfuly removed << {input_data_dir} >> before loading external data.")
            except: 
                PROC_LOGGER.process_error(f"Failed to remove << {input_data_dir} >> before loading external data.")
            # external 데이터 가져오기 
            for ext_path in external_data_path:
                ext_type = self._get_ext_path_type(ext_path) # absolute / relative / s3
                self._load_data(pipe_mode, ext_type, ext_path, load_s3_key_path)
                PROC_LOGGER.process_info(f"Successfuly finish loading << {ext_path} >> into << {INPUT_DATA_HOME} >>")
            
            return

    def external_load_model(external_path, external_path_permission): 
        '''
        # external_load_model은 inference pipeline에서만 실행함 (alo.py에서)
        # external_load_model은 path 하나만 지원 (list X --> str only)
        # external_path에 (local이든 s3든) model.tar.gz이 있으면 해당 파일을 .train_artifacts/models/ 에 압축해제 
        # model.tar.gz이 없으면 그냥 external_path 밑에 있는 파일(or 서브폴더)들 전부 .train_artifacts/models/ 로 copy
        '''
        ####################################################################################################
        models_path = PROJECT_HOME + '.train_artifacts/models/'
        # .train_artifacts/models 폴더 비우기
        try: 
            if os.path.exists(models_path) == False: 
                os.makedirs(models_path)
            else:    
                shutil.rmtree(models_path, ignore_errors=True)
                os.makedirs(models_path)
                PROC_LOGGER.process_info(f"Successfully emptied << {models_path} >> ")
        except: 
            PROC_LOGGER.process_error(f"Failed to empty & re-make << {models_path} >>")
        ####################################################################################################  
        ext_path = external_path['load_model_path']

        # get s3 key 
        try:
            load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
            PROC_LOGGER.process_info(f's3 private key file << load_s3_key_path >> loaded successfully. \n')
        except:
            PROC_LOGGER.process_info('You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment. \n')
            load_s3_key_path = None
        
        PROC_LOGGER.process_info(f"Start load model from external path: << {ext_path} >>. \n")
        
        ext_type = self._get_ext_path_type(ext_path) # absolute / relative / s3

        # temp model dir 생성 
        if os.path.exists(TEMP_MODEL_DIR):
            shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
            os.makedirs(TEMP_MODEL_DIR)
        else: 
            os.makedirs(TEMP_MODEL_DIR)
            
        if (ext_type  == 'absolute') or (ext_type  == 'relative'):
            ext_path = PROJECT_HOME + 'config/' + ext_path if ext_type == 'relative' else ext_path 
            try: 
                if 'model.tar.gz' in os.listdir(ext_path):
                    shutil.copy(ext_path + 'model.tar.gz', TEMP_MODEL_DIR)  
                    tar = tarfile.open(TEMP_MODEL_DIR + 'model.tar.gz') # model.tar.gz은 models 폴더를 통째로 압축한것 
                    # FIXME [주의] 만약 models를 통째로 압축한 model.tar.gz 이 아니고 내부 구조가 다르면 이후 진행과정 에러날 것임 
                    #압축시에 절대경로로 /home/~ ~/models/ 경로 전부 다 저장됐다가 여기서 해제되므로 models/ 경로 이후 것만 압축해지 필요   
                    tar.extractall(models_path) # TEMP_MODEL_DIR) 본인경로에 풀면안되는듯 
                    tar.close() 
                else: # model.tar.gz 이 없을때 대응 코드  
                    base_norm_path = os.path.basename(os.path.normpath(ext_path)) + '/' # ex. 'aa/bb/' --> bb/
                    os.makedirs(TEMP_MODEL_DIR + base_norm_path)
                    shutil.copytree(ext_path, TEMP_MODEL_DIR + base_norm_path, dirs_exist_ok=True)
                    for i in os.listdir(TEMP_MODEL_DIR + base_norm_path):
                        shutil.move(TEMP_MODEL_DIR + base_norm_path + i, models_path + i) 
                PROC_LOGGER.process_info(f'Success << external load model >> from << {ext_path} >> \n into << {models_path} >>')
            except:
                PROC_LOGGER.process_error(f'Failed to external load model from {ext_path} into {models_path}')
            finally:
                # TEMP_MODEL_DIR는 삭제 
                shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
                
        elif ext_type  == 's3':
            try: 
                s3_downloader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
                model_existence = s3_downloader.download_model(TEMP_MODEL_DIR) # 해당 s3 경로에 model.tar.gz 미존재 시 False, 존재 시 다운로드 후 True 반환
                if model_existence: # TEMP_MODEL_DIR로 model.tar.gz 이 다운로드 된 상태 
                    tar = tarfile.open(TEMP_MODEL_DIR + 'model.tar.gz')
                    #압축시에 절대경로로 /home/~ ~/models/ 경로 전부 다 저장됐다가 여기서 해제되므로 models/ 경로 이후 것만 옮기기 필요  
                    tar.extractall(models_path)
                    tar.close()
                else:
                    PROC_LOGGER.process_warning(f"No << model.tar.gz >> exists in the path << ext_path >>. \n Instead, try to download the all of << ext_path >> ")
                    s3_downloader.download_folder(models_path)  
                PROC_LOGGER.process_info(f'Success << external load model >> from << {ext_path} >> \n into << {models_path} >>') 
            except:
                PROC_LOGGER.process_error(f'Failed to external load model from {ext_path} into {models_path}')
            finally:
                # TEMP_MODEL_DIR는 삭제 
                shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
            
            
    def external_save_artifacts(self, pipe_mode, external_path, external_path_permission):
        """ Description
            -----------
                - 생성된 .train_artifacts, /inference_artifacts를 압축하여 (tar.gzip) 외부 경로로 전달  
            Parameters
            -----------
                - proc_start_time: alo runs start 시간 
                - pipe_mode: 호출 시의 파이프라인 (train_pipeline, inference_pipeline)
                - external_path: experimental_plan.yaml에 적힌 external_path 전체를 dict로 받아옴 
                - external_path_permission: experimental_plan.yaml에 적힌 external_path_permission 전체를 dict로 받아옴 
            Return
            -----------
                - 
            Example
            -----------
                - load_data(self.external_path, self.external_path_permission)
        """
        
        # external path가 train, inference 둘다 존재 안하는 경우 
        if (external_path['save_train_artifacts_path'] is None) and (external_path['save_inference_artifacts_path'] is None): 
            PROC_LOGGER.process_info('None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path. \n')
            return
        
        save_artifacts_path = None 
        if pipe_mode == "train_pipeline": 
            save_artifacts_path = external_path['save_train_artifacts_path'] 
        elif pipe_mode == "inference_pipeline":
            save_artifacts_path = external_path['save_inference_artifacts_path']
        else: 
            PROC_LOGGER.process_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")

        if save_artifacts_path == None: 
            PROC_LOGGER.process_info(f'[@{pipe_mode}] None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path. \n')
            return  
            
        # get s3 key 
        try:
            load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
            PROC_LOGGER.process_info(f's3 private key file << load_s3_key_path >> loaded successfully. \n')
        except:
            PROC_LOGGER.process_info('You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment. \n' )
            load_s3_key_path = None

        # external path가 존재하는 경우 
        # save artifacts 
        PROC_LOGGER.process_info(f" Start saving generated artifacts into external path << {save_artifacts_path} >>. \n")
        ext_path = save_artifacts_path
        ext_type = self._get_ext_path_type(ext_path) # absolute / s3
        artifacts_tar_path = None 
        model_tar_path = None 
        if pipe_mode == "train_pipeline":
            artifacts_tar_path = self._tar_dir(".train_artifacts") 
            model_tar_path = self._tar_dir(".train_artifacts/models") 
        # FIXME train-inference 같이 돌릴 때 train, inf 같은 external save 경로로 plan yaml에 지정하면  models tar gz 덮어씌워질수있음 
        elif pipe_mode == "inference_pipeline": 
            artifacts_tar_path = self._tar_dir(".inference_artifacts") 
            if "models" in os.listdir(PROJECT_HOME + ".inference_artifacts/"): # FIXME 이거 필요할지? 
                model_tar_path = self._tar_dir(".inference_artifacts/models") 
            
        # FIXME external save path 를 지우고 다시 만드는게 맞는가 ? (로컬이든 s3든)
        if (ext_type  == 'absolute') or (ext_type  == 'relative'):
            ext_path = PROJECT_HOME + 'config/' + ext_path if ext_type == 'relative' else ext_path
            try: 
                os.makedirs(ext_path, exist_ok=True) 
                shutil.copy(artifacts_tar_path, ext_path)
                if model_tar_path is not None: 
                    shutil.copy(model_tar_path, ext_path)
            except: 
                PROC_LOGGER.process_error(f'Failed to copy compressed artifacts from << {artifacts_tar_path} >> & << {model_tar_path} >> into << {ext_path} >>.')
            finally: 
                os.remove(artifacts_tar_path)
                shutil.rmtree(TEMP_ARTIFACTS_DIR , ignore_errors=True)
                if model_tar_path is not None: 
                    os.remove(model_tar_path)
                    shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
                
        elif ext_type  == 's3':  
            try: 
                # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
                # s3 접근권한 없으면 에러 발생 
                s3_uploader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
                s3_uploader.upload_file(artifacts_tar_path)
                if model_tar_path is not None: 
                    s3_uploader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
                    s3_uploader.upload_file(model_tar_path)
            except:
                PROC_LOGGER.process_error(f'Failed to upload << {artifacts_tar_path} >> & << {model_tar_path} >> onto << {ext_path} >>')
            finally: 
                os.remove(artifacts_tar_path)
                # [중요] 압축 파일 업로드 끝나면 TEMP_ARTIFACTS_DIR 삭제 
                shutil.rmtree(TEMP_ARTIFACTS_DIR , ignore_errors=True)
                if model_tar_path is not None: 
                    os.remove(model_tar_path)
                    shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
        else: 
            # 미지원 external data storage type
            PROC_LOGGER.process_error(f'{ext_path} is unsupported type of external data path.') 
        
        PROC_LOGGER.process_info(f" Successfully done saving << artifacts: {artifacts_tar_path} >> & << model: {model_tar_path} >> \n onto << {save_artifacts_path} >> & removing local files.")
        
        return ext_path 

    def _check_duplicated_basedir(self, data_path):
        base_dir_list = [] 
        for ext_path in data_path: 
            base_dir = os.path.basename(os.path.normpath(ext_path)) 
            base_dir_list.append(base_dir)
        if len(set(base_dir_list)) != len(base_dir_list): # 중복 mother path 존재 경우 
            PROC_LOGGER.process_error(f"You may have entered paths which have duplicated basename in the same pipeline. \n \
                                        For example, these are not allowed: \n \
                                        - load_train_data_path: [/users/train1/data/, /users/train2/data/] \n \
                                        which have << data >> as duplicated basename of the path.")
        return base_dir_list # 마지막 base폴더 이름들 리스트          

    def _load_data(self, pipeline, ext_type, ext_path, load_s3_key_path): 
        # 실제로 데이터 복사 (절대 경로) or 다운로드 (s3) 
        ####################################################
        # inpt_data_dir 변수화 
        input_data_dir = ""
        if pipeline == 'train_pipeline':
            input_data_dir = INPUT_DATA_HOME + "train/"
        elif pipeline == 'inference_pipeline':
            input_data_dir = INPUT_DATA_HOME + "inference/"
        ####################################################
        # input_data_dir 만들기 
        try: 
            os.makedirs(input_data_dir) # , exist_ok=True) 할 필요 없음. 어짜피 이미 external_load_data 함수 마지막 단에서 지워놨기 때문에 
        except: 
            PROC_LOGGER.process_error(f'Failed to create << {input_data_dir} >> path.') 
        # 외부 경로 type에 따른 데이터 가져오기 분기 
        if ext_type  == 'absolute':
            # 해당 폴더 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
            # nas 접근권한 없으면 에러 발생 
            try: 
                # 사용자가 실수로 yaml external path에 마지막에 '/' 쓰든 안쓰든, 동작엔 이상X
                # [참고] https://stackoverflow.com/questions/3925096/how-to-get-only-the-last-part-of-a-path-in-python
                base_dir = os.path.basename(os.path.normpath(ext_path)) # 가령 /nas001/test/ 면 test가 mother_path, ./이면 .가 mother_path 
                # [참고] python 3.7에서는 shutil.copytree 시 dirs_exist_ok라는 인자 없음  
                shutil.copytree(ext_path, input_data_dir + base_dir) # base_dir 라는 폴더를 만들면서 가져옴 
            except: 
                PROC_LOGGER.process_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong absolute path (must be existing directory!) \n / or You do not have permission to access.')
        elif ext_type == 'relative': 
            try:
                base_dir = os.path.basename(os.path.normpath(ext_path))
                rel_config_path = PROJECT_HOME + 'config/' + ext_path
                shutil.copytree(rel_config_path, input_data_dir + base_dir) 
            except: 
                PROC_LOGGER.process_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong relative path (must be existing directory!) \n / or You do not have permission to access.')
        elif ext_type  == 's3':  
            # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
            # 해당 s3 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
            # s3 접근권한 없으면 에러 발생 
            # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
            try: 
                s3_downloader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
                s3_downloader.download_folder(input_data_dir)
            except:
                PROC_LOGGER.process_error(f'Failed to download s3 data folder from << {ext_path} >>')

        PROC_LOGGER.process_info(f'==================== Successfully done loading external data: \n {ext_path} --> {f"{input_data_dir}"}') 
        
        return 

    ## Common Func. 
    def _get_ext_path_type(self, _ext_path: str): # inner function 
        if 's3:/' in _ext_path: 
            return 's3'
        elif os.path.isabs(_ext_path) == True: # 절대경로. nas, local 둘다 가능 
            return 'absolute'
        elif os.path.isabs(_ext_path) == False: # file이름으로 쓰면 에러날 것임 
            PROC_LOGGER.process_info(f'<< {_ext_path} >> may be relative path. The reference folder of relative path is << config/ >>. \n If this is not appropriate relative path, Loading external data process would raise error.')
            # [중요] 외부 데이터를 ALO main.py와 같은 경로에 두면 에러 
            base_dir = os.path.basename(os.path.normpath(_ext_path)) 
            parent_dir = _ext_path.split(base_dir)[0] # base dir 바로 위 parent dir 
            # 외부 데이터 폴더는 main.py랑 같은 경로에 두면 안된다. 물론 절대경로로도 alo/ 포함 시키는 등 뚫릴 수 있는 방법은 많지만, 사용자 가이드 목적의 에러이다. 
            if parent_dir == '../':
                PROC_LOGGER.process_error(f'Placing the external data in the same path as << {PROJECT_HOME} >> is not allowed.')
            if parent_dir == '~/':
                PROC_LOGGER.process_error(f'External path starting with << ~/ >> is not allowed.')
            return 'relative'
        else: 
            PROC_LOGGER.process_error(f'<< {_ext_path} >> is unsupported type of external save artifacts path. \n Do not enter the file path. (Finish the path with directory name)')
                
    def _tar_dir(self, _path): 
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
        for root, dirs, files in os.walk(PROJECT_HOME  + _path):
            #base_dir = last_dir + root.split(last_dir)[-1] + '/' # ex. /home/~~/models/ --> models/
            base_dir = root.split(last_dir)[-1] + '/'
            for file_name in files:
                #https://stackoverflow.com/questions/2239655/how-can-files-be-added-to-a-tarfile-with-python-without-adding-the-directory-hi
                tar.add(os.path.join(root, file_name), arcname = base_dir + file_name) # /home부터 시작하는 절대 경로가 아니라 .train_artifacts/ 혹은 moddels/부터 시작해서 압축해야하므로 
        tar.close()
        
        return _save_path