
# --------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
# default values 
LOAD_MODEL_PATH = None
RESET_ASSETS = False 
#--------------------------------------------------------------------------------------------------------------------------
# compare yaml의 버전이 업될 때 인자 remove, add, modify가 다 될수있다고 가정 
# [23.11.13 송세현C, 장우성Y 논의] 사용자가 2.0도 아니고 2.1도 아닌 그 사이의 포함관계 (2.0은 포함하는데 2.1이랑 일치는 안하는)인 plan yaml을 작성했으면 그냥 2.0으로 인지 
def from_2_0_to_2_1(exp_plan):
    '''
    1. external_path의 load_model_path 인자 추가 
    2. control 부 reset_assets 인자 추가 # TODO  release 해도 import 패키지 메모리에 남아있는 지 검증필요 
    '''
    # external_path의 load_model_path 인자 추가 
    exp_plan['external_path'].append({'load_model_path': LOAD_MODEL_PATH})
    
    # control 부 reset_assets 인자 추가 # TODO  release 해도 import 패키지 메모리에 남아있는 지 검증필요
    exp_plan['control'].append({'reset_assets': RESET_ASSETS})
    
    return exp_plan 



