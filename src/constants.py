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