import os
import sys 

PROJECT_HOME = os.path.dirname(os.path.abspath(os.path.dirname(__file__))) + "/"
SOLUTION_HOME = PROJECT_HOME + "solution/"
# experimental plan yaml의 위치
EXP_PLAN = SOLUTION_HOME + "experimental_plan.yaml"
ALO_LIB = PROJECT_HOME + "alolib/"

SOLUTION_META = PROJECT_HOME + "solution_metadata.yaml"

# interface mode support type 
INTERFACE_TYPES = ['memory', 'file']

# asset 코드들의 위치
# FIXME wj mnist, titanic example을 만들기 사용하는 함수 리스트를 작성
ASSET_HOME = PROJECT_HOME + "assets/"

INPUT_DATA_HOME = PROJECT_HOME + "input/"


TRAIN_LOG_PATH = PROJECT_HOME + ".train_artifacts/log/"

artifacts_structure = {
    'input': {}, 
    '.train_artifacts': {
        'score': {},
        'output': {},
        'log': {},
        'report': {},
        'models': {}
    },
    '.inference_artifacts': {
        'score': {},
        'output': {},
        'log': {}
    },
    '.asset_interface': {},
    '.history': {}
}

###################################
##### Set sagemaker 
###################################
SAGEMAKER_CONFIG = PROJECT_HOME + "setting/sagemaker_config.yaml"
SAGEMKAER_DOCKERFILE = PROJECT_HOME + 'src/Dockerfiles/SagemakerDockerfile'


###################################
##### Register AI Solution 
###################################
### 삭제되어야 할 대상
REGISTER_MODEL_PATH = PROJECT_HOME + ".register_model/"   ## AIC 에서 download 한 model.tar.gz 임시 저장
REGISTER_ARTIFACT_PATH = PROJECT_HOME + ".register_artifacts/"
REGISTER_SOURCE_PATH = PROJECT_HOME + ".register_source/"


INFRA_CONFIG = PROJECT_HOME + "setting/infra_config.yaml"

REGISTER_WRANGLER_PATH = SOLUTION_HOME + "wrangler/wrangler.py"
REGISTER_INTERFACE_PATH = PROJECT_HOME + ".register_interface/"
REGISTER_ICON_PATH = PROJECT_HOME + "src/icons/"
REGISTER_DOCKER_PATH = PROJECT_HOME + "src/Dockerfiles/register/"
REGISTER_EXPERIMENTAL_PLAN = REGISTER_SOURCE_PATH + "solution/experimental_plan.yaml"