import re
import os
import sys
import subprocess
import shutil
import tiktoken
import numpy as np
import pandas as pd
from glob import glob

def compare_and_touch_req(req_old,req_new):

    lines_req_old = req_old.split('\n')
    lines_req_new = req_new.split('\n')

    lib_names_old = []
    lib_names_new = []

    lines_old_dict = {}
    lines_new_dict = {}

    for line_req_old in lines_req_old:

        if not line_req_old or line_req_old.startswith('#'):
            continue

        lib_name = re.split(r'[<>=!~]', line_req_old)[0].strip()
        if lib_name not in lib_names_old:
            lib_names_old.append(lib_name)
            lines_old_dict[lib_name] = line_req_old.strip()

    for line_req_new in lines_req_new:

        if not line_req_new or line_req_new.startswith('#'):
            continue

        lib_name = re.split(r'[<>=!~]', line_req_new)[0].strip()
        if lib_name not in lib_names_new:
            lib_names_new.append(lib_name)
            lines_new_dict[lib_name] = line_req_new.strip()


    new_req = []
    # # lib 추가, 제거 없는 경우
    if sorted(lib_names_old) == sorted(lib_names_new):
        for lib_name in lib_names_new:
            if lines_old_dict[lib_name] == lines_new_dict[lib_name]:
                new_req.append(lib_name)
            else:
                new_req.append(lines_new_dict[lib_name])
    else:
        for lib_name in lib_names_new:
            if lib_name not in lib_names_old:
                new_req.append(lib_name)
            else:
                new_req.append(lines_old_dict[lib_name])

    return '\n'.join(new_req)

def load_prompt(file_path,placeholder_lst=None):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except:
        raise Exception('failed loading md, path: {file_path}')

    # placeholders = re.findall(r'\{(.*?)\}', content
    return content

def file_to_str(file_path,read_type='str'):

        if read_type not in ['str','lst']:
            raise Exception(
                '----- [INFO] VAR : "read_type" muust be "str" or "lst" '
            )
        try:
            with open(file_path,'r') as F:

                if read_type == 'str':

                    txt_str = F.read()
                    return txt_str
                else:

                    txt_lst = F.readlines()
                    return txt_lst
        except:
            print(f'failed loading {file_path}')

def analyze_csv(file_path):
    # CSV 파일을 읽어들임
    df = pd.read_csv(file_path)

    # 0) 데이터프레임의 크기
    dataframe_shape = df.shape

    # 1) 컬럼 명들
    column_names = df.columns.tolist()

    # 2) 각 컬럼의 타입 분석
    column_types = {}
    for column in df.columns:
        unique_values = df[column].dropna().unique()
        if all(isinstance(val, (int, float, np.number)) for val in unique_values):
            column_types[column] = 'Numerical'
        elif all(isinstance(val, str) for val in unique_values):
            column_types[column] = 'Categorical'
        elif any(isinstance(val, (int, float, np.number)) for val in unique_values) and any(isinstance(val, str) for val in unique_values):
            column_types[column] = 'Mixed'
        elif df[column].dtype == object and any(isinstance(val, (int, float, np.number)) for val in unique_values):
            column_types[column] = 'column contains numerical value and categorical value.'
        else:
            column_types[column] = 'Unknown'

    # 3) 각 컬럼마다 NaN과 같이 AI 모델의 input이 될 수 없는 값들이 존재하는지 확인
    column_invalid_values = {}
    for column in df.columns:
        has_nan = df[column].isna().any()
        column_invalid_values[column] = {'NaN': has_nan}

    # 4) 각 컬럼의 카디널리티 계산
    column_cardinality = {}
    for column in df.columns:
        cardinality = df[column].nunique()
        column_cardinality[column] = cardinality

    # 분석 결과를 반환
    analysis_result = {
        'DataFrame Shape': dataframe_shape,
        'Column Names': column_names,
        'Column Types': column_types,
        'Invalid Values': column_invalid_values,
        'Cardinality': column_cardinality
    }

    analysis_result_core = [
        f'shape of raw data is : {analysis_result["DataFrame Shape"]}',
        f'columns of dataframe is : {df.columns}'
    ]

    # for column in df.columns:

    #     analysis_result_core.append(f'# value type of column(categorical or numerical) : {column} is {analysis_result["Column Types"][column]}')
    #     analysis_result_core.append(f'# value type of column(categorical or numerical) : {column} is {analysis_result["Column Types"][column]}')
    #     analysis_result_core.append(f'# NAN value is in column {column} : {analysis_result["Invalid Values"][column]["NaN"]}')
    #     analysis_result_core.append(f'# cardinality of column {column} : {analysis_result["Cardinality"][column]}')
    
    return analysis_result_core

