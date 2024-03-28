import argparse
from src.constants import *
from src.logger import ProcessLogger
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
#--------------------------------------------------------------------------------------------------------------------------
COLOR_RED = '\033[91m'
COLOR_END = '\033[0m'
ARG_NAME_MAX_LENGTH = 30
COLOR_DICT = {
   'PURPLE':'\033[95m',
   'CYAN':'\033[96m',
   'DARKCYAN':'\033[36m',
   'BLUE':'\033[94m',
   'GREEN':'\033[92m',
   'YELLOW':'\033[93m',
   'RED':'\033[91m',
   'BOLD':'\033[1m',
   'BOLD-GREEN':'\033[1m\033[92m',
   'BOLD-CYAN':'\033[1m\033[96m',
   'UNDERLINE':'\033[4m',
}
COLOR_END = '\033[0m'

def print_color(msg, color):
    """ Description
        -----------
            Display text with color 

        Parameters
        -----------
            msg (str) : text
            _color (str) : PURPLE, CYAN, DARKCYAN, BLUE, GREEN, YELLOW, RED, BOLD, UNDERLINE

        example
        -----------
            print_color('Display color text', 'BLUE')
    """
    if color.upper() in COLOR_DICT.keys():
        print(COLOR_DICT[color.upper()] + msg + COLOR_END)
    else:
        raise ValueError('[ERROR] print_color() function call error. - selected color : {}'.format(COLOR_DICT.keys()))
    
def set_args():
    """
    set args for ALO
    """
    parser = argparse.ArgumentParser(description="Enter the options: << config, system, mode, loop >>")
    parser.add_argument("--config", type=str, default=None, help="config option: experimental_plan.yaml")
    parser.add_argument("--system", type=str, default=None, help="system option: jsonized solution_metadata.yaml")
    parser.add_argument("--mode", type=str, default="all", help="ALO mode: train, inference, all")
    parser.add_argument("--loop", type=bool, default=False, help="On/off infinite loop: True, False")
    parser.add_argument("--computing", type=str, default="local", help="training resource: local, sagemaker, ..") # local = on-premise
    args = parser.parse_args()
    return args

def init_redis(system):
    ##### import RedisQueue ##### 
    from src.redisqueue import RedisQueue
    import json
    ##### parse redis server port, ip #####
    sol_meta_json = json.loads(system)
    redis_host, redis_port = sol_meta_json['edgeapp_interface']['redis_server_uri'].split(':')
    # FIXME 이런데서 죽으면 EdgeApp은 ALO가 죽었는 지 알 수 없다? >> 아마 alo 실행 실패 시 error catch하는 게 EdgeAPP 이든 host든 어디선가 필요하겠지? 
    if (redis_host == None) or (redis_port == None): 
        raise ValueError("Missing redis server uri in solution metadata.")
    ##### make RedisQueue instance #####
    #q = RedisQueue('my-queue', host='172.17.0.2', port=6379, db=0)
    q = RedisQueue('request_inference', host=redis_host, port=int(redis_port), db=0)
    return q        
        
def _log_process(msg):
    PROC_LOGGER.process_info(f'====================     {msg}')

