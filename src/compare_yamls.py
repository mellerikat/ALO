import os
import yaml
from collections import defaultdict
from src.constants import *
from src.yaml_upgrade import from_2_0_to_2_1
from alolib import logger 
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = logger.ProcessLogger(PROJECT_HOME)
# TODO compare yaml 업그레이드 될 때마다 아래 전역 변수를 업데이트해야하고, src.yaml_upgrade 내에 함수 구현 필요 
YAML_UPGRADE_FUNC = {'2.0': from_2_0_to_2_1} # key: current compare yaml version, value: yaml upgrade function 
#--------------------------------------------------------------------------------------------------------------------------
    

def get_yaml(_yaml_file):
    yaml_dict = dict()
    try:
        with open(_yaml_file, encoding='UTF-8') as f:
            yaml_dict  = yaml.load(f, Loader=yaml.FullLoader)
    except FileNotFoundError:
        PROC_LOGGER.process_error(f"Not Found : {_yaml_file}")
    except:
        PROC_LOGGER.process_error(f"Check yaml format : {_yaml_file}")

    return yaml_dict 


# plan yaml과 모든 compared yaml 들 각각을 대조 해보면서 어떤게 버전 일치하는 지 찾아낸다.
def _compare_dict_keys(dict1, dict2): # inner func. of compare_yaml func.
    # dict1: exp, dict2: compare
    # 상위 key의 하위 key들 (ex. external_path가 상위 key면, [load_train_data_path, load_inference_data_path ..] 등이 하위 키)
    keys1 = set(key for d in dict1 for key in d.keys())
    keys2 = set(key for d in dict2 for key in d.keys())

    diff = keys2 - keys1

    if keys1 == keys2: 
        return 'same'
    # [중요 plan yaml 에서 train 혹은 inference만 돌릴수도있으므로 이 경우는 pass]
    if (diff == {'train_pipeline'}) or (diff == {'inference_pipeline'}):
        return 'same' 
    return 'different'

