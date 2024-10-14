# -*- coding: utf-8 -*-
import os 
# LangGraph home
ENGINE_HOME = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__)))) + "/"
LANGGRAPH_HOME = os.path.dirname(os.path.abspath(os.path.dirname(__file__))) + "/"
INTERFACE_HOME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))) + '/interface/'
print('----- ENGINE HOME: ', ENGINE_HOME)
print('----- LANGGRAPH HOME: ', LANGGRAPH_HOME)

LANGGRAPH_ARTIFACTS_PATH = LANGGRAPH_HOME + "langgraph_artifacts/" 

# template 
TEMPLATE_HOME = LANGGRAPH_HOME + 'templates/'
EXPERIMENTAL_PLAN_TEMPLATE = 'experimental_plan_template.yaml'
PIPELINE_TEMPLATE = 'pipeline_template.py'

# prompts
PROMPTS_PATH = LANGGRAPH_HOME + 'prompts/'
SYSTEM_MD = 'system.md'
ERROR_YES_MD = 'error_yes.md'
ERROR_MD = 'error.md'
CONTEXT_MD = 'context.md'
QUESTION_MD = 'question.md'

# alo 
ALO_HOME = ENGINE_HOME + 'alo_engine/'
ALO_MAIN_FILE = ALO_HOME + 'main.py'
ALO_REQUIREMENTS = ALO_HOME + 'requirements.txt'

SOLUTION_PATH = ALO_HOME + 'solution/'
EXPERIMENTAL_PLAN_PATH = SOLUTION_PATH + 'experimental_plan.yaml'
SINGLE_DATA_PATH = SOLUTION_PATH + 'data/single/' #FIXME TEMP
TRAIN_DATA_PATH = SOLUTION_PATH + 'data/train/' #FIXME TEMP
INFERENCE_DATA_PATH = SOLUTION_PATH + 'data/inference/' #FIXME TEMP
PIPELINE_PATH = SOLUTION_PATH + 'pipeline.py'