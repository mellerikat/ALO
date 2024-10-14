import git
import os
import shutil
from path_list import *
import zipfile
import streamlit as st 
from git import Repo
from uuid import uuid4

class FromGit:
    def __init__(self, check_jupyter):
        self.git_url = None
        self.branch = None
        self.file_name = None

        ## MLOps feasibility 확인 용 instance
        self.check_jupyter = check_jupyter


    def download_from_git(self):
        save_folder = SOURCE_NOTEBOOK_PATH  ## .py, .ipynb 일단 이곳으로 다운로드 통일
        valid_formats = [".ipynb", ".zip", ".py"]
        if self.file_name == None:
            st.error("Insert file name ...")
            return
        if not any(self.file_name.endswith(fmt) for fmt in valid_formats):
            st.error("Only *.ipynb, *.py or *.zip formats are supported.")
            return
        temp_dir = f"/tmp/{uuid4()}"
        os.makedirs(temp_dir, exist_ok=True)
        try:
            Repo.clone_from(self.git_url, temp_dir, branch=self.branch)
            src_file = os.path.join(temp_dir, self.file_name)
            if os.path.exists(src_file):
                ## unzip 은 check_jupyter.py 에서 진행 한다. 

                # save_folder가 이미 존재하면 삭제 후 다시 생성
                if os.path.exists(save_folder):
                    shutil.rmtree(save_folder)                                
                os.makedirs(save_folder, exist_ok=True)
                
                dest_file = os.path.join(save_folder, os.path.basename(src_file))
                with open(dest_file, "wb") as f_dest:
                    with open(src_file, "rb") as f_src:
                        f_dest.write(f_src.read())

                ## MLOps feasibility 체크 위함
                st.session_state['download_file'] = self.file_name.split(".")[0]
                self.check_jupyter.click_check_btn(self.file_name.split(".")[0])
            else:
                st.error(f"{self.file_name} does not exist in the repo.")
        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            shutil.rmtree(temp_dir)

    def render(self):
        st.write("### Import Code for Git")
        st.caption('사용자 모델링 code를 Git 으로부터 업로드 할 수 있습니다.')
        with st.expander('💥 코드들의 파일구조는 이렇게 구성해주세요!'):
            st.markdown("""
                아래 유형 중 하나의 형태로 코드들을 구성해서 업로드 해주세요. 
                - *.ipynb 1개 
                - *.py 1개 
                - main.py 1개 및 src 폴더 (src의 하위 폴더 및 파일 구성은 자유롭게 구성해주세요.) <br>
                  : 이 경우는 <span style="color:red"> .zip </span>으로 압축해서 업로드해주세요! 
                """, unsafe_allow_html=True)

        self.git_url = st.text_input("Git Repository URL")
        self.branch = st.text_input("default branch")
        self.file_name = st.text_input("Path to a model code file (must be .py, .ipynb or *.zip)")

        return self.git_url