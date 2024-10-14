import os
import shutil
import nbformat
import re
import pandas as pd
import altair as alt
import streamlit as st
import tiktoken
import zipfile
from datetime import datetime
from engine.chatgpt import chatgpt_query
from ui.src.chat_prompts.read_prompt import read_prompt

CONDITION_POINT = 7
TOKEN_MARGIN = 500 # for langgraph alo template 

class CheckJupyter:
    """MLOps 실행 적합성을 6가지 항목에 대해 평가"""
    def __init__(self, api, path):
        self.api = api
        self.download_path = path['source_notebook']
        self.py_path = path['source_py']
        self.metadata_path = path['metadata']
        # check 하려는 노트북이 변경되었는지 확인하기 위한 변수
        self.update_file = None    
        # download_path에 존재하는 파일, self.notebook과 구분되어야 함
        st.session_state['download_file'] = None    
        st.session_state['analysis_result'] = None

    def click_check_btn(self, notebook):
        """get_ai_source에서 버튼이 클릭되면 함수 호출"""
        self.update_file = notebook

    def extract_notebook_content(self, ipynb_file_path, only_code=False):
        """Jupyter 노트북 파일의 내용을 추출"""
        with open(ipynb_file_path, 'r', encoding='utf-8') as f:
            notebook = nbformat.read(f, as_version=4)

        content = ''
        for cell in notebook.cells:
            if cell.cell_type == 'code':
                content += cell.source + '\n\n'
        return content

    def analyze_mlops_compatibility(self, notebook_content):
        """ChatGPT를 사용한 MLOps 적합성 분석 및 설명"""
        template = read_prompt('analysis_mlops_score.md')
        print(template)
        prompt = template.format(notebook_content=notebook_content)

        try:
            result = chatgpt_query(prompt)
            parts = result.strip().split('==Divide==')
            response1 = parts[0].strip()  # Divide 이전 부분
            response2 = parts[1].strip()  # Divide 이후 부분
            # FIXME 
            response2 = response2.replace('Request2', 'Metadata extracted from code')
            response2 = response2.replace('Request 2', 'Metadata extracted from code')
            # metadata_path에 저장되도록 설정 (없으면 생성)
            metadata_file_path = os.path.join(self.metadata_path, "metadata.md")
            # 폴더가 존재하지 않으면 생성
            os.makedirs(self.metadata_path, exist_ok=True)
            # response2를 metadata.md 파일로 저장
            with open(metadata_file_path, "w") as file:
                file.write(response2)
            print(f"metadata for data 내용이 {metadata_file_path} 파일로 저장되었습니다.")
            scores, reasons = self.parse_analysis_scores_and_reasons(response1)
            return {
                'title': st.session_state['download_file'], 
                'scores': scores,
                'reasons': reasons
            }
        except Exception as e:
            return {
                'title': None, 
                'scores': {},
                'reasons': f"노트북 분석에 실패했습니다: {e}"
            }

    def parse_analysis_scores_and_reasons(self, response):
        """ChatGPT 응답에서 점수 및 평가 이유 추출"""
        scores = {
            'Training Code': 0,
            'Inference Code': 0,
            'Model Evaluation': 0,
            'Preprocess Code': 0,
            'Input Definition': 0,
            'Output Definition': 0
        }
        reasons = {
            'Training Code': '',
            'Inference Code': '',
            'Model Evaluation': '',
            'Preprocess Code': '',
            'Input Definition': '',
            'Output Definition': ''
        }
        matches = re.findall(r'\d+\.\s+.*?\?\s*(\d+)P\s*(.*?)(?=\d+\.|$)', response, re.DOTALL)
        for i, match in enumerate(matches, 1):
            score, reason = match
            components = {'1': 'Training Code', '2': 'Inference Code', '3': 'Model Evaluation', '4':'Preprocess Code', '5':'Input Definition', '6': 'Output Definition'}
            scores[components[str(i)]] = int(score.strip())
            reasons[components[str(i)]] = reason.strip() 
        return scores, reasons

    def display_analysis(self):
        """분석 결과 및 이유 UI에 표시"""
        selected_file = self.update_file
        analysis_result = st.session_state['analysis_result']
        scores = analysis_result['scores']
        reasons = analysis_result['reasons']
        if not scores:
            st.write("No scores to display.")
            return
        df_scores = pd.DataFrame(list(scores.items()), columns=['항목', '점수'])
        df_scores['이유'] = df_scores['항목'].map(reasons)
        with st.expander("📊 Evaluation Criteria Explained 📝"):
            st.markdown("""
            MLOps 실행 적합성을 6가지 항목에 대해 평가합니다. 각 기준은 최대 10점 만점으로 평가됩니다. 성공적인 평가를 위해서는 1번에서 3번 항목이 무조건 7점 이상이어야 합니다. 기준은 다음과 같습니다:

            1. **Training Code 🏋️**: <span style="color:red">모델 훈련 코드를 포함하고 있습니까?</span>
            2. **Inference Code 📈**: <span style="color:red">입력 데이터에 대한 추론 코드를 포함하고 있습니까?</span>
            3. **Model Evaluation 📊**: <span style="color:red">모델 평가를 위한 지표가 포함되어 있습니까?</span>
            4. **Data Preprocessing 🧹**: 데이터 전처리 코드를 포함하고 있습니까?
            5. **Input Definition 📂**: 훈련 및 추론 데이터의 정의가 명확합니까?
            6. **Output Definition 🎯**: 추론 후 생성될 출력이 명확합니까?
            
            참고로, python 파일에 들어가는 내용은 학습 호출 함수와 추론 호출 함수를 분리해서 작성해주세요. 
            예를들어, train()과 inference() 함수가 별도로 호출되어야 합니다. 두 함수를 하나의 별도 함수에 함께 넣지 말아주세요.  
            """, unsafe_allow_html=True)
        chart = alt.Chart(df_scores).mark_bar(color='skyblue').encode(
            x=alt.X('항목:N', sort=None),
            y=alt.Y('점수:Q', scale=alt.Scale(domain=[0, 10])),
            tooltip=['항목', '점수', '이유']
        )
        rule = alt.Chart(df_scores).mark_rule(
            color='red'
        ).encode(
            y=alt.datum(7)
        )
        combined_chart = alt.layer(chart, rule).configure_axis(
            domain=False,
            grid=True
        ).properties(
            width=700,
            height=400
        )
        st.altair_chart(combined_chart)
        # 성공 조건 검사
        successful_criteria = (df_scores['항목'] == 'Training Code') & (df_scores['점수'] >= CONDITION_POINT) | \
                              (df_scores['항목'] == 'Inference Code') & (df_scores['점수'] >= CONDITION_POINT) | \
                              (df_scores['항목'] == 'Model Evaluation') & (df_scores['점수'] >= CONDITION_POINT)
        if successful_criteria.sum() == 3:
            st.success("🎉 Notebook has passed the MLOps compatibility check! 🥳")
            return True # pass했는지 return
        else:
            st.warning("🚨 Notebook did not pass MLOps compatibility check. It has been deleted due to failing the score threshold.")
            file_path = os.path.join(self.download_path, f"{selected_file}.ipynb")
            py_path = os.path.join(self.download_path, f"{selected_file}.py")
            file_path2 = os.path.join(self.metadata_path, f"metadata.md")
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    # 업데이트된 파일 목록을 반영하여 리스트에서 삭제하고, 다시 선택되지 않도록 설정
                    st.session_state['download_file'] = None
                if os.path.exists(py_path):
                    os.remove(py_path)
                    # 업데이트된 파일 목록을 반영하여 리스트에서 삭제하고, 다시 선택되지 않도록 설정
                    st.session_state['download_file'] = None

                if os.path.exists(file_path2):
                    os.remove(file_path2)
                st.success(f"🗑️ '{selected_file}' and its corresponding file have been deleted.")
            except Exception as e:
                st.error(f"❌ Failed to delete {selected_file}: {e}")
            return False

    def check_jupyter(self):

        def get_max_out_token(model_id): 
            model_id_out_token_table = {
                            'gpt-4o-2024-08-06': 16384,
                            'gpt-4o-mini-2024-07-18': 16384,
                            'gpt-4o-2024-05-13': 4096,
                            'gpt-4-turbo-2024-04-09': 4096,
                            'gpt-4-0125-Preview': 4096,
                            'gpt-4-vision-preview': 4096,
                            'gpt-4-1106-Preview': 4096,
                            'gpt-35-turbo-0125': 4096,
                            'gpt-35-turbo-1106': 4096
                            }
            if model_id in model_id_out_token_table: 
                max_out_token = model_id_out_token_table[model_id]
                print(f"[INFO] max out token: {max_out_token}")
                return max_out_token
            else: 
                print(f"[WARNING] Your OPENAI_MODEL_ID: {model_id} is not supported. Your output token is limited to 4096.")
                return 4096 

        self.max_token = get_max_out_token(os.getenv('OPENAI_MODEL_ID')) - TOKEN_MARGIN

        def count_tokens(text: str, model: str = 'cl100k_base') -> int:
            # GPT-4의 토크나이저 사용을 가정
            enc = tiktoken.get_encoding(model)  # GPT-4 모델명에 맞는 인코딩 지정
            tokens = enc.encode(text)
            return len(tokens)
        title = st.session_state['download_file']
        if os.path.exists(self.py_path):
            shutil.rmtree(self.py_path)
        # re-create source_py path 
        os.makedirs(self.py_path)
        content, token_length = None, None
        is_single_file = True 
        
        if len(os.listdir(self.download_path)) != 1: 
            st.error("1개의 파일만 업로드 가능합니다.") 
        # ipynb case
        if os.path.exists(os.path.join(self.download_path, f"{title}.ipynb")):
            content = self.extract_notebook_content(os.path.join(self.download_path, f"{title}.ipynb"))
        # single py case
        elif os.path.exists(os.path.join(self.download_path, f"{title}.py")):
            py_path = os.path.join(self.download_path, f"{title}.py")
            with open(py_path, 'r', encoding='utf-8') as file:
                content = file.read()
        # zip case (src directory + main.py) - multi files
        elif os.path.exists(os.path.join(self.download_path, f"{title}.zip")):
            zip_file_path = os.path.join(self.download_path, f"{title}.zip")
            extract_zip_to_directory(zip_file_path, self.download_path)
            # check if only main.py and src directory exist 
            if check_zip_contents(self.download_path):
                main_py_path = os.path.join(self.download_path, "main.py") 
                header_content = """from pathlib import Path
 
# 현재 파일(d.py)의 부모 디렉토리를 기준으로 'src' 경로를 계산합니다.
src_path = Path(__file__).parent / 'src'
for root, dirs, files in os.walk(src_path):
    module_path = Path(root)
    if str(module_path) not in sys.path:
        sys.path.insert(0, str(module_path))
"""
                with open(main_py_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                new_content = header_content + content
                with open(main_py_path, 'w', encoding='utf-8') as file:
                    file.write(new_content)

                is_single_file = False # multi files
            else:
                st.error("압축 파일 내에 'main.py' 파일과 'src' 폴더만 포함 되어야 합니다.") 
        else:
            st.error("다운로드된 소스 코드가 존재하지 않거나 요구되는 파일구조에 부합하지 않습니다. 가이드대로 소스 코드를 다운로드 혹은 업로드해주세요.")
        if content:
            token_length = count_tokens(content)
            if token_length > self.max_token:
                st.error(f"토큰의 개수가 {token_length} 입니다, 현재 {self.max_token} 토큰까지만 지원할 수 있습니다")
            else: 
                st.session_state['analysis_result'] = self.analyze_mlops_compatibility(content)
                is_passed = self.display_analysis() # 점수 통과 여부 

                header_content = """from pathlib import Path
 
import sys
# 현재 파일(d.py)의 부모 디렉토리를 기준으로 'src' 경로를 계산합니다.
src_path = Path(__file__).parent / 'src'
for root, dirs, files in os.walk(src_path):
    module_path = Path(root)
    if str(module_path) not in sys.path:
        sys.path.insert(0, str(module_path))
"""
                new_content = header_content + content
                if is_passed and is_single_file:
                    script_path = os.path.join(self.py_path, f"{title}.py")
                    with open(script_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                elif is_passed and not is_single_file:
                    script_path = os.path.join(self.py_path, f"main.py")
                    with open(script_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    # copy source_notebook/src --> source_py/src
                    shutil.copytree(os.path.join(self.download_path, 'src'), os.path.join(self.py_path, 'src'))
                                    
    def render(self):
        st.divider()
        st.subheader("Pre-condition: Check Code Quality")
        # 파일은 유지되나 페이지가 새로 렌더링 되는 경우 display만 호출
        analysis_result = st.session_state['analysis_result']
        if analysis_result and analysis_result['title'] == self.update_file:
            st.write(f"Checking notebook: {self.update_file}")
            with st.spinner('Wait for checking...'):
                self.display_analysis()
        # 파일 다운로드(변경) 시 check_jupyter 실행
        elif self.update_file:
            print(self.update_file)
            st.session_state['download_file'] = self.update_file
            st.write(f"Checking notebook: {self.update_file}")
            with st.spinner('Wait for checking...'):
                self.check_jupyter()
        else:
            st.error("다운로드된 소스 코드가 존재하지 않습니다. 소스 코드를 다운로드 혹은 업로드해주세요.")

def extract_zip_to_directory(zip_path, extract_to):
    if not os.path.exists(zip_path):
        print(f".zip 파일이 존재하지 않습니다: {zip_path}")
        return
    if not os.path.isdir(extract_to):
        print(f"추출할 디렉토리가 존재하지 않습니다: {extract_to}")
        os.makedirs(extract_to)
        print(f"디렉토리를 생성했습니다: {extract_to}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    print(f"{zip_path} 파일의 모든 내용을 {extract_to} 디렉토리에 추출했습니다.")
    os.remove(zip_path)
    print(f"{zip_path} 파일을 삭제합니다.")
    
def check_zip_contents(extracted_zip_path):
    items = os.listdir(extracted_zip_path)
    required_items = {'main.py', 'src'}
    if set(items) == required_items:
        print("[SUCCESS] 압축 파일 내에 'main.py' 파일과 'src' 폴더만 포함하고 있습니다.")
        return True
    else:
        print("f[FAIL] 압축 파일 내에 'main.py' 파일과 'src' 폴더만 포함 되어야 합니다. 현재 구성은 다음과 같습니다: \n {set(items)}")
        return False