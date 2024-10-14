import json
import os
import streamlit as st
import yaml
import sys
import pandas as pd
import re
import subprocess
import yaml

from engine.chatgpt import chatgpt_query
from ui.src.chat_prompts.read_prompt import read_prompt

# 경로 추가하기
root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(root_path + '/engine/alo_engine/')  # 필요한 경우 하위 디렉토리 추가
# sys.path.append(root_path + '/alo_engine/alo/')  # 필요한 경우 src 디렉토리 추가
from engine.gen_solution.langgraph_src.venv_controller import VenvController

ALO_HOME = root_path + '/engine/alo_engine/'
ALO_MAIN_FILE = ALO_HOME + 'main.py'
EXPERIMENTAL_PLAN_PATH = os.path.join(root_path, 'engine', 'alo_engine', 'solution', 'experimental_plan.yaml')

os.environ["ALO_HOME"] = ALO_HOME
# alo model 제작전 alo_home 지정, alo_home은 subprocess로 동작하기 때문에 alo main 코드가 있는 곳으로 해야함
from alo.alo import Alo

 # 커스텀 태그 핸들러 함수 정의
def env_var_constructor(loader, node):
    value = loader.construct_scalar(node)
    # 환경 변수에서 해당 값을 가져오거나 기본값을 설정할 수 있습니다.
    return os.getenv(value, "")

# Loader에 커스텀 태그 추가
class EnvVarLoader(yaml.SafeLoader):
    pass

EnvVarLoader.add_constructor('!Env', env_var_constructor)

