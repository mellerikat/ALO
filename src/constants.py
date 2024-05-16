import os

###################################
##### Info / Format / Type
###################################
## alolib url candidates
## 1. http://mod.lge.com/hub/dxadvtech/aicontents-framework/alolib-source.git
## 2. https://github.com/meerkat-alo/alolib-source.git
ALO_LIB_URI = "https://github.com/meerkat-alo/alolib-source.git"
TIME_FORMAT = "%Y%m%dT%H%M%SZ"
TIME_FORMAT_DISPLAY = "%Y-%m-%d %H:%M:%S"
## interface mode support type 
INTERFACE_TYPES = ["memory", "file"]
TABULAR_OUTPUT_FORMATS = [".csv"]
IMAGE_OUTPUT_FORMATS = [".jpg", ".jpeg", ".png", ".svg"]
BASE_DIRS_STRUCTURE = {
    'input': {}, 
    'train_artifacts': {
        'score': {},
        'output': {},
        'extra_output': {}, 
        'log': {},
        'report': {},
        'models': {}
    },
    'inference_artifacts': {
        'score': {},
        'output': {},
        'extra_output': {}, 
        'log': {}
    },
    '.asset_interface': {},
    'history': {}
}
## performance check option (True: measure memory, cpu / False)
CHECK_RESOURCE_LIST = [True, False] 
EXPERIMENTAL_OPTIONAL_KEY_LIST = ["ui_args_detail"]
###################################
##### Path
###################################
## alo base path
PROJECT_HOME = os.path.dirname(os.path.abspath(os.path.dirname(__file__))) + "/"
ALO_LIB = PROJECT_HOME + "alolib/"
ASSET_HOME = PROJECT_HOME + "assets/"
INPUT_DATA_HOME = PROJECT_HOME + "input/"
TRAIN_ARTIFACTS_PATH = PROJECT_HOME + "train_artifacts/"
INFERENCE_ARTIFACTS_PATH = PROJECT_HOME + "inference_artifacts/"
TRAIN_LOG_PATH = PROJECT_HOME + "train_artifacts/log/"
TRAIN_MODEL_PATH = PROJECT_HOME + "train_artifacts/models/"
INFERENCE_MODEL_PATH = PROJECT_HOME + "inference_artifacts/models/"
EXPERIMENTAL_HISTORY_PATH = "log/experimental_history.json"
## artifacts.tar.gz temp saved path before export
TEMP_ARTIFACTS_PATH = PROJECT_HOME + ".TEMP_ARTIFACTS_PATH/"
## model.tar.gz temp saved path before import  
TEMP_MODEL_PATH = PROJECT_HOME + ".TEMP_MODEL_PATH/"
HISTORY_PATH = PROJECT_HOME + "history/"
INFERENCE_LOG_PATH = PROJECT_HOME + "inference_artifacts/log/"
INFERENCE_SCORE_PATH = PROJECT_HOME + "inference_artifacts/score/" 
INFERENCE_OUTPUT_PATH = PROJECT_HOME + "inference_artifacts/output/" 
ASSET_PACKAGE_DIR = ".package_list/"
ASSET_PACKAGE_PATH = PROJECT_HOME + ASSET_PACKAGE_DIR
## AI solution related path 
SOLUTION_HOME = PROJECT_HOME + "solution/"
SOURCE_HOME = PROJECT_HOME + "src/"
BACKUP_SOURCE_DIRECTORY = "backup_source/"
## AWS codebuild related path 
AWS_CODEBUILD_ZIP_PATH = PROJECT_HOME + ".codebuild_solution_zip/"
AWS_CODEBUILD_BUILD_SOURCE_PATH = AWS_CODEBUILD_ZIP_PATH + ".register_source/"
## AWS sagemaker related path 
SAGEMAKER_PATH = PROJECT_HOME + ".sagemaker/"
TEMP_SAGEMAKER_MODEL_PATH = PROJECT_HOME + ".temp_sagemaker_model/"
SAGEMAKER_DOCKER_WORKDIR = "/opt/ml/code/"
## AI solution registration related path 
REGISTER_SOURCE_PATH = PROJECT_HOME + ".register_source/"
REGISTER_MODEL_PATH = PROJECT_HOME + ".register_model/"  
REGISTER_ARTIFACT_PATH = PROJECT_HOME + ".register_artifacts/"
REGISTER_INTERFACE_PATH = PROJECT_HOME + ".register_interface/"
REGISTER_ICON_PATH = PROJECT_HOME + "src/icons/"
REGISTER_DOCKER_PATH = PROJECT_HOME + "src/Dockerfiles/register/"
###################################
##### Files 
###################################
COMPRESSED_MODEL_FILE = "model.tar.gz"
COMPRESSED_TRAIN_ARTIFACTS_FILE = "train_artifacts.tar.gz"
## inference_artifacts compression format: tar.gz / zip (experimental_plan.yaml - save_inference_format)
COMPRESSED_INFERENCE_ARTIFACTS_TAR_GZ = "inference_artifacts.tar.gz"
COMPRESSED_INFERENCE_ARTIFACTS_ZIP = "inference_artifacts.zip"
## log file 
PROCESS_LOG_FILE = "process.log"
PIPELINE_LOG_FILE = "pipeline.log" 
## default experimental plan yaml
DEFAULT_EXP_PLAN = SOLUTION_HOME + "experimental_plan.yaml"
EXPERIMENTAL_PLAN_FORMAT_FILE = PROJECT_HOME + "src/ConfigFormats/experimental_plan_format.yaml"
## AI solution related file 
SOLUTION_META = PROJECT_HOME + "solution_metadata.yaml"
## AWS codebuild related file
AWS_CODEBUILD_BUILDSPEC_FORMAT_FILE = PROJECT_HOME + "src/ConfigFormats/aws_codebuild_buildspec_format.yaml"
AWS_CODEBUILD_S3_PROJECT_FORMAT_FILE = PROJECT_HOME + "src/ConfigFormats/aws_codebuild_s3_project_format.json"
AWS_CODEBUILD_S3_SOLUTION_FILE = "codebuild_solution" 
AWS_CODEBUILD_BUILDSPEC_FILE = "buildspec.yml" 
## AWS sagemaker related file
SAGEMAKER_PACKAGE = "sagemaker==2.203.1"
SAGEMAKER_CONFIG = PROJECT_HOME + "setting/sagemaker_config.yaml"
SAGEMKAER_DOCKERFILE = PROJECT_HOME + "src/Dockerfiles/SagemakerDockerfile"
SAGEMAKER_EXP_PLAN = SAGEMAKER_PATH + 'solution/experimental_plan.yaml'
## AI solution registration related file
DEFAULT_INFRA_SETUP = PROJECT_HOME + "setting/infra_config.yaml"
DEFAULT_SOLUTION_INFO = PROJECT_HOME + "setting/solution_info.yaml"
REGISTER_WRANGLER_PATH = SOLUTION_HOME + "wrangler/wrangler.py"
REGISTER_EXPPLAN = REGISTER_SOURCE_PATH + "solution/experimental_plan.yaml"
## Redis pubsub error code table
REDIS_ERROR_TABLE = PROJECT_HOME + "src/config/redis_error_table.json" 