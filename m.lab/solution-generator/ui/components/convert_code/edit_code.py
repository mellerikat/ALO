import os
import streamlit as st
import subprocess
from streamlit_ace import st_ace
from engine.chatgpt import chatgpt_query
from ui.src.chat_prompts.read_prompt import read_prompt

class EditCode:
    def __init__(self, path):
        self.py_path = path['source_py']
        self.package_path = os.path.join(self.py_path, 'requirements.txt')
        self.source_name = ""
        
        st.session_state["packages"] = ""
        st.session_state["contents"] = ""

    def read_file(self, file_type='.py'):
        file = None
        if os.path.exists(self.py_path) and os.path.isdir(self.py_path):
            files = [f for f in os.listdir(self.py_path) if f.endswith(file_type)]
            if len(files) == 1:
                file = os.path.join(self.py_path, files[0])
                if file_type == '.py':
                    self.source_name = files[0]
            elif len(files) > 1:
                # TODO: 모두 지우기 버튼 등이 필요함
                st.error("디렉토리에 하나 이상의 소스코드가 존재합니다.")
            else:
                st.error("디렉토리에 소스코드가 존재하지 않습니다. 'Get AI Source'에서 소스코드를 받아올 수 있습니다.")
        else:
            st.error(f"해당 디렉토리가 존재하지 않음: {self.py_path}")

        if file and os.path.exists(file):
            with open(file, 'r') as file:
                content = file.read()
        else:
            content = ""

        return content
    
    def write_file(self, path, text):
        with open(path, 'w') as file:
                file.write(text)
    
    def read_requirements_file(self, req_path):
        """
        주어진 경로에 있는 requirements.txt 파일을 읽어옵니다.
        """
        with open(req_path, 'r') as file:
            lines = file.readlines()
        return lines

    def write_requirements_in(self, lines, in_path):
        """
        읽어온 의존성 목록을 requirements.in 파일로 저장합니다.
        """
        with open(in_path, 'w') as file:
            file.writelines(lines)

    def update_requirements_by_tool(self, venv_python, in_path, out_path):
        """
        pip-compile을 사용하여 requirements.txt 파일을 업데이트합니다.
        """
        try:
            # requirements.txt를 requirements_by_tool.txt로 업데이트
            #subprocess.run(['pip-compile', in_path, '-o', out_path], check=True)
            subprocess.run([venv_python, '-m', 'piptools', 'compile' ,'--resolver=backtracking', in_path, '-o', out_path], check=True)
            print(f"Requirements updated and saved to {out_path}")
        except subprocess.CalledProcessError as e:
            print(f"명령 실행 중 오류 발생: {e}")

    def recommend_package_list(self):
        template = read_prompt('recommend_packages_jj.md')
        prompt = template.format(content=st.session_state["contents"])

        try:
            response = chatgpt_query(prompt).replace("```txt", "").replace("```", "")
            self.write_file(self.package_path, response.strip())
            
        except Exception as e:
            response = "packages 추천에 실패했습니다."
            self.write_file(self.package_path, response)

        #try:
        print('package_path', self.package_path)
        print('py_path', self.py_path)

        try:
            with open(self.py_path + 'requirements.txt', 'r') as file:
                final_response = file.read()
        except Exception as e:
            print('requirements.txt error', e)

        print(final_response)
        # except Exception as e:
        #     response = "requirements.txt 읽기 실패"
        #     self.write_file(self.package_path, response)
        return final_response
    
    def display_package_editor(self):
        st.write('#### Edit requirements.txt')
        st.caption('다음은 추천하는 requirements.txt로 추가 또는 제거할 패키지가 있으면 업데이트해주세요.   \n   누락되거나 잘못된 패키지가 있으면 코드 실행이 원활하지 않습니다.')

        # TODO: parameter을 제공할 것인가?
        # c1, c2 = st.columns([3,1])
        # c2.subheader("Parameters")
        # with c1:
        #     package_content = st_ace(
        #         value = st.session_state['packages'],
        #         placeholder = "Write your code here",
        #         language="text",
        #         theme=c2.selectbox("Theme", options=THEMES, index=35),
        #         auto_update=c2.checkbox("Auto update", value=False),
        #         key = "package",
        #     )

        with st.expander(label="requirements.txt 수정", expanded=True):
            package_content = st_ace(
                value = st.session_state['packages'],
                placeholder = "Write your code here",
                theme='vibrant_ink',
                language="text",
                key = "package",
            )
        
        if package_content:
            # st.text(package_content)
            st.session_state['packages'] = package_content
            self.write_file(self.package_path, st.session_state['packages'])


    def display_code_editor(self):
        st.write('#### Edit source.py')
        st.caption(f"이 코드는 소스 코드({self.source_name})를 .py로 변환한 것입니다. 아래에서 수정 가능하며 서버에 저장됩니다.")
        
        # TODO: 길이 조절 필요. 우선은 expander로 임시 해결
        with st.expander(label=f"{self.source_name} 수정", expanded=False):
            code_content = st_ace(
                value = st.session_state['contents'],
                placeholder = "Write your code here",
                theme='vibrant_ink',
                language="python",
                key = "code",
            )
        
        if code_content:
            # st.text(code_content)
            st.session_state['contents'] = code_content
            self.write_file(os.path.join(self.py_path, self.source_name), st.session_state['contents'])

    def render(self):
        st.write("### Edit Code (Opt.)")
        st.caption('원할한 소스코드 자동 변경을 위해 사용자가 requirements.txt와 소스코드를 직접 수정할 수 있습니다.   \n   **단, 필수로 진행하지 않아도 됩니다.**')
        st.session_state["contents"] = self.read_file()

        if st.session_state["contents"]:
            if not os.path.exists(self.package_path):
                st.session_state['packages'] = self.recommend_package_list()
            else:
                st.session_state['packages'] = self.read_file(file_type='.txt')
            
            self.display_package_editor()
            self.display_code_editor()
