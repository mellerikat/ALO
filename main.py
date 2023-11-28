import argparse
from src.alo import ALO

# --------------------------------------------------------------------------------------------------------------------------
#    MAIN
# --------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    # while(1):
    parser = argparse.ArgumentParser(description="Enter the options: << config, system, mode, loop >>")
    parser.add_argument("--config", type=str, default=None, help="config option: experimental_plan.yaml")
    parser.add_argument("--system", type=str, default=None, help="system option: jsonized solution_metadata.yaml")
    parser.add_argument("--mode", type=str, default="all", help="ALO mode: train, inference (inf), all")
    parser.add_argument("--loop", type=bool, default=False, help="On/off infinite loop: True, False")
    args = parser.parse_args()
    
    if args.loop == False: 
        try:
            if args.config != None: 
                if args.config == "": # FIXME 임시 (AIC에서도 임시)
                    alo = ALO(sol_meta_str = args.system, alo_mode = args.mode)
                else: 
                    alo = ALO(exp_plan_file = args.config, sol_meta_str = args.system, alo_mode = args.mode)  # exp plan path
            else: 
                alo = ALO(sol_meta_str = args.system, alo_mode = args.mode)
        except:
            raise ValueError("Inappropriate config yaml file.")

        try:
            alo.runs()
        except Exception as e: 
            print("\033[91m" + "Error: " + str(e) + "\033[0m") # print red 
            
    elif args.loop == True: 
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
        
        ##### Boot-on sequence #####
        # TODO http://clm.lge.com/issue/browse/DXADVTECH-520?attachmentSortBy=dateTime&attachmentOrder=asc 11.16 댓글 (boot-on 완료 메시지관련)
        # [주의] boot-on을 위해선 solution meta yaml 과 일치하는 experimental plan yaml 이 이미 존재해야한다. 
        # boot-on: inference alo_mode로 하면 약 3.xx 초 
        # FIXME alo_mode train-inference 인 경우 검증 필요 
        alo = ALO(alo_mode = args.mode, boot_on = True)
        alo.runs() 
        print('==================== Finish boot-on ====================\n')
        # TODO boot-on 끝났다는 메시지 전송 필요 ?

        ##### Infinite loop ##### 
        while True: 
            start_msg = q.rget(isBlocking=True) # 큐가 비어있을 때 대기
            if start_msg is not None:
                try: 
                    # http://clm.lge.com/issue/browse/AIADVISOR-705?attachmentSortBy=dateTime&attachmentOrder=asc
                    msg_dict = json.loads(start_msg.decode('utf-8')) # dict 
                    sol_meta_str = msg_dict['solution_metadata']
                    try:
                        if args.config != None: 
                            if args.config == "": # FIXME 임시 (AIC에서도 임시)
                                alo = ALO(sol_meta_str = sol_meta_str, alo_mode = args.mode)
                            else: 
                                alo = ALO(exp_plan_file = args.config, sol_meta_str = sol_meta_str, alo_mode = args.mode)  # exp plan path
                        else: 
                            alo = ALO(sol_meta_str = sol_meta_str, alo_mode = args.mode)
                    except:
                        raise ValueError("Inappropriate config yaml file.")
                    alo.runs()
                except Exception as e: 
                    print("\033[91m" + "Error: " + str(e) + "\033[0m") # print red 
                    continue # loop는 죽이지 않는다. 
    else: 
        raise ValueError("Invalid << loop >> arguments. It must be True or False.")