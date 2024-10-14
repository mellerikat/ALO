from contextlib import redirect_stdout
from io import StringIO
import os
import re
import shutil
import json
import streamlit as st
from engine.chatgpt import chatgpt_query
# from engine.adapt_data.adapt_data_to_code import DataAdapt
from engine.adapt_data.graph_runner import GraphRunner
import pandas as pd
from rich.tree import Tree
from rich.console import Console
from ui.components.convert_code.upload_data import UploadData

from path_list import *

class AdaptCode:
    def __init__(self, path):
        self.data_path = path['data']
        self.py_path = path['source_py']
        self.metadata_path = path['metadata']
        self.data_path = path['data']

        self._initialize_session_state()

    def _initialize_session_state(self):
        default_states = {
            "max_iterations_data": 10,
            'log_data': "",
            'placeholder_data': None,
            'is_btn_clicked_data': False,
            'data_adapt': None,
        }

        for key, value in default_states.items():
            if key not in st.session_state:
                st.session_state[key] = value

    def check_condition(self):
        with st.container(border=True):
            st.caption('실행 조건')

            # Check if 'train' and 'inference' folders exist in data_path
            train_path = os.path.join(self.data_path, 'train')
            inference_path = os.path.join(self.data_path, 'inference')

            train_exists = os.path.isdir(train_path) and len(os.listdir(train_path)) > 0
            inference_exists = os.path.isdir(inference_path) and len(os.listdir(inference_path)) > 0
            data_checked = train_exists and inference_exists

            # Check if 'requirements.txt' and at least one .py file exist in py_path
            requirements_exists = os.path.isfile(os.path.join(self.py_path, 'requirements.txt'))
            py_files_exist = any(file.endswith('.py') for file in os.listdir(self.py_path) if os.path.isfile(os.path.join(self.py_path, file)))
            source_code_checked = requirements_exists and py_files_exist

            col1, col2 = st.columns(2)
            with col1:
                st.checkbox("데이터셋이 존재하는가?", value=data_checked, disabled=True)
            with col2:
                st.checkbox("소스코드가 존재하는가?", value=source_code_checked, disabled=True)

        return data_checked and source_code_checked
        
    def show_adapt_code_info(self):
        st.caption('AI Agent를 활용해 데이터셋을 사용할 수 있도록 소스 코드를 자동으로 변경합니다.   \n   실패한다면 현재 탭의 `Edit Code`에서 수정하거나 `Get AI Source`에 돌아가 새로운 소스 코드를 받아올 수 있습니다.')
        with st.expander('💥 왜 코드 수정 과정을 두 번(Adapt Code for Dataset, Generate AI Solution)이나 진행하나요?'):
            st.markdown("""
                - 공통점: 두 코드의 수정 모두 AI Agent를 활용해 코드를 실행 가능하도록 수정합니다.
                - 차이점: 
                    - `Adapt Code for Dataset`에서 진행하는 수정: 사용자가 제공하는 데이터셋과 kaggle에서 다운로드 받은 노트북의 코드가 호환이 안될 수 있어, <span style="color:red">데이터셋에 맞게</span> 코드를 수정합니다.
                    - `Generate AI Solution`에서 진행하는 수정: 실행되는 소스 코드를 <span style="color:red">AI Solution의 형식에 적합한</span> 코드로 변경합니다.
            """, unsafe_allow_html=True)

    def print_directory_tree(self, startpath, max_files=5):
        """
        Given a startpath, print a visual tree with a limited number of files.
        """
        tree = Tree(startpath)

        def add_branch(tree, path, max_files=5):
            dirs = []
            files = []
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    dirs.append(item)
                elif os.path.isfile(full_path):
                    files.append(item)

            for dir_ in dirs:
                branch = tree.add(f"📁 {dir_}")
                add_branch(branch, os.path.join(path, dir_), max_files)

            for f in files[:max_files]:  # only show up to max_files files
                tree.add(f"📄 {f}")

            if len(files) > max_files:  # add ellipsis for remaining files
                tree.add(f"...and {len(files) - max_files} more")

        add_branch(tree, startpath)

        console = Console()
        output = StringIO()
        with redirect_stdout(output):
            console.print(tree)
        return output.getvalue()
    
    def create_solution(self):
        st.write('#### Adapt Code')
        st.caption('소스 코드를 dataset에 맞도록 자동 코드화 합니다. 코드 생성 반복 횟수를 선택할 수 있니다.   \n   1회 실행 시에 2~3분 정도 소요되며, iteration보다 일찍 성공한 경우 자동 종료되므로 10회 설정을 권장합니다.')
        
        # cols = st.columns([1, 1])
        # with cols[0]:
        #     st.session_state['max_iterations_data'] = st.number_input("iteration", 1, 20, value=st.session_state['max_iterations_data'], step=1, key="code_gen_iteration", help="생성형 AI 기반으로 code 제작 시, 최대 반복 횟수를 의미 합니다.")
        # with cols[1]:
        #     st.text("")  # 공백 추가
        #     btn_create = st.button("Create", use_container_width=True, )
        st.text("")  # 공백 추가
        btn_create = st.button("Create", use_container_width=True, )
        return btn_create
    
    def check_progress(self, btn_create):
        st.write('#### Check Progress')
        st.caption('진행 상황을 확인할 수 있습니다. 새로고침이나 버튼을 클릭하면 진행이 멈출 수 있습니다.')

        if st.session_state["log_data"] and not st.session_state["is_btn_clicked_data"]:
            st.markdown(st.session_state["log_data"], unsafe_allow_html=True)

        if btn_create:
            st.session_state["is_btn_clicked_data"] = True
            st.session_state["placeholder_data"] = st.empty()
            st.session_state["log_data"] = ""
            st.session_state["data_adapt"] = None

    def _get_log(self, log):
        st.session_state["log_data"] += log
        st.markdown(log, unsafe_allow_html=True)

    def check_source_code(self):
        log = ""
        file_name = None

        if os.path.exists(self.py_path):
            py_files = [f for f in os.listdir(self.py_path) if f.endswith('.py')]
            file_name = py_files[0]
            log = f"python ({file_name}) 파일이 있습니다. code 변환을 시작합니다.\n"
        else:
            log = "소스 코드가 존재하지 않습니다.\n"
        
        return [file_name, log]

    def read_metadata_from_markdown(self, file_path):
        metadata = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as md_file:
                current_section = None
                for line in md_file:
                    line = line.strip()
                    if line.startswith("- **") and line.endswith("**:"):
                        current_section = line[4:-3]
                        metadata[current_section] = {}
                    elif line.startswith("  - **") and line.endswith("**:"):
                        if current_section is not None:
                            sub_section = line[6:-3]
                            sub_value = line.split("**: ")[1]
                            metadata[current_section][sub_section] = sub_value
                    elif current_section and line:
                        if "description:" in current_section:
                            metadata[current_section] = line  # 전체 내용으로 갱신
        return metadata

    def parse_md_to_dict(self, md_file_path):
        with open(md_file_path, 'r') as file:
            content = file.read()

        # Define a regex pattern to match the key-value pairs
        pattern = r'- \*\*(.*?)\*\*:\s*(\{.*?\})'

        # Find all matches in the content
        matches = re.findall(pattern, content, re.DOTALL)

        result_dict = {}
        for key, value in matches:
            clean_key = key.strip()
            clean_value = value.strip()

            # Attempt to convert clean_value to a valid JSON format if necessary
            if clean_key in ['data_path', 'data_hierarchy']:
                try:
                    result_dict[clean_key] = json.loads(clean_value.replace("'", "\""))
                except json.JSONDecodeError as e:
                    print(f"JSON decode error for key '{clean_key}': {e}")
                    print(f"Original value: {clean_value}")
            else:
                result_dict[clean_key + ':'] = clean_value

        return result_dict

    def generate_code(self):

        def read_py_files(folder_path):
            py_files_content = {}

            for filename in os.listdir(folder_path):
                if filename.endswith('.py'):
                    file_path = os.path.join(folder_path, filename)
                    with open(file_path, 'r', encoding='utf-8') as file:
                        file_content = file.read()
                        py_files_content['generation_py'] = file_content

                if filename.endswith('requirements.txt'):
                    file_path = os.path.join(folder_path, filename)
                    with open(file_path, 'r', encoding='utf-8') as file:
                        file_content = file.read()
                        py_files_content['generation_req'] = file_content

            return py_files_content

        
        
        def format_table_as_string(data):
            """
            주어진 이차원 문자열 리스트를 테이블 형태로 변환하여 문자열 반환.

            Args:
            data (list of list of str): 테이블로 변환할 문자열 이차원 리스트.

            Returns:
            str: 테이블 형태로 변환된 문자열.
            """
            # 헤더와 구분선
            separator = "-" * 50 + "\n"

            # 데이터 행 생성
            rows = [separator]
            for idx, item in enumerate(data, start=1):
                row = f"{idx:<5}. || {item[0]:<15} || {item[1]} \n"
                rows.append(row)

            # 테이블 문자열 결합
            table_string = separator + ''.join(rows)

            return table_string

        self._get_log("<p style='color:blue; font-weight:bold;'>🚗 Processing...</p>")
        file_name, log = self.check_source_code()
        py_path = os.path.join(self.py_path, file_name)
        req_path = os.path.join(self.py_path, 'requirements.txt')
        self._get_log(log)

        with open(DATA_META_PATH + 'data_meta.json', 'r', encoding='utf-8') as json_file:
            metadata = json.load(json_file)

        runner_input_dict = read_py_files(self.py_path)
        metadata2 = {'data_meta':metadata}
        runner_input_dict.update(metadata2)

        st.session_state['data_adapt'] = GraphRunner(
            prev_step_result_dict=runner_input_dict,
            py_path = py_path,
            req_path = req_path
        )

        # st.session_state['data_adapt'] = DataAdapt(
        #     py_path,
        #     req_path,
        #     data_meta_path= os.path.join(self.data_path, 'description.txt'),
        #     max_iterations=st.session_state.max_iterations)
        #     #generation_mode= 'data_adaptation')
        try:
            
            with st.spinner('Code generator running...'):
                result = st.session_state['data_adapt'].run()
            #     for i in range(10):
            #         print(result)   
            
            if isinstance(result, dict):
                self._get_log("<p style='color:blue; font-weight:bold;'>🚩 End</p>")
                error_log_list = []
                error_log = result['log_lst']
                for i in range(len(error_log)):
                    error_log_prompt = f"""
                    아래에 입력받는 딕셔너리는 코드의 오류에 대한 log야. 너는 에러 로그를 확인하고 간단하게 요약해주는 시스템이야.
                    너의 출력을 table의 description에 들어갈거야.
                    ```
                    {error_log[i]['error_raw']}
                    ```
                    출력은 주요 에러 로그 한 줄과 발생한 원인을 한줄로 아래의 형태를 유지해줘.
                    ex) ModuleNotFoundError:, 모듈을 설치해야 합니다.
                    """
                    try:
                        error_log_response = chatgpt_query(error_log_prompt)
                    except Exception as e:
                        st.error(f"ChatGPT API 호출에 실패했습니다: {e}")
                        return None
                    #error_log_list += [f"No. {i+1} || {error_log[i]['error_type']} || {error_log_response} \n"]
                    error_log_list.append({
                        "Error Type": error_log[i]['error_type'],
                        "Description": error_log_response
                    })
                df = pd.DataFrame(error_log_list)
                st.write("**Error Type Description**")
                st.write("type_1, 2: code error")
                st.write("type_3: library error")
                st.write("type_4: envirments error")
                st.write("**Inprogress history**")
                st.table(df)
                if 'success' in result['graph_result'].lower():
                    self._get_log("⭕ Data Adaptaion 성공 !!\n")
                    # 복사 VENV_PATH 여기서 복사
                    source_file_path = os.path.join(VENV_PATH, 'requirements.txt')
                    # 파일이 존재하는지 확인
                    if os.path.exists(source_file_path):
                        # B 폴더에 복사할 파일의 경로
                        destination_file_path = os.path.join(SOURCE_PY_PATH, 'requirements.txt')
                        shutil.copy(source_file_path, destination_file_path)
                        print(f"requirements.txt 파일을 {VENV_PATH}에서 {SOURCE_PY_PATH}로 복사했습니다.")
                    else:
                        print(f"requirements.txt 파일이 {VENV_PATH}에 존재하지 않습니다.")
                else:
                    last_error = result['last_error']
                    #지피티에 대한 질문 추가
                    error_report_prompt = f"""
                    아래에 입력받는 딕셔너리는 코드의 오류에 대한 log야. 너는 에러 로그를 확인하고 사용자에게 어떻게 수정해야되는지 알려주는 시스템이야.
                    ```
                    {last_error}
                    ```
                    주요한 에러 로그와 어떻게 수정해야되는지 등의 가이드라인을 리포트 형태로 답변해줘.
                    설명은 한글로 부탁해.
                    제일 큰 글씨는 제목은 **로 내용은 그거보다 작게 써주고, 내용은 오류 메시지(주요 내용 포함), 원인, 수정방법만 짧게 적어줘.
                    """
                    try:
                        response = chatgpt_query(error_report_prompt)
                    except Exception as e:
                        st.error(f"ChatGPT API 호출에 실패했습니다: {e}")
                        return None
                        #error_log_table = format_table_as_string(error_log_list)
                    self._get_log(f"❌ Data Adaptaion 실패함. Artifact files 에서 Error log 를 확인 하세요.\n")
                    self._get_log(f" {response} \n")

            else:
                pass
            # st.text(f"{file_name} 변환이 완료되었습니다.")
        except Exception as e:
            with st.expander(f"❌ {file_name} 변환 중 오류가 발생했습니다"):
                self._get_log(f"{e}\n")
        st.session_state['progress_data'] = "end"
    
    def render(self):
        st.write('### Adapt code for dataset with AI Agent')
        self.show_adapt_code_info()
        is_checked = False 
        try: 
            is_checked = self.check_condition() 
        except: 
            st.error("소스코드 혹은 데이터셋이 준비되지 않았습니다.")
        if is_checked:
            directory_structure = self.print_directory_tree(self.data_path)
            btn_create = self.create_solution()

            st.divider()
            self.check_progress(btn_create)

            if st.session_state["placeholder_data"] and st.session_state["is_btn_clicked_data"]:
                st.session_state["is_btn_clicked_data"] = False
                with st.session_state["placeholder_data"].container():
                    # self.init_solution()
                    self.generate_code()
        else: 
            pass 