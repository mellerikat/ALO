import json
import os
import re
import streamlit as st
import subprocess
from streamlit_ace import st_ace
from engine.chatgpt import chatgpt_query
from ui.src.chat_prompts.read_prompt import read_prompt

from path_list import *

class EditMetaData:
    def __init__(self, path):
        self.path = path
        self.metadata_file_path = path['data_metadata']

    def read_metadata(self):
        metadata = ""
        if os.path.exists(self.metadata_file_path):
            with open(DATA_META_PATH + 'data_meta.json', 'r', encoding='utf-8') as json_file:
                metadata = json.load(json_file)
        else:
            st.warning("Warning: metadata.md file does not exist.")
        return metadata

    def write_metadata(self, content):
        with open(DATA_META_PATH + "data_meta.json", 'w', encoding='utf-8') as json_file:
            json.dump(content, json_file, ensure_ascii=False, indent=4)

    def render_editor(self):
        with st.expander("Input Data Definition:", expanded=False):
            # Read existing metadata
            metadata_ori = self.read_metadata()
            # Input field for metadata
            metadata_input_descr = st.text_area("입력 데이터 설명 추가:", value=st.session_state["contents"]['data_description:']['data_description'], height=200, key="metadata_editor1")
            metadata_input_y = st.text_area("입력 데이터 Label 정의 추가:", value=st.session_state["contents"]['y_description:']['y_description'], height=200, key="metadata_editor2")

            metadata_ori['data_description:']['data_description'] = metadata_input_descr
            metadata_ori['y_description:']['y_description'] = metadata_input_y
            
            if st.button("Save Metadata"):
                self.write_metadata(metadata_ori)
                st.success("Metadata saved successfully!")

            # st.markdown("---")
            # st.subheader("Preview")
            # st.markdown(metadata_input)

    def render(self):
        st.write("### Write Data Metadata (for Upload Data)")
        st.caption("만약 입력한 코드와 데이터가 불일치 할 경우 Runnable 한 코드 생성이 힘들 수 있습니다. \n 데이터 정의가 추가될 경우 성공률이 향상됩니다. !! ")

        st.session_state["contents"] = self.read_metadata()
        self.render_editor()