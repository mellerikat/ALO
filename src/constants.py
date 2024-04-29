import os

PROJECT_HOME = os.path.dirname(os.path.abspath(os.path.dirname(__file__))) + "/"
# alolib-url candidates
# 1. http://mod.lge.com/hub/dxadvtech/aicontents-framework/alolib-source.git
# 2. https://git-codecommit.ap-northeast-2.amazonaws.com/v1/repos/alolib
ALO_LIB = PROJECT_HOME + "alolib/"
ALO_LIB_URI = "http://mod.lge.com/hub/dxadvtech/aicontents-framework/alolib-source.git"
ALO_LIB_MEERKAT_URI = "https://github.com/meerkat-aicontents-framework/alolib-source"
TIME_FORMAT = '%Y%m%dT%H%M%SZ'
TIME_FORMAT_DISPLAY = '%Y-%m-%d %H:%M:%S'
# interface mode support type 
INTERFACE_TYPES = ['memory', 'file']
# asset 코드들의 위치
# FIXME wj mnist, titanic example을 만들기 사용하는 함수 리스트를 작성
ASSET_HOME = PROJECT_HOME + "assets/"
INPUT_DATA_HOME = PROJECT_HOME + "input/"
TRAIN_ARTIFACTS_PATH = PROJECT_HOME + "train_artifacts/"
INFERENCE_ARTIFACTS_PATH = PROJECT_HOME + "inference_artifacts/"
TRAIN_LOG_PATH = PROJECT_HOME + "train_artifacts/log/"
TRAIN_MODEL_PATH = PROJECT_HOME + "train_artifacts/models/"
INFERENCE_MODEL_PATH = PROJECT_HOME + "inference_artifacts/models/"
# artifacts.tar.gz  압축 파일을 외부 업로드하기 전 로컬 임시 저장 경로 
TEMP_ARTIFACTS_PATH = PROJECT_HOME + ".TEMP_ARTIFACTS_PATH/"
# 외부 model.tar.gz (혹은 부재 시 해당 경로 폴더 통째로)을 train_artifacts/models 경로로 옮기기 전 임시 저장 경로 
TEMP_MODEL_PATH = PROJECT_HOME + ".TEMP_MODEL_PATH/"
HISTORY_PATH = PROJECT_HOME + "history/"
COMPRESSED_MODEL_FILE = "model.tar.gz"
COMPRESSED_TRAIN_ARTIFACTS_FILE = "train_artifacts.tar.gz"
INFERENCE_LOG_PATH = PROJECT_HOME + "inference_artifacts/log/"
INFERENCE_SCORE_PATH = PROJECT_HOME + "inference_artifacts/score/" 
INFERENCE_OUTPUT_PATH = PROJECT_HOME + "inference_artifacts/output/" 
TABULAR_OUTPUT_FORMATS = [".csv"]
IMAGE_OUTPUT_FORMATS = [".jpg", ".jpeg", ".png", ".svg"]
ASSET_PACKAGE_DIR = ".package_list/"
ASSET_PACKAGE_PATH = PROJECT_HOME + ASSET_PACKAGE_DIR
PROCESS_LOG_FILE = "process.log"
PIPELINE_LOG_FILE = "pipeline.log" 
artifacts_structure = {
    'input': {}, 
    'train_artifacts': {
        'score': {},
        'output': {},
        'log': {},
        'report': {},
        'models': {}
    },
    'inference_artifacts': {
        'score': {},
        'output': {},
        'log': {}
    },
    '.asset_interface': {},
    'history': {}
}
###################################
##### Solution 
###################################
SOLUTION_HOME = PROJECT_HOME + "solution/"
SOLUTION_META = PROJECT_HOME + "solution_metadata.yaml"
SOURCE_HOME = PROJECT_HOME + "src/"
###################################
##### Experimental Plan 
###################################
# experimental plan yaml의 위치
DEFAULT_EXP_PLAN = SOLUTION_HOME + "experimental_plan.yaml"
EXPERIMENTAL_PLAN_FORMAT_FILE = PROJECT_HOME + "src/ConfigFormats/experimental_plan_format.yaml"
EXPERIMENTAL_OPTIONAL_KEY_LIST = ['ui_args_detail']
###################################
##### AWS CodeBuild
###################################
AWS_CODEBUILD_BUILDSPEC_FORMAT_FILE = PROJECT_HOME + "src/ConfigFormats/aws_codebuild_buildspec_format.yaml"
AWS_CODEBUILD_S3_PROJECT_FORMAT_FILE = PROJECT_HOME + "src/ConfigFormats/aws_codebuild_s3_project_format.json"
AWS_CODEBUILD_S3_SOLUTION_FILE = "codebuild_solution" #.zip
AWS_CODEBUILD_ZIP_PATH = PROJECT_HOME + ".codebuild_solution_zip/"
AWS_CODEBUILD_BUILD_SOURCE_PATH = AWS_CODEBUILD_ZIP_PATH + ".register_source/"
AWS_CODEBUILD_BUILDSPEC_FILE = "buildspec.yml" 
###################################
##### Set sagemaker 
###################################
# FIXME sagemaker version hard-fixed
SAGEMAKER_PACKAGE = "sagemaker==2.203.1"
SAGEMAKER_CONFIG = PROJECT_HOME + "setting/sagemaker_config.yaml"
SAGEMKAER_DOCKERFILE = PROJECT_HOME + "src/Dockerfiles/SagemakerDockerfile"
SAGEMAKER_PATH = PROJECT_HOME + ".sagemaker/"
TEMP_SAGEMAKER_MODEL_PATH = PROJECT_HOME + ".temp_sagemaker_model/"
###################################
##### Register AI Solution 
###################################
REGISTER_MODEL_PATH = PROJECT_HOME + ".register_model/"   ## AIC 에서 download 한 model.tar.gz 임시 저장
REGISTER_ARTIFACT_PATH = PROJECT_HOME + ".register_artifacts/"
REGISTER_SOURCE_PATH = PROJECT_HOME + ".register_source/"
DEFAULT_INFRA_SETUP = PROJECT_HOME + "setting/infra_config.yaml"
DEFAULT_SOLUTION_INFO = PROJECT_HOME + "setting/solution_info.yaml"
REGISTER_WRANGLER_PATH = SOLUTION_HOME + "wrangler/wrangler.py"
REGISTER_INTERFACE_PATH = PROJECT_HOME + ".register_interface/"
REGISTER_ICON_PATH = PROJECT_HOME + "src/icons/"
REGISTER_DOCKER_PATH = PROJECT_HOME + "src/Dockerfiles/register/"
REGISTER_EXPPLAN = REGISTER_SOURCE_PATH + "solution/experimental_plan.yaml"