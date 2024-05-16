import boto3
import os
import pkg_resources
import shutil
import subprocess
import sys 
import tarfile 
from botocore.exceptions import ProfileNotFound
from urllib.parse import urlparse
from src.constants import *
from src.logger import ProcessLogger
from src.yaml import Metadata

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
#--------------------------------------------------------------------------------------------------------------------------

class SagemakerHandler:
    def __init__(self, aws_key_profile, sm_config):
        """ Initialize path info and solution metadata info. for AWS sagemaker execution 

        Args:
            aws_key_profile     (str): aws configure profile name 
            sm_config           (dict): solution_metadata.yaml info.

        Returns: -

        """
        self.aws_key_profile = aws_key_profile
        try:
            self.session = boto3.Session(profile_name=self.aws_key_profile)
        except ProfileNotFound:
            PROC_LOGGER.process_error(f"The profile {self.aws_key_profile} not found.")
        self.sm_config = sm_config
        self.sagemaker_path = SAGEMAKER_PATH
        self.temp_model_extract_dir = TEMP_SAGEMAKER_MODEL_PATH
        self.meta = Metadata()
        
    def init(self):
        """ Initialize various SageMaker-related config information as class variables.

        Args: -

        Returns: -

        """
        os.environ["AWS_PROFILE"] = self.aws_key_profile
        ## install and import sagemaker pip package
        self._install_sagemaker()
        try: 
            # (Note) get_execution_role() only returns the SageMaker role when running within a SageMaker Jupyter notebook
            import sagemaker
            sagemaker_session = sagemaker.Session()
            self.role = sagemaker.get_execution_role()
        except:
            PROC_LOGGER.process_warning("sagemaker get-execution-role not allowed.") 
            self.role = self.sm_config['role'] 
        self.region = self.sm_config['region'] 
        self.account_id = str(self.sm_config['account_id'])
        self.region = self.sm_config['region']
        ## set s3 info.
        self.s3_uri = self.sm_config['s3_bucket_uri']
        self.bucket, self.s3_folder =  self._parse_s3_uri(self.s3_uri) 
        ## set ecr info.
        self.ecr_repository = self.sm_config['ecr_repository']
        ## FIXME ecr tag not needed ?
        self.ecr_tag = [] 
        self.docker_tag = 'latest'
        self.ecr_uri = f'{self.account_id}.dkr.ecr.{self.region}.amazonaws.com'
        self.ecr_full_uri = self.ecr_uri + f'/{self.ecr_repository}:{self.docker_tag}'
        ## sagemaker resource 
        ## FIXME need to extract into sagemaker_config ?
        self.train_instance_count = 1 
        self.train_instance_type = self.sm_config['train_instance_type']
    
    def setup(self, pipeline_list):
        """ Copy the elements required for docker build into the sagemaker directory for the given list of pipelines

        Args: 
            pipeline_list   (list): pipe line list to sagemaker run 
            
        Returns: -

        """
        assert (len(pipeline_list) > 0) and (len(pipeline_list) <= 2)
        ## reset sagemaker path 
        if os.path.exists(self.sagemaker_path):
            shutil.rmtree(self.sagemaker_path)
        os.mkdir(self.sagemaker_path)
        ## copy materials for docker build into sagemaker directory  
        alo_src = ['main.py', 'src', 'solution', 'assets', 'alolib', '.git', 'input', 'requirements.txt']
        ## assumption required for 'inference only' is that the training should already be completed
        if pipeline_list == ['inference_pipeline']:
            alo_src.append('train_artifacts')
            if (not os.path.isdir(TRAIN_MODEL_PATH)) or (len(os.listdir(TRAIN_MODEL_PATH)) == 0):
                PROC_LOGGER.process_error("Train first. Sagemaker & Inference mode needs trained model")
        for item in alo_src:
            src_path = PROJECT_HOME + item
            if os.path.isfile(src_path):
                shutil.copy2(src_path, self.sagemaker_path)
                PROC_LOGGER.process_message(f'copy from << {src_path} >>  -->  << {self.sagemaker_path} >> ')
            elif os.path.isdir(src_path):
                dst_path =  self.sagemaker_path + os.path.basename(src_path)
                shutil.copytree(src_path, dst_path)
                PROC_LOGGER.process_message(f'copy from << {src_path} >>  -->  << {self.sagemaker_path} >> ') 
        ## Since arguments cannot be passed after main.py in the SageMaker Dockerfile,
        ## modify the content of the pipeline determined in the plan yaml copied for docker build and rewrite it. 
        exp_plan_dict = self.meta.get_yaml(SAGEMAKER_EXP_PLAN)
        pipeline_candidates = ['train_pipeline', 'inference_pipeline']
        PROC_LOGGER.process_message(f"{pipeline_list} executed in sagemaker docker (cloud)")
        if pipeline_list == pipeline_candidates: 
            pass
        ## for just one pipeline 
        else: 
            delete_pipe = [pipe for pipe in pipeline_candidates if pipe not in pipeline_list][0]
            ## remove the pipe from the exp plan (to prevent execution within the SageMaker Docker)
            exp_plan_dict['user_parameters'] = [
                item for item in exp_plan_dict['user_parameters'] if delete_pipe not in item]
            exp_plan_dict['asset_source'] = [
                item for item in exp_plan_dict['asset_source'] if delete_pipe not in item]
            PROC_LOGGER.process_message(f"{delete_pipe} deleted in experimental plan. Re-written experimental plan for sagemaker: \n {exp_plan_dict}")
        ## rewrite experimental plan yaml
        self.meta.save_yaml(exp_plan_dict, SAGEMAKER_EXP_PLAN)
        
    def build_solution(self): 
        """ docker build, ecr push, create s3 bucket for sagemaker

        Args: -
            
        Returns: -

        """
        ## Dockefile setting
        self._set_dockerfile()
        ## aws ecr login 
        p1 = subprocess.Popen(
            ['aws', 'ecr', 'get-login-password', '--region', self.region], stdout=subprocess.PIPE
        )
        p2 = subprocess.Popen( 
            [f'docker', 'login', '--username', 'AWS','--password-stdin', self.ecr_uri], stdin=p1.stdout, stdout=subprocess.PIPE
        )
        p1.stdout.close()
        output = p2.communicate()[0]
        PROC_LOGGER.process_message(f"AWS ECR | docker login result: \n {output.decode()}")
        ## aws ecr repo create 
        self._create_ecr_repository(ecr_repository=self.ecr_repository)
        ## docker build 
        subprocess.run(['docker', 'build', '.', '-t', f'{self.ecr_full_uri}'])
        ## docker push to ecr 
        subprocess.run(['docker', 'push', f'{self.ecr_full_uri}'])
        ## create the s3 bucket if it does not exist as specified by the user
        self._create_bucket()

    def _set_dockerfile(self): 
        """ setup sagemaker Dockerfile

        Args: -
            
        Returns: -

        """
        sagemaker_dockerfile = SAGEMKAER_DOCKERFILE
        ## delete the Dockerfile if it already exists
        if os.path.isfile(PROJECT_HOME + 'Dockerfile'):
            os.remove(PROJECT_HOME + 'Dockerfile')
        ## copy the Dockerfile to the project home
        shutil.copy(sagemaker_dockerfile, PROJECT_HOME + 'Dockerfile')
        ## modify the Dockerfile for the installation of the package list into docker
        docker_location = SAGEMAKER_DOCKER_WORKDIR
        file_list = sorted(next(os.walk(ASSET_PACKAGE_PATH))[2], key=lambda x:int(os.path.splitext(x)[0].split('_')[-1]))
        ## sort to install train first, followed by inference
        file_list = [i for i in file_list if i.startswith('train')] + [i for i in file_list if i.startswith('inference')]
        search_string = 'site_packages_location'
        with open(PROJECT_HOME + 'Dockerfile', 'r', encoding='utf-8') as file:
            content = file.read()
        path = ASSET_PACKAGE_PATH.replace(PROJECT_HOME, "./")
        replace_string = '\n'.join([f"COPY {path}{file} {docker_location}" for file in file_list])
        requirement_files = [file for file in file_list if file.endswith('.txt')]
        pip_install_commands = '\n'.join([f"RUN pip3 install --no-cache-dir -r {docker_location}{file}" for file in requirement_files])
        if search_string in content:
            content = content.replace(search_string, replace_string + "\n" + pip_install_commands)
            with open(PROJECT_HOME + 'Dockerfile', 'w', encoding='utf-8') as file:
                file.write(content)
    
    def fit_estimator(self):
        """ fit sagemaker estimator (execute on cloud resource)

        Args: -
            
        Returns: -

        """
        from sagemaker.estimator import Estimator
        training_estimator = Estimator(image_uri=self.ecr_full_uri,
                                role=self.role,
                                train_instance_count=self.train_instance_count,
                                train_instance_type=self.train_instance_type,
                                output_path=self.s3_uri)
        training_estimator.fit() 
          
    def _install_sagemaker(self):
        """ install sagemaker pip package

        Args: -
            
        Returns: -

        """
        package = SAGEMAKER_PACKAGE
        ## check if the same version is already installed
        try: 
            pkg_resources.get_distribution(package) 
            PROC_LOGGER.process_message(f'[OK] << {package} >> already exists')
        ## in the case where the package is not installed at all in the user's virtual environment
        except: 
            try: 
                PROC_LOGGER.process_message(f'>> Start installing package - {package}')
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
            except Exception as e:
                PROC_LOGGER.process_error(f"Failed to install {package}: \n {str(e)}")
                   
    def _parse_s3_uri(self, uri):
        """ parse s3 uri

        Args: 
            uri (str): s3 uri (e.g. s3://bucket-name/path/)
            
        Returns: 
            bucket  (str): bucket name (e.g. bucket-name)
            key     (str): key path (e.g. path/)

        """
        parts = urlparse(uri)
        bucket = parts.netloc
        key = parts.path.lstrip('/')
        return bucket, key
    
    def _create_bucket(self):
        """ create s3 bucket 

        Args: -
            
        Returns: -

        """
        ## s3 session client 
        s3 = self.session.client('s3', region_name=self.region) 
        ## list s3 bucket
        response = s3.list_buckets()
        bucket_list_log = "Pre-existing S3 Bucket list: \n"
        bucket_list = list()
        for existing_bucket in response['Buckets']:
            bucket_list_log += f"{existing_bucket['Name']} \n"
            bucket_list.append(existing_bucket['Name'])
        PROC_LOGGER.process_message(bucket_list_log)
        if not self.bucket in bucket_list: 
            ## create s3 bucket 
            s3.create_bucket(Bucket=self.bucket,
                        CreateBucketConfiguration={'LocationConstraint': self.region})
            PROC_LOGGER.process_message(f"Complete creating S3 bucket (bucket name:{self.bucket})")
        else:
            PROC_LOGGER.process_message(f"S3 Bucket already exists. (bucket name:{self.bucket})")
        

    def _create_ecr_repository(self, ecr_repository):
        """ create aws ecr repository 

        Args: -
            
        Returns: -

        """
        ## ecr session client 
        ecr = self.session.client('ecr', region_name=self.region)
        def repository_exists(ecr_client, repository_name): 
            try:
                response = ecr_client.describe_repositories(repositoryNames=[repository_name])
                return True
            except ecr_client.exceptions.RepositoryNotFoundException:
                return False
        ## check pre-existence of ecr repo
        if repository_exists(ecr, ecr_repository):
            response = ecr.describe_repositories()
            uri_list = response['repositories']
            for uri in uri_list:
                if ecr_repository == uri['repositoryUri'].split('/')[1]:
                    ## FIXME ecr tag needed ? (e.g. repository_uri = uri['repositoryUri'] + ":" + ecr_tag)
                    repository_uri_without_tag = uri['repositoryUri']
                    PROC_LOGGER.process_message(f"ECR repository << {ecr_repository} >> already exists - repository_uri: {repository_uri_without_tag}")
        else:
            PROC_LOGGER.process_message(f"ECR repository << {ecr_repository} >> does not exist.")
            ## create ecr repo 
            response = ecr.create_repository(repositoryName=ecr_repository, imageScanningConfiguration={'scanOnPush': True}) 
            ## FIXME ecr tag needed ? (e.g. repository_uri = uri['repositoryUri'] + ":" + ecr_tag)
            repository_uri_without_tag = response['repository']['repositoryUri']

            PROC_LOGGER.process_message(f"Created repository URI: {repository_uri_without_tag}")
    
    def download_latest_model(self, inf_artifact_format: str):
        """ download latest trained model or inference artifacts by sagemaker from s3 bucket 

        Args: 
            inf_artifact_format (str): inference artifacts compression format (e.g. tar.gz / zip)
            
        Returns: -

        """
        try: 
            ## setup s3 session resource
            s3 = self.session.resource('s3', region_name=self.region) 
            ## list s3 bucket 
            bucket = s3.Bucket(self.bucket)
            model_path_list = list()
            for object_summary in bucket.objects.filter(Prefix=self.s3_folder):
                if COMPRESSED_MODEL_FILE in object_summary.Object().key:
                    model_path_list.append(object_summary.Object().key)
            ## download latest model.tar.gz 
            latest_model_path = sorted(model_path_list, reverse=True)[0]
            ## setup s3 session client
            client = self.session.client('s3', region_name=self.region)
            ## download s3 model.tar.gz --> local project home
            client.download_file(self.bucket, latest_model_path, PROJECT_HOME + COMPRESSED_MODEL_FILE)  
            PROC_LOGGER.process_message(f"Success downloading << {self.bucket}/{latest_model_path} >> into << {PROJECT_HOME} >>")
            ## remove model.tar.gz after decompression 
            def _create_dir(_dir):
                # create temporary model directory
                if os.path.exists(_dir):
                    shutil.rmtree(_dir, ignore_errors=True)
                    os.makedirs(_dir)
                else: 
                    os.makedirs(_dir)
            # create temporary directory for decompressing model.tar.gz 
            _create_dir(self.temp_model_extract_dir)
            # 압축 해제 
            if COMPRESSED_MODEL_FILE in os.listdir(PROJECT_HOME):
                ## FIXME (Note) model.tar.gz in sagemaker is different from alo's \
                ## model.tar.gz in sagemaker includes  train_artifacts.tar.gz & model.tar.gz
                tar = tarfile.open(PROJECT_HOME + COMPRESSED_MODEL_FILE) 
                ## cannot extract into self path 
                tar.extractall(self.temp_model_extract_dir) 
                tar.close() 
            ## extract current pipelines artifacts
            ## FIXME check if it overwrites without error, even if train_artifacts already exists ?
            if COMPRESSED_TRAIN_ARTIFACTS_FILE in os.listdir(self.temp_model_extract_dir): 
                tar = tarfile.open(self.temp_model_extract_dir + COMPRESSED_TRAIN_ARTIFACTS_FILE)
                _create_dir(TRAIN_ARTIFACTS_PATH)
                tar.extractall(TRAIN_ARTIFACTS_PATH)
                tar.close() 
            ## inference artifact compression format : zip or tar.gz
            COMPRESSED_INFERENCE_ARTIFACTS_FILE = COMPRESSED_INFERENCE_ARTIFACTS_ZIP if inf_artifact_format == 'zip' else COMPRESSED_INFERENCE_ARTIFACTS_TAR_GZ
            if COMPRESSED_INFERENCE_ARTIFACTS_FILE in os.listdir(self.temp_model_extract_dir): 
                tar = tarfile.open(self.temp_model_extract_dir + COMPRESSED_INFERENCE_ARTIFACTS_FILE)
                _create_dir(INFERENCE_ARTIFACTS_PATH)
                tar.extractall(INFERENCE_ARTIFACTS_PATH)
                tar.close() 
        except: 
            PROC_LOGGER.process_error(f"Failed to download latest sagemaker created model from s3 : \n << {self.s3_uri} >>")
        finally: 
            ## remove model.tar.gz (from sageamekr s3 bucket) & temporary directories
            if os.path.exists(PROJECT_HOME + COMPRESSED_MODEL_FILE): 
                os.remove(PROJECT_HOME + COMPRESSED_MODEL_FILE)
            shutil.rmtree(self.temp_model_extract_dir, ignore_errors=True)

