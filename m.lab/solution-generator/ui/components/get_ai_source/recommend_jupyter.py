import datetime
import json
import os
import re
import shutil
import textwrap
import streamlit as st

from engine.chatgpt import chatgpt_query

# 예시
USE_CASES = {
    "Bolt Fastening VAD": {
        "project_background": """Bolt Fastening은 제조 공정에서 흔히 볼 수 있는 핵심 작업입니다.
        이 과정은 전동 드라이버를 이용하여 볼트를 부품에 자동으로 조립하는 ETC(Electronic Torque Controller) Tool을 활용합니다. 다음과 같은 ETC Tool 장비가 제조 현장에 설치 되며, 작업자는 제품을 스캔하고 정해진 수의 볼트를 받은 다음 제품에 순서대로 체결하는 작업을 반복합니다.
        ETC Tool 장비는 정상 체결 여부에 대해 판정 하는 기능도 제공하지만, 이 결과에 대해 100% 신뢰할 수 없는 문제가 있습니다. 정상 체결 여부를 확인하기 위해 기존의 장비는 규칙 기반으로 체결의 마지막 Torque 값이 Target Torque에 오차 범위 내인지로 판정 하는데 아래와 같은 경우에 대해 결함으로 인지하지 못합니다. 각각의 경우 마지막 Torque 값이 Target Torque와 일치하여 모두 정상으로 판정하며 작업자가 면밀히 살펴보지 않으면 인지하기 어렵습니다. 특히 볼트 혼용은 작업자가 부품에 체결하는 모든 볼트를 한 손에 파지하고 순서에 맞게 탭에 끼워 체결하는데 순서와 다른 볼트가 체결 되었을 때 발생하게 됩니다. 아래 그림과 같이 제품에 6개의 볼트를 체결하는데 스펙이 다른 4번째 볼트가 5번 째 또는 6번째에 체결되는 경우입니다. 볼트는 길이, 헤드의 형태, 나사의 형태에 따라 종류가 다양하며 설계와 다른 볼트가 체결된 경우 열이나 흔들림에 의해 풀릴 수 있습니다. 이러한 문제를 제조 과정에서 검사하지 못하면 시장에서 품질 이슈를 초래하게 됩니다. 그러나 이러한 결함은 양산 공장에서 매우 희소하게 발생하여 데이터가 많지 않으며, 현장의 새로운 유형의 결함이 발생하였을 때 빠르게 대응할 수 있어야 합니다. 또한, 제조 현장은 생산량 달성을 위한 사이클 타임이 중요하므로 볼트 체결과 동시에 판정 결과를 요구합니다.
        볼트 체결 과정에서 저장된 사진 이미지를 통해 식별하고 판정하여 정상 체결여부를 판정하는 것이 목표입니다.
        """,
        "data_type": "image",
        "data_description": """볼트 체결 후 찍은 이미지 데이터입니다. 이미지는 정상 및 비정상 체결 여부를 레이블로 가지고 있습니다. 
        데이터 구조는 train에 abnormal과 OK 디레토리가 있으며 이미지가 제공됩니다. test에는 NG(abnormal)과 ok로 파일 이름이 시작되는 이미지 파일이 제공됩니다.
        """,
        "task": "vision anomaly detection",
         "dataset_notebooks": {
            "thomasdubail/screwanomalies-detection": {'reason': '', 'notebooks': [
                {
                    "title": "VAE+GAN",
                    "ref": "thomasdubail/vae-gan",
                    "lastRunTime": datetime.datetime.strptime("2022-08-24 19:31:07", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 20
                },
                {
                    "title": "3d printer defect detection_BasicModels_tensorflow",
                    "ref": "mubtasimahasan/3d-printer-defect-detection-basicmodels-tensorflow",
                    "lastRunTime": datetime.datetime.strptime("2022-09-04 08:10:58", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 13
                },
                {
                    "title": "Auto-CNN",
                    "ref": "thomasdubail/auto-cnn",
                    "lastRunTime": datetime.datetime.strptime("2021-11-09 17:16:30", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 10
                },
                {
                    "title": "AE+GAN",
                    "ref": "thomasdubail/ae-gan",
                    "lastRunTime": datetime.datetime.strptime("2021-11-17 03:43:17", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 8
                },
            ]},
            "wardaddy24/marble-surface-anomaly-detection-2": {'reason': '', 'notebooks': [
                {
                    "title": "Marble Defect",
                    "ref": "rishirajak/marble-defect",
                    "lastRunTime": datetime.datetime.strptime("2021-07-12 10:16:35", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 12
                },
                {
                    "title": "marbles quality with VGG19",
                    "ref": "zzettrkalpakbal/marbles-quality-with-vgg19",
                    "lastRunTime": datetime.datetime.strptime("2022-08-11 22:37:49", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 7
                },
                {
                    "title": "Marble Surface Detection DenseNet201",
                    "ref": "stpeteishii/marble-surface-detection-densenet201",
                    "lastRunTime": datetime.datetime.strptime("2021-06-24 16:24:23", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 4
                },
                {
                    "title": "Thomas_Marble Surface Defect Detector",
                    "ref": "samlinsen/thomas-marble-surface-defect-detector",
                    "lastRunTime": datetime.datetime.strptime("2022-07-21 06:37:27", "%Y-%m-%d %H:%M:%S"),
                    "totalVotes": 2
                },
            ]},
        }
    }
}

class RecommendJupyter:
    """사용자가 입력한 정보를 토대로 주피터 노트북을 추천"""
    def __init__(self, api, download_path, check_jupyter):
        self.api = api
        self.download_path = download_path
        self.check_jupyter = check_jupyter

        # 사용자의 입장에서 input 예시를 제공후 추천 결과도 처음에 보여줌
        use_case = USE_CASES['Bolt Fastening VAD']
        session_defaults = {
            "project_background": use_case['project_background'],
            "data_type": use_case['data_type'],
            "data_description": use_case['data_description'],
            "task": use_case['task'],
            "dataset_notebooks": use_case['dataset_notebooks'],
            "is_rec_btn_clicked": False,
        }

        for key, value in session_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def search_datasets(self, keyword, max_results = 20, max_size=None):
        """kaggle api로 데이터셋 검색 (keyword = data_type + task)"""
        all_datasets = []
        current_page = 1    # 페이지당 20개의 데이터셋 가짐
        
        # 현재는 최대 20개만 검색
        while len(all_datasets) < max_results:
            if max_size is None: 
                result = self.api.dataset_list(search=keyword, page=current_page)
            else: 
                result = self.api.dataset_list(search=keyword, page=current_page, max_size=max_size)
            # if max_size is None: 
            #     result = self.api.dataset_list(search=keyword, page=current_page)
            # else: 
            #     result = self.api.dataset_list(search=keyword, page=current_page, max_size=max_size)
            if len(result) == 0:
                break
            all_datasets.extend(result)
            if len(result) < 20:
                break
            current_page = current_page + 1

        return all_datasets[:max_results]
    
    def fetch_dataset_metadata(self, ref):
        """검색된 데이터셋의 metadata 저장"""
        # 데이터셋 정보가 dataset_metadata.json으로 저장, path만 리턴해 해당 파일을 다시 읽어옴
        data_path = self.api.dataset_metadata(ref, path=None)
        try:
            with open(data_path, 'r') as f:
                metadata = json.load(f)
        except json.JSONDecodeError:
            st.error(f"Invalid JSON format for dataset {ref}")
            return None
        
        # 중요한 key만 다시 저장
        core_keys = ['id', 'title', 'subtitle', 'description', 'usabilityRating', 'totalViews', 'totalVotes', 'totalDownloads', 'keywords', 'licenses', 'data']
        result = {key: metadata[key] for key in core_keys}

        # dataset_metadata.json 제거
        try:
            os.remove('dataset-metadata.json')
        except OSError as e:
            st.error(f"Error removing metadata file: {e.strerror}")

        return result
    
    def fetch_dataset_list_files(self, ref):
        """검색된 데이터셋의 파일 리스트(즉, 파일 구조) 저장"""
        # TODO: 파일 구조로 변환 필요
        result = self.api.dataset_list_files(ref)
        return result
    
    def recommend_datasets(self, datasets_metadata):
        """# LLM을 통해 관련된 데이터셋 추천"""
        datasets_metadata_text = json.dumps(datasets_metadata, indent=4)

        # TODO: 프롬프트 분리 필요
        recommendations_input = f"""
        The user has provided the following information. If the information is not in English, please translate it into English first:
        Data Type: {st.session_state['data_type']}
        Data Description: {st.session_state['data_description']}
        Project Background: {st.session_state['project_background']}
        Task: {st.session_state['task']}

        Based on the provided information, recommend 5 datasets from the following list with explanation:

        {datasets_metadata_text}

        Please provide the recommendations in Korean.

        Output should be in the following format:
        1. **Dataset Name**: https://www.kaggle.com/datasets/ipythonx/mvtec-ad
        - **Reason**: Explanation of why this dataset is suitable (relevance to the dataset, project suitability, etc.)

        You should hold this letters as English: **Dataset Name**, **Reason**
        """
        try:
            response = chatgpt_query(recommendations_input)
        except Exception as e:
            st.error(f"ChatGPT API 호출에 실패했습니다: {e}")
            return None
        
        # print(response)
        recommended_refs = re.findall(r'https://www.kaggle.com/datasets/([^ \n]+)', response)
        reasons = re.findall(r'- \*\*Reason\*\*: ([^\n]+)', response)

        return recommended_refs, reasons
    
    def get_top_kernels(self, ref, max_results=4):
        """추천받은 데이터셋을 사용하는 노트북 get"""
        kernels = self.api.kernels_list(dataset=ref, sort_by='voteCount')
        return kernels[:max_results]
    
    def save_jupyter(self, ref):
        """업로드 주피터를 download_path 에 저장"""
        if os.path.exists(self.download_path):
            shutil.rmtree(self.download_path)
        os.makedirs(self.download_path)

        self.api.kernels_pull(kernel=ref, path=self.download_path)

        # TODO: 데이터셋 정보 저장? (기존 코드에 존재)
        # file_path = os.path.join(self.download_path, f"{ref.split("/")[1]}.ipynb")

    def get_notebook_attribute(self, notebook, attribute):
        """노트북 속성을 가져오거나 기본값을 반환합니다."""
        if isinstance(notebook, dict):
            return notebook.get(attribute, None)
        return getattr(notebook, attribute, None)

    def display_notebook(self):
        """노트북 카드를 화면에 표시"""
        # TODO: 현재는 데이터셋 별로 노트북 카드를 표시, search와 디자인 통일 필요
        NUM_COLS = 4
        for i, dataset in enumerate(st.session_state['dataset_notebooks'].keys()):
            st.write(f"### {i + 1}. {dataset}")
            st.caption(st.session_state['dataset_notebooks'][dataset]['reason'])
            for idx, notebook in enumerate(st.session_state['dataset_notebooks'][dataset]['notebooks']):
                if idx % NUM_COLS == 0:
                    cols = st.columns(NUM_COLS)  # 행 바꿈

                with cols[idx % NUM_COLS]:
                    title = self.get_notebook_attribute(notebook, 'title')
                    last_run_date = self.get_notebook_attribute(notebook, 'lastRunTime')
                    ref = self.get_notebook_attribute(notebook, 'ref')
                    totalVotes = self.get_notebook_attribute(notebook, 'totalVotes')
                    shortened_title = textwrap.shorten(title, width=90, placeholder="...")

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
                                    <a href="https://www.kaggle.com/code/{ref}" target="_blank">{shortened_title}</a>
                                </h5>
                                <p style="line-height: 0.8; margin-top: 0; margin-bottom: 10px;"><strong>Votes:</strong> {totalVotes}</p>
                                <p style="line-height: 0.8; margin-top: 0;"><strong>Update:</strong> {last_run_date.date()}</p>
                            </div>
                    """, unsafe_allow_html=True)

                    # 파일 다운로드 버튼 클릭 이벤트 설정
                    if st.button("Download", key=f"download_{i}_{idx}"):
                        self.save_jupyter(ref) # wait
                        self.check_jupyter.click_check_btn(ref.split('/')[1])
                    st.markdown("</div>", unsafe_allow_html=True)

    def recommend_keyword(self):
        """ChatGPT를 통해 Kaggle 검색 키워드 추천 받기"""
        recommendations_input = f"""
        The user has provided the following information. If the information is not in English, please translate it into English first:
        Data Type: {st.session_state['data_type']}
        Data Description: {st.session_state['data_description']}
        Project Background: {st.session_state['project_background']}
        Task: {st.session_state['task']}

        Based on the provided information, recommend a single keyword for Kaggle dataset search.

        Please provide the keyword in English. Output should be in the following format:
        keyword:recommended_keyword
        """

        try:
            response = chatgpt_query(recommendations_input)
        except Exception as e:
            st.error(f"ChatGPT API 호출에 실패했습니다: {e}")
            return None

        # 키워드 추출 (다음의 경우 단일 키워드를 가정합니다)
        keyword_match = re.search(r'keyword:\s*\b(\w+)\b', response, re.IGNORECASE)
        if keyword_match:
            keyword = keyword_match.group(1)
            return keyword
        else:
            st.warning("추천된 키워드를 추출할 수 없습니다.")
            return None

    def run_recommend_pipeline(self):
        """추천 파이프라인 실행"""
        # step1: 데이터셋 검색
        keyword = f"{st.session_state['data_type']} {st.session_state['task']}"
        # keyword = self.recommend_keyword()
        datasets = self.search_datasets(keyword)
        print(datasets)
        st.session_state['dataset_notebooks'] = {}

        # step2: 데이터셋 정보 kaggle에서 가져오기
        datasets_metadata = {}
        for dataset in datasets:
            ref = dataset.ref
            metadata = self.fetch_dataset_metadata(ref)
            if metadata is None:
                continue
            # TODO: file_list 진행 예정
            # file_list = self.fetch_dataset_list_files(ref)
            datasets_metadata[metadata["title"]] = metadata

        # step3: 사용자의 정보와 관련된 데이터셋 추천
        rec_datasets, reasons = self.recommend_datasets(datasets_metadata)

        if len(rec_datasets) is not len(reasons):
            pass

        # step4: 추천받은 데이터셋을 사용하는 주피터 최대 4개씩 리스트업
        for i, rec_dataset in enumerate(rec_datasets):
            notebooks = self.get_top_kernels(rec_dataset)
            st.session_state['dataset_notebooks'][rec_dataset] = {'reason': reasons[i], 'notebooks': notebooks}
        
            # st.session_state['dataset_notebooks'][rec_dataset] = notebooks
            
    def set_input(self):
        """사용자로부터 프로젝트 배경, 데이터 타입, 목표 태스크, 데이터 설명 등의 정보를 입력받음"""
        with st.form(key='recommend_form'):
            project_background = st.text_area("프로젝트 배경 및 목표", value=st.session_state["project_background"])
            data_type = st.selectbox(
                "데이터 타입",
                ["image", "text", "audio", "multimodal", "tabular", "video", "categorical"],
                index=["image", "text", "audio", "multimodal", "tabular", "video", "categorical"].index(st.session_state["data_type"])
            )
            task = st.text_area("목표 Task/Model", value=st.session_state["task"])
            data_description = st.text_area("데이터 설명", value=st.session_state["data_description"])
            submit_button = st.form_submit_button(label='추천')

            if submit_button:
                st.session_state["is_rec_btn_clicked"] = True

    def render(self):
        st.write("### Recommend Jupyter")
        st.caption("사용자가 원하는 프로젝트와 데이터셋 기반으로 활용할 수 있는 kaggle jupyter을 추천합니다. 아래 예시를 참고하여 프로젝트 정보와 데이터셋 정보를 입력해주세요.")
        self.set_input()

        if st.session_state["is_rec_btn_clicked"]:
            self.run_recommend_pipeline()
            st.session_state["is_rec_btn_clicked"] = False
        self.display_notebook()