# -*- coding: utf-8 -*-

import os
import subprocess
import shutil
import re
import psutil

def check_performance(config, stepname, runtime):
    """ Descr

    """
    print(f'[SYSTEM] {stepname} asset -> run time : {runtime:.2f} sec')

    if 'runtime' not in config:
        config['runtime'] = {f"{stepname}": runtime}
    else:
        config["runtime"][f"{stepname}"] = runtime

    # Get cpu usage
    cpu_percent = psutil.cpu_percent(interval=1)

    # Get memory usage
    memory_info = psutil.virtual_memory()
    total_memory = memory_info.total / (1024 ** 3)  # Convert bytes to GB
    available_memory = memory_info.available / (1024 ** 3)  # Convert bytes to GB
    memory_percent = memory_info.percent
    memory_usage = total_memory * memory_percent / 100

    print(f"[SYSTEM] Total CPU: {cpu_percent:.2f}%")
    print(f"[SYSTEM] Total Memory: {total_memory:.2f} GB")
    print(f"[SYSTEM] Available Memory: {available_memory:.2f} GB")
    print(f"[SYSTEM] Current Memory Usage: {memory_percent:.2f}%")

    if 'cpu_usage' not in config:
        config['cpu_usage'] = {f"{stepname}": cpu_percent}
    else:
        config["cpu_usage"][f"{stepname}"] = cpu_percent
    if 'mem_usage' not in config:
        config['mem_usage'] = {f"{stepname}": memory_usage}
    else:
        config["mem_usage"][f"{stepname}"] = memory_usage

def display_version(_class_name, _path):
    """ Description
        -----------
            Display version information with git log

        Parameters
        -----------
            _class_name (str) : Module Name
            _path (str) : Module Path

        Example
        -----------
        display_version(sys._getframe().f_code.co_filename[:-3], self._path)
    """
    os.chdir(_path)

    print('\n')
    print('='*70)
    print('[Name]\t\t: {}'.format(_class_name))
    print('[latest tag]\t: {}'.format(get_latest_tag(_path)))
    git_log = subprocess.check_output(['git', 'log', '-1'])
    print('[git log]')
    git_log = str(git_log, "utf-8").strip()
    print(git_log)
    print('='*70)
    print('\n\n')


def get_latest_tag(_path):
    """ Description
        -----------
            Get the latest tag

        Parameters
        -----------
            _path (str) : Module Path

        Return
        -----------
            the latest tag or none

        Example
        -----------
        get_latest_tag(self._path)
    """
 
    os.chdir(_path)
    
    try:
        git_tag = subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0'])
        git_tag = str(git_tag, "utf-8").strip()
        return git_tag
    # nothing
    except:
        return 'none'


def check_path(_filename, remake=False):
    """ Description
        -----------
            Check the directory of file

        Parameters
        -----------
            _filename (str) : the file name with full directory 
            options
                remake (bool) : Create the path if not path

        Return
        -----------
            bool

        Example
        -----------
            check_path('/home/user/work/filename.csv', remake=True)
    """
 
    # 접근 폴더가 없다면
    if not os.path.exists(os.path.dirname(_filename)):
        os.makedirs(os.path.dirname(_filename))
        return False
    else:
        # 폴더가 있다면 삭제하고, 다시 만든다.
        if remake == True:
            shutil.rmtree(os.path.dirname(_filename))
            os.makedirs(os.path.dirname(_filename))
        return True
 

def replace_pattern(_str, _old, _new, _ord):
    """ Description
        -----------
            Replace pattern from old to new in String

        Parameters
        -----------
            _str (str) : Target String
            _old (str) : old pattern
            _new (str) : new pattern
            _ord (int) : the order to find old pattern (..., 3, 2, 1, -1, -2, -3, ...)

        Return
        -----------
            the replaced string

        Example
        -----------
            replace_pattern(_str, 'inference', 'train', -1)
    """
 
    
    if _ord > 0:
        index_num = 0
    elif _ord < 0:
        index_num = len(_str)
    else:
        return 'none'
        
    for i in range(abs(_ord)):
        if _ord > 0:
            index_old = _str.find(_old, index_num)
            index_num = index_old + (len(_old) - 1)
        elif _ord < 0:
            index_old = _str.rfind(_old, 0, index_num)
            index_num = index_old
        
        if index_old == -1:
            return 'none'
        else:
            pass
        
    ret_str = _str[:index_old] + _new + _str[index_old + len(_old):]
    return ret_str

def check_arg_values(arg_key, arg_range, reg_pattern=r''):
    if reg_pattern != '':
        regex = re.compile(reg_pattern)  # 패턴을 컴파일하여 정규 표현식 객체 생성
        if regex.match(arg_key):
            pass
    else:
        if type(arg_key) == list :
            rslt = all(elem in arg_range for elem in arg_key)
            if not rslt:
                raise ValueError(f"The parameter '{arg_key}' is not allowed. [range: '{arg_range}']")
        else: ## str
            if arg_key not in arg_range:
                raise ValueError(f"The parameter '{arg_key}' is not allowed. [range: '{arg_range}']")

def check_columns_existence(df, columns):
    columns = [item for item in columns if item != ""]

    if len(columns) != 0:
        missing_columns = [col for col in columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"The following columns are missing in the DataFrame: {missing_columns}")

def check_and_remove_duplicates(df, group_columns, time_column):
    grouped = df.groupby(group_columns)

    for _, group in grouped:
        if group[time_column].duplicated().any():
            group_identifier = ', '.join(f"{col}='{_}'" for col, _ in zip(group_columns, _))
            print(f"Duplicate values found in the time column for {group_identifier}.")
            df.drop_duplicates(subset=[time_column], keep='first', inplace=True)
            print(f"Duplicate rows removed for {group_identifier}.")
        else:
            group_identifier = ', '.join(f"{col}='{_}'" for col, _ in zip(group_columns, _))
            print(f"No duplicate values found in the time column for {group_identifier}.")

def make_group_by(df, group_cnt, group_keys, keys):
    ## group단위 dataframe 인 partial_df 생성하기
    if group_cnt == 3:
        partial_df = df[(df[group_keys[0]] == keys[0]) & (df[group_keys[1]] == keys[1]) &
                    (df[group_keys[2]] == keys[2])].reset_index(drop=True)
    elif group_cnt == 2:
        partial_df = df[(df[group_keys[0]] == keys[0]) &
                        (df[group_keys[1]] == keys[1])].reset_index(drop=True)
    elif group_cnt == 1 or group_cnt == 0 :
        partial_df = df[(df[group_keys[0]] == keys[0])].reset_index(drop=True)
    else:
        ## groupby 는 최대 3개 column 까지 지원합니다. column 갯수 별로 코드가 달라져야 합니다.
        return ValueError(f'group_key: {group_keys} has a maximum value of 3. The current value is: {group_cnt}')

    return partial_df


############################################
###  Internal Function
############################################

