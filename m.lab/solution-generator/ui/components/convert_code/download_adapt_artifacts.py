import streamlit as st
import os
import re
from collections import defaultdict

class DownloadAdaptArtifacts:
    def __init__(self):
        self.artifacts_path = './engine/adapt_data/adapt_artifacts'

        if 'adapt_artifacts_files' not in st.session_state:
            st.session_state['adapt_artifacts_files'] = None

    def organize_files_by_iteration(self):
        files = os.listdir(self.artifacts_path)
        files.sort()

        iteration_dict = defaultdict(list)
        pattern = re.compile(r'iter(\d+)_')

        for file in files:
            match = pattern.search(file)
            if match:
                iter_num = match.group(1)
                iteration_dict[f'iter{iter_num}'].append(file)

        return iteration_dict
    
    def read_file_content(self, file_path):
        with open(file_path, 'r') as file:
            return file.read()
        
    def show_files(self):
        with st.container(border=True):
            for iteration, files in st.session_state['adapt_artifacts_files'].items():
                st.markdown(f"**Iteration {iteration} files**")
                for file in files:
                    file_path = os.path.join(self.artifacts_path, file)
                    with st.expander(file):
                        content = self.read_file_content(file_path)
                        st.text_area(f"Content of {file}", content, height=200)
    
    # def check_artifacts(self):
    #     btn_check = st.button("Check artifact files", help="현재 존재하는 artifacts 파일을 확인합니다.")
    #     if btn_check:
    #         st.session_state['adapt_artifacts_files'] = self.organize_files_by_iteration()

#     def render(self):
#         st.subheader('Check Artifact Files')
#         st.caption(""" Iteration 내에 생성 실패 할 경우, Data Adaptation 과정을 반복 진행 하면서 생성되는 code 및 error log 파일을 
#                     확인하여 생성형 AI 가 헷갈려 하는 사항을  VS Code에서 수정합니다. 

# - iterN_code.txt : 실행 python 코드     
# - iterN_requirements.txt : install되는 pip pacakge가 작성된 requirements.txt     
# - iterN_error.txt : python 코드 에러 발생 시 error log    """)
        
#         # self.check_artifacts()

#         if st.session_state['adapt_artifacts_files']:
#             self.show_files()