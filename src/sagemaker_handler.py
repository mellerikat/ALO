import os
import boto3
from src.constants import *
from urllib.parse import urlparse
import subprocess
import pkg_resources
import tarfile 
import shutil
from src.logger import ProcessLogger
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
# FIXME sagemaker version hard-fixed
SAGEMAKER_PACKAGE = "sagemaker==2.203.1"
#--------------------------------------------------------------------------------------------------------------------------

class SagemakerHandler:
    def __init__(self, sm_config):
        self.sm_config = sm_config
        self.sagemaker_dir = PROJECT_HOME + '.sagemaker/'
        self.temp_model_extract_dir = PROJECT_HOME + '.temp_sagemaker_model/'
        
        
    def init(self):
        """
        각종 config를 클래스 변수화 합니다.
        """
        # aws configure의 profile을 sagemaker-profile로 변경 (sagemaker 및 본인 계정 s3, ecr 권한 있는)
        # 사외 서비스 시엔 사용자가 미리 sagemaker-profile와 meerkat-profile를 aws configure multi-profile 등록해놨어야 함
        os.environ["AWS_PROFILE"] = "sagemaker-profile"
        # FIXME sagemaker install 은 sagemaker_runs일 때만 진행 
        self._install_sagemaker()
        try: 
            # FIXME get_execution_role은 sagemaker jupyter notebook에서만 sagemaker role을 반환한다. 
            # 참고 https://github.com/aws/sagemaker-python-sdk/issues/300
            import sagemaker
            sagemaker_session = sagemaker.Session()
            self.role = sagemaker.get_execution_role()
        except: 
            self.role = self.sm_config['role'] 
        self.region = self.sm_config['region'] 
        self.account_id = str(self.sm_config['account_id'])
        self.region = self.sm_config['region']
        ## s3
        self.s3_uri = self.sm_config['s3_bucket_uri']
        self.bucket, self.s3_folder =  self._parse_s3_url(self.s3_uri) # (ex) aicontents-marketplace, cad/inference/
        ## ecr
        self.ecr_repository = self.sm_config['ecr_repository']
        # FIXME ecr tag ??
        self.ecr_tag = [] 
        self.docker_tag = 'latest'
        self.ecr_uri = f'{self.account_id}.dkr.ecr.{self.region}.amazonaws.com'
        self.ecr_full_uri = self.ecr_uri + f'/{self.ecr_repository}:{self.docker_tag}'
        ## resource
        # FIXME 일단 이건 sagemaker_config 로는 안뺌 
        self.train_instance_count = 1 
        self.train_instance_type = self.sm_config['train_instance_type']
            
    
    def setup(self):
        """
        docker build 에 필요한 요소들을 sagemaker dir에 복사합니다.
        """
        # 폴더가 이미 존재하는 경우 삭제합니다.
        if os.path.exists(self.sagemaker_dir):
            shutil.rmtree(self.sagemaker_dir)
        # 새로운 폴더를 생성합니다.
        os.mkdir(self.sagemaker_dir)
        # 컨테이너 빌드에 필요한 파일들을 sagemaker dir로 복사 
        alo_src = ['main.py', 'src', 'solution', 'assets', 'alolib', '.git', 'input', 'requirements.txt']
        for item in alo_src:
            src_path = PROJECT_HOME + item
            if os.path.isfile(src_path):
                shutil.copy2(src_path, self.sagemaker_dir)
                PROC_LOGGER.process_info(f'copy from << {src_path} >>  -->  << {self.sagemaker_dir} >> ')
            elif os.path.isdir(src_path):
                dst_path =  self.sagemaker_dir + os.path.basename(src_path)
                shutil.copytree(src_path, dst_path)
                PROC_LOGGER.process_info(f'copy from << {src_path} >>  -->  << {self.sagemaker_dir} >> ')
                

    def build_solution(self): 
        """
        docker build, ecr push, create s3 bucket 
        """
        # Dockefile setting
        sagemaker_dockerfile = PROJECT_HOME + 'src/Dockerfiles/SagemakerDockerfile'
        # Dockerfile이 이미 존재하는 경우 삭제합니다. 
        if os.path.isfile(PROJECT_HOME + 'Dockerfile'):
            os.remove(PROJECT_HOME + 'Dockerfile')
        shutil.copy(sagemaker_dockerfile, PROJECT_HOME + 'Dockerfile')
        # aws ecr login 
        p1 = subprocess.Popen(
            ['aws', 'ecr', 'get-login-password', '--region', self.region], stdout=subprocess.PIPE
        )
        # 주의: 여기선 ecr_full_uri 가 아닌 ecr_uri 
        p2 = subprocess.Popen( 
            [f'docker', 'login', '--username', 'AWS','--password-stdin', self.ecr_uri], stdin=p1.stdout, stdout=subprocess.PIPE
        )
        p1.stdout.close()
        output = p2.communicate()[0]
        PROC_LOGGER.process_info(f"AWS ECR | docker login result: \n {output.decode()}")
        # aws ecr repo create 
        # ECR 클라이언트 생성
        self._create_ecr_repository(ecr_repository=self.ecr_repository)
        # docker build 
        subprocess.run(['docker', 'build', '.', '-t', f'{self.ecr_full_uri}'])
        # docker push to ecr 
        subprocess.run(['docker', 'push', f'{self.ecr_full_uri}'])
        # 사용자가 작성한 s3 bucket이 존재하지 않으면 생성하기 
        self._create_bucket()


    def fit_estimator(self):
        """
        fit sagemaker estimator (cloud resource train)
        """
        from sagemaker.estimator import Estimator
        training_estimator = Estimator(image_uri=self.ecr_full_uri,
                                role=self.role,
                                train_instance_count=self.train_instance_count,
                                train_instance_type=self.train_instance_type,
                                output_path=self.s3_uri)
        training_estimator.fit() 
        
        
    def _install_sagemaker(self):
        # FIXME 버전 hard coded: 어디다 명시할지?
        package = SAGEMAKER_PACKAGE
        try: # 이미 같은 버전 설치 돼 있는지 
            pkg_resources.get_distribution(package) # get_distribution tact-time 테스트: 약 0.001s
            PROC_LOGGER.process_info(f'[OK] << {package} >> already exists')
        except: # 사용자 가상환경에 해당 package 설치가 아예 안 돼있는 경우 
            try: # nested try/except 
                PROC_LOGGER.process_info(f'>>> Start installing package - {package}')
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
            except Exception as e:
                PROC_LOGGER.process_error(f"Failed to install {package}: \n {str(e)}")
                
                
    def _parse_s3_url(self, uri):
        parts = urlparse(uri)
        bucket = parts.netloc
        key = parts.path.lstrip('/')
        return bucket, key
    
    
    def _create_bucket(self):
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
        

    def _create_ecr_repository(self, ecr_repository):
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
            client.download_file(self.bucket, latest_model_path, PROJECT_HOME + 'model.tar.gz')  
            PROC_LOGGER.process_info(f"Succes downloading {self.bucket}/{latest_model_path} --> {PROJECT_HOME}")
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
            # alo에서 생성했던 'train_artifacts.tar.gz'과 'model.tar.gz' 중 train_artifacts 만 PROJECT HOME에 압축해제 (--> log, models, output,..)
            # FIXME 이미 .train_artifacts 존재해도 에러 안나고 덮어쓰기 되는지 ? 
            if 'train_artifacts.tar.gz' in os.listdir(self.temp_model_extract_dir): 
                tar = tarfile.open(self.temp_model_extract_dir + 'train_artifacts.tar.gz')
                # .train_artifacts 폴더 없으면 생성 
                _create_dir(PROJECT_HOME + '.train_artifacts')
                tar.extractall(PROJECT_HOME + '.train_artifacts/')
                tar.close() 
        except: 
            PROC_LOGGER.process_error(f"Failed to download latest sagemaker created model from s3 : \n << {self.s3_uri} >>")
        finally: 
            # PROJECT_HOME 상의 model.tar.gz (s3로 부터 받은) 제거 및 temp dir 제거 
            if os.path.exists(PROJECT_HOME + 'model.tar.gz'): 
                os.remove(PROJECT_HOME + 'model.tar.gz')
            shutil.rmtree(self.temp_model_extract_dir, ignore_errors=True)


## FIXME sagemaker notebook 이외의 로컬 환경에서 sagemaker role 어떻게 얻을지? 
## https://github.com/aws/sagemaker-python-sdk/issues/300
# def resolve_sm_role():
#     client = boto3.client('iam', region_name=region)
#     response_roles = client.list_roles(
#         PathPrefix='/',
#         # Marker='string',
#         MaxItems=999
#     )
#     for role in response_roles['Roles']:
#         if role['RoleName'].startswith('AmazonSageMaker-ExecutionRole-'):
#             print('Resolved SageMaker IAM Role to: ' + str(role))
#             return role['Arn']
#     raise Exception('Could not resolve what should be the SageMaker role to be used')