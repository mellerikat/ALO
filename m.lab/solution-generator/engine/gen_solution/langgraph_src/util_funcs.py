# -*- coding: utf-8 -*-
import os 
import re
import logging
import json
import pandas as pd 
import yaml 
from collections import OrderedDict
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pytz import timezone
from .path_list import * 

class OrderedLoader(yaml.Loader):
    pass

class OrderedDumper(yaml.Dumper):
    pass

def construct_mapping(loader, node):
    '''Construct an OrderedDict from YAML
    '''
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))

def represent_odict(dumper, data):
    '''Represent an OrderedDict in YAML
    '''
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
OrderedDumper.add_representer(OrderedDict, represent_odict)

def load_yml(path: str):
    with open(path, encoding='UTF-8') as file:
        return yaml.load(file, Loader=get_loader())
    
def load_markdown(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    return content

def find_variables(md_content):
    pattern = r'\{(\w+)\}'  # find {variable_name} pattern 
    variables = re.findall(pattern, md_content)
    return variables

def replace_variables(md_content, variable_dict):
    for var_name, var_value in variable_dict.items():
        md_content = re.sub(rf'\{{{var_name}\}}', str(var_value), md_content)
    return md_content

def load_and_replace_yaml(yaml_path, variables):
    with open(yaml_path, 'r') as file:
        yaml_content = file.read()
    for key, value in variables.items():
        yaml_content = re.sub(r'\$\{' + key + r'\}', value, yaml_content)
    config = yaml.safe_load(yaml_content)
    return config

def read_yaml(yaml_file): 
    with open(yaml_file, 'r', encoding='utf-8') as f: 
        return yaml.load(f, Loader=OrderedLoader)
    
def save_yaml(yaml_file, yaml_contents): 
    with open(yaml_file, 'w', encoding='utf-8') as f: 
        yaml.dump(yaml_contents, f, Dumper=OrderedDumper, default_flow_style=False, sort_keys=False, allow_unicode=True) 
    print(f"----- {yaml_file} saved.")
    
def read_python_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
        return file_content
    except FileNotFoundError:
        raise FileNotFoundError(f"{file_path} not found.")
    except Exception as e:
        raise NotImplementedError(f"{file_path} read error. \n {e}")

# def read_txt_file(file_path):
#     try:
#         with open(file_path, 'r', encoding='utf-8') as file:
#             file_content = file.read()
#             return file_content
#     except FileNotFoundError:
#         raise FileNotFoundError(f"txt file not found: {file_path}")
#     except IOError as e:
#         raise IOError(f"file read error: {e}")
 
def read_requirements_to_list(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            # # 주석이 아니고 빈 줄이 아닌 경우에만 패키지에 추가
            # # space로 시작하는 # 이면 필터링하는 코드 = strip() 
            requirements = [line.strip() for line in file if (line.strip() and not line.strip().startswith('#'))]
            return requirements
    except FileNotFoundError:
        raise FileNotFoundError(f"txt file not found: {file_path}")
    except IOError as e:
        raise IOError(f"file read error: {e}")
    
def generate_directory_structure(startpath, max_show_len=5):
    structure = []
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * level
        structure.append(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 4 * (level + 1) 
        if len(files) < max_show_len:
            for f in files:
                structure.append(f"{subindent}{f}")
        else: 
            for f in files[:max_show_len]:
                structure.append(f"{subindent}{f}")
    return '\n'.join(structure)

def format_string(string): 
    string = '-'*150 + '\n' + '\t'*7 + f'{string}\n' + '-'*150  
    return string 

def save_code_to_file(file_path, code_string):
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(code_string)
        print(f"----- {file_path} saved.")
    except Exception as e:
        print(f"----- {file_path} save failed. \n {str(e)}")

def init_pipelines():
    # os.makedirs(SOLUTION_PATH, exist_ok=True) 
    if os.path.isfile(EXPERIMENTAL_PLAN_PATH):
        os.remove(EXPERIMENTAL_PLAN_PATH) 
        print(f"----- {EXPERIMENTAL_PLAN_PATH} removed")
    if os.path.isfile(PIPELINE_PATH):
        os.remove(PIPELINE_PATH) 
        print(f"----- {PIPELINE_PATH} removed")
        
def save_generated_codes(experimental_plan, pipeline_code): 
    save_yaml(EXPERIMENTAL_PLAN_PATH, json.loads(experimental_plan))
    save_code_to_file(PIPELINE_PATH, pipeline_code) 

def ymd(f='%Y%m%d', tz=None, **kwargs):
    if tz:
        tz = timezone(tz)
    date = datetime.now(tz) if 'datetime' not in kwargs else kwargs['datetime']
    if kwargs:
        date = date + relativedelta(**{date_delta_key[k]: v for k, v in kwargs.items() if k in date_delta_key})
    return date.strftime(f)

def env_constructor(loader, node):
    """!Env tag"""
    value = str(loader.construct_scalar(node))  # get the string value next to !Env
    match = re.compile(".*?\\${(\\w+)}.*?").findall(value)
    if match:
        for key in match:
            if not os.environ.get(key):
                raise ValueError(f"Unable to find the {key} item set in the OS environment variables.\n"
                                 f"Please define the {key} environment variable when running the application.")
            value = value.replace(f'${{{key}}}', os.environ[key])
        return value
    return value

def python_constructor(loader, node):
    """!Python tag"""
    value = str(loader.construct_scalar(node))  # get the string value next to !Env
    return eval(value)

def get_loader():
    """Get custom loaders."""
    loader = yaml.SafeLoader  # yaml.FullLoader
    loader.add_constructor("!Env", env_constructor)
    loader.add_constructor("!Python", python_constructor)
    return loader