def get_chunk_with_token_limit(text, token_limit):
        # Initialize the tokenizer
        tokenizer = tiktoken.encoding_for_model("gpt-4o")

        # Tokenize the input text
        tokens = tokenizer.encode(text)

        # Check if the number of tokens exceeds the limit
        if len(tokens) > token_limit:
            # Get the chunk from the end that is within the token limit
            chunk = tokens[-token_limit:]
        else:
            # If the number of tokens is within the limit, return the entire text
            chunk = tokens

        # Decode the token chunk back to text
        text_chunk = tokenizer.decode(chunk)

        return text_chunk

def make_py_pattern( py_name, model_resp):
    match = '' 
    match = re.search(r'```python\s*# {}(.*?)```'.format(py_name), model_resp, re.DOTALL) 
    if match is None:
        match = re.search(r'```Python\s*# {}(.*?)```'.format(py_name), model_resp, re.DOTALL) 
    if match is None:
        match = re.search(r'### {}\s*```python(.*?)```'.format(py_name), model_resp, re.DOTALL) 
    if match is None: 
        match = re.search(r'```python\s*### {}(.*?)```'.format(py_name), model_resp, re.DOTALL)
    if match is None: 
        raise ValueError(f"----- [ERROR] FAILED TO MAKE MATCH FOR {py_name}: \n{model_resp}")
    else: 
        return match 

def with_structured_output_python(model_response: str):
    
    match = '' 
    match = re.search(r'```python\s*(.*?)```', model_response, re.DOTALL) 
    if match is None:
        match = re.search(r'```Python\s*# (.*?)```', model_response, re.DOTALL) 
    if match is None:
        match = re.search(r'### \s*```python(.*?)```', model_response, re.DOTALL) 
    if match is None: 
        match = re.search(r'```python\s*### (.*?)```', model_response, re.DOTALL)
    if match is None: 
        match = re.search(r'```python\s*### (.*?)```', model_response, re.DOTALL)
    if match is None: 
        match = re.search(r'```python\s(.*?)```', model_response, re.DOTALL)
    if match is None: 
        match = re.search(r'```Python\s(.*?)```', model_response, re.DOTALL)
    if match is None: 
        raise ValueError(f"----- [ERROR] FAILED TO MAKE MATCH FOR PYTHON FILE")

    code_block = match.group(1).strip() if match else "" 
    
    return code_block

def with_structured_output_req(model_response: str):

    match = re.search(
        r'```requirements(.*?)```',
        model_response,
        re.DOTALL
    )
    if match is None:
        match = re.search(
            r'```\srequirements(.*?)```',
            model_response,
            re.DOTALL
        )

    if match is None:
        match = re.search(
            r'``` \srequirements(.*?)```',
            model_response,
            re.DOTALL
        )

    if match is None:
        match = re.search(
            r'```\s requirements(.*?)```',
            model_response,
            re.DOTALL
        )

    requirements_block = match.group(1).strip()

    return requirements_block 
    
def with_structured_output_json(model_response: str):
    match = ''
    match = re.search(
        r'```json(.*?)```',
        model_response,
        re.DOTALL
    )
    if match is None:
        match = re.search(
            r'```\sjson(.*?)```',
            model_response,
            re.DOTALL
        )

    json_block = match.group(1).strip()
    return json_block

def with_structured_output_md(model_response: str):
    match = ''
    match = re.search(
        r'```markdown(.*?)```',
        model_response,
        re.DOTALL
    )
    if match is None:
        match = re.search(
            r'```\smarkdown(.*?)```',
            model_response,
            re.DOTALL
        )

    md_block = match.group(1).strip()
    return md_block


def find_py_files(directory):
    # find .py file recursively
    return glob.glob(os.path.join(directory, '**', '*.py'), recursive=True)

def find_req_files(directory):
    # find .py file recursively
    return glob.glob(os.path.join(directory, '**', 'requirements.txt'), recursive=True)

def find_files_all(directory):
    return glob.glob(os.path.join(directory, '**', '*.*'), recursive=True)
 
def run_py(venv_python, py_file):
    try:
        result = subprocess.run([venv_python, py_file],
                    check=True,  
                    capture_output=True,  
                    text=True
                   )
        # print(result.stdout)

        return 'no', 'no'
    except subprocess.CalledProcessError as e:
        
        return e.stdout, e.stderr

