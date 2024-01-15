import argparse
from src.constants import *
from src.logger import ProcessLogger
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
OUTPUT_IMAGE_EXTENSIONS = ["*.jpg", "*.jpeg", "*.png"]
#--------------------------------------------------------------------------------------------------------------------------

        

    


def set_args():
    parser = argparse.ArgumentParser(description="Enter the options: << config, system, mode, loop >>")
    parser.add_argument("--config", type=str, default=None, help="config option: experimental_plan.yaml")
    parser.add_argument("--system", type=str, default=None, help="system option: jsonized solution_metadata.yaml")
    parser.add_argument("--mode", type=str, default="all", help="ALO mode: train, inference, all")
    parser.add_argument("--loop", type=bool, default=False, help="On/off infinite loop: True, False")
    parser.add_argument("--computing", type=str, default="local", help="training resource: local, sagemaker, ..") # local = on-premise
    args = parser.parse_args()
    
    return args

def init_redis(args):
    ##### import RedisQueue ##### 
    from src.redisqueue import RedisQueue
    import json
    
    ##### parse redis server port, ip #####
    sol_meta_json = json.loads(args.system)
    redis_host, redis_port = sol_meta_json['edgeapp_interface']['redis_server_uri'].split(':')
    # FIXME 이런데서 죽으면 EdgeApp은 ALO가 죽었는 지 알 수 없다? >> 아마 alo 실행 실패 시 error catch하는 게 EdgeAPP 이든 host든 어디선가 필요하겠지? 
    if (redis_host == None) or (redis_port == None): 
        raise ValueError("Missing redis server uri in solution metadata.")
    
    ##### make RedisQueue instance #####
    #q = RedisQueue('my-queue', host='172.17.0.2', port=6379, db=0)
    q = RedisQueue('request_inference', host=redis_host, port=int(redis_port), db=0)

    return q        
        
        
        
        
### LEGACY

## alo.py의 empty_artifacts로 대체함 
# def remove_log_files(artifacts): 
#     if '.train_artifacts' in artifacts: 
#         log_path = artifacts['.train_artifacts'] + 'log'
#         if os.path.exists(log_path):
#             shutil.rmtree(log_path, ignore_errors=True)
#     if '.inference_artifacts' in artifacts:
#         log_path = artifacts['.inference_artifacts'] + 'log'
#         if os.path.exists(log_path):
#             shutil.rmtree(log_path, ignore_errors=True)

# # TODO logger 코드 정리하기
# class Logger:
#     def __init__(self, filename):
#         self.terminal = sys.stdout
#         self.log = open(filename, "a")

#     def write(self, message):
#         self.terminal.write(message)
#         self.log.write(message)

#     def flush(self):
#         pass