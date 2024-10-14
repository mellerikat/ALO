# -*- coding: utf-8 -*-
import argparse
import logging
import os
import re
import subprocess
import sys 
from typing import List, TypedDict
from langgraph.graph import END, StateGraph
from langchain_core.prompts import ChatPromptTemplate,PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from openai import AzureOpenAI
from pathlib import Path
from langchain.chat_models import AzureChatOpenAI
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from operator import itemgetter
import os
import subprocess
import shutil
import glob
from pprint import pprint 
import tiktoken

current_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_directory) 
from prompt_paths import *
from path_list import *

INTERFACE_DIR = INTERFACE_PATH
SRC_DIR = os.path.join(SOURCE_PY_PATH,'src')
TRAIN_DATA_PATH = os.path.join(DATA_PATH, 'train')
INFERENCE_DATA_PATH = os.path.join(DATA_PATH, 'inference')

from util_funcs import (
    get_chunk_with_token_limit,
    with_structured_output_python,
    with_structured_output_req,
    create_and_use_venv,
    do_pip_tools,
    compare_and_touch_req,
    file_to_str,
    load_prompt
)

# Constant
TEMPERATURE = 0.7
FLAG = "do not reflect"  # 'reflect'
class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        error : Binary flag for control flow to indicate whether test error was tripped
        messages : With user question, error messages, reasoning
        generation : Code solution
        iterations : Number of tries
    """
    error: str
    error_type: str

    msg_stdout: str
    
    err_sol_pair_py: List
    err_sol_pair_req: List
    err_sol_pair_env: List

    log_lst: List

    rules: str
    generation_guide: str
    code_summary: str
    paper_summary: str
    paper_name: str

    generation_py: str
    generation_req : str

    iteration_py: int
    iteration_data: int
    iteration_req: int
    iteration_env: int

    data_meta: str
    src_path: str

    branch_flg: str

    graph_result : str

class GraphRunner:
    def __init__(
            self,
            prev_step_result_dict,
            py_path,
            req_path,
            src_path = SRC_DIR,
            max_iterations_py= 10,
            max_iterations_data= 5,
            max_iterations_req = 3,
            max_iterations_env = 5
        ):

        # print(f"------- [INFO] current generation mode: << {self.generation_mode} >>")
        
        self.max_iterations_py = max_iterations_py
        self.max_iterations_req = max_iterations_req
        self.max_iterations_env = max_iterations_env
        self.max_iterations_data = max_iterations_data

        self.src_path = src_path
        
        self.py_file_path = py_path
        self.req_file_path = req_path
        self.prev_step_result_dict = prev_step_result_dict

        print(f"----- [INFO] INPUT METADATA: {self.prev_step_result_dict} -----")
        print(f"----- [INFO] PYTHON FILE PATH: {self.py_file_path} -----")
        print(f"----- [INFO] REQUIREMENTS FILE PATH: {self.req_file_path} -----")
        print(f"----- [INFO] MAX LANGGRAPH ITERATION TYPE 1: {self.max_iterations_py} -----")
        print(f"----- [INFO] MAX LANGGRAPH ITERATION TYPE 2: {self.max_iterations_data} -----")
        print(f"----- [INFO] MAX LANGGRAPH ITERATION TYPE 3: {self.max_iterations_req} -----")
        print(f"----- [INFO] MAX LANGGRAPH ITERATION TYPE 4: {self.max_iterations_env} -----")

        self.setup_paths()

    def setup_paths(self):

        self.prompt_path_data_adapt = PROMPT_PATH_DATA_ADAPT
        self.prompt_path_classify_error= PROMPT_PATH_CLASSIFY_ERROR

        self.prompt_path_find_method_in_py = PROMPT_PATH_FIND_METHOD_IN_PY
        self.prompt_path_summarize_codes = PROMPT_PATH_SUMMARIZE_CODES

        self.prompt_path_pwc_type_1_fix= PROMPT_PATH_PWC_TYPE_1_FIX
        self.prompt_path_pwc_type_1_analyze= PROMPT_PATH_PWC_TYPE_1_ANALYZE
        self.prompt_path_pwc_type_3_fix= PROMPT_PATH_PWC_TYPE_3_FIX
        self.prompt_path_pwc_type_3_analyze= PROMPT_PATH_PWC_TYPE_3_ANALYZE
        
        self.prompt_path_single_type_1_fix= PROMPT_PATH_SINGLE_TYPE_1_FIX
        self.prompt_path_single_type_1_analyze= PROMPT_PATH_SINGLE_TYPE_1_ANALYZE
        self.prompt_path_single_type_3_fix= PROMPT_PATH_SINGLE_TYPE_3_FIX
        self.prompt_path_single_type_3_analyze= PROMPT_PATH_SINGLE_TYPE_3_ANALYZE
        
        self.prompt_path_multi_type_1_fix= PROMPT_PATH_MULTI_TYPE_1_FIX
        self.prompt_path_multi_type_1_analyze= PROMPT_PATH_MULTI_TYPE_1_ANALYZE
        self.prompt_path_multi_type_3_fix= PROMPT_PATH_MULTI_TYPE_3_FIX
        self.prompt_path_multi_type_3_analyze= PROMPT_PATH_MULTI_TYPE_3_ANALYZE
        
        self.prompt_path_type_2_fix= PROMPT_PATH_TYPE_2_FIX
        self.prompt_path_type_2_analyze= PROMPT_PATH_TYPE_2_ANALYZE
        
        self.prompt_path_type_4_analyze= PROMPT_PATH_TYPE_4_ANALYZE

    def setup_model(self,input_temp=None):

        # EXPT_LLM = "gpt-4o-2024-05-13"
        api_type = os.getenv("OPENAI_API_TYPE")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("OPENAI_API_VERSION")
        EXPT_LLM = os.getenv("OPENAI_MODEL_ID")

        if input_temp is None:

            temperature = TEMPERATURE
        else:
            temperature = input_temp

        return AzureChatOpenAI(
            azure_deployment = EXPT_LLM,
            model= 'gpt-4o', # 협의 후 이름 정해서 env로 뺼 예정
            temperature=temperature
        )
    
    def fix_req(self,state: GraphState):

        """
        Generate a modified requiremnets.txt

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, generation
        """

        print("----- [INFO] FIXING TYPE 3 ERROR NODE: START GENERATING MODIFED REQUIREMENTS.TXT -----")
        code_summary = state['code_summary']

        error_type= state['error_type']
        err_sol_pair_req = state['err_sol_pair_req']
        error = err_sol_pair_req[-1][0]
        current_req = err_sol_pair_req[-1][1]
        current_py = state['generation_py']

        branch_flg = state['branch_flg']

        print('----- [INFO] FIXING TYPE 3 ERROR NODE: REQRUIREMENTS BEFORE FIXING ERROR IS : \n')
        print(current_req)
        if branch_flg == 'paper_with_code':

            prompt_placeholder = load_prompt(
                self.prompt_path_pwc_type_3_analyze
            )
            prompt_analyze_req= PromptTemplate.from_template(
                    prompt_placeholder
                )
            chain_context = {
                    'original_requirements' : itemgetter('original_requirements'),
                    'error': itemgetter('error'),
                    'code_summary': itemgetter('code_summary')
                }
            invoke_dict= {
                'original_requirements': current_req,
                'error': get_chunk_with_token_limit(error,token_limit=2048),
                'code_summary':code_summary
            }

        elif branch_flg == 'single_py':
            
            prompt_placeholder = load_prompt(
                self.prompt_path_single_type_3_analyze
            )
            prompt_analyze_req= PromptTemplate.from_template(
                    prompt_placeholder
                )
            chain_context = {
                    'original_requirements' : itemgetter('original_requirements'),
                    'error': itemgetter('error'),
                }
            invoke_dict= {
                'original_requirements': current_req,
                'error': get_chunk_with_token_limit(error,token_limit=2048),
            }

        elif branch_flg == 'multi_py':

            if code_summary is None:
                src_path = state['src_path']
                code_summary = self.summarize_codes(
                    src_path = src_path
                )
            prompt_placeholder = load_prompt(
                self.prompt_path_multi_type_3_analyze
            )
            prompt_analyze_req= PromptTemplate.from_template(
                prompt_placeholder
            )
            chain_context = {
                    'original_requirements' : itemgetter('original_requirements'),
                    'error': itemgetter('error'),
                    'code_summary': itemgetter('code_summary')
                }
            invoke_dict= {
                'original_requirements': current_req,
                'error': get_chunk_with_token_limit(error,token_limit=2048),
                'code_summary':code_summary
            }
        
        llm_model = self.setup_model()

        chain_analyze_req = (
            chain_context
            | prompt_analyze_req
            | llm_model
            | StrOutputParser()
        )
        response = chain_analyze_req.invoke(invoke_dict)
        error_analysis = response
        
        if branch_flg == 'paper_with_code':

            prompt_placeholder = load_prompt(
                self.prompt_path_pwc_type_3_fix
            )
            prompt_fix_req= PromptTemplate.from_template(
                    prompt_placeholder
                )
            chain_context = {
                    'original_requirements' : itemgetter('original_requirements'),
                    'error_analysis': itemgetter('error_analysis'),
                    'code_summary': itemgetter('code_summary')
                }
            invoke_dict= {
                'original_requirements': current_req,
                'error_analysis': error_analysis,
                'code_summary':code_summary
            }
        elif branch_flg == 'single_py':
            prompt_placeholder = load_prompt(
                self.prompt_path_single_type_3_fix
            )
            prompt_fix_req= PromptTemplate.from_template(
                    prompt_placeholder
                )
            chain_context = {
                    'original_requirements' : itemgetter('original_requirements'),
                    'error_analysis': itemgetter('error_analysis'),
                }
            invoke_dict= {
                'original_requirements': current_req,
                'error_analysis': error_analysis,
            }

        elif branch_flg == 'multi_py':

            if code_summary is None:
                src_path = state['src_path']
                code_summary = self.summarize_codes(
                    src_path = src_path
                )
            prompt_placeholder = load_prompt(
                self.prompt_path_multi_type_3_fix
            )
            prompt_fix_req= PromptTemplate.from_template(
                prompt_placeholder
            )
            chain_context = {
                    'original_requirements' : itemgetter('original_requirements'),
                    'error_analysis': itemgetter('error_analysis'),
                    'code_summary': itemgetter('code_summary')
                }
            invoke_dict= {
                'original_requirements': current_req,
                'error_analysis': error_analysis,
                'code_summary':code_summary
            }
        
        chain_fix_req = (
            chain_context
            | prompt_fix_req
            | llm_model
            | StrOutputParser()
        )

        response = chain_fix_req.invoke(invoke_dict)
        req_parsed = with_structured_output_req(response)

        if len(req_parsed) <= 1:
            req_touched = req_parsed
        else:
            req_touched = compare_and_touch_req(
                req_old= current_req,
                req_new= req_parsed
            )
        req_piptooled = do_pip_tools(
            req_touched,
            venv_dir= os.path.join(
                INTERFACE_DIR,
                'py310_venv'
            )
        ) #추가1111
        print('----- [INFO] FIXING TYPE 3 ERROR NODE: REQUIREMENTS AFTER FIXING ERROR IS : \n')
        print(req_piptooled)
        
        iteration_req = state['iteration_req']
        iteration_req += 1

        log_lst = state['log_lst']
        log_lst.append(
            {
                'error_type': error_type,
                'error_raw': error,
                'error_analysis': error_analysis,
                'state_old_py': current_py,
                'state_new_py': current_py,
                'state_old_req': current_req,
                'state_new_req': req_piptooled,
            }
        )
        print("----- [INFO] FIXING TYPE 3 ERROR NODE : GENERATING MODIFED REQUIREMENTS.TXT FINISHED -----")
        return {"generation_req": req_piptooled, "iteration_req": iteration_req,"code_summary":code_summary,'log_lst':log_lst}
    
    def summarize_codes(
            self,
            src_path,
            run_code_path=None
        ):
        print('----- [INFO] START SUMMARIZING SRC DIRECTORY -----')
        if run_code_path is None:
            run_code_path = src_path

        files = glob.glob(
            src_path+'/**/*.py'
        )
        print('----- [INFO] NEXT FILES WILL BE SUMMARIZED :')
        pprint(files)
        if len(files) == 0:
            print('----- [INFO] GLOB FAILED RETURN EMPTY STRING AS CODE_SUMMARY.')
            return ''

        py_to_str = []
        for cloned_file_path in files:
                
            py_opened = file_to_str(
                cloned_file_path,
                read_type='str'
            )
            py_to_str.append(
                [
                    cloned_file_path,
                    py_opened
                ]
            )
        prompt_placeholder_find_method = load_prompt(
                self.prompt_path_find_method_in_py
            )
        prompt_find_method_in_py = PromptTemplate.from_template(
                prompt_placeholder_find_method
            )
        llm_model = self.setup_model(input_temp=0.1)
        chain_get_method_name = (
            prompt_find_method_in_py
            | llm_model
            | StrOutputParser()
        )

        prompt_placeholder_summarize_codes = load_prompt(
                self.prompt_path_summarize_codes
            )
        prompt_summarize_codes = PromptTemplate.from_template(
                prompt_placeholder_summarize_codes
            )

        chain_summarize_codes = (
            prompt_summarize_codes
            | llm_model
            | StrOutputParser()
        )
        code_summary = []
        for path_code in py_to_str:

            file_path,codes = path_code[0], path_code[1]
            method_names=  chain_get_method_name.invoke(
                {
                    'codes':codes
                }
            )
            
            # gpt 가 항상 # 형식 맞춰서 준다고 가정
            method_names = method_names.split('#')
            for each_method in method_names:

                response = chain_summarize_codes.invoke(
                    {
                        'method': each_method,
                        'code_path': os.path.relpath(file_path,start=run_code_path),
                        'run_path' : run_code_path,
                        'codes':codes,
                    }
                )

                code_summary.append(response)
                print(response)
                

        code_summary = '\n'.join(
            code_summary
        )
        return code_summary
        
    def fix_py(self,state: GraphState):
        """
        Generate a modified template.py

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, generation
        
        """

        print("----- [INFO] FIXING TYPE 1 ERROR NODE: START GENERATING MODIFED PY -----")

        paper_summary = state['paper_summary']
        code_summary = state['code_summary']
        rules = state['rules']
        generation_guide = state['generation_guide']
        paper_name = state['paper_name']

        error_type = state['error_type']
        err_sol_pair_py = state['err_sol_pair_py']
        error = err_sol_pair_py[-1][0]
        current_py = err_sol_pair_py[-1][1]
        current_req = state['generation_req']

        msg_stdout = state['msg_stdout']
        data_meta = state['data_meta']

        branch_flg = state['branch_flg']

        llm_model = self.setup_model()
        print("----- [INFO] FIXING TYPE 1 ERROR NODE: START SUB STEP 1(ANALYZING ERROR) -----")
        if branch_flg =='paper_with_code':

            prompt_placeholder = load_prompt(
                self.prompt_path_pwc_type_1_analyze
            )
            prompt_analyze_error = PromptTemplate.from_template(
                    prompt_placeholder
                )            
            chain_context = {
                    'original_codes': itemgetter('original_codes'),
                    'printed_stdout' : itemgetter('printed_stdout'),
                    'error': itemgetter('error'),
                    'data_meta' : itemgetter('data_meta'),
                    'code_summary': itemgetter('code_summary')
                }
            invoke_dict = {
                    'original_codes': current_py,
                    'printed_stdout': get_chunk_with_token_limit(msg_stdout,token_limit=2048),
                    'error': get_chunk_with_token_limit(error,token_limit=2048),
                    'data_meta': data_meta,
                    'code_summary':code_summary
                }
            
        elif branch_flg =='single_py':
            
            prompt_placeholder = load_prompt(
                self.prompt_path_single_type_1_analyze
            )
            prompt_analyze_error = PromptTemplate.from_template(
                    prompt_placeholder
                )
            chain_context = {
                    'original_codes': itemgetter('original_codes'),
                    'printed_stdout' : itemgetter('printed_stdout'),
                    'error': itemgetter('error'),
                    'data_meta' : itemgetter('data_meta')
                }
            invoke_dict = {
                    'original_codes': current_py,
                    'printed_stdout': get_chunk_with_token_limit(msg_stdout,token_limit=2048),
                    'error': get_chunk_with_token_limit(error,token_limit=2048),
                    'data_meta': data_meta,
                }
        elif branch_flg == 'multi_py':
        
            if code_summary is None:

                src_path = state['src_path']
                code_summary = self.summarize_codes(
                    src_path = src_path
                )

            prompt_placeholder = load_prompt(
                self.prompt_path_multi_type_1_analyze
            )
            prompt_analyze_error = PromptTemplate.from_template(
                    prompt_placeholder
                )
            chain_context = {
                    'original_codes': itemgetter('original_codes'),
                    'printed_stdout' : itemgetter('printed_stdout'),
                    'error': itemgetter('error'),
                    'data_meta' : itemgetter('data_meta'),
                    'code_summary': itemgetter('code_summary')
                }
            invoke_dict = {
                    'original_codes': current_py,
                    'printed_stdout': get_chunk_with_token_limit(msg_stdout,token_limit=2048),
                    'error': get_chunk_with_token_limit(error,token_limit=2048),
                    'data_meta': data_meta,
                    'code_summary':code_summary
                }

        chain_analyze_error = (
            chain_context
            | prompt_analyze_error
            | llm_model
            | StrOutputParser()
        )
        response = chain_analyze_error.invoke(invoke_dict)
        error_analysis = response
        print("----- [INFO] FIXING TYPE 1 ERROR NODE: SUB STEP 1 FINISHED(ANALYZING ERROR) -----")
        print('----- [INFO] FIXING TYPE 1 ERROR NODE: RESULT OF ANALYZING ERROR : -----\n')
        print(error_analysis)
        print("----- [INFO] FIXING TYPE 1 ERROR NODE: START SUB STEP 2(FIXING PY BY USING ERROR ANALYSIS) -----")
        
        if branch_flg == 'paper_with_code':

            prompt_placeholder = load_prompt(
                self.prompt_path_pwc_type_1_fix
            )       
            prompt_fix_py= PromptTemplate.from_template(
                prompt_placeholder
            )
            chain_context = {
                    'algorithm': itemgetter('algorithm'),
                    'rules': itemgetter('rules'),
                    'paper_summary': itemgetter('paper_summary'),
                    'code_summary': itemgetter('code_summary'),
                    'generation_guide': itemgetter('generation_guide'),
                    'original_codes': itemgetter('original_codes'),
                    'error_analysis': itemgetter('error_analysis')
                }
            invoke_dict = {
                    'algorithm': paper_name,
                    'paper_summary': paper_summary,
                    'rules': rules,
                    'code_summary': code_summary,
                    'generation_guide': generation_guide,
                    'original_codes': current_py,
                    'error_analysis': error_analysis
                }
        elif branch_flg == 'single_py':

            prompt_placeholder = load_prompt(
                self.prompt_path_single_type_1_fix
            )
            prompt_fix_py= PromptTemplate.from_template(
                    prompt_placeholder
                )
            chain_context = {
                    'original_codes': itemgetter('original_codes'),
                    'error_analysis': itemgetter('error_analysis')
                }
            invoke_dict = {
                    'original_codes': current_py,
                    'error_analysis': error_analysis,
                }

        elif branch_flg == 'multi_py':

            prompt_placeholder = load_prompt(
                self.prompt_path_multi_type_1_fix
            )
            prompt_fix_py= PromptTemplate.from_template(
                prompt_placeholder
            )
            chain_context = {
                    'original_codes': itemgetter('original_codes'),
                    'error_analysis': itemgetter('error_analysis'),
                    'code_summary': itemgetter('code_summary'),
                }
            invoke_dict = {
                    'original_codes': current_py,
                    'error_analysis': error_analysis,
                    'code_summary': code_summary,
                }
        
        chain_fix_py = (
            chain_context
            | prompt_fix_py
            | llm_model
            | StrOutputParser()
        )
        response = chain_fix_py.invoke(
                invoke_dict
            )

        py_parsed = with_structured_output_python(response)

        iteration_py = state['iteration_py']
        iteration_py += 1

        log_lst = state['log_lst']
        log_lst.append(
            {
                'error_type': error_type,
                'error_raw': error,
                'error_analysis': error_analysis,
                'state_old_py': current_py,
                'state_new_py': py_parsed,
                'state_old_req': current_req,
                'state_new_req': current_req,
            }
        )

        print("----- [INFO] FIXING TYPE 1 ERROR NODE: SUB STEP 2 FINISHED(FIXING PY BY USING ERROR ANALYSIS) -----")
        print("----- [INFO] FIXING TYPE 1 ERROR NODE: RESULT OF FIXED PY IS : -----\n")
        print(py_parsed)
        print('----- [INFO] FIXING TYPE 1 ERROR NODE: GENERATING MODIFED PY FINISHED -----')
        
        return {"generation_py": py_parsed, "iteration_py": iteration_py,"code_summary":code_summary,'log_lst':log_lst}

    def fix_py_data(self,state: GraphState):
        """
        Generate a modified template.py

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, generation
        
        """

        print("----- [INFO] FIXING TYPE 2 ERROR NODE: GENERATING MODIFED PY BY USING DATA DISCREPANCIES -----")
        print("----- [INFO] FIXING TYPE 2 ERROR NODE: START SUB STEP 1(ANALYZING ERROR) -----")
        error_type = state['error_type']
        err_sol_pair_py = state['err_sol_pair_py']
        error = err_sol_pair_py[-1][0]
        current_py = err_sol_pair_py[-1][1]
        current_req = state['generation_req']

        msg_stdout = state['msg_stdout']
        data_meta = state['data_meta']

        llm_model = self.setup_model()

        prompt_placeholder = load_prompt(
            self.prompt_path_type_2_analyze
        )    
        prompt_analyze_error = PromptTemplate.from_template(
            prompt_placeholder
        )
        chain_context = {
                'original_codes': itemgetter('original_codes'),
                'printed_stdout' : itemgetter('printed_stdout'),
                'error': itemgetter('error'),
                'data_meta' : itemgetter('data_meta')
            }
        invoke_dict = {
                'original_codes': current_py,
                'printed_stdout': get_chunk_with_token_limit(msg_stdout,token_limit=2048),
                'error': get_chunk_with_token_limit(error,token_limit=2048),
                'data_meta': data_meta,
            }
        chain_analyze_error = (
            chain_context
            | prompt_analyze_error
            | llm_model
            | StrOutputParser()
        )
        response = chain_analyze_error.invoke(
                invoke_dict
            )
        
        error_analysis = response
        print("----- [INFO] FIXING TYPE 2 ERROR NODE: SUB STEP 1 FINISHED(ANALYZING ERROR) -----")
        print('----- [INFO] FIXING TYPE 2 ERROR NODE: RESULT OF ANALYZING ERROR : -----\n')
        print(error_analysis)
        print("----- [INFO] FIXING TYPE 2 ERROR NODE: START SUB STEP 2(FIXING PY BY USING ERROR ANALYSIS) -----")
        prompt_placeholder = load_prompt(
            self.prompt_path_type_2_fix
        )
        prompt_fix_py= PromptTemplate.from_template(
                prompt_placeholder
            )
        chain_context = {
                'original_codes': itemgetter('original_codes'),
                'error_analysis': itemgetter('error_analysis'),
                'data_meta': itemgetter('data_meta'),
            }
        invoke_dict = {
                'original_codes': current_py,
                'error_analysis': error_analysis,
                'data_meta' : data_meta,
            }
        chain_fix_py = (
            chain_context
            | prompt_fix_py
            | llm_model
            | StrOutputParser()
        )
        response = chain_fix_py.invoke(
                invoke_dict
            )
        py_parsed = with_structured_output_python(response)

        iteration_data = state['iteration_data']
        iteration_data += 1

        log_lst = state['log_lst']
        log_lst.append(
            {
                'error_type': error_type,
                'error_raw': error,
                'error_analysis': error_analysis,
                'state_old_py': current_py,
                'state_new_py': py_parsed,
                'state_old_req': current_req,
                'state_new_req': current_req,
            }
        )
        print("----- [INFO] FIXING TYPE 2 ERROR NODE: SUB STEP 2 FINISHED(FIXING PY BY USING ERROR ANALYSIS) -----")
        print("----- [INFO] FIXING TYPE 2 ERROR NODE: RESULT OF FIXED PY IS : -----\n")
        print(py_parsed)
        print('----- [INFO] FIXING TYPE 2 ERROR NODE: GENERATING MODIFED PY BY USING DATA DISCREPANCY FINISHED -----')
        
        return {"generation_py": py_parsed, "iteration_data": iteration_data,'log_lst':log_lst}
    
    def data_adapt(self,state: GraphState):
        """
        Generate a modified template.py

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, generation
        
        """

        print("----- DATA ADAPTATION NODE: STARTING DATA ADAPTATION -----")

        current_py = state['generation_py']
        data_meta = state['data_meta']
        print("************************************************")
        print(f"DATA_META{data_meta}")
        print("************************************************")

        llm_model = self.setup_model()

        prompt_placeholder = load_prompt(
            self.prompt_path_data_adapt
        )
        prompt_fix_py= PromptTemplate.from_template(
                prompt_placeholder
            )
        chain_context = {
                'original_codes': itemgetter('original_codes'),
                'data_meta': itemgetter('data_meta')
            }
        invoke_dict = {
                'original_codes': current_py,
                'data_meta': data_meta,
            }
        
        chain_fix_py = (
            chain_context
            | prompt_fix_py
            | llm_model
            | StrOutputParser()
        )

        response = chain_fix_py.invoke(
                invoke_dict
            )
        py_parsed = with_structured_output_python(response)
        print('----- [INFO] DATA ADAPTATION RESULT IS : \n')
        print(py_parsed)
        print('----- [INFO] DATA ADAPTATION NODE: DATA ADAPTATION FINISHED -----')
        return {"generation_py": py_parsed, 'error_type':'data_adapt'}
        
    def py_check(self,state: GraphState):
        print("----- [INFO] START RUNNING BY USING MODIFIED PY AND REQUIREMENTS -----")
        code_solution = state['generation_py']
        requirements = state['generation_req']

        error_type = state['error_type']
        src_path_interface= state['src_path']
        
        msg_stdout, msg_stderr = create_and_use_venv( #추가 2222
            code_solution=code_solution,
            requirements=requirements,
            error_type= error_type,
            src_path_interface= src_path_interface,
            venv_dir=os.path.join(INTERFACE_DIR, 'py310_venv') 
        )
        py_run_test_msg = f'std out : {msg_stdout} \n\n std err : {msg_stderr}'
        print('RUN RESULT IS  : \n')
        print(py_run_test_msg)

        if msg_stdout == 'no':

            graph_result = 'success'
        else:
            graph_result = 'failed'
        print("----- [INFO] RUNNING BY USING MODIFIED PY AND REQUIREMENTS FINISHED -----")
        return {'error':msg_stderr,'msg_stdout':msg_stdout, 'graph_result': graph_result}


    def classify_error(self,state: GraphState):

        print('----- [INFO] CLASSIFYING ERROR NODE: START CLASSIFYING ERROR -----')
        
        latest_error_msg = state['error']
        if latest_error_msg == 'no':
            return {'error_type':'no'}

        prompt_placeholder = load_prompt(
            self.prompt_path_classify_error
        )
        prompt_classify_error = PromptTemplate.from_template(
                prompt_placeholder
            )
        llm_model = self.setup_model(
            input_temp = 0
        )
        chain_classify_error = (
            prompt_classify_error
            | llm_model
            | StrOutputParser()
        )
        invoke_dict = {
                'error' : latest_error_msg
            }
        response = chain_classify_error.invoke(
            invoke_dict
        )
        match = re.search(
            r'```response(.*?)```',
            response,
            re.DOTALL
        )
        if match is None:
            match = re.search(
                r'```\sresponse(.*?)```',
                response,
                re.DOTALL
            )
        
        if 'type_1' in response:
            
            error_type =  'type_1'
            current_py = state['generation_py']
            
            err_sol_pair_py = state['err_sol_pair_py']
            err_sol_pair_py.append(
                (
                    latest_error_msg,
                    current_py,
                    error_type
                )
            )
            print(f'----- [INFO] ERROR CLASSIFIED AS : {error_type} -----')
            print('----- [INFO] CLASSIFYING ERROR NODE: CLASSIFYING ERROR FINISHED -----')
            return {'error_type': error_type,'err_sol_pair_py':err_sol_pair_py}

        elif 'type_2' in response:
            
            error_type =  'type_2'
            current_py = state['generation_py']
            
            err_sol_pair_py = state['err_sol_pair_py']
            err_sol_pair_py.append(
                (
                    latest_error_msg,
                    current_py,
                    error_type
                )
            )
            print(f'----- [INFO] ERROR CLASSIFIED AS : {error_type} -----')
            print('----- [INFO] CLASSIFYING ERROR NODE: CLASSIFYING ERROR FINISHED -----')
            return {'error_type': error_type,'err_sol_pair_py':err_sol_pair_py}
    
        elif 'type_3' in response:
            
            error_type =  'type_3'
            current_req =  state['generation_req']

            err_sol_pair_req = state['err_sol_pair_req']
            err_sol_pair_req.append(
                (
                    latest_error_msg,
                    current_req,
                    error_type
                )
            )
            print(f'----- [INFO] ERROR CLASSIFIED AS : {error_type} -----')
            print('----- [INFO] CLASSIFYING ERROR NODE: CLASSIFYING ERROR FINISHED -----')
            return {'error_type': error_type, 'err_sol_pair_req':err_sol_pair_req}

        elif 'type_4' in response:
            
            error_type = 'type_4'
            current_py = state['generation_py']
            current_req= state['generation_req']
            err_sol_pair_env = state['err_sol_pair_env']

            err_sol_pair_env.append(
                (
                    latest_error_msg,
                    current_py,
                    current_req,
                    error_type
                )
            )

            err_sol_pair_py = state['err_sol_pair_py']
            err_sol_pair_py.append(
                (
                    latest_error_msg,
                    current_py,
                    error_type
                )
            )
            print(f'----- [INFO] ERROR CLASSIFIED AS : {error_type} -----')
            print('----- [INFO] CLASSIFYING ERROR NODE: CLASSIFYING ERROR FINISHED -----')
            return {'error_type': error_type, 'err_sol_pair_env': err_sol_pair_env,'err_sol_pair_py':err_sol_pair_py}

        else:
            raise Exception(f'error happened while classifying error. error must be class_py or class_req or class_env but got {response}')

    def reflect(self, state: GraphState):
        print(f"----- [INFO] REFLECT NODE: DO NOTHING -----")
        
        iterations = state["iteration_py"]
        code_solution = state["generation_py"]
        
        return {"generation_py": code_solution,  "iterations": iterations}
            
    def decide_to_finish(self,state: GraphState):

        error_type = state['error_type']

        iteration_py = state['iteration_py']
        iteration_data = state['iteration_data']
        iteration_req = state['iteration_req']
        iteration_env = state['iteration_env']

        if error_type == 'no':
            print("----- [INFO] GENERATING PY AND REQUIREMETNS SUCCESS! -----")
            return 'end'

        elif error_type == 'type_1':

            if iteration_py == self.max_iterations_py:
                
                print('----- [INFO] GRAPH FAILED: MAX ITERATION(TYPE 1 ERROR) REACHED -----')
                return 'failed_py'
            else:
                return 'fix_py'

        elif error_type == 'type_2':

            if iteration_data == self.max_iterations_data:
                
                print('----- [INFO] GRAPH FAILED: MAX ITERATION(TYPE 2 ERROR) REACHED -----')
                return 'failed_data'
            else:
                return 'fix_py_data'
        
        elif error_type in 'type_3':

            if iteration_req == self.max_iterations_req:
                
                print('----- [INFO] GRAPH FAILED: MAX ITERATION(TYPE 3 ERROR) REACHED -----')
                return 'failed_req'
            else:
                return 'fix_req'

        elif error_type in 'type_4':

            if iteration_env == self.max_iterations_env:

                print('----- [INFO] GRAPH FAILED: MAX ITERATION(TYPE 4 ERROR) REACHED -----')
                return 'failed_env'
            else:
                return 'fix_py'

        else:
            raise Exception(f'error type must be type_1, type_2, type_3, type_4 but got {error_type}')


    def save_log_py(self,state:GraphState):
        
        # need update 
        err_sol_pair_py = state['err_sol_pair_py']

        graph_result = state['graph_result']
        graph_result = 'failed_at_py'

        return {'err_sol_pair_py':err_sol_pair_py,'graph_result':graph_result}
    
    def save_log_data(self,state:GraphState):
        
        # need update 
        err_sol_pair_py = state['err_sol_pair_py']

        graph_result = state['graph_result']
        graph_result = 'failed_at_data'

        return {'err_sol_pair_py':err_sol_pair_py,'graph_result':graph_result}

    def save_log_req(self,state:GraphState):
        # need update 
        err_sol_pair_req = state['err_sol_pair_req']

        graph_result = state['graph_result']
        graph_result = 'failed_at_req'

        return {'err_sol_pair_req':err_sol_pair_req,'graph_result':graph_result}

    
    def save_log_env(self,state:GraphState):
        # need update 

        error_type = state['error_type']
        error = state['error']
        current_py = state['generation_py']
        current_req = state['generation_req']
        err_sol_pair_env = state['err_sol_pair_env']

        graph_result = state['graph_result']
        graph_result = 'failed_at_env'

        llm_model = self.setup_model()
        prompt_placeholder = load_prompt(
                self.prompt_path_type_4_analyze
            )
        prompt_analyze_error = PromptTemplate.from_template(
                prompt_placeholder
            )
        chain_context = {
                'error': itemgetter('error'),
            }
        invoke_dict = {
                'error': error,
            }

        chain_analyze_error = (
            chain_context
            | prompt_analyze_error
            | llm_model
            | StrOutputParser()
        )
        error_analysis = chain_analyze_error.invoke(invoke_dict)

        log_lst = state['log_lst']
        log_lst.append(
            {
                'error_type': error_type,
                'error_raw': error,
                'error_analysis': error_analysis,
                'state_old_py': current_py,
                'state_new_py': current_py,
                'state_old_req': current_req,
                'state_new_req': current_req,
            }
        )

        return {'err_sol_pair_env':err_sol_pair_env,'graph_result':graph_result,'log_lst':log_lst}

    def run_langgraph(self, example: dict, app):

        branch_flg = 'single_py'

        paper_summary_exist = example.get('paper_summary')
        if paper_summary_exist not in ['None','none',None,'',' ',0]:
            print('----- [INFO] PAPER_SUMMARY EXIST -> BRANCH : PAPER_WITH_CODE -----')
            branch_flg =  'paper_with_code'
        else:
            src_path = self.src_path
            if os.path.exists(src_path):
                print('----- [INFO] SRC PATH EXISTS TRUE -> BRANCH : MULTI_PY -----')
                branch_flg = 'multi_py'
            else:
                print('----- [INFO] SRC PATH EXISTS FALSE -> BRANCH : SINGLE_PY -----')
                branch_flg = 'single_py'
        

        old_venv_path = os.path.join(INTERFACE_DIR, 'py310_venv')
        shutil.rmtree(old_venv_path,ignore_errors=True)
        print('----- [INFO] REMOVING EXISTING VENV COMPLETE ')

        graph = app.invoke(
            {
                'error': '',
                'error_type': '',

                'msg_stdout': '',
    
                'err_sol_pair_py': [],
                'err_sol_pair_req': [],
                'err_sol_pair_env': [],
                'log_lst': [],

                'rules': example.get('rules',''),
                'generation_guide': example.get('generation_guide',''),
                'code_summary': example.get('code_summary',None),
                'paper_summary': example.get('paper_summary',''),
                'paper_name' : example.get('paper_name',''),

                'generation_py': example.get('generation_py',''),
                'generation_req' : example.get('generation_req',''),
                'data_meta' : example.get('data_meta',''),

                'branch_flg' :  branch_flg,
                'src_path' : src_path,

                'iteration_py': 0,
                'iteration_data': 0,
                'iteration_req': 0,
                'iteration_env': 0,
            },
            config = {
                'recursion_limit': 50
            }
        )

        solution = {
            'graph_result' : graph['graph_result'],
            'last_error': graph['error'], 
            'failed_type':graph['error_type'],   
            'err_sol_pair_py' : graph['err_sol_pair_py'],
            'err_sol_pari_req': graph['err_sol_pair_req'],
            'err_sol_pair_env': graph['err_sol_pair_env'],
            'log_lst': graph['log_lst'],
        }

        if solution['graph_result'] == 'success':

            with open(self.py_file_path,'w') as F:
                F.write(graph['generation_py'])
                print('----- [INFO] SAVING MODIFIED PY COMPLETE! -----')
            with open(self.req_file_path,'w') as F:
                F.write(graph['generation_req'])
                print('----- [INFO] SAVING MODIFIED REQUIREMENTS COMPLETE! -----')
        else:
            # need update
            print('-------[INFO] LANG GRAPH RUNNED BUT FAILED MODIFYING SOURCE_PY. START SAVING ERRORS.')
            # with open('./py_errors.txt','w') as F:
            #     for pair in graph['err_sol_pair_py']:
            #         print('---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------')
            #         F.writelines(pair[0])
            #         F.writelines(pair[1])
            #         print('---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------')
            
        return solution
        
    def run(self):
        
        workflow = StateGraph(GraphState)
    
        workflow.add_node("reflect", self.reflect)  
        workflow.add_node('py_check',self.py_check)
        workflow.add_node('classify_error',self.classify_error)
        
        workflow.add_node('fix_py',self.fix_py)
        workflow.add_node('fix_py_data',self.fix_py_data)
        workflow.add_node('data_adapt',self.data_adapt)
        workflow.add_node('fix_req',self.fix_req)

        workflow.add_node('failed_py',self.save_log_py)
        workflow.add_node('failed_data',self.save_log_data)
        workflow.add_node('failed_req',self.save_log_req)
        workflow.add_node('failed_env',self.save_log_env)

        workflow.set_entry_point("data_adapt")

        workflow.add_edge("data_adapt", "py_check")
        workflow.add_edge("py_check", "classify_error")
        workflow.add_conditional_edges(
            "classify_error",
            self.decide_to_finish,
            {
                "failed_py": "failed_py",
                "fix_py": "fix_py",
                "fix_py_data": "fix_py_data",
                "reflect": "reflect",
                "failed_req": "failed_req",
                "fix_req": "fix_req",
                "failed_env": "failed_env",
                "failed_data": "failed_data",
                'end': END,
            },
        )
        
        workflow.add_edge("reflect", "py_check")
        workflow.add_edge("fix_py", "py_check")
        workflow.add_edge("fix_py_data", "py_check")
        workflow.add_edge("fix_req", "py_check")

        workflow.add_edge("failed_py", END)
        workflow.add_edge("failed_data", END)
        workflow.add_edge("failed_req", END)
        workflow.add_edge("failed_env", END)

        app = workflow.compile()
        result = self.run_langgraph(self.prev_step_result_dict,app)
        
        return result

if __name__ == "__main__":
    import pickle
    
    with open('./tmp_pkl.pkl','rb') as F:
        prev_result= pickle.load(F)
        # pprint(prev_result)
        
    prev_result.update(
        {
            'paper_summary': None,
        }
    )
    
    
    graph_runnder = GraphRunner(
        # py_path='/home/jiseong.hah/forAiHub/solutionGen20240813/interface/source_py/imbalanced-garbage-classification-resnet50.py',
        prev_step_result_dict=prev_result,
        py_path='./py_modified_',
        req_path= './requirements_modified_',
        
    )
    graph_runnder.run()
