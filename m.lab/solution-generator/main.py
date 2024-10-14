import json
import os
import yaml
import socket
import streamlit as st
from streamlit_option_menu import option_menu
from kaggle.api.kaggle_api_extended import KaggleApi
from pathlib import Path
from dotenv import load_dotenv, set_key

from engine.alo_funcs import clone_repository_from_config, add_to_sys_path, check_and_copy, initialize_key_files
from path_list import *
import logging
logging.getLogger('streamlit.runtime.scriptrunner_utils.script_run_context').setLevel(logging.ERROR)
current_dir = os.path.dirname(os.path.abspath(__file__))

os.environ["GIT_PYTHON_REFRESH"] = "quiet"
# ALOApp 클래스 정의
class ALOApp:
    def __init__(self, host_ip):
        # from alo_engine.src.alo import ALO
        # alo = ALO()

        path_to_append1 = os.path.join(current_dir, 'engine/alo_engine')
        path_to_append2 = os.path.join(current_dir, 'engine/alo_engine/src')
        add_to_sys_path(path_to_append1)
        add_to_sys_path(path_to_append2)

        os.chdir(current_dir)

        self.config_path = os.path.join(current_dir, 'engine/alo_engine/setting/infra_config.yaml')

        self.api = self.initialize_kaggle_api()

        self.host_ip = host_ip

        self.path = {
            'source_notebook': os.path.join(current_dir, 'interface/source_notebook/'),
            'source_py': os.path.join(current_dir, 'interface/source_py/'),
            'data': os.path.join(current_dir, 'interface/data/'),
            'metadata': os.path.join(current_dir, 'interface/metadata/'),
            'prompt': os.path.join(current_dir, 'ui/src/chat_prompts/'),
            'data_metadata': os.path.join(current_dir, 'interface/data_metadata/')
            # 'result': './result',
        }
        self.make_interface_dir()

        # 경로 때문에 add_to_sys_path 다음에 import 되어야 함
        from ui.components import GetAISource, ConvertCode, CreateSolution, PublishSolution   
        self.pages = {
            "Get AI Source": GetAISource(self.api, self.path),
            "Adapt AI Source for Dataset": ConvertCode(self.api, self.path),
            'Create AI solution': CreateSolution(self.path),
            "Publish AI solution": PublishSolution(self.path),
            "Settings": None,
        }

        self.initialize_session_state()

    def make_interface_dir(self):
        """interface(input) 디렉토리 생성"""
        # TODO: results는?
        if not os.path.exists(self.path['source_notebook']):
            os.makedirs(self.path['source_notebook'])
        # if not os.path.exists(self.path['data']):
        #     os.makedirs(self.path['data'])

    def initialize_session_state(self):
        """Session State 초기화"""
        session_defaults = {
            "show_settings": False,
            "show_keys": False,
            "settings_data": self.read_config()
        }
        for key, value in session_defaults.items():
            st.session_state[key] = value

    def initialize_kaggle_api(self):
        try:
            api = KaggleApi()
            api.authenticate()
            return api
        except Exception as e:
            st.error(f"Failed to authenticate Kaggle API: {e}")
            return None

    def read_config(self):
        try:
            with open(self.config_path, 'r') as file:
                config = yaml.safe_load(file)
        except FileNotFoundError:
            config = {}

        default_config = {
            'AIC_URI': "https://aicond.meerkat-ai.com/",
            "REGION": "ap-northeast-2",
            "WORKSPACE_NAME": "meerkat-ws",
            "BUILD_METHOD": "codebuild",
            "LOGIN_MODE": "static",
            "VERSION": 1.1,
            "REPOSITORY_TAGS": ["Key=Owner,Value=Meerkat"],
            "AWS_KEY_PROFILE": "alo-aws-profile",
            "CODEBUILD_ENV_TYPE": "LINUX_CONTAINER",
            "CODEBUILD_ENV_COMPUTE_TYPE": "BUILD_GENERAL1_SMALL"
        }

        # 설정 파일 내용을 기본 설정에 덮어쓰기
        default_config.update(config or {})
        return default_config

    def write_config(self, config):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as file:
                yaml.safe_dump(config, file)
            st.success("Settings saved successfully.")
        except Exception as e:
            st.error(f"Failed to save the settings: {e}")

    def run_sidebar(self):
        st.sidebar.image("ui/icons/mellerilab.png", width=170)
        st.sidebar.markdown("---")
        st.sidebar.markdown("""<div style='text-align: left; font-size: 25px; font-weight: bold; color: #d1e4e4 ; padding-left: 20px;'>Action Steps:</div>""", unsafe_allow_html=True)

        with st.sidebar:
            self.option = option_menu(
                menu_title=None,
                options=["Get AI Source", "Adapt AI Source for Dataset","Create AI solution", "Publish AI solution"],
                icons=["1-square", "2-square", "3-square", "4-square"],
                menu_icon="cast",
                default_index=0,
            )

        with st.sidebar:
            if st.button("Upload Settings", key="settings_button"):
                st.session_state["show_settings"] = True
                st.session_state["show_keys"] = False
            if st.button("Upload Keys", key="settings_keys"):
                st.session_state["show_settings"] = False
                st.session_state["show_keys"] = True

        # Jupyter Lab과 VSCode 버튼 추가
        st.sidebar.markdown("---")
        jupyter_port = os.environ.get('JUPYTER_PORT')
        vscode_port = os.environ.get('VSCODE_PORT')

        # jupyter_url = f"http://{self.host_ip}:8888"
        vscode_url = f"http://{self.host_ip}:{vscode_port}"

        if 'clicked' not in st.session_state:
            st.session_state.clicked = False

        # if st.sidebar.button("Open Jupyter Lab"):
        #     js_open_window(jupyter_url)
        #     st.rerun()
        if st.sidebar.button("Open VSCode"):
            st.session_state.clicked = not st.session_state.clicked
            # js_open_window(vscode_url)

        if st.session_state.clicked:
            js_open_window(vscode_url)
            st.session_state.clicked = False

        if st.session_state["show_settings"]:
            self.option = "Settings"

        if st.session_state["show_keys"]:
            self.option = "Keys"

    def render_keys(self):
        st.title("Keys")

        # OPENAI 키 입력 UI 설정
        st.subheader("OpenAI Keys")
        dotenv_path = os.path.join(current_dir, 'engine', '.env')

        # `./engine/.env` 파일에서 설정 값 로드
        load_dotenv(dotenv_path)

        # 기본 설정 값을 UI에 표시
        openai_api_type = os.getenv("OPENAI_API_TYPE", "azure")
        azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        openai_api_version = os.getenv("OPENAI_API_VERSION", "")
        openai_modedl_id = os.getenv("OPENAI_MODEL_ID", "")

        openai_settings_data = {
            "OPENAI_API_TYPE": st.text_input("OPENAI_API_TYPE", openai_api_type, help="Type of OpenAI API."),
            "AZURE_OPENAI_API_KEY": st.text_input("AZURE_OPENAI_API_KEY", azure_openai_api_key, type="password", help="Azure OpenAI API Key."),
            "AZURE_OPENAI_ENDPOINT": st.text_input("AZURE_OPENAI_ENDPOINT", azure_openai_endpoint, help="Azure OpenAI Endpoint."),
            "OPENAI_API_VERSION": st.text_input("OPENAI_API_VERSION", openai_api_version, help="Version of OpenAI API."),
            "OPENAI_MODEL_ID": st.text_input("OPENAI_MODEL_ID", openai_modedl_id, help="OPENAI MODEL ID.")
        }

        # KAGGLE 키 입력 UI 설정
        st.subheader("Kaggle Keys")
        kaggle_json_path = Path.home() / ".kaggle" / "kaggle.json"

        if kaggle_json_path.exists():
            with open(kaggle_json_path, 'r') as f:
                kaggle_keys = json.load(f)
        else:
            kaggle_keys = {"username": "", "key": ""}

        kaggle_username = st.text_input("Kaggle Username", kaggle_keys["username"], help="Kaggle Account Username")
        kaggle_key = st.text_input("Kaggle API Key", kaggle_keys["key"], type="password", help="Kaggle API Key")

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Save", use_container_width=True):
                try:
                    # `.env` 파일에 OPENAI 설정 값 덮어쓰기 및 os.environ 업데이트
                    for key, value in openai_settings_data.items():
                        set_key(dotenv_path, key, value)
                        os.environ[key] = value

                    # `kaggle.json` 파일에 KAGGLE 설정 값 저장
                    kaggle_keys["username"] = kaggle_username
                    kaggle_keys["key"] = kaggle_key

                    kaggle_json_path.parent.mkdir(parents=True, exist_ok=True)

                    with open(kaggle_json_path, 'w') as f:
                        json.dump(kaggle_keys, f)

                    st.success("Keys saved successfully.")
                except Exception as e:
                    st.error(f"Failed to save the keys: {e}")
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state["show_keys"] = False
                st.rerun()            

    def render_settings(self):
        st.title("Settings")

        # settings_data 초기화
        settings_data = st.session_state["settings_data"]

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Save", use_container_width=True):
                self.write_config(settings_data)
                st.session_state["show_settings"] = False
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state["show_settings"] = False
                st.rerun()

        settings_data['AIC_URI'] = st.text_input('AIC_URI', settings_data.get('AIC_URI'), help="Web server address of AI Conductor.")
        settings_data['REGION'] = st.text_input('REGION', settings_data.get('REGION'), help="AWS Cloud region.")
        settings_data['WORKSPACE_NAME'] = st.text_input('WORKSPACE_NAME', settings_data.get('WORKSPACE_NAME'), help="Workspace assigned by AI Conductor.")
        settings_data['BUILD_METHOD'] = st.selectbox('BUILD_METHOD', ["docker", "buildah", "codebuild"], 
                                                     index=["docker", "buildah", "codebuild"].index(settings_data.get('BUILD_METHOD', "codebuild")), 
                                                     help="Choose one among docker, buildah, and codebuild depending on the development environment.")
        settings_data['LOGIN_MODE'] = st.text_input('LOGIN_MODE', settings_data.get('LOGIN_MODE'), help="AI Conductor login method.")
        settings_data['VERSION'] = st.number_input('VERSION', value=settings_data.get('VERSION'), step=0.1, help="Version of the Solution Metadata.")
        settings_data['AWS_KEY_PROFILE'] = st.text_input('AWS_KEY_PROFILE', settings_data.get('AWS_KEY_PROFILE'), help="The name of the AWS configure profile.")
        settings_data['CODEBUILD_ENV_TYPE'] = st.selectbox('CODEBUILD_ENV_TYPE', ["LINUX_CONTAINER", "WINDOWS_CONTAINER", "LINUX_GPU_CONTAINER", "ARM_CONTAINER", "WINDOWS_SERVER_2019_CONTAINER", "LINUX_LAMBDA_CONTAINER", "ARM_LAMBDA_CONTAINER"],
                                                           index=["LINUX_CONTAINER", "WINDOWS_CONTAINER", "LINUX_GPU_CONTAINER", "ARM_CONTAINER", "WINDOWS_SERVER_2019_CONTAINER", "LINUX_LAMBDA_CONTAINER", "ARM_LAMBDA_CONTAINER"].index(settings_data.get('CODEBUILD_ENV_TYPE', "LINUX_CONTAINER")),
                                                           help="The build environment type used by AWS Codebuild when BUILD_METHOD=codebuild.")
        settings_data['CODEBUILD_ENV_COMPUTE_TYPE'] = st.selectbox('CODEBUILD_ENV_COMPUTE_TYPE', ["BUILD_GENERAL1_SMALL", "BUILD_GENERAL1_MEDIUM", "BUILD_GENERAL1_LARGE", "BUILD_GENERAL1_XLARGE", "BUILD_GENERAL1_2XLARGE", "BUILD_LAMBDA_1GB", "BUILD_LAMBDA_2GB", "BUILD_LAMBDA_4GB", "BUILD_LAMBDA_8GB", "BUILD_LAMBDA_10GB"],
                                                                   index=["BUILD_GENERAL1_SMALL", "BUILD_GENERAL1_MEDIUM", "BUILD_GENERAL1_LARGE", "BUILD_GENERAL1_XLARGE", "BUILD_GENERAL1_2XLARGE", "BUILD_LAMBDA_1GB", "BUILD_LAMBDA_2GB", "BUILD_LAMBDA_4GB", "BUILD_LAMBDA_8GB", "BUILD_LAMBDA_10GB"].index(settings_data.get('CODEBUILD_ENV_COMPUTE_TYPE', "BUILD_GENERAL1_SMALL")),
                                                                   help="The compute type of the environment where containers are built by AWS Codebuild when BUILD_METHOD=codebuild.")
        repository_tags_str = st.text_input('REPOSITORY_TAGS', ','.join(settings_data.get('REPOSITORY_TAGS', [])), help="Tags values to be entered when creating an ECR repository.")
        settings_data['REPOSITORY_TAGS'] = [','.join(tag.strip() for tag in repository_tags_str.split(','))]

        st.session_state["settings_data"] = settings_data   # 업데이트

    def render_page(self):
        if self.option == "Settings":
            self.render_settings()
        elif self.option == "Keys":
            self.render_keys()
        else:
            self.pages[self.option].render()

    def run(self):
        self.run_sidebar()
        self.render_page()

