# -*- coding: utf-8 -*-
import os
import subprocess
import shutil
import re
import argparse

class VenvController:
    def __init__(self, python_version, init_path): 
        self.py_ver = python_version
        self.init_path = init_path
        # ex. py310_venv 
        _ver_split = self.py_ver.split('.')
        # ex. py310_venv
        self.venv_path = os.path.join(init_path, 'py{}_venv'.format(_ver_split[0] + _ver_split[1]))

        
    def install_requirements(self, req_path):
        if os.path.exists(req_path):
            # req_tool_path 파일이 존재하는 경우
            try:
                result = subprocess.run([os.path.join(self.venv_path, 'bin', 'pip'), 'install', '-r', req_path],
                                        check=True,  
                                        capture_output=True,  
                                        text=True
                                        )
                print(result.stdout)
                print("----- Success requirements installation in venv -----")
            except subprocess.CalledProcessError as e:
                raise NotImplementedError(f"Failed to install requirements in venv: {e.stderr}")
        else:
            raise FileNotFoundError(f"File {req_path} does not exist")

    def install_python(self):
        # 현재 설치된 버전 목록 조회
        installed_versions = subprocess.check_output(['pyenv', 'versions', '--bare']).decode('utf-8').split()
        # 필요한 파이썬 버전이 이미 설치되어 있는지 확인
        if self.py_ver in installed_versions:
            print(f"Python {self.py_ver} already installed.")
        else:
            # pyenv를 사용하여 파이썬 설치
            try: 
                print(f"Installing Python {self.py_ver}...")
                subprocess.run(['pyenv', 'install', self.py_ver], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Failed to install python by pyenv: {e.stderr}")
        # 원한다면 특정 디렉토리의 로컬 파이썬 버전으로 설정
        subprocess.run(['pyenv', 'local', self.py_ver], check=True)
        print(f"Python {self.py_ver} 설치 및 설정 완료")

    def replace_version_in_path(self, path, new_version):
        """
        지정된 경로 문자열에서 버전을 바꿉니다.
        :param path: 버전을 변경할 경로 문자열
        :param new_version: 변경할 새로운 버전 문자열 (예: "3.8.0")
        :return: 버전이 변경된 새로운 경로 문자열
        """
        # 정규 표현식을 이용하여 버전 부분을 찾고 바꿉니다.
        new_path = re.sub(r"/\d+\.\d+\.\d+/bin/", f"/{new_version}/bin/", path)
        return new_path

    def create_venv(self, whether_create=True):
        venv_py = os.path.join(self.venv_path, 'bin', 'python')
        venv_pip = os.path.join(self.venv_path, 'bin', 'pip')
        if not whether_create: 
            print(f"Skip creating {self.venv_path}")
            pass
        else: 
            if os.path.exists(self.venv_path):
                print(f"{self.venv_path} already exists. Remove it.")
                shutil.rmtree(self.venv_path, ignore_errors=True)
            pyenv_python = subprocess.check_output(['pyenv', 'which', 'python', self.py_ver]).strip().decode('utf-8')
            user_py_path = self.replace_version_in_path(pyenv_python, self.py_ver)
            if os.name == 'nt':  # Windows
                user_py_path = self.replace_version_in_path(pyenv_python, self.py_ver)
                pip_path = user_py_path[:-9] + 'Scripts/pip' 
            else:  # macOS/Linux
                user_py_path = self.replace_version_in_path(pyenv_python, self.py_ver)
                pip_path = user_py_path[:-6] + '/pip'
            subprocess.run([pip_path, 'install', 'virtualenv'], check=True)
            subprocess.run([user_py_path, '-m', 'virtualenv', self.venv_path], check=True)
            print(f"{self.venv_path} virtualenv created")
            check_py_ver = subprocess.run([venv_py, '--version'], capture_output=True, text=True, check=True)
            print(f"{self.venv_path} python version: {check_py_ver.stdout.strip()}")
        return venv_py, venv_pip 


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--venv_python_version', type=str, help='it will be used python version ex) 3.10.2',  default='3.10.2')
    parser.add_argument('--requirements_path', type=str, help='path for requirements.txt',  default='requirements.txt')
    args = parser.parse_args()
    python_ver = args.venv_python_version
    req_path = args.requirements_path
    '''
    venv_ctrl = VenvController(python_version='3.10.2', init_path=os.path.abspath(__file__))
    venv_ctrl.install_python()
    venv_py, venv_pip = venv_ctrl.create_venv()
    venv_ctrl.install_requirements(req_path)
    '''