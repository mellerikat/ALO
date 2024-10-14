# -*- coding: utf-8 -*-
import argparse
import os
import re
import subprocess
import sys 
import shutil
from typing import List, TypedDict
from langgraph.graph import END, StateGraph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field

current_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_directory) 

try:
    from engine.chatgpt import get_gpt_client
except:
    p_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(p_directory)  
    pp_directory = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.append(pp_directory)  
finally: 
    from engine.chatgpt import get_gpt_client
    from engine.gen_solution.langgraph_src.util_funcs import * 
    from engine.gen_solution.langgraph_src.path_list import * 
    from engine.gen_solution.langgraph_src.venv_controller import VenvController

# Constants
TEMPERATURE = 0.1
FLAG = "do not reflect"  # 'reflect'
EXPT_LLM = os.getenv('OPENAI_MODEL_ID')
print("----- OPENAI MODEL ID: ", EXPT_LLM)
# Data model
class AloModel(BaseModel):
    """Code output"""
    pipeline_code: str = Field(description="Code block for pipeline.py")
    experimental_plan: str = Field(description="Yaml block for experimental_plan.yaml")
    description = "Schema for code solution to questions."

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
    messages: List
    generation: str
    iterations: int

class CodeGenerator:
    def __init__(self, py_ver='3.10.2', py_path=None, req_path=None, max_iterations=10, generation_mode='dual_pipeline', create_venv=False):
        self.py_ver = py_ver
        assert generation_mode  in ['single_pipeline', 'dual_pipeline']
        self.generation_mode = generation_mode
        self.create_venv = create_venv
        print(f"----- [INFO] current generation mode: << {self.generation_mode} >>")
        self.init_prompts_path()
        self.init_templates_path()
        self.venv_path = None 
        self.py_path = py_path 
        self.req_path = req_path 
        print('py path, req path: ', self.py_path, self.req_path)
        self.max_iterations = max_iterations
        self.client = get_gpt_client()
        self.context = self.create_context()
        print(f"----- [INFO] python file path: {self.py_path}")
        print(f"----- [INFO] requirements.txt file path: {self.req_path}")
        print(f"----- [INFO] max langgraph iterations: {self.max_iterations}")
        # Grader prompt
        system_md = load_markdown(self.system_md)
        self.code_gen_prompt = ChatPromptTemplate.from_messages(
                                    [("system", system_md), ("placeholder", "{messages}")]
                                    ) 
    
    def init_templates_path(self):
        self.experimental_plan_template = TEMPLATE_HOME + f'{self.generation_mode}/' + EXPERIMENTAL_PLAN_TEMPLATE
        self.pipeline_template = TEMPLATE_HOME +  f'{self.generation_mode}/' + PIPELINE_TEMPLATE
        print(f"----- [INFO] updated template files path: {TEMPLATE_HOME}, {self.generation_mode}, {self.pipeline_template}")

    def init_prompts_path(self): 
        self.system_md = PROMPTS_PATH + f'{self.generation_mode}/' + SYSTEM_MD
        self.error_yes_md = PROMPTS_PATH + f'{self.generation_mode}/' + ERROR_YES_MD
        self.error_md = PROMPTS_PATH + f'{self.generation_mode}/' + ERROR_MD
        self.context_md = PROMPTS_PATH + f'{self.generation_mode}/' + CONTEXT_MD
        self.question_md = PROMPTS_PATH + f'{self.generation_mode}/' + QUESTION_MD
        print("----- [INFO] updated prompt markdown file path")
        
    def call_azure_openai(self, prompt):
        response = self.client.chat.completions.create(
            model=os.getenv('OPENAI_MODEL_ID'),
            messages=prompt,
            temperature=TEMPERATURE,
            )
        return response.choices[0].message.content

    def make_py_pattern(self, model_resp):
        match = '' 
        match = re.search('```python(.*?)```', model_resp, re.DOTALL) 
        if match is None: 
            raise ValueError(f"----- [ERROR] Failed to make match for python code: \n{model_resp}")
        else: 
            return match 

    def with_structured_output(self, model_response: str):
        # print('model_response: \n', model_response)
        pipeline_match = self.make_py_pattern(model_response)
        experimental_plan_match =  re.search(r'```json(.*?)```', model_response, re.DOTALL)
        pipeline_code_block = pipeline_match.group(1).strip() if pipeline_match else "" 
        experimental_plan_block = experimental_plan_match.group(1).strip() if experimental_plan_match else "" 
        structured_output = AloModel(pipeline_code=pipeline_code_block, experimental_plan=experimental_plan_block)
        return structured_output

    def create_context(self): 
        shutil.rmtree(SOLUTION_PATH, ignore_errors=True)
        print(f"Delete {SOLUTION_PATH}")
        os.makedirs(SOLUTION_PATH, exist_ok=True) 
        print(f"Create empty {SOLUTION_PATH}")
        pipeline_template = read_python_file(self.pipeline_template)
        context_md = load_markdown(self.context_md)
        if self.generation_mode == 'single_pipeline':
            replaced_variables = {
                                'single_dataset_uri': SINGLE_DATA_PATH
                                }
        elif self.generation_mode == 'dual_pipeline':  
            replaced_variables = {
                                'train_dataset_uri': TRAIN_DATA_PATH,
                                'inference_dataset_uri': INFERENCE_DATA_PATH
                                }
        # replace dataset uri & requirements 
        replaced_yaml = load_and_replace_yaml(self.experimental_plan_template, replaced_variables)
        # TODO remove it 
        # try: 
        #     shutil.copyfile(self.req_path, os.path.join(SOLUTION_PATH, 'requirements.txt'))
        #     print(f'Success copy {self.req_path} --> {SOLUTION_PATH}')
        # except Exception as e:
        #      print(f'Failed to copy {self.req_path} --> {SOLUTION_PATH}: \n {str(e)}')
        # FIXME requirements.txt 로 이름 고정 
        replaced_yaml['solution']['pip']['requirements'] = read_requirements_to_list(self.req_path) 
        experimental_plan_template = json.dumps(replaced_yaml)
        variable_dict = {
                    'pipeline_template': pipeline_template, 
                    'experimental_plan_template': experimental_plan_template
                    }
        context_prompt = replace_variables(context_md, variable_dict)
        # print("\n----- context prompt: \n", context_prompt)
        return context_prompt

    def code_gen_chain(self, data):
        prompt = self.code_gen_prompt.format(context=data["context"], messages=data["messages"])
        messages = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": data["messages"][0][1]}
                ]   
        response = self.call_azure_openai(messages)
        return self.with_structured_output(response)

    def generate(self, state: GraphState):
        """
        Generate a code solution

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, generation
        """
        print(format_string("--- GENERATING CODE SOLUTION ---"))
        messages = state["messages"]
        iterations = state["iterations"]
        error = state["error"]
        if error == "yes":
            messages += [("user", load_markdown(self.error_yes_md))]
        code_solution = self.code_gen_chain({"context": self.context, "messages": messages})
        parsed_code_solution = f"pipeline.py: {code_solution.pipeline_code} \n experimental_plan.yaml: {code_solution.experimental_plan}"
        messages += [("assistant", parsed_code_solution),]
        iterations += 1
        return {"generation": code_solution, "messages": messages, "iterations": iterations}

    def make_error_message(self, err_msg):
        """format error markdown file 
        """
        error_md = load_markdown(self.error_md)
        if self.generation_mode == 'single_pipeline':
            variable_dict = {
                'err_msg': err_msg,
                'single_input_dir_structure': generate_directory_structure(SINGLE_DATA_PATH)
                }
        elif self.generation_mode == 'dual_pipeline':
            variable_dict = {
                'err_msg': err_msg,
                'train_input_dir_structure': generate_directory_structure(TRAIN_DATA_PATH),
                'inference_input_dir_structure': generate_directory_structure(INFERENCE_DATA_PATH)
                }
        error_prompt = replace_variables(error_md, variable_dict)
        return [("user", error_prompt)] 

    def backup_langgraph_artifacts(self, iterations, code, yml=None): 
        os.makedirs(LANGGRAPH_ARTIFACTS_PATH, exist_ok=True)
        save_code_to_file(LANGGRAPH_ARTIFACTS_PATH + f'iter{iterations}_generated_code.txt', code) 
        if yml: 
            save_yaml(LANGGRAPH_ARTIFACTS_PATH + f'iter{iterations}_experimental_plan.yaml', json.loads(yml))
        else: 
            pass 
        
    def get_venv(self):
        venv_ctrl = VenvController(python_version=self.py_ver, init_path=INTERFACE_HOME)
        self.venv_path = venv_ctrl.venv_path
        if self.create_venv:
            venv_ctrl.install_python()
        # passed if venv already exists 
        venv_py, venv_pip = venv_ctrl.create_venv(whether_create=self.create_venv) 
        print(f'----- python venv path: {venv_py}')
        print(f'----- pip venv path: {venv_pip}')
        if self.create_venv:
            venv_ctrl.install_requirements(self.req_path)
        return venv_py, venv_pip
            
    def set_alo(self, experimental_plan, pipeline_code):
        init_pipelines() 
        save_generated_codes(experimental_plan, pipeline_code)

    def run_alo(self, venv_py='python'): 
        result = subprocess.run(
            [venv_py, ALO_MAIN_FILE],
            check=True,  
            capture_output=True,  
            text=True 
            )
    
    def install_alo_req(self, venv_pip='pip'):
        try:
            result = subprocess.run([venv_pip, 'install', '-r', ALO_REQUIREMENTS],
                                    check=True,  
                                    capture_output=True,  
                                    text=True
                                    )
            # print(result.stdout)
            print("----- Success requirements installation -----")
        except subprocess.CalledProcessError as e:
            raise NotImplementedError(f"Failed to install requirements: {e.stderr}")
    
    def code_check(self, state: GraphState):
        """
        Check code

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, error
        """
        # State
        messages = state["messages"]
        code_solution = state["generation"]
        iterations = state["iterations"]
        # Get solution components
        # print(code_solution)
        print(format_string(f"--- CHECKING GENERATED CODE - ITER. : {iterations} ---"))
        try: 
            # main langgraph running logic 
            pipeline_code = code_solution.pipeline_code
            experimental_plan = code_solution.experimental_plan
            self.backup_langgraph_artifacts(iterations, pipeline_code, experimental_plan)
            venv_py, venv_pip = self.get_venv()
            self.set_alo(experimental_plan, pipeline_code)
            self.install_alo_req(venv_pip)
            self.run_alo(venv_py)
        except subprocess.CalledProcessError as e:
            print(format_string(f"--- [ERROR] CODE CHECK: FAILED (ITER: {iterations}) ---"))
            save_code_to_file(LANGGRAPH_ARTIFACTS_PATH + f'iter{iterations}_error_message.txt', str(e.stderr))
            messages += self.make_error_message(str(e.stderr))
            return {
                "generation": code_solution,
                "messages": messages,
                "iterations": iterations,
                "error": "yes",
            }
        except Exception as e:
            print(format_string(f"--- [ERROR] CODE CHECK: FAILED (ITER: {iterations}) ---"))
            save_code_to_file(LANGGRAPH_ARTIFACTS_PATH + f'iter{iterations}_error_message.txt', str(e))
            messages += self.make_error_message(str(e))
            return {
                "generation": code_solution,
                "messages": messages,
                "iterations": iterations,
                "error": "yes",
            }
        print(format_string(f"--- [SUCCESS] CODE RUN FINISH ---"))
        return {
            "generation": code_solution,
            "messages": messages,
            "iterations": iterations,
            "error": "no",
        }

    def reflect(self, state: GraphState):
        print(format_string(f"--- GENERATING NEW CODE ---"))
        messages = state["messages"]
        iterations = state["iterations"]
        code_solution = state["generation"]
        reflections = self.code_gen_chain({"context": self.context, "messages": messages})
        messages += [("assistant", f"Here are reflections on the error: {reflections}")]
        return {"generation": code_solution, "messages": messages, "iterations": iterations}

    def decide_to_finish(self, state: GraphState):
        error = state["error"]
        iterations = state["iterations"]
        if error in ["no", None] or iterations == self.max_iterations:
            print(format_string("--- DECISION: FINISH ITERATIONS ---"))
            return "end"
        else:
            print(format_string("--- DECISION: RE-TRY GENERATING SOLUTION ---"))
            if FLAG == "reflect":
                return "reflect"
            else:
                return "generate"

    def predict_langgraph(self, example: dict, app):
        graph = app.invoke({"messages": [("user", example["question"])], "iterations": 0})
        solution = graph["generation"]
        return {"experimental_plan.yaml": solution.experimental_plan, "pipeline.py": solution.pipeline_code, "error": graph['error']}

    def create_question(self, py_file):
        original_code = read_python_file(py_file) 
        question_md = load_markdown(self.question_md)
        if self.generation_mode == 'single_pipeline':
            variable_dict = {
                        'original_code': original_code, 
                        'single_input_dir_structure': generate_directory_structure(SINGLE_DATA_PATH)
                        }
        elif self.generation_mode == 'dual_pipeline':
            variable_dict = {
                        'original_code': original_code, 
                        'train_input_dir_structure': generate_directory_structure(TRAIN_DATA_PATH),
                        'inference_input_dir_structure': generate_directory_structure(INFERENCE_DATA_PATH)
                        }
        question_prompt = replace_variables(question_md, variable_dict)
        # print('----- question prompt: \n', question_prompt)
        return question_prompt

    def remove_macosx_folders(self, path):
        for root, dirs, files in os.walk(path, topdown=False):
            for name in dirs:
                if name == '__MACOSX':
                    folder_path = os.path.join(root, name)
                    try:
                        shutil.rmtree(folder_path)
                        print(f"'{folder_path}' 폴더가 성공적으로 삭제되었습니다.")
                    except Exception as e:
                        print(f"'{folder_path}' 폴더 삭제 중 오류 발생: {e}")

    def set_src(self): 
        source_path = os.path.dirname(self.py_path)
        if 'src' in os.listdir(source_path): 
            shutil.copytree(os.path.join(source_path, 'src'), os.path.join(SOLUTION_PATH, 'src'))
            print(f"[Success] Copied < src > from {source_path} to {SOLUTION_PATH}")
        else: 
            print(f"No < src > directory exists in {source_path}")
        
    def run(self):
        # delete langgraph artifacts path 
        shutil.rmtree(LANGGRAPH_ARTIFACTS_PATH, ignore_errors=True)
        print("Delete LANGGRAPH_ARTIFACTS_PATH")
        if not os.path.exists(SOLUTION_PATH + 'data/'):
            os.makedirs(SOLUTION_PATH + 'data/')
        shutil.copytree(INTERFACE_HOME + "data/", SOLUTION_PATH + 'data/', dirs_exist_ok=True)
        print(f"'{INTERFACE_HOME + 'data/'}' 폴더가 '{SOLUTION_PATH + 'data/'}'로 성공적으로 복사되었습니다.")
        self.remove_macosx_folders(SOLUTION_PATH + 'data/')
        # set src directory into solution path when multi-files case
        self.set_src()
        
        question = self.create_question(self.py_path)
        workflow = StateGraph(GraphState)
        workflow.add_node("generate", self.generate)  
        workflow.add_node("check_code", self.code_check)  
        workflow.add_node("reflect", self.reflect)  
        workflow.set_entry_point("generate")
        workflow.add_edge("generate", "check_code")
        workflow.add_conditional_edges(
            "check_code",
            self.decide_to_finish,
            {
                "end": END,
                "reflect": "reflect",
                "generate": "generate",
            },
        )
        workflow.add_edge("reflect", "generate")
        app = workflow.compile()
        result = self.predict_langgraph({'question': question}, app)
        # print(f"langgraph result: {result}")
        # FIXME delete venv - page 2 adapta data에서 진행  
        # shutil.rmtree(self.venv_path, ignore_errors=True)
        return result['error']

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run code generator")
    parser.add_argument('--py_ver', type=str, help="python version of source", default='3.10.2')
    parser.add_argument('--py_path', type=str, help="Path to the Python file")
    parser.add_argument('--req_path', type=str, help="Path to the requirements.txt file")
    parser.add_argument('--max_iterations', type=int, default=10, help="Maximum number of iterations for LangGraph")
    parser.add_argument('--generation_mode', type=str, default='dual_pipeline', help="LangGraph generation modes: single_pipeline / dual_pipeline")
    parser.add_argument("--create_venv", dest='create_venv', action='store_true', help="Create pyenv and pipenev at start: True, False")
    args = parser.parse_args()
    
    code_generator = CodeGenerator(py_ver=args.py_ver, py_path=args.py_path, req_path=args.req_path, max_iterations=args.max_iterations, generation_mode=args.generation_mode, create_venv=args.create_venv)
    code_generator.run()
