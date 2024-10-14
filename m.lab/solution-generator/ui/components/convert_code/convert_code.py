import streamlit as st

from ui.components.convert_code.upload_data import UploadData
from ui.components.convert_code.edit_code import EditCode
from ui.components.convert_code.adapt_code import AdaptCode
from ui.components.convert_code.download_adapt_artifacts import DownloadAdaptArtifacts
from ui.components.convert_code.edit_metadata import EditMetaData

class ConvertCode:
    def __init__(self, api, path):
        self.api = api 
        self.path = path
        
    def render(self):
        st.title("Adapt Code for Dataset")
        with st.expander("📝 처음 사용하는 사람을 위한 Adapt Code for Dataset 설명 📝"):
            st.markdown("""
                이 탭은 사용자가 데이터를 업로드하면 'Get AI Source'의 소스 코드를 데이터에 맞게 변환합니다.
                이 과정은 소스 코드가 사용자의 데이터에 맞게 작성되지 않아 바로 적용할 수 없어 LLM을 활용해 :red[데이터에 맞게] 코드를 수정하고자 합니다.
                        
                :red[데이터셋에 맞게 수정하자는 목표를 가지고 있어 AI solution을 제작하는 다음 step과 주요하게 변경하고자 하는 부분에서 차이점]을 가집니다.
                
                1. 📂 사용자가 데이터를 업로드합니다.
                2. 🔨 (Opt) 사용자가 수정을 원한다면, 추천된 requirements.txt와 소스 코드를 수정합니다.
                3. 💻 AI Agent를 활용해 소스코드를 사용자가 제공한 데이터에 맞게 수정합니다. *(데이터셋과 소스코드가 있을 경우에만 실행됩니다)*

                """, unsafe_allow_html=True)
        upload_data = UploadData(self.api, self.path)
        upload_data.render()

        st.divider()
        data_meta = EditMetaData(self.path)
        data_meta.render()

        st.divider()
        edit_code = EditCode(self.path)
        edit_code.render()

        st.divider()
        adapt_code = AdaptCode(self.path)
        adapt_code.render()
    
        # st.divider()
        # download_artifacts = DownloadAdaptArtifacts()
        # download_artifacts.render()