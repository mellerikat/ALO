import os
import shutil
import streamlit as st

# 사용자가 직접 주피터 업로드 (단, 체크를 위한 용도)
class ImportJupyter:
    def __init__(self, download_path, check_jupyter):
        self.download_path = download_path
        self.check_jupyter = check_jupyter

    def save_jupyter(self, uploaded_file):
        """업로드 주피터를 download_path 에 저장"""
        if os.path.exists(self.download_path):
            shutil.rmtree(self.download_path)
        os.makedirs(self.download_path)

        upload_path = os.path.join(self.download_path, uploaded_file.name)
        with open(upload_path, "wb") as file:
            file.write(uploaded_file.getbuffer())

        # 파일 저장 확인
        if os.path.getsize(upload_path) > 0:
            st.success(f"'{uploaded_file.name}' 파일이 성공적으로 업로드 되었습니다.")
        else:
            st.error(f"Error: '{uploaded_file.name}' 파일이 업로드 되지 않았습니다. 다시 시도해 주세요.")

    def set_input(self):
        with st.container(border=True):
            st.markdown("##### Upload:")

            # 파일 업로드 컴포넌트
            uploaded_file = st.file_uploader("Choose a notebook file to check", type=['ipynb', 'py', 'zip'])
            if uploaded_file:
                self.save_jupyter(uploaded_file)
                self.check_jupyter.click_check_btn(uploaded_file.name.split(".")[0])

    def render(self):
        st.write("### Import Code")
        st.caption('사용하고 싶은 source code를 사용자가 가지고 있다면 직접 업로드 할 수 있습니다.')
        with st.expander('💥 코드들의 파일구조는 이렇게 구성해주세요!'):
            st.markdown("""
                아래 유형 중 하나의 형태로 코드들을 구성해서 업로드 해주세요. 
                - *.ipynb 1개 
                - *.py 1개 
                - main.py 1개 및 src 폴더 (src의 하위 폴더 및 파일 구성은 자유롭게 구성해주세요.) <br>
                  : 이 경우는 <span style="color:red"> .zip </span>으로 압축해서 업로드해주세요! 
                """, unsafe_allow_html=True)
        self.set_input()