import datetime
import os
import shutil
import textwrap
import streamlit as st
from streamlit_pills import pills

TOP_MODELS = [
    "Linear Regression", "Logistic Regression", "Decision Tree", "Random Forest", "Gradient Boosting", "XGBoost", "LightGBM", "CatBoost", "SVM", "KNN",
    "MLP", "CNN", "RNN", "LSTM", "GRU", "Autoencoders", "GANs", "BERT", "K-Means Clustering", "Hierarchical Clustering", 
    "AdaBoost", "Extra Trees", "Elastic Net", "Polynomial Regression", "Bayesian Ridge Regression", "OMP", "Passive Aggressive Classifier", "Vanilla GANs", "Stacking", "Blending", 
]


class SearchJupyter:
    """kaggle api로 주피터 검색"""
    def __init__(self, api, download_path, check_jupyter):
        self.api = api
        self.download_path = download_path
        self.check_jupyter = check_jupyter
        
        if 'keyword' not in st.session_state:
            st.session_state['keyword'] = TOP_MODELS[0]
        if 'pills' not in st.session_state:
            st.session_state['pills'] = TOP_MODELS[0]
        # 기본값 3년 전부터 오늘까지
        if 'search_date' not in st.session_state:
            st.session_state['search_date'] = datetime.date.today() - datetime.timedelta(days=3*365)
        if 'notebooks' not in st.session_state:
            st.session_state['notebooks'] = None

    def search_jupyter(self):
        """선택된 키워드에 대해 주피터 검색"""
        MIN_VOTE = 0
        kernels = self.api.kernels_list(
            search = st.session_state['keyword'], 
            kernel_type = "all",
            page = 1,
            page_size = 20,
        )

        result = []
        for kernel in kernels:
            if kernel.totalVotes >= MIN_VOTE:
                kernel_last_run_time = kernel.lastRunTime
            if isinstance(kernel_last_run_time, str):
                kernel_last_run_time = datetime.datetime.strptime(kernel_last_run_time, "%Y-%m-%dT%H:%M:%S.%fZ")
            
            kernel_last_run_date = kernel_last_run_time.date()
            if kernel_last_run_date >= st.session_state['search_date']:
                result.append({
                    "ref": kernel.ref,
                    "title": kernel.title,
                    "votes": kernel.totalVotes,
                    # "url": f"https://www.kaggle.com/{kernel.ref}",
                    "author": kernel.author,
                    "last_run_time": kernel.lastRunTime
                })
        result = sorted(result, key=lambda x: x['votes'], reverse=True)[:10]

        return {st.session_state['keyword']: result}
    
    def save_jupyter(self, ref):
        """다운로드 받은 주피터를 download_path 에 저장"""
        if os.path.exists(self.download_path):
            shutil.rmtree(self.download_path)
        os.makedirs(self.download_path)

        # download_path에 .ipynb 저장
        self.api.kernels_pull(kernel=ref, path=self.download_path)

        # TODO: 데이터셋 정보 저장? (기존 코드에 존재)
        # file_path = os.path.join(self.download_path, f"{ref.split("/")[1]}.ipynb")

    def display_notebook(self):
        if not len(st.session_state['notebooks'][st.session_state['keyword']]):
            st.error("검색된 주피터 노트북이 없습니다.")
        else:
            """노트북 카드를 화면에 표시"""
            NUM_COLS = 4
            MAX_DISPLAY = 8

            notebooks = st.session_state['notebooks'][st.session_state['keyword']]
            for idx, notebook in enumerate(notebooks[:MAX_DISPLAY]):
                if idx % NUM_COLS == 0:
                    cols = st.columns(NUM_COLS) # 새로운 행 시작

                with cols[idx % NUM_COLS]:
                    shortened_title = textwrap.shorten(notebook['title'], width=90, placeholder="...")

                    # 연월일까지만 표시하도록 last_run_time 수정
                    if isinstance(notebook['last_run_time'], str):
                        last_run_date = datetime.datetime.strptime(notebook['last_run_time'], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%d")
                    else:
                        last_run_date = notebook['last_run_time'].strftime("%Y-%m-%d")

                    # 다운로드 버튼 준비
                    st.markdown("""
                        <style>
                        .stDownloadButton button {
                            padding: 5px 10px; 
                            width: auto;
                        }
                        </style>
                    """, unsafe_allow_html=True)

                    st.markdown(f"""
                        <div style="border: 1px solid #ddd; border-radius: 5px; padding: 10px; margin-bottom: 5px; height: 130px; display: flex; flex-direction: column; justify-content: space-between;">
                            <div>
                                <h5 style="font-size: 14px; margin-bottom: 0.5rem; height: 3rem; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;">
                                    <a href="{f"https://www.kaggle.com/{notebook['ref']}"}" target="_blank">{shortened_title}</a>
                                </h5>
                                <p style="line-height: 0.8; margin-top: 0; margin-bottom: 10px;"><strong>Votes:</strong> {notebook['votes']}</p>
                                <p style="line-height: 0.8; margin-top: 0;"><strong>Update:</strong> {last_run_date}</p>
                            </div>
                    """, unsafe_allow_html=True)

                    # 파일 다운로드 버튼 클릭 이벤트 설정
                    if st.button("Download", key=f"download_{idx}"):
                        self.save_jupyter(notebook['ref']) # wait
                        self.check_jupyter.click_check_btn(notebook['ref'].split('/')[1])

                    st.markdown("</div>", unsafe_allow_html=True)

    def set_input(self):
        selected_model = pills("Select a model", TOP_MODELS)

        # 모델 pill 항목을 클릭하면 해당 모델명으로 자동 검색
        if selected_model and st.session_state['pills']!=selected_model:
            st.session_state['pills'] = selected_model
            st.session_state['keyword'] = selected_model
            
        # 입력 폼
        with st.form(key='search_form'):
            keyword = st.text_input("Enter search keyword:", value=st.session_state.get('keyword', ''))

            # 날짜 선택
            selected_date = st.date_input(
                "Select a date (Notebooks from this date and newer will be shown):", 
                value=st.session_state['search_date']
            )

            search_button = st.form_submit_button(label='Search')

            if search_button:
                st.session_state['keyword'] = keyword
                st.session_state['search_date'] = selected_date
            
                    
    def render(self):
        st.write("### Search Jupyter")
        st.caption("필요한 소스 코드를 키워드로 쉽게 kaggle에서 검색해 사용할 수 있습니다.")

        self.set_input()

        if not st.session_state['notebooks'] or (st.session_state['keyword'] and list(st.session_state['notebooks'].keys())[0] != st.session_state['keyword']):
            st.session_state['notebooks'] = self.search_jupyter()
        self.display_notebook()