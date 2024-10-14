import os
import shutil
import streamlit as st

from path_list import *
from engine.gen_solution.code_generator import CodeGenerator
from ui.components.create_solution.download_artifacts import DownloadArtifacts

class CreateSolution:
    def __init__(self, path):
        self.source_path = path['source_py']
        self.data_path = path['data']

        self._initialize_session_state()

    def _initialize_session_state(self):
        default_states = {
            "max_iterations": 10,
            'log': "",
            'ipynb_files': self._get_files(directory=self.source_path, file_ext='.ipynb'),
            'placeholder': None,
            'is_btn_clicked': False,
            'code_gen': None,
            'progress': 'ready' # ready, run, end
        }

        for key, value in default_states.items():
            if key not in st.session_state:
                st.session_state[key] = value

    ### 파일 리스트 확인
    def _get_files(self, directory, file_ext=None):
        if os.path.exists(directory):
            return [file for file in os.listdir(directory) if not file_ext or file.endswith(file_ext)]
        return []
    
    def _clean_dir(self, path, recursive=False):
        log = ""
        if os.path.exists(path):
            log += f"{path} 내 파일들을 삭제합니다.\n"
            for file in os.listdir(path):
                file_path = os.path.join(path, file)
                if os.path.isfile(file_path):  # 파일인지 확인
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        log += f"{file_path} 삭제 중 오류가 발생했습니다: {e}\n"
                elif recursive and os.path.isdir(file_path):  # recursive 옵션이 켜져 있고 디렉토리일 경우
                    try:
                        shutil.rmtree(file_path)  # 디렉토리를 통째로 삭제
                        log += f"{file_path} 디렉토리를 삭제했습니다.\n"
                    except Exception as e:
                        log += f"{file_path} 디렉토리 삭제 중 오류가 발생했습니다: {e}\n"
        else:
            log += f"{path} 디렉토리가 없습니다.\n"
        return log
    
    def _get_log(self, log):
        st.session_state["log"] += log
        st.markdown(log, unsafe_allow_html=True)

    # def check_condition(self):
    #     with st.container(border=True):
    #         st.caption('실행 조건')
    #         st.checkbox("데이터셋이 존재하는가?", value=self.condition['dataset'], disabled=True)
    #         st.checkbox("소스코드가 존재하는가?", value=self.condition['source'], disabled=True)
    #         st.checkbox('데이터 adaption을 성공했는가?', value=self.condition['adaption'], disabled=True)

    def create_solution(self):
        st.subheader('Create AI solution')
        st.caption('소스 코드를 ALO framework에 맞도록 자동 코드화 합니다. 코드 생성 반복 횟수를 선택할 수 있니다.   \n   1회 실행 시에 2~3분 정도 소요되며, iteration보다 일찍 성공한 경우 자동 종료되므로 10회 설정을 권장합니다.')
        

        cols = st.columns([1, 1])
        with cols[0]:
            st.session_state['max_iterations'] = st.number_input("iteration", 1, 20, value=st.session_state['max_iterations'], step=1, key="code_gen_iteration", help="생성형 AI 기반으로 code 제작 시, 최대 반복 횟수를 의미 합니다.")
        with cols[1]:
            st.text("")  # 공백 추가
            st.text("")  # 공백 추가
            btn_create = st.button("Create", use_container_width=True, )

        return btn_create
        
    def check_progress(self, btn_create):
        st.subheader('Check Progress')
        st.caption('진행 상황을 확인할 수 있습니다. 새로고침이나 버튼을 클릭하면 진행이 멈출 수 있습니다.')

        if st.session_state["log"] and not st.session_state["is_btn_clicked"]:
            st.markdown(st.session_state["log"], unsafe_allow_html=True)

        if btn_create:
            st.session_state["is_btn_clicked"] = True
            st.session_state["placeholder"] = st.empty()
            st.session_state["log"] = ""
            st.session_state["code_gen"] = None

    def check_source_code(self):
        log = ""
        file_name = None

        if os.path.exists(self.source_path):
            file_name = [file for file in os.listdir(self.source_path) if file.endswith('.py')][0]
            log = f"({file_name}) 파일이 있습니다. code 변환을 시작합니다.\n"
        else:
            log = "소스 코드가 존재하지 않습니다.\n"
        
        return [file_name, log]

    def init_solution(self):
        st.session_state['progress'] = "run"
        self._get_log("<p style='color:blue; font-weight:bold;'>🗑️ Initializing...</p>")
        self._get_log(self._clean_dir('./engine/gen_solution/langgraph_artifacts'))

    def generate_solution(self):
        # Feature 1: 솔루션 생성 실행하기
        self._get_log("<p style='color:blue; font-weight:bold;'>🚗 Processing...</p>")
        file_name, log = self.check_source_code()
        py_path = os.path.join(self.source_path, file_name)
        req_path = os.path.join(self.source_path, 'requirements.txt')
        print('----- python file path', py_path)
        print('----- requirements.txt path', req_path)
        # FIXME 추후에 UI 줄 예정이지만 지금 default는 dual
        generation_mode = 'dual_pipeline'   
        self._get_log(log)
        st.session_state['code_gen'] = CodeGenerator(py_path=py_path, req_path=req_path, max_iterations=st.session_state.max_iterations, generation_mode=generation_mode)
        try:
            with st.spinner('Code generator running...'):
                result = st.session_state['code_gen'].run()
            # print(result)
            if isinstance(result, str):
                self._get_log("<p style='color:blue; font-weight:bold;'>🚩 End</p>")
                if 'yes' in result:
                    self._get_log("❌ AI Solution 생성을 실패함. Artifact files 에서 Error log 를 확인 하세요.\n")
                else:
                    self._get_log("⭕ AI Solution 생성 성공 !!\n")
            else:
                pass
            # st.text(f"{file_name} 변환이 완료되었습니다.")
        except Exception as e:
            with st.expander(f"❌ {file_name} 변환 중 오류가 발생했습니다"):
                self._get_log(f"{e}\n")
        st.session_state['progress'] = "end"

    def show_description(self):
        with st.expander("📝 처음 사용하는 사람을 위한 Create AI solution 설명 📝"):
            st.markdown("""
                <p>AI Agent 로 interpreter error 가 발생하지 않을 때까지 code generation 을 반복 실행합니다. </p>
                
                1. 🔄 code generation을 성공할 때 까지 몇 회를 반복할지 결정하고, create를 시작합니다. 
                    - iteration보다 일찍 코드 생성이 성공한 경우 자동 종료되므로 10회 설정을 권장합니다.
                2. ✅ system logs 창을 열어서 진행 상황을 확인합니다.
                3. 📥 10회 이상에서도 성공하지 못한 경우, iterations 로그를 확인하여 원인을 파악합니다.
            """, unsafe_allow_html=True)

    def render(self):
        st.title("Create AI Solution")
        self.show_description()

        btn_create = self.create_solution()
        
        st.divider()
        self.check_progress(btn_create)

        st.divider()
        download_artifacts = DownloadArtifacts()
        download_artifacts.render()

        if st.session_state["placeholder"] and st.session_state["is_btn_clicked"]:
            st.session_state["is_btn_clicked"] = False
            with st.session_state["placeholder"].container():
                self.init_solution()
                self.generate_solution()
                
