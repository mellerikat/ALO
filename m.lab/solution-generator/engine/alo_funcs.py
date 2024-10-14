import json
from pathlib import Path
import git
import os
import sys
import shutil
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__)) + "/"

def read_git_address(file_path):
    """
    .git_address 파일에서 저장소 URL과 브랜치를 읽어오는 함수

    :param file_path: .git_address 파일의 경로
    :return: 저장소 URL과 브랜치
    """
    url = None
    branch = None

    with open(file_path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            if line.startswith('url:'):
                url = line.split('url:')[1].strip()
            elif line.startswith('branch:'):
                branch = line.split('branch:')[1].strip()

    return url, branch

def git_clone(repository_url, clone_directory, branch=None):
    """
    Git 저장소를 클론하는 함수

    :param repository_url: 복제할 Git 저장소의 URL
    :param clone_directory: 저장소를 복제할 디렉터리 경로
    :param branch: 복제할 브랜치 (없으면 기본 브랜치 사용)
    """
    try:
        if branch:
            # branch 옵션이 있는 경우
            git.Repo.clone_from(repository_url, current_dir + clone_directory, branch=branch)
        else:
            # 기본 브랜치 사용
            git.Repo.clone_from(repository_url, current_dir + clone_directory)

        print(f"Successfully cloned {repository_url}")

    except git.exc.GitCommandError as e:
        print(f"An error occurred while trying to clone the repository: {e}")

# .env 및 kaggle.json 파일이 없으면 빈 파일을 생성하는 함수
def initialize_key_files():
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), 'engine', '.env') ## 위치만 변경
    kaggle_json_path = Path.home() / ".kaggle" / "kaggle.json"

    ## .envs 없으면 생성되는 내용
    if not os.path.exists(dotenv_path):
        os.makedirs(os.path.dirname(dotenv_path), exist_ok=True)
        with open(dotenv_path, 'w') as f:
            f.write("OPENAI_API_TYPE=''\n"
                    "AZURE_OPENAI_API_KEY=''\n"
                    "AZURE_OPENAI_ENDPOINT=''\n"
                    "OPENAI_API_VERSION=''\n"
                    "OPENAI_MODEL_ID=''\n"
                    )
        print(f"Created new .env file at {dotenv_path}")

    ## .kaggle 없으면 생성되는 내용
    if not kaggle_json_path.exists():
        kaggle_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(kaggle_json_path, 'w') as f:
            json.dump({"username": "", "key": ""}, f)
        print(f"Created new kaggle.json file at {kaggle_json_path}")

def check_and_copy():
    ## data_path 를 환경변수로 선언
    specific_path = 'alo_engine/alo/test/'
    current_directory = os.getcwd()
    combined_path = os.path.join(current_directory, specific_path)
    os.environ['SOLUTION_DATA_PATH'] = combined_path
    os.environ['SOLUTION_ARTIFACT_PATH'] = combined_path

def clone_repository_from_config():
    """
    .git_address 파일에서 URL과 브랜치를 읽고 지정된 디렉터리에 Git 저장소를 클론하는 함수
    """
    git_address_file = ".git_address"  # .git_address 파일 경로
    clone_directory = "alo_engine"  # 복제할 디렉터리 경로

    # .git_address 파일에서 URL과 브랜치를 읽어옴
    repository_url, branch = read_git_address(current_dir + git_address_file)

    if repository_url:
        # clone_directory 디렉터리가 존재하는 경우 삭제
        if os.path.exists(clone_directory):
            shutil.rmtree(clone_directory)
            print(f"Directory {clone_directory} already existed and was removed.")

        # Git 저장소 클론
        git_clone(repository_url, clone_directory, branch)
        install_requirements_once(current_dir + clone_directory)
        print(f"Cloned repository from {repository_url} into {clone_directory}.")
    else:
        print("The repository URL was not found in the .git_address file.")


def add_to_sys_path(path):
    if path not in sys.path:
        sys.path.append(path)

def install_requirements(folder_path):
    # requirements.txt 경로 설정
    requirements_path = os.path.join(folder_path, 'requirements.txt')

    # requirements.txt 파일이 있는지 확인
    if os.path.isfile(requirements_path):
        try:
            # pip로 requirements.txt 파일에 명시된 패키지를 설치
            subprocess.check_call(['pip', 'install', '-r', requirements_path])
            print(f'Successfully installed packages from {requirements_path}')
        except subprocess.CalledProcessError as e:
            print(f'Error occurred while installing packages: {e}')
    else:
        print(f'{requirements_path} does not exist.')

def install_requirements_once(folder_path):
    # 설치 완료 여부를 기록할 파일 경로 설정
    marker_file = os.path.join(folder_path, 'requirements_installed')

    # 설치 완료 파일이 존재하지 않으면, 설치 수행
    if not os.path.isfile(marker_file):
        install_requirements(folder_path)
        # 설치 완료 파일 생성
        with open(marker_file, 'w') as file:
            file.write('Requirements installed.')
    else:
        print('Requirements already installed.')