class PublishSolution:
    def __init__(self, path ):

        self.source_path = path['source_py']
        self.data_path = path['data']
        self.metadata_path = path['metadata']
        self.prompt_path = path['prompt']

        self.initialize_session_state()
        self.venv_ctrl = VenvController(python_version='3.10.2', init_path=root_path + '/interface/')
        self.venv_path = self.venv_ctrl.venv_path
        self.venv_py = os.path.join(self.venv_path, 'bin', 'python')
        self.experimental_plan = None

        # ALO Pipeline 초기화 여부 확인
        self.solme_title_list = []
        self.solme_descr = None
        self.new_solution_name = None
        self.train_columns = ['start_time', 'end_time', 'status']
        self.inference_columns = ['id', 'status', 'score', 'result', 'note', 'probability']

        # 교체를 위해 experimental_plan을 다시 로드합니다.
        try:
            def has_required_keys(dictionary, keys):
                return any(key in dictionary for key in keys)

            ## experimental_plan 존재 확인 부터가 페이지 전부의 시작
            self.experimental_plan = self._load_experimental_plan()
            self.train_pipeline_exists = has_required_keys(self.experimental_plan['solution']['function'], ['train', 'alo_train'])
            self.inference_pipeline_exists = has_required_keys(self.experimental_plan['solution']['function'], ['inference', 'alo_inference'])
        except:
            self.experimental_plan = None

        self.alo = None
        self.train_pipeline = None # <-- yaml 읽어서 train True
        self.inference_pipeline = None # <-- True

        # try:
        #     self.alo = ALO()
        #     self.train_pipeline = self.alo.pipeline(pipeline_type='train_pipeline')
        #     self.inference_pipeline = self.alo.pipeline(pipeline_type='inference_pipeline')
        # except:
        #     st.error("ALO engin 을 찾을 수 없습니다.")
        #     self.alo = None
        #     self.train_pipeline = None
        #     self.inference_pipeline = None

    def initialize_session_state(self):
        default_states = {
            'status_message': {},
        }
        for key, value in default_states.items():
            if key not in st.session_state:
                st.session_state[key] = value

    #####################################
    ####    Step 1: Registration solution
    #####################################

    def recommand_solution_name_descr(self):
        """ title 와 descr 를 추천 받기 위한 
        """

        ## 1) main.py 를 읽거나 대체되는 .py 를 읽어 오기 
        file_path = os.path.join(self.source_path, 'main.py')

        if os.path.exists(file_path):
            # If main.py exists, read and print its contents
            with open(file_path, 'r', encoding='utf-8') as file:
                code_contents = file.read()
                
        else:
            # List all .py files in the directory (excluding subfolders)
            py_files = [f for f in os.listdir(self.source_path) if f.endswith('.py') and os.path.isfile(os.path.join(self.source_path, f))]

            if len(py_files) == 0:
                # No .py files found in the directory
                raise FileNotFoundError("No .py files found in the directory")
            elif len(py_files) == 1:
                # Only one .py file exists, read and print its contents
                file_path =  os.path.join(self.source_path, py_files[0])
                with open(file_path, 'r', encoding='utf-8') as file:
                    code_contents = file.read()
            else:
                # Multiple .py files exist, raise an error
                raise RuntimeError("Multiple .py files found in the directory but main.py is missing")
            

        ## 2) data metadata 를 로드 하기
        path = os.path.join(self.metadata_path, 'metadata.md')
        with open(path, 'r', encoding='utf-8') as file:
            data_metadata = file.read()

        ## 1) solme format 을 로드 하기
        path = os.path.join(self.prompt_path, 'solme_description_format.yaml')
        with open(path, 'r') as file:
            solme_format = yaml.safe_load(file)

        template = read_prompt('recommend_solme_description.md')

        
        prompt = template.format(code_contents=code_contents,
                                 data_metadata=data_metadata,
                                 result_format=solme_format,
                                 )

        prompt_result = chatgpt_query(prompt)
        prompt_result_match = re.search('```json(.*?)```', prompt_result, re.DOTALL) 
        result = prompt_result_match.group(1).strip() if prompt_result_match else "" 
        solme_result = json.loads(result)
        return solme_result['title_list'], solme_result['description']

        

    def update_solution_name(self, new_solution_name):
        # YAML 파일 읽기
        yaml_file_path = root_path + '/engine/alo_engine/setting/solution_info.yaml'

        with open(yaml_file_path, 'r') as file:
            data = yaml.safe_load(file)

        # 데이터 수정: solution_name 변경
        if 'solution_name' in data:
            old_solution_name = data['solution_name']
            data['solution_name'] = new_solution_name
            print(f"Changed solution_name from '{old_solution_name}' to '{new_solution_name}'")
        else:
            print("solution_name key not found in the YAML file.")
            return

        # 변경된 데이터 다시 저장
        with open(yaml_file_path, 'w') as file:
            yaml.safe_dump(data, file, default_flow_style=False)

    def init_alo(self):
        if self.alo is None:
            try:
                self.alo = Alo()
            except Exception as e:
                pass

    def register_solution(self, username=None, password=None):
        st.info("Registering the solution...")
        self.init_alo() 
        
        # 유저이름과 비밀번호가 None인지 확인
        if username is None or password is None:
            raise ValueError("Username and password must be provided.")
        try:
            self.alo.register_solution(id=username, pw=password, description=self.solme_descr)
            st.success("AI Solution Registration completed!")
        except Exception as e:
            st.error(f"Error during solution registration: \n {e}")

    #####################################
    ####    Step 2: Test pipeline
    #####################################

    #### 2-1: Save 버튼
    def save_experimental_plan(self):
        # Ensure ui_args_detail is set to an empty list if it is empty or None
        if not self.experimental_plan.get('ui_args_detail'):
            self.experimental_plan['ui_args_detail'] = []

        # Ensure every args in user_parameters is set to an empty list if it is empty or None
        user_params = [self.experimental_plan['solution']['function']]
        for param_set in user_params:
            for pipeline_name, pipeline_info in param_set.items():
                # pipeline_info는 'def'와 'argument'를 포함하는 딕셔너리입니다.
                arguments = pipeline_info.get('argument', {})

                # 만약 arguments가 존재하지 않거나 None이면 빈 딕셔너리로 설정합니다.
                if arguments is None:
                    pipeline_info['argument'] = {}
                else:
                    for key, value in arguments.items():
                        if value is None:
                            arguments[key] = ""

        with open(EXPERIMENTAL_PLAN_PATH, 'w') as file:
            yaml.safe_dump(self.experimental_plan, file)


    ### 2-2: Train 실행 코드 
    def run_alo_train(self):
        self.init_alo()

        status = None
        error = None

        try:
            process = subprocess.run(
                [self.venv_py, ALO_MAIN_FILE, "--mode", "train"],
                check=True,
                stdout=None,
                stderr=None,
                text=True 
                )

            # self.alo.reload()
            # self.alo.train()
            # self.alo.history()
            # # self.train_pipeline.setup()
            # # self.train_pipeline.load()
            # # self.train_pipeline.run()
            # # self.train_pipeline.save()
            self.train_pipeline = True
            status = "Training completed!"  # 상태 메시지를 업데이트합니다.
        except Exception as e:
            error = f"Error during training: {e}"

        return status, error

    ### 2-3: Inference 실행 코드 
    def run_alo_inference(self):
        self.init_alo()
        
        status = None
        error = None

        try:
            process = subprocess.run(
                [self.venv_py, ALO_MAIN_FILE, "--mode", "inference"],
                check=True,
                stdout=None,
                stderr=None,
                text=True 
                )
            
            # self.alo.reload()
            # self.alo.inference()
            # self.alo.history()

            self.inference_pipeline = True
            status = "Inferencing completed!"
        except Exception as e:
            error = f"Error during inferencing: {e}"

        return status, error

    ## 2-4: user parameter 를 ui화 
    def render_user_parameters(self):
        user_params = [self.experimental_plan['solution']['function']]  # self.experimental_plan['solution']['function']

        pipe_cnt = 0
        for param_set in user_params:
            for pipeline_key, pipeline_info in param_set.items():
                if pipe_cnt != 0:
                    st.divider()
                st.subheader("{}\n".format(pipeline_key))

                def_info = pipeline_info.get('def', '')
                st.markdown("**Definition**: {}<br>".format(def_info), unsafe_allow_html=True)

                args = pipeline_info.get('argument', {})
                if args is None:
                    args = {}

                num_args = len(args)
                if num_args > 0:
                    cols = st.columns(num_args)  # 각 arg를 개별 열에 배치합니다.

                    for arg_index, (key, value) in enumerate(args.items()):
                        with cols[arg_index]:  # 각 열에 맞게 컴포넌트를 배치합니다.
                            widget_key = "{}_{}_argument".format(pipeline_key, key)
                            new_value = st.text_input("{}".format(key), value=str(value), key=widget_key)
                            pipeline_info['argument'][key] = yaml.safe_load(new_value) if new_value else value
                else:
                    pass

                pipe_cnt += 1

    def display_training_history(self):
        # train_history_path = os.path.abspath(os.path.join(root_path, 'alo_engine', 'history', 'train'))

        # if not os.path.isdir(train_history_path):
        #     self.train_history_container.table(pd.DataFrame(columns=self.train_columns))  # 디렉토리가 없으면 컬럼명만 있는 빈 테이블을 표시합니다.
        #     return

        if self.train_pipeline:
            try:
                table_list = self.alo.history(type='train')
                # 필요한 컬럼만 남기고 순서를 맞추기
                pipline_history_df = pd.DataFrame(table_list)[self.train_columns].head(10)
                self.train_history_container.table(pipline_history_df)
            except (FileNotFoundError, KeyError):
                self.train_history_container.table(pd.DataFrame(columns=self.train_columns))  # 파일을 찾을 수 없거나 컬럼이 없으면 컬럼명만 있는 빈 테이블을 표시합니다.
        else:
            self.train_history_container.table(pd.DataFrame(columns=self.train_columns))  # 초기에는 컬럼명만 있는 빈 테이블을 표시합니다.

    def display_inference_history(self):
        # inference_history_path = os.path.abspath(os.path.join(root_path, 'alo_engine', 'history', 'inference'))

        # if not os.path.isdir(inference_history_path):
        #     self.inference_history_container.table(pd.DataFrame(columns=self.inference_columns))  # 디렉토리가 없으면 컬럼명만 있는 빈 테이블을 표시합니다.
        #     return

        if self.inference_pipeline:
            try:
                table_list = self.alo.history(type='inference')
                # 필요한 컬럼만 남기고 순서를 맞추기
                pipline_history_df = pd.DataFrame(table_list)[self.inference_columns].head(10)
                self.inference_history_container.table(pipline_history_df)
            except (FileNotFoundError, KeyError):
                self.inference_history_container.table(pd.DataFrame(columns=self.inference_columns))  # 파일을 찾을 수 없거나 컬럼이 없으면 컬럼명만 있는 빈 테이블을 표시합니다.
        else:
            self.inference_history_container.table(pd.DataFrame(columns=self.inference_columns))  # 초기에는 컬럼명만 있는 빈 테이블을 표시합니다.


    #############################################
    ######   Internal function
    #############################################

    def update_title_list(self, add_name):
        unique_titles = []
        for item in self.solme_title_list:
            if item != '' and item not in unique_titles:
                unique_titles.append(item)

        if add_name not in unique_titles:
            unique_titles = [add_name] + unique_titles

        self.solme_title_list = unique_titles
   

    def _load_experimental_plan(self):
        with open(EXPERIMENTAL_PLAN_PATH, 'r') as file:
            return yaml.load(file, Loader=EnvVarLoader)
    
    # Dict를 Markdown 형식의 문자열로 변환하는 함수
    def _dict_to_markdown(self, d, indent=0):
        md = ''
        indent_space = ' ' * indent
        for key, value in d.items():
            if isinstance(value, dict):
                md += f'{indent_space}- **{key}**:\n{self._dict_to_markdown(value, indent + 2)}'
            elif isinstance(value, list):
                md += f'{indent_space}- **{key}**:\n'
                for item in value:
                    if isinstance(item, dict):
                        md += f'{self._dict_to_markdown(item, indent + 2)}'
                    else:
                        md += f'  {indent_space}- {item}\n'
            else:
                md += f'{indent_space}- **{key}**: {value}\n'
        return md


    #############################################
    ######   Rendering
    #############################################
    def render(self):

        self.experimental_plan = self._load_experimental_plan()

        ### Step 1: register solution
        st.markdown("")
        st.markdown("")
        st.markdown("#### Registrate AI solution:")
        if self.experimental_plan is None:
            st.error("Experimental plan not found.")
        else: 
            with st.container():
                register_cols = st.columns([1, 1, 1, 1, 1])  # 다섯 개의 동일한 너비를 가지는 열
                with register_cols[0]:
                    if st.button('Register', use_container_width=True):
                        # 사용자가 입력한 username과 password를 사용하여 등록
                        if self.new_solution_name:
                            self.update_solution_name(self.new_solution_name)
                            # st.success(f"Solution name has been updated to '{self.new_solution_name}'")
                        self.register_solution(self.username, self.password)

                with register_cols[4]:
                    if st.button('Recommend', use_container_width=True):
                        ## title & description 추천을 위한 GenAI 실행
                        self.solme_title_list, self.solme_descr = self.recommand_solution_name_descr()
                        
                        print(f"GenAI 로 부터 추천받은 AI Solution 이름 및 설명 정보: {self.solme_title_list[0]}, {self.solme_descr}")   



            with st.container(border=True):
                register_cols2 = st.columns([1, 1])  # 두 개의 동일한 너비를 가지는 열
                # 사용자가 username과 password를 입력할 수 있는 텍스트 박스 추가
                with register_cols2[0]:
                    self.username = st.text_input("ID")
                with register_cols2[1]:
                    self.password = st.text_input("Password", type="password")

                # 사용자가 새로운 솔루션 이름을 입력할 수 있는 텍스트 박스 추가
                if len(self.solme_title_list) == 0 :
                    self.new_solution_name = st.text_input("AI Solution Name", placeholder="AI solution 이름을 등록해 주세요 (한글 & 특수문자 미지원. 단, '-' 제외).")
                else:
                    add_name = st.text_input("Add new name", placeholder="Recommend Name 외 추가하기. (한글 & 특수문자 미지원. 단, '-' 제외).")
                    self.update_title_list(add_name)
                    self.new_solution_name = st.selectbox("AI Solution Name", tuple(self.solme_title_list), placeholder="AI solution 이름을 등록해 주세요 (한글 & 특수문자 미지원. 단, '-' 제외).")
                
                if self.solme_descr != None:
                    descr_md = self._dict_to_markdown(self.solme_descr)
                    with st.expander("View the description of AI Solution ", expanded=True):
                        # Markdown 형식으로 표시
                        st.markdown(descr_md)
                    

                # 유효성 검사
                if self.new_solution_name == '':
                    pass
                else:
                    if len(self.new_solution_name) > 50:
                        st.error("Solution name must be 50 characters or fewer.")
                    elif not re.match(r'^[a-zA-Z0-9-]+$', self.new_solution_name):  # 하이픈만 허용하는 정규식
                        st.error("Solution name can only contain letters, numbers, and hyphens.")
                    else:
                        pass  # 이 영역에서 추가 처리를 수행합니다.

            st.divider()

            ##### Step2 : Control buttons
            # Save Changes, Run, and Register 버튼을 한 줄에 배치합니다.
            st.markdown("#### Test AI solution:")

            test_container = st.container()
            with test_container:
                save_run_cols = st.columns([1, 1, 1, 1, 1])  # 다섯 개의 동일한 너비를 가지는 열
                with save_run_cols[0]:
                    if st.button('Save', use_container_width=True):
                        self.save_experimental_plan()
                        test_container.success("experimental_plan.yaml has been updated!")

                with save_run_cols[1]:
                    if not self.train_pipeline_exists:
                        st.button('Run train', key='disabled_train', disabled=True, use_container_width=True)
                    else:
                        if st.button('Run train', use_container_width=True):
                            status, error = self.run_alo_train()
                            if status:
                                test_container.success(status)
                            if error:
                                test_container.error(error)

                with save_run_cols[2]:
                    if not self.inference_pipeline_exists:
                        st.button('Run inference', key='disabled_inference', disabled=True, use_container_width=True)
                    else:
                        if st.button('Run inference', use_container_width=True):
                            status, error = self.run_alo_inference()
                            if status:
                                test_container.success(status)
                            if error:
                                test_container.error(error)

                with save_run_cols[4]:
                    if st.button('Update', use_container_width=True):
                        self.experimental_plan = self._load_experimental_plan()
                    else:
                        pass

            ### Step 3: View user parameters
            with st.container(border=True):
                # user_parameters 편집 UI 생성
                self.render_user_parameters()

        #### step 4: history 
        st.markdown("#### Training history:")
        with st.container():
            self.train_history_container = st.empty()
            self.display_training_history()

        st.markdown("#### Inferencing history:")
        with st.container():
            st.markdown("""
추론 결과와 추론 결과에 대한 Score 등을 담은 inference summary 정보는 ALO 필수 항목 입니다.
- result: Inference 수행의 결과를 나타냅니다. 영소문자 기준 최대 32자 까지 가능합니다.
- score: 재학습(Re-train) 여부를 판단하는 기준으로 활용할 수 있으며, 소수 둘 째 자리까지 표시됩니다. 가령 분류 문제인 경우 예측된 결과의 probability 값을 활용합니다.
- note: AI Solution에서 Inference에 대해 참고할 사항 입니다. 영소문자 기준 최대 128자까지 가능합니다. 가령 score가 의미하는 바에 대한 설명 등 Edge Conductor UI 상에서 사용자가 보게 될 설명을 작성합니다.
- probability: Optional하게 작성하는 key로서, 분류에 대한 AI Solution일 때 Inference Data가 한 개인 경우 모든 Labels (ex. 'OK', 'NG1', 'NG2') 에 대한 probability 값을 요구 합니다.
""")
            self.inference_history_container = st.empty()
            self.display_inference_history()

# Streamlit 앱 실행 부분
if __name__ == "__main__":
    publish_solution = PublishSolution()
    publish_solution.render()