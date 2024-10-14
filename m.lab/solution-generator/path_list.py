import os
import sys
PROJECT_PATH = os.path.abspath(os.path.dirname(__file__)) + "/"
# interface
INTERFACE_PATH = PROJECT_PATH + "interface/"
SOURCE_NOTEBOOK_PATH = INTERFACE_PATH + "source_notebook/"
SOURCE_PY_PATH = INTERFACE_PATH + "source_py/"
DATA_PATH = INTERFACE_PATH + "data/"
DATA_META_PATH = INTERFACE_PATH + "data_metadata/"
DATA_META_FILE = DATA_META_PATH + "data_meta.json"
VENV_PATH = INTERFACE_PATH + "py310_venv/"
MULTIPY_SRC_PATH = SOURCE_PY_PATH + "src/"

# engine
ENGINE_PATH = PROJECT_PATH + "engine/"

# alo
ALO_PATH = ENGINE_PATH + "alo_engine/"
MAIN_FILE_PATH = ALO_PATH + "main.py"
# SOLUTION_PATH = ALO_PATH + "solution/"
# EXPERIMENTAL_PLAN_PATH = SOLUTION_PATH + 'experimental_plan.yaml'
# PIPELINE_PATH = SOLUTION_PATH + 'pipeline.py'
# DATA_PATH = ALO_PATH + "data"    # 수정 필요
# SINGLE_DATA_PATH = DATA_PATH + 'single/'
# TRAIN_DATA_PATH = DATA_PATH + 'train/'
# INFERENCE_DATA_PATH = DATA_PATH + 'inference/'

# gen_soltion(langgraph)
LANGGRAPH_PATH = ENGINE_PATH + "gen_soltuion/"

sys.path.append(MULTIPY_SRC_PATH)