# JavaScript function to open URL in a new tab
def js_open_window(url):

    js = f"""
        <script>
            window.open("{url}", "_blank").focus();
        </script>
    """
    st.components.v1.html(js, height=0)

if __name__ == "__main__":
    # ALO 설치
    if not os.path.exists(os.path.join(current_dir + '/engine/alo_engine/.git')):
        clone_repository_from_config()

    ## alo smaple experimental_plan.yaml 에서 필요로 하는 환경변수 선언
    check_and_copy()

    ## .kaggle, .envs 가 없을 경우 빈 파일 생성 
    initialize_key_files()

    st.set_page_config(
        page_title="mellerilab",
        page_icon="ui/icons/favicon.png",
    )

    def get_external_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Google DNS 서버 사용
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
        except Exception:
            ip_address = "Unable to get IP Address"
        finally:
            s.close()
        return ip_address

    host_ip = os.environ.get('HOST_IP')
    if host_ip is None:
        host_ip = get_external_ip()

    
    if 'host_ip_printed' not in st.session_state:
        jupyter_port = os.environ.get('JUPYTER_PORT')
        vscode_port = os.environ.get('VSCODE_PORT')
        streamlit_port = os.environ.get('STREAMLIT_PORT')
        st.session_state['host_ip_printed'] = True  # 세션 상태를 통해 중복 출력 방지
        print(f"##########################{host_ip}###############################")

        # Streamlit 앱에서 IP와 포트를 강렬한 메시지로 출력
    # ALOApp 인스턴스를 세션 상태에 저장
    if 'app' not in st.session_state:
        st.session_state['app'] = ALOApp(host_ip)

    app = st.session_state['app']
    app.run()