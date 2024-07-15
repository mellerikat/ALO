import boto3
import hashlib
import os
import shutil
import tarfile 
from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ProfileNotFound, NoCredentialsError, ClientError
from botocore.handlers import set_list_objects_encoding_type_url
from functools import partial
from urllib.parse import urlparse
from src.constants import *
from src.logger import ProcessLogger

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME) 
#--------------------------------------------------------------------------------------------------------------------------

class S3Handler:
    def __init__(self, s3_uri: str, aws_key_profile: str):
        """ initalize s3 handler

        Args:           
            s3_uri          (str): aws s3 bucket uri 
                                    (e.g. "s3://bucket-name/path/")
            aws_key_profile (str): aws configure profile name 
                                    (e.g. aws configure --profile {alo-aws-profile})
            
        Returns: -

        """
        self.access_key, self.secret_key = self.load_aws_key(aws_key_profile) 
        if s3_uri:
            self.s3_uri = s3_uri 
            ## (e.g.) bucket name, path/sub-path/ 
            self.bucket, self.s3_folder =  self.parse_s3_uri(s3_uri) 
        
    def load_aws_key(self, aws_key_profile): 
        """ Load aws keys. Basically load from aws configure with profile. 
            If profile name not entered, try to get keys from os environmental variables
            (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY >> AI Conductor uses this method). 
            In service-account (SA) way, return None.

        Args:           
            aws_key_profile (str): aws configure profile name 
                                    (e.g. aws configure --profile {alo-aws-profile})
            
        Returns: 
            access_key  (str, None): aws access key
            secret_key  (str, None): aws secret key 

        """
        if (aws_key_profile != None) and (len(aws_key_profile)>0): 
            try:
                session = boto3.Session(profile_name=aws_key_profile)
                credentials = session.get_credentials().get_frozen_credentials()
                access_key = credentials.access_key
                secret_key = credentials.secret_key
                return access_key, secret_key 
            except ProfileNotFound: 
                PROC_LOGGER.process_error(f'Failed to get s3 key from "{aws_key_profile}". The profile may be incorrect.')
        else: 
            ## Could be AI Conductor way
            access_key, secret_key = os.getenv("AWS_ACCESS_KEY_ID"), os.getenv("AWS_SECRET_ACCESS_KEY")
            if (access_key != None) and (secret_key != None):
                PROC_LOGGER.process_message('Successfully got << AWS_ACCESS_KEY_ID >> or << AWS_SECRET_ACCESS_KEY >> from os environmental variables.') 
                return access_key, secret_key 
            else: 
                ## Could be SA way
                PROC_LOGGER.process_warning('<< AWS_ACCESS_KEY_ID >> or << AWS_SECRET_ACCESS_KEY >> is not defined on your system environment.')  
                return access_key, secret_key 
                
    def parse_s3_uri(self, uri):
        """ Parse aws s3 URI

        Args:           
            uri (str): aws s3 uri (e.g. "s3://bucket-name/path/")
            
        Returns: 
            bucket  (str): e.g. "bucket-name"
            key     (str): e.g. "path/"  
        """
        parts = urlparse(uri)
        bucket = parts.netloc
        key = parts.path.lstrip('/')
        return bucket, key
    
    def create_s3_session(self):
        """ create aws s3 session 

        Args: -
            
        Returns: 
            aws s3 client object 
        
        """
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
        """ create aws s3 session resource

        Args: -
            
        Returns: 
            aws s3 session resource  
        
        """
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
        """ download file from aws s3 

        Args: 
            _from   (str): aws s3 uri to download file from 
            _to     (str): local path to download file 
            
        Returns: -
        
        """
        PROC_LOGGER.process_message(f">>>>>> Start downloading file from s3 << {_from} >> into \n local << {_to} >>")
        if not os.path.exists(_to):
            self.s3.download_file(self.bucket, _from, _to)
            
    def download_folder(self, input_path):
        """ download all the contents in the s3 uri recursively

        Args: 
            input_path  (str): path tobe downloaded 
            
        Returns: -
        
        """
        self.s3 = self.create_s3_session() 
        ## last folder name in s3 uri 
        s3_basename = os.path.basename(os.path.normpath(self.s3_folder)) 
        target = os.path.join(input_path, s3_basename)
        if os.path.exists(target):
            PROC_LOGGER.process_error(f"{s3_basename} already exists in the << input >> folder.")    
        def _download_folder_from_s3_recursively(s3_dir_path):
            paginator = self.s3.get_paginator('list_objects_v2')
            for dir_list in paginator.paginate(Bucket=self.bucket, Delimiter='/', Prefix=s3_dir_path):
                ## if directory exists
                if 'CommonPrefixes' in dir_list:  
                    ## iterate the directory 
                    for i, each_dir in enumerate(dir_list['CommonPrefixes']):  
                        PROC_LOGGER.process_message('>> Start downloading s3 directory << {} >> | Progress: ( {} / {} total directories )'.format(each_dir['Prefix'], i+1, len(dir_list['CommonPrefixes'])))
                        ## call the function recursively using directory's prefix
                        _download_folder_from_s3_recursively(each_dir['Prefix'])  
                ## if file exists
                if 'Contents' in dir_list:  
                    ## iterate the files
                    for i, each_file in enumerate(dir_list['Contents']):  
                        ## keep the names of directories and files among the s3 uri & local path  
                        sub_folder = os.path.dirname(os.path.relpath(each_file['Key'], self.s3_folder))
                        filename = os.path.basename(each_file['Key']) 
                        ## logging every 10 files
                        if i % 10 == 0: 
                            PROC_LOGGER.process_message('>>>> S3 downloading file << {} >> | Progress: ( {} / {} total file )'.format(filename, i+1, len(dir_list['Contents'])))
                        ## FIXME check this logic 
                        ## if sub_folder and s3_basename are same, don't create s3_basename in the sub_folder 
                        if sub_folder == s3_basename: 
                            target = os.path.join(input_path, s3_basename) + '/'
                        else: 
                            target = os.path.join(input_path + s3_basename + '/', sub_folder) + '/'
                        ## create target directory 
                        os.makedirs(target, exist_ok=True)
                        ## download file from s3 
                        self.download_file_from_s3(each_file['Key'], target + filename)  
        ## download recursively 
        _download_folder_from_s3_recursively(self.s3_folder)

    def download_model(self, target):
        """ download model file (e.g. model.tar.gz) from aws s3

        Args: 
            target  (str): path tobe downloaded 
            
        Returns: 
            exist_flag  (bool): whether the model file exists in the s3 uri 
        
        """
        self.s3 = self.create_s3_session()   
        s3_basename = os.path.basename(os.path.normpath(self.s3_folder)) 
        paginator = self.s3.get_paginator('list_objects_v2')
        exist_flag = False 
        ## FIXME self variable to local variable 
        for dir_list in paginator.paginate(Bucket=self.bucket, Delimiter='/', Prefix=self.s3_folder):
            ## if file exists
            if 'Contents' in dir_list: 
                for i, each_file in enumerate(dir_list['Contents']):  
                    sub_folder, filename = each_file['Key'].split('/')[-2:]
                    if (sub_folder == s3_basename) and (filename == COMPRESSED_MODEL_FILE): 
                            self.download_file_from_s3(each_file['Key'], target + filename)
                            exist_flag = True 
        return exist_flag
                        
    def upload_file(self, file_path):
        """ upload file onto aws s3 

        Args: 
            file_path  (str): file path for uploading  
            
        Returns: -
        
        """
        s3 = self.create_s3_session_resource() 
        bucket = s3.Bucket(self.bucket)
        ## check bucket access  
        try:
            ## list contents in the bucket 
            for obj in bucket.objects.limit(1):
                PROC_LOGGER.process_message(f"Access to the bucket '{self.bucket}' is confirmed.")
                break
            else:
                PROC_LOGGER.process_message(f"Bucket '{self.bucket}' is accessible but may be empty.")
        except NoCredentialsError:
            PROC_LOGGER.process_error("Credentials not found. Unable to test bucket access.")
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDenied':
                PROC_LOGGER.process_error(f"Access denied for bucket '{self.bucket}'.")
            elif e.response['Error']['Code'] == 'NoSuchBucket':
                PROC_LOGGER.process_error(f"Bucket '{self.bucket}' does not exist.")
            else:
                PROC_LOGGER.process_error(f"An error occurred: {e.response['Error']['Message']}")
        base_name = os.path.basename(os.path.normpath(file_path))
        bucket_upload_path = self.s3_folder + base_name 
        try:
            with open(f'{file_path}', 'rb') as tar_file:  
                bucket.put_object(Key=bucket_upload_path, Body=tar_file, ContentType='artifacts/gzip')
        except: 
            PROC_LOGGER.process_error(f"Failed to upload << {file_path} >> onto << {self.s3_uri} >>.")

