import streamlit as st
import os
from ui.components.get_ai_source.search_jupyter import SearchJupyter
from ui.components.get_ai_source.import_jupyter import ImportJupyter
from ui.components.get_ai_source.recommend_jupyter import RecommendJupyter
from ui.components.get_ai_source.check_jupyter import CheckJupyter
from ui.components.get_ai_source.from_git import FromGit

class GetAISource:
    """Get AI Source: 세가지 방법으로 주피터를 get하고, 정성적으로 해당 코드를 체크하기까지의 과정"""
    def __init__(self, api, path):
        if os.path.exists('interface/data_metadata/data_meta.json'):
            os.remove('interface/data_metadata/data_meta.json')
        self.api = api
        self.path = path
        self.download_path = path['source_notebook']
        self.source_py_path = path['source_py']
        # 탭마다 CheckJupyter 클래스를 두지 않고 공용으로 사용
        self.check_jupyter = CheckJupyter(api, self.path)

    def show_description(self):
        with st.expander("📝 처음 사용하는 사람을 위한 Get Ai Source 설명 📝"):
            st.markdown("""
                <p>Get AI Source에서는 세가지 방법으로 사용자가 소스 코드를 다운로드 혹은 업로드할 수 있습니다. 소스코드가 등록되면 mellerilab의 기준에 따라 실행 적합성을 평가합니다.</p>
                
                - ⭕: 평가 기준을 만족한다면 <span style="color:red">자동으로 AI Soulution을 생성 가능한 위치로 배치</span>됩니다.
                - ❌: 평가 기준을 만족하지 못한 소스 코드는 <span style="color:red">자동으로 삭제</span>됩니다.
            """, unsafe_allow_html=True)
            st.warning("⚠️ 현재 Streamlit의 에러로 처음 모델, Search, Download, 추천 버튼을 누르면 리셋이 되는 문제가 발생합니다. 이후에는 발생하지 않아 문제 없이 사용하실 수 있습니다.")
        # TODO: Streamlit 앱에서 첫 번째 상호작용은 선택한 탭을 첫 번째 탭으로 재설정하는 문제 발생(https://discuss.streamlit.io/t/returning-to-the-right-tab-after-clicking-button/31554/13)


    def render(self):
        if self.api is None:
            st.error("Kaggle API is not available.")
            return

        st.title("Get AI Source")
        self.show_description()

        tabs = st.tabs(["Search Jupyter", "Recommend Jupyter", "Import Code", "From Git"])
        # 선택된 탭에 대해 content 보여주기
        with tabs[0]:
            search_jupyter = SearchJupyter(self.api, self.download_path, self.check_jupyter)
            search_jupyter.render()

        with tabs[1]:
            recommend_jupyter = RecommendJupyter(self.api, self.download_path, self.check_jupyter)
            recommend_jupyter.render()
            
        with tabs[2]:
            import_jupyter = ImportJupyter(self.download_path, self.check_jupyter)
            import_jupyter.render()

        with tabs[3]:
            from_git = FromGit(self.check_jupyter)
            git_url = from_git.render()
            if st.button("Download from Git"):
                if git_url:
                    from_git.download_from_git()

        # check_jupyter는 세가지 탭에 대해 공용으로 사용
        self.check_jupyter.render()