def compare_yaml(exp_plan):
    '''
    1. 모든 compare_<version>.yaml을 list-up 한다. 
    2. ALO 최신 버전과 compare yaml의 최신 버전의 버전 숫자는 일치하지 않을 수 있다. 
    3. compare yaml의 최신 버전을 가져온다.
    4. 이미 compare yaml의 version이 하나씩 올라갈 때 마다 어떤게 바꼈는지에 대한 정보는 ALO에서 알고 있다.   
    5. plan yaml과 모든 compare yaml 들 각각을 대조해보면서 어떤게 버전 일치하는 지 찾아낸다. 
    6. 가령, compare yaml version 2.0, 2.1, 2.2 가 존재하는데 그중 plan yaml이 2.1과 버전이 같다면, 
       compare yaml의 latest인 2.2까지 순차적으로 plan yaml을 version up 한다. 
    '''
    # 모든 compare_<version>.yaml을 list-up 한다. 
    compare_yaml_versions = []
    compare_yaml_paths = [] 
    compare_yaml_dir = PROJECT_HOME + 'src/config_format/'
    for i in os.listdir(compare_yaml_dir):
        file_name, file_extension = os.path.splitext(i)
        if file_extension == '.yaml':
            compare_yaml_versions.append(file_name.split('_')[-1]) # ex. ['2.0', '2.1', '2.2']
            compare_yaml_paths.append(compare_yaml_dir + i)
            
    # compare yaml의 최신 버전을 가져온다.
    compare_yaml_versions.sort() # version을 오름차순 정렬 
    latest_compare_yaml_ver = compare_yaml_versions[-1]
     
    # compare yaml 경로 version 순으로 오름차순 정렬 
    compare_yaml_paths.sort()
    
    same_compare_ver = None  
    flag_same = False # 밑에서 모든 key 가 일치할 때 flag를 True로 변환 
    all_compare_key_dict = defaultdict(list) # plan yaml과 각 버전의 compare yaml의 상위 key와 하위 key 모두 1d list로 취합  
    all_plan_key_list =  [] 
    # plan yaml의 모든 key 취합 --> [가정] plan yaml 및 compare yaml 에는 key를 2-depth 보다 크게 들어가지 않는다 
    for main_key in exp_plan.keys():
        all_plan_key_list.append(main_key)
        sub_key_list = [key for d in exp_plan[main_key] for key in d.keys()]
        for sub_key in sub_key_list:
            all_plan_key_list.append(sub_key)
    # 모든 key 구성이 완전히 같은 버전의 compare yaml 있는지 찾기 / 그 과정에서 각 compare yaml의 모든 key 취합 (dict ~ key: ver, value: 모든 key list) 
    for idx, compare_yaml_path in enumerate(compare_yaml_paths): 
        compared_yaml = get_yaml(compare_yaml_path)
        # compare yaml의 모든 key 취합
        for main_key in compared_yaml.keys():
            all_compare_key_dict[compare_yaml_versions[idx]].append(main_key)
            sub_key_list = [key for d in compared_yaml[main_key] for key in d.keys()]
            for sub_key in sub_key_list: 
                all_compare_key_dict[compare_yaml_versions[idx]].append(sub_key)
        # 상위 key (ex. ['asset_source', 'control', 'external_path', 'external_path_permission', 'user_parameters']) 다르면 1차 불일치 
        if sorted(exp_plan.keys()) != sorted(compared_yaml.keys()):
            continue
        compared_dict_keys = [_compare_dict_keys(exp_plan[key], compared_yaml[key]) for key in exp_plan] 
        if 'different' in compared_dict_keys:
            continue 
        else: # 전부 'same'일 때 같은 버전의 yaml이라고 (완전 일치) 판단 가능  
            flag_same = True  
            same_compare_ver = compare_yaml_versions[idx]
            break # 처음으로 같은 버전 나오면 break 
                
    # [23.11.13 송세현C, 장우성Y 논의] 모든 compare yaml과 다 비교 했는데도 하나도 같은 version이 없으면, \
        # 가령 사용자가 2.0도 아니고 2.1도 아닌 그 사이의 포함관계 (2.0은 포함하는데 2.1이랑 일치는 안하는)인 plan yaml을 작성했으면 그냥 2.0으로 인지 
    # 그래도 없으면 plan yaml의 포맷이 잘못된 것이므로 에러 
    if flag_same == False: 
        sorted_versions = sorted(list(all_compare_key_dict.keys())) # 오름차순 version (str) 정렬
        for ver in sorted_versions[:-1]: 
            next_ver = str(float(ver) + 0.1)
            # 현재 버전과 다음 버전 사이에 plan yaml이 사이에 낀 포함관계로 들어가 있다면 그냥 이전 버전으로 인지 
            if set(all_compare_key_dict[ver]).issubset(set(all_plan_key_list)) and set(all_plan_key_list).issubset(set(all_compare_key_dict[next_ver])):
                same_compare_ver = ver 
        
        if same_compare_ver != None: # 현재 버전과 다음 버전 사이의 포함관계 일때 
            PROC_LOGGER.process_info(f"None of << compare yaml >> version is matched. \n \
However, The version of << experimental_plan.yaml >> is recognized as same as compare yaml version << {same_compare_ver} >> ")
        else: # 포함관계도 아닐때 
            PROC_LOGGER.process_error(f"\n You entered wrong format of << experimental_plan.yaml >>. \n \
There are no << compare yaml >> with same format. \n \
Please edit your << experimental_plan.yaml >> by reffering to latest version of << compare yaml >> \n \
=============================================================================================================== \n \
{get_yaml(compare_yaml_paths[-1])} ")
    
    # latest compare yaml 형태까지 upgrade exp plan 
    # 가령, compare yaml version 2.0, 2.1, 2.2 가 존재하는데 그중 plan yaml이 2.1과 버전이 같다면, compare yaml의 latest인 2.2까지 순차적으로 plan yaml을 version up 한다 
    ver_diff = float(latest_compare_yaml_ver) - float(same_compare_ver)
    # 약속: compare yaml version은 0.1 단위로 업그레이드 하도록 관리 
    cur_ver = same_compare_ver
    if ver_diff != 0:
        for i in range(int(ver_diff // 0.1)): 
            exp_plan = YAML_UPGRADE_FUNC[cur_ver](exp_plan) # exp plan yaml을 compare yaml 기준 + 0.1 ver upgrade  
            PROC_LOGGER.process_info(f"Success versioning up experimental_plan.yaml : {cur_ver} --> {str(float(cur_ver) + 0.1)} (version ref. : compare yaml version)", color='green')
            cur_ver = str(float(cur_ver) + 0.1) # cur_ver += 0.1 

    return exp_plan 


###########################################################################################################################################################################
# <LEGACY> 
# def compare_yaml_dicts(dict1, dict2):
#     # 두 딕셔너리의 키를 비교
#     keys1 = set(dict1.keys())
#     keys2 = set(dict2.keys())
#     if keys1 != keys2:
#         return False

#     # 모든 키에 대해 재귀적으로 하위 딕셔너리 비교
#     for key in keys1:
#         if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
#             if not compare_yaml_dicts(dict1[key], dict2[key]):
#                 return False
#         elif dict1[key] != dict2[key]:
#             return False
#     return True