class ExternalHandler:
    def __init__(self):
        pass

    def external_load_data(self, pipe_mode: str, external_path: dict, external_path_permission: dict): 
        """ get data from external path 

        Args: 
            pipe_mode                   (str): (e.g. train_pipeline, inference_pipeline)
            external_path               (dict): experimental_plan.yaml - external_path dict
            external_path_permission    (dict): experimental_plan.yaml - external_path_permission dict  
            
        Returns: -
        
        """
        ## common process for both train and inference pipeline
        ## get aws key profile (single str or None)
        aws_key_profile = external_path_permission['aws_key_profile'] 
        if aws_key_profile is None: 
            PROC_LOGGER.process_warning('Not allowed to access aws infra. You did not write any << aws_key_profile >> in the experimental_plan.yaml file.')
        else: 
            if type(aws_key_profile) != str: 
                PROC_LOGGER.process_error(f"You entered wrong type of << aws_key_profile >> in your expermimental_plan.yaml: << {aws_key_profile} >>. \n Only << str >> type is allowed.")
        external_data_path = []  
        input_data_dir = ""
        if pipe_mode =='train_pipeline':
            ## convert to list type (if None or str)
            external_data_path = [] if external_path['load_train_data_path'] is None else external_path['load_train_data_path']
            external_data_path = [external_data_path] if type(external_data_path) == str else external_data_path
            ## error if external path unwritten   
            if len(external_data_path) == 0: 
                ## (Note) input directory already created   
                PROC_LOGGER.process_warning(f'External path - << load_train_data_path >> in experimental_plan.yaml are not written. You must fill the path.') 
                checksums = {}
                checksums['data_id_description'] = {}
                ## FIXME 12 zeros 
                checksums['data_id'] = "000000000000"
                return checksums
            else: 
                ## check duplicated base directory name for train pipeline
                external_base_dirs = self._check_duplicated_basedir(external_data_path)
            ## create train directory in the input directory 
            input_data_dir = INPUT_DATA_HOME + "train/"
            if not os.path.exists(input_data_dir):
                os.mkdir(input_data_dir)
        elif pipe_mode == 'inference_pipeline':
            external_data_path = [] if external_path['load_inference_data_path'] is None else external_path['load_inference_data_path']
            external_data_path = [external_data_path] if type(external_data_path) == str else external_data_path
            ## error if external path unwritten
            if len(external_data_path) == 0: 
                PROC_LOGGER.process_warning(f'External path - << load_inference_data_path >> in experimental_plan.yaml is not written. You must fill the path.') 
                checksums = {}
                checksums['data_id_description'] = {}
                ## FIXME 12 zeros 
                checksums['data_id'] = "000000000000"
                return checksums
            else: 
                external_base_dirs = self._check_duplicated_basedir(external_data_path)
            ## create inference directory in the input directory 
            input_data_dir = INPUT_DATA_HOME + "inference/"
            if not os.path.exists(input_data_dir):
                os.mkdir(input_data_dir)
        else: 
            PROC_LOGGER.process_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")
        ## copy (local absolute or relative path) or download (s3) data --> input folder
        try: 
            ## remove data folder (e.g. input/train/) before load new data
            shutil.rmtree(input_data_dir, ignore_errors=True)
            PROC_LOGGER.process_message(f"Successfuly removed << {input_data_dir} >> before loading external data.")
        except: 
            PROC_LOGGER.process_error(f"Failed to remove << {input_data_dir} >> before loading external data.")
        # get data from external path  
        for ext_path in external_data_path:
            ## external path type: absolute / relative / s3
            ext_type = self._get_ext_path_type(ext_path) 
            data_checksums = self._load_data(pipe_mode, ext_type, ext_path, aws_key_profile)
            PROC_LOGGER.process_message(f"Successfuly finish loading << {ext_path} >> into << {INPUT_DATA_HOME} >>")
        return data_checksums
            
    def external_load_model(self, external_path, external_path_permission): 
        """ Get model from external path (single path). Only supported in inference pipeline.
            If model.tar.gz file exists in the external path, download it into "train_artifacts/models/" as decompressed. 
            If model.tar.gz file doesn't exist in the external path, copy all the files (or folders) into "train_artifacts/models/"
        Args: 
            external_path               (dict): experimental_plan.yaml - external_path dict
            external_path_permission    (dict): experimental_plan.yaml - external_path_permission dict  
            
        Returns: -
        
        """
        models_path = TRAIN_MODEL_PATH
        ## empty "train_artifacts/models/"
        try: 
            if os.path.exists(models_path) == False: 
                os.makedirs(models_path)
            else:    
                shutil.rmtree(models_path, ignore_errors=True)
                os.makedirs(models_path)
                PROC_LOGGER.process_message(f"Successfully emptied << {models_path} >> ")
        except: 
            PROC_LOGGER.process_error(f"Failed to empty & re-make << {models_path} >>")
        ext_path = external_path['load_model_path']
        ## get aws s3 key profile 
        try:
            aws_key_profile = external_path_permission['aws_key_profile'] 
            PROC_LOGGER.process_message(f's3 private key file << aws_key_profile >> loaded successfully. \n')
        except:
            PROC_LOGGER.process_warning('Not allowed to access aws infra. You did not write any << aws_key_profile >> in the experimental_plan.yaml file.')
            aws_key_profile = None
        PROC_LOGGER.process_message(f"Start load model from external path: << {ext_path} >>. \n")
        ## external path type: absolute / relative / s3
        ext_type = self._get_ext_path_type(ext_path) 
        ## create temporary model directory
        if os.path.exists(TEMP_MODEL_PATH):
            shutil.rmtree(TEMP_MODEL_PATH, ignore_errors=True)
            os.makedirs(TEMP_MODEL_PATH)
        else: 
            os.makedirs(TEMP_MODEL_PATH)
        if (ext_type  == 'absolute') or (ext_type  == 'relative'):
            ext_path = PROJECT_HOME + ext_path if ext_type == 'relative' else ext_path 
            ## check whether external path is different from alo model path 
            if os.path.samefile(ext_path, models_path):
                PROC_LOGGER.process_error(f'External load model path should be different from base models_path: \n - external load model path: {ext_path} \n - base model path: {models_path}')
            try: 
                if COMPRESSED_MODEL_FILE in os.listdir(ext_path):
                    shutil.copy(ext_path + COMPRESSED_MODEL_FILE, TEMP_MODEL_PATH)  
                    ## Make sure that model.tar.gz is compressed file of models directory
                    tar = tarfile.open(TEMP_MODEL_PATH + COMPRESSED_MODEL_FILE) 
                    tar.extractall(models_path) 
                    tar.close() 
                ## when model.tar.gz doesn't exist 
                else:   
                    ## e.g. "path1/path2/" --> "path2/"
                    base_norm_path = os.path.basename(os.path.normpath(ext_path)) + '/'
                    os.makedirs(TEMP_MODEL_PATH + base_norm_path)
                    shutil.copytree(ext_path, TEMP_MODEL_PATH + base_norm_path, dirs_exist_ok=True)
                    for i in os.listdir(TEMP_MODEL_PATH + base_norm_path):
                        shutil.move(TEMP_MODEL_PATH + base_norm_path + i, models_path + i) 
                PROC_LOGGER.process_message(f'Success << external load model >> from << {ext_path} >> \n into << {models_path} >>')
            except:
                PROC_LOGGER.process_error(f'Failed to external load model from {ext_path} into {models_path}')
            finally:
                # remove temporary model path 
                shutil.rmtree(TEMP_MODEL_PATH, ignore_errors=True)     
        elif ext_type  == 's3':
            try: 
                s3_downloader = S3Handler(s3_uri=ext_path, aws_key_profile=aws_key_profile)
                ## False if model.tar.gz doesn't exist in the s3 uri 
                model_existence = s3_downloader.download_model(TEMP_MODEL_PATH)
                ## model.tar.gz already downloaded in the temporary model path 
                if model_existence: 
                    tar = tarfile.open(TEMP_MODEL_PATH + COMPRESSED_MODEL_FILE)
                    tar.extractall(models_path)
                    tar.close()
                else:
                    PROC_LOGGER.process_warning(f"No << model.tar.gz >> exists in the path << {ext_path} >>. \n Instead, try to download the all of << {ext_path} >> ")
                    s3_downloader.download_folder(models_path)  
                PROC_LOGGER.process_message(f'Success << external load model >> from << {ext_path} >> \n into << {models_path} >>') 
            except:
                PROC_LOGGER.process_error(f'Failed to external load model from {ext_path} into {models_path}')
            finally:
                # remove temporary model path 
                shutil.rmtree(TEMP_MODEL_PATH, ignore_errors=True)    
            
    def external_save_artifacts(self, pipe_mode, external_path, external_path_permission, save_inference_format):
        """ save compressed artifacts into the external path. 
            train_artifacts: tar.gz
            inference_artifacts: tar.gz or zip 
        
        Args: 
            pipe_mode                   (str): (e.g. train_pipeline, inference_pipeline)
            external_path               (dict): experimental_plan.yaml - external_path dict
            external_path_permission    (dict): experimental_plan.yaml - external_path_permission dict  
            save_inference_format       (str): inference artifact compression type (at experimental_plan.yaml - control) 
                                                supported types: tar.gz, zip
        Returns: 
            ext_type    (str, None): external save artifacts path type: absolute, relative, s3 
            ext_path    (str, None): external save artifacts path 
        
        """
        ext_type, ext_path = None, None
        ## both train, inference save artifacts path don't exist 
        if (external_path['save_train_artifacts_path'] is None) and (external_path['save_inference_artifacts_path'] is None): 
            PROC_LOGGER.process_message('None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path. \n')
            return ext_type, ext_path
        save_artifacts_path = None 
        if pipe_mode == "train_pipeline": 
            save_artifacts_path = external_path['save_train_artifacts_path'] 
        elif pipe_mode == "inference_pipeline":
            save_artifacts_path = external_path['save_inference_artifacts_path']
        else: 
            PROC_LOGGER.process_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")
        if save_artifacts_path == None: 
            PROC_LOGGER.process_message(f'[@{pipe_mode}] None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path. \n')
            return ext_type, ext_path
        ## get awws s3 key profile
        try:
            aws_key_profile = external_path_permission['aws_key_profile'] 
            PROC_LOGGER.process_message(f's3 private key file << aws_key_profile >> loaded successfully. \n')
        except:
            PROC_LOGGER.process_warning('Not allowed to access aws infra. You did not write any << aws_key_profile >> in the experimental_plan.yaml file.')
            aws_key_profile = None
        ## save artifacts if external path exists
        PROC_LOGGER.process_message(f" Start saving generated artifacts into external path << {save_artifacts_path} >>. \n")
        ext_path = save_artifacts_path
        ext_type = self._get_ext_path_type(ext_path) 
        artifacts_path, model_path = None, None
        if pipe_mode == "train_pipeline":
            artifacts_path = self._compress_dir("train_artifacts") 
            ## only compress when model file created
            if len(os.listdir(TRAIN_MODEL_PATH)) != 0:
                model_path = self._compress_dir("train_artifacts/models") 
        ## FIXME when execute both train-inference pipelines and both pipeline create model file, same external save path is not allowed
        elif pipe_mode == "inference_pipeline": 
            ## inference artifacts supports zip compression (for EdgeConductor)
            artifacts_path = self._compress_dir("inference_artifacts", save_inference_format) 
            if "models" in os.listdir(PROJECT_HOME + "inference_artifacts/"):
                ## only compress when model file created
                if len(os.listdir(INFERENCE_MODEL_PATH)) != 0:
                    model_path = self._compress_dir("inference_artifacts/models") 
        ## FIXME is it right to empty & recreate external save path ? (both local, s3)
        if (ext_type  == 'absolute') or (ext_type  == 'relative'):
            ext_path = PROJECT_HOME + ext_path if ext_type == 'relative' else ext_path
            try: 
                os.makedirs(ext_path, exist_ok=True) 
                shutil.copy(artifacts_path, ext_path)
                if model_path is not None: 
                    shutil.copy(model_path, ext_path)
                ## save process.log & pipeline.logs into external save path 
                self._external_copy_logs(pipe_mode, ext_path, ext_type)
            except: 
                PROC_LOGGER.process_error(f'Failed to copy compressed artifacts from << {artifacts_path} >> & << {model_path} >> into << {ext_path} >>.')
            ## remove temporary artifacts and model path tar 
            finally:  
                os.remove(artifacts_path)
                shutil.rmtree(TEMP_ARTIFACTS_PATH , ignore_errors=True)
                if model_path is not None: 
                    os.remove(model_path)
                    shutil.rmtree(TEMP_MODEL_PATH, ignore_errors=True)
        elif ext_type  == 's3':  
            try:  
                s3_uploader = S3Handler(s3_uri=ext_path, aws_key_profile=aws_key_profile)
                s3_uploader.upload_file(artifacts_path)
                ## save process.log & pipeline.logs into external save path 
                self._external_copy_logs(pipe_mode, ext_path, ext_type, aws_key_profile)
                if model_path is not None: 
                    s3_uploader = S3Handler(s3_uri=ext_path, aws_key_profile=aws_key_profile)
                    s3_uploader.upload_file(model_path)
            except:
                PROC_LOGGER.process_error(f'Failed to upload << {artifacts_path} >> & << {model_path} >> onto << {ext_path} >>')
            finally: 
                os.remove(artifacts_path)
                ## remove temporary artifacts path after uploading compressed fils 
                shutil.rmtree(TEMP_ARTIFACTS_PATH , ignore_errors=True)
                if model_path is not None: 
                    os.remove(model_path)
                    shutil.rmtree(TEMP_MODEL_PATH, ignore_errors=True)
        else: 
            ## unsupported external save storage type error 
            PROC_LOGGER.process_error(f'{ext_path} is unsupported type of external data path.') 
        PROC_LOGGER.process_message(f" Successfully done saving (path: {save_artifacts_path})")
        return ext_type, ext_path 

    def _external_copy_logs(self, pipe_mode, ext_path, ext_type, aws_key_profile=None):
        """ copy internal logs into external path 
        
        Args: 
            pipe_mode       (str): (e.g. train_pipeline, inference_pipeline)
            ext_path        (str): external log saved path
            ext_type        (str): external path type (absolute, relative, s3)
            aws_key_profile (str, None): aws key profile 
            
        Returns: -
        
        """
        try: 
            assert pipe_mode in ['train_pipeline', 'inference_pipeline']
            assert ext_type in ['absolute', 'relative', 's3']
            log_path = TRAIN_LOG_PATH if pipe_mode == 'train_pipeline' else INFERENCE_LOG_PATH
            if ext_type == 's3':
                s3_uploader = S3Handler(s3_uri=ext_path, aws_key_profile=aws_key_profile)
                ## log file could not be created (especially, pipeline log)
                if os.path.isfile(log_path + PROCESS_LOG_FILE): 
                    s3_uploader.upload_file(log_path + PROCESS_LOG_FILE)
                if os.path.isfile(log_path + PIPELINE_LOG_FILE):
                    s3_uploader.upload_file(log_path + PIPELINE_LOG_FILE)
            else: 
                if os.path.isfile(log_path + PROCESS_LOG_FILE):
                    shutil.copy(log_path + PROCESS_LOG_FILE, ext_path)
                if os.path.isfile(log_path + PIPELINE_LOG_FILE):
                    shutil.copy(log_path + PIPELINE_LOG_FILE, ext_path)
        except: 
            PROC_LOGGER.process_error(f'Failed to external copy logs')

    def _check_duplicated_basedir(self, data_path):
        """ check if user entered duplicated base norm directories in the data path list 
        
        Args: 
            data_path   (list): data path list to check duplication   
            
        Returns: 
            base_dir_list   (list): base norm directories list 
        
        """
        base_dir_list = [] 
        for ext_path in data_path: 
            base_dir = os.path.basename(os.path.normpath(ext_path)) 
            base_dir_list.append(base_dir)
        ## if duplicated base norm directories exist
        if len(set(base_dir_list)) != len(base_dir_list): 
            PROC_LOGGER.process_error(f"You may have entered paths which have duplicated basename in the same pipeline. \n \
                                        For example, these are not allowed: \n \
                                        - load_train_data_path: [/users/train1/data/, /users/train2/data/] \n \
                                        which have << data >> as duplicated basename of the path.")
        return base_dir_list          

    def _load_data(self, pipeline, ext_type, ext_path, aws_key_profile): 
        """ load data from external path 
        
        Args: 
            pipeline        (str): (e.g. train_pipeline, inference_pipeline)
            ext_path        (str): external load data path 
            ext_type        (str): external path type (absolute, relative, s3)
            aws_key_profile (str, None): aws key profile 
            
        Returns: 
            checksums   (dict): 64-bit checksum based on the contents of the file 
        
        """
        ## (Note) data id creation (for checking data history)
        def copy_and_checksums(src, dst):
            """The contents of the directory are copied and the checksum of all files is calculated. 
            Alternatively, if {src} is an empty string, the checksum for the contents of {dst} is calculated.
            
            """
            def _calculate_checksum(file_path):
                ## Calculates and returns a 64-bit checksum based on the contents of the file.
                with open(file_path, 'rb') as file:
                    data = file.read()
                    hash_obj = hashlib.sha256(data)
                    # Reduces the SHA-256 hash value to 64 bits.
                    return int(hash_obj.hexdigest(), 16) & ((1 << 64) - 1)
            def _aggregate_checksums(checksums_dict):
                ## Combines the checksum values of all files to generate a single value.
                ## Creates a hash object for the entire checksum using hashlib.
                total_hash = hashlib.sha256()
                for checksum in checksums_dict.values():
                    ## Converts the 64-bit checksum to a string and encodes it to bytes.
                    checksum_str = str(checksum)
                    total_hash.update(checksum_str.encode())
                ## Converts the final hash to a hexadecimal string and truncates it to 12 characters.
                total_checksum_hex = total_hash.hexdigest()[:12]
                return total_checksum_hex
            checksums_dict = {}
            if src and os.path.isdir(src):
                def _custom_copy_function(src, dst, checksums_dict):
                    ## User defined file copy function.
                    shutil.copy2(src, dst)
                    checksums_dict[dst] = _calculate_checksum(dst)
                ## Copies while calculating checksum.
                customized_copy = partial(_custom_copy_function, checksums_dict=checksums_dict)
                shutil.copytree(src, dst, copy_function=customized_copy)
            ## If {src} is empty, calculates the checksum from {dst}.
            elif not src:
                for root, _, files in os.walk(dst):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        checksums_dict[file_path] = _calculate_checksum(file_path)
            ## checksum aggregation 
            total_checksum = _aggregate_checksums(checksums_dict)
            checksums = {}
            checksums['data_id_description'] = checksums_dict
            checksums['data_id'] = total_checksum
            return checksums 
        ## data copy (local or s3)
        input_data_dir = ""
        if pipeline == 'train_pipeline':
            input_data_dir = INPUT_DATA_HOME + "train/"
        elif pipeline == 'inference_pipeline':
            input_data_dir = INPUT_DATA_HOME + "inference/"
        ## create input data directory 
        try: 
            os.makedirs(input_data_dir , exist_ok=True)  
        except: 
            PROC_LOGGER.process_error(f'Failed to create << {input_data_dir} >> path.') 
        ## fetch data based on the type of external path. 
        if ext_type  == 'absolute':
            ## error occurs if the specified folder is missing
            try: 
                base_dir = os.path.basename(os.path.normpath(ext_path))  
                ## Copies the directory and calculates checksums for all files within.
                dst_path = input_data_dir + base_dir
                checksums = copy_and_checksums(ext_path, dst_path )
            except: 
                PROC_LOGGER.process_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong absolute path (must be existing directory!) \n / or You do not have permission to access.')
        elif ext_type == 'relative': 
            try:
                base_dir = os.path.basename(os.path.normpath(ext_path))
                rel_config_path = PROJECT_HOME + ext_path
                dst_path = input_data_dir + base_dir
                checksums = copy_and_checksums(rel_config_path, dst_path)
            except: 
                PROC_LOGGER.process_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong relative path (must be existing directory!) \n / or You do not have permission to access.')
        elif ext_type  == 's3':  
            ## If a folder with the same name as the external data path folder already exists in the 
            ## user environment's input directory, notify the user and then overwrite it.
            try: 
                s3_downloader = S3Handler(s3_uri=ext_path, aws_key_profile=aws_key_profile)
                s3_downloader.download_folder(input_data_dir)
                ## calculate checksum
                checksums = copy_and_checksums('', input_data_dir) 
            except:
                PROC_LOGGER.process_error(f'Failed to download s3 data folder from << {ext_path} >>')
        PROC_LOGGER.process_message(f'Successfully done loading external data: \n {ext_path} --> {f"{input_data_dir}"}') 
        return checksums

    def _get_ext_path_type(self, _ext_path: str): 
        """ get external path type 
        
        Args: 
            _ext_path   (str): external path type
            
        Returns: 
            e.g. 's3', 'absolute', 'relative'  
        
        """
        ## (Note) error occurs if file path entered
        if 's3:/' in _ext_path: 
            return 's3'
        elif os.path.isabs(_ext_path) == True: 
            return 'absolute'
        ## relative local path 
        elif os.path.isabs(_ext_path) == False: 
            PROC_LOGGER.process_message(f'<< {_ext_path} >> may be relative path. The reference folder of relative path is << {PROJECT_HOME} >>. \n If this is not appropriate relative path, Loading external data process would raise error.')
            ## (Note) placing external data in the same path as ALO main will result in an error.
            base_dir = os.path.basename(os.path.normpath(_ext_path)) 
            parent_dir = _ext_path.split(base_dir)[0] # base dir 바로 위 parent dir 
            ## FIXME add check for alo main absolute path ?  
            ## parent_dir e.g. './folder' --> './'  ,  'folder' --> '' 
            if parent_dir == './' or parent_dir == '': 
                PROC_LOGGER.process_error(f'Placing the external data in the same path as << {PROJECT_HOME} >> is not allowed.')
            if parent_dir == '~/':
                PROC_LOGGER.process_error(f'External path starting with << ~/ >> is not allowed.')
            return 'relative'
        else: 
            PROC_LOGGER.process_error(f'<< {_ext_path} >> is unsupported type of external save artifacts path. \n Do not enter the file path. (Finish the path with directory name)')
                
    def _compress_dir(self, _path, file_extension='tar.gz'): 
        """ compress directory 
        
        Args: 
            _path   (str): path tobe compressed
            
        Returns: 
            _save_path  (str): compressed file save path
        
        """
        ## file_extension: tar.gz / zip 
        assert file_extension in ['tar.gz', 'zip']
        os.makedirs(TEMP_ARTIFACTS_PATH , exist_ok=True)
        os.makedirs(TEMP_MODEL_PATH, exist_ok=True)
        last_dir = None
        if 'models' in _path: 
            _save_path = TEMP_MODEL_PATH + COMPRESSED_MODEL_FILE
            last_dir = 'models/'
            ## error occurs if there are no files present in the models directory.
            if not os.listdir(PROJECT_HOME + _path):
                PROC_LOGGER.process_error(f"The folder '{PROJECT_HOME + _path}' is empty. Cannot create model.tar.gz file.")
        else: 
            _save_file_name = _path.strip('.') 
            _save_path = TEMP_ARTIFACTS_PATH +  f'{_save_file_name}.{file_extension}'
            ## e.g. "train_artifacts/""
            last_dir = _path 
        # compress directory 
        if file_extension == 'tar.gz':
            self._tar_dir(_path, _save_path, last_dir)
        elif file_extension == 'zip': 
            self._zip_dir(_path, _save_path, last_dir)
        return _save_path

    def _zip_dir(self, _path, _save_path, last_dir):
        """ compress directory as zip 
        
        Args: 
            _path       (str): path tobe compressed
            _save_path  (str): zip file save path 
            _last_dir   (str): last directory for _path 
            
        Returns: -
        
        """
        ## remove .zip extension 
        _save_path = os.path.splitext(_save_path)[0] 
        shutil.make_archive(_save_path, 'zip', PROJECT_HOME + _path)

    def _tar_dir(self, _path, _save_path, last_dir):
        """ compress directory as tar.gz
        
        Args: 
            _path       (str): path tobe compressed
            _save_path  (str): tar.gz file save path 
            _last_dir   (str): last directory for _path 
            
        Returns: -
        
        """
        tar = tarfile.open(_save_path, 'w:gz')
        for root, dirs, files in os.walk(PROJECT_HOME  + _path):
            base_dir = root.split(last_dir)[-1] + '/'
            for file_name in files:
                ## Arcname: Compress starting not from the absolute path beginning with /home, 
                ## but from train_artifacts/ or models/
                tar.add(os.path.join(root, file_name), arcname = base_dir + file_name) 
        tar.close()