def create_and_use_venv(
        code_solution,
        requirements,
        error_type,
        src_path_interface= './interface',
        venv_dir='./interface/py310_venv',
        python_executable='python3.10',
):
    
    if os.path.exists(venv_dir):
        pass
    else:
        subprocess.run([python_executable, '-m', 'venv', venv_dir])
        print(f"{venv_dir} created with {python_executable}")
        
        if os.path.exists(src_path_interface):
            shutil.copytree(
                src_path_interface,
                os.path.join(venv_dir,'src') 
            )
            print('----- [INFO] COPYING SRC FOLDER INTO VENV DIRECTORY COMPLETE')
        else:
            pass
            
            
    with open(os.path.join(venv_dir,'tmp.py'),'w' ) as F:
        F.write(code_solution)

        # print('-========================================================================')
        # print('next code will be executed')
        # print(code_solution)
        # print('-========================================================================')
        print(f'----- [INFO] SAVING CODE INTO PATH : {venv_dir} COMPLETE!')

    # install requirements.txt
    if os.name == 'nt':  # Windows
        pip_path = os.path.join(venv_dir, 'Scripts', 'pip')
        venv_python = os.path.join(venv_dir, 'Scripts', 'python')
    else:  # macOS/Linux
        pip_path = os.path.join(venv_dir, 'bin', 'pip')
        venv_python = os.path.join(venv_dir, 'bin', 'python')
    
    if error_type in ['type_1','type_2','type_4']:
        pass
    else:
        install_req_msg = do_pip_tools(
            requirements=requirements,
            venv_dir=venv_dir,
            python_executable=python_executable
        )
    msg_stdout, msg_stderr = run_py(
        venv_python,
        os.path.join(venv_dir,'tmp.py')
    )
    
    # del venv
    # shutil.rmtree(venv_dir)
    # print(f"venv {venv_dir} is deleted")

    return msg_stdout, msg_stderr

def remove_sub_lib(req_in_lines,req_txt_lines):
    '''
    requirements.txt에는 라이브러리와 #으로 시작하는 주석만 있다고 가정
    '''
    new_req = []

    for line_req_in in req_in_lines:

        if not line_req_in or line_req_in.startswith('#'):
            continue

        lib_name = re.split(r'[<>=!~]', line_req_in)[0].strip()

        for line_req_txt in req_txt_lines:

            if not line_req_txt or line_req_txt.startswith('#'):
                continue

            if lib_name in line_req_txt and line_req_txt not in new_req:
                new_req.append(line_req_txt)

    return '\n'.join(new_req)

def do_pip_tools(requirements,venv_dir='./interface/py310_venv', python_executable='python3.10'):

    # if os.path.exists(venv_dir):
    #     shutil.rmtree(venv_dir)
    #     print(f"venv {venv_dir} is deleted")
    if os.path.exists(venv_dir):
        pass
    else:
        try:
            subprocess.run(
                [
                    python_executable,
                    '-m',
                    'venv',
                    venv_dir
                ]
            )
            print(f"----- [INFO] {venv_dir} CREATED WITH PYTHON VERSION :  {python_executable}")
        except subprocess.CalledProcessError as e:
            print("----- [INFO] ERROR DURING CREWATING VENV:\n", e.stderr)

    if os.name == 'nt':  # Windows
        pip_path = os.path.join(venv_dir, 'Scripts', 'pip')
        venv_python = os.path.join(venv_dir, 'Scripts', 'python')
    else:  # macOS/Linux
        pip_path = os.path.join(venv_dir, 'bin', 'pip')
        venv_python = os.path.join(venv_dir, 'bin', 'python')
    
    req_in_path = os.path.join(
        venv_dir,
        'requirements.in'
    )
    req_txt_path = os.path.join(
        venv_dir,
        'requirements.txt'
    )

    with open(req_in_path,'w') as F:
        F.write(requirements)

    try:
        result = subprocess.run(
            [
                pip_path,
                'install', 
                'pip-tools'
            ],
            check=True,
            capture_output=True,
            text=True
        )
        # print("installing pip-tools output:\n", result.stdout)
    
    except subprocess.CalledProcessError as e:
        raise Exception("Error during installing pip-tools output:\n", e.stderr)
        
    try:
        result = subprocess.run(
            [
                venv_python,
                '-m', 
                'piptools', 
                'compile',
                req_in_path, 
                '-o',
                req_txt_path,
                '--no-annotate',
                '--no-header'
            ],
            check=True,
            capture_output=True,
            text=True
        )
        # print("pip-compile output:\n", result.stdout)
    
    except subprocess.CalledProcessError as e:
        raise Exception("Error during pip-compile:\n", e.stderr)
    
    try:
        result = subprocess.run(
            [
                venv_python,
                '-m', 
                'piptools', 
                'sync', 
                req_txt_path
            ],
            check=True,
            capture_output=True,
            text=True
        )
        # print("pip-sync output:\n", result.stdout)
    except subprocess.CalledProcessError as e:
        raise Exception("Error during pip-sync:\n",f'{e}')
        # print("Error during pip-sync:\n", e.stderr)


    with open(req_txt_path,'r') as F:
        return_req = F.read()

        return return_req
    

