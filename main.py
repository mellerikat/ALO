import json
from src.alo import ALO
from src.utils import set_args, init_redis

# --------------------------------------------------------------------------------------------------------------------------
#    MAIN
# --------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    
    # ALO 실행 전 필요한 args를 받아옴
    args = set_args()

    if args.loop == False: 
        try:
            # ALO instance를 입력받은 args를 기반으로 초기화
            kwargs = {'sol_meta_str': args.system, 'alo_mode': args.mode, 'exp_plan_file': args.config, 'boot_on': args.loop}
            alo = ALO(**kwargs)
            # 초기화된 ALO를 실행
            alo.runs()
        except Exception as e: 
            #print("\033[91m" + "Error: " + str(e) + "\033[0m") # print red 
            raise NotImplementedError(str(e))
        
    elif args.loop == True: 
        
        # redis를 초기화
        q = init_redis()
        
        ##### Boot-on sequence #####
        # TODO http://clm.lge.com/issue/browse/DXADVTECH-520?attachmentSortBy=dateTime&attachmentOrder=asc 11.16 댓글 (boot-on 완료 메시지관련)
        # [주의] boot-on을 위해선 solution meta yaml 과 일치하는 experimental plan yaml 이 이미 존재해야한다. 
        # boot-on: inference alo_mode로 하면 약 3.xx 초 
        # FIXME alo_mode train-inference 인 경우 검증 필요 
        try: 
            alo = ALO(alo_mode = args.mode, boot_on = True)
            alo.runs() 
            print('\033[92m==================== Finish ALO boot-on ====================\033[0m \n')
            # TODO boot-on 끝났다는 메시지 전송 필요 ?
        except: 
            raise NotImplementedError("Failed to ALO boot-on.")
        ##### Infinite loop ##### 
        while True: 
            start_msg = q.lget(isBlocking=True) # 큐가 비어있을 때 대기 / lget, rput으로 통일 
            if start_msg is not None:
                try: 
                    # http://clm.lge.com/issue/browse/AIADVISOR-705?attachmentSortBy=dateTime&attachmentOrder=asc
                    msg_dict = json.loads(start_msg.decode('utf-8')) # dict 
                    sol_meta_str = msg_dict['solution_metadata']
                    kwargs = {'sol_meta_str': args.system, 'alo_mode': args.mode, 'exp_plan_file': args.config, 'boot_on': args.loop}
                    alo = ALO(**kwargs)
                    alo.runs()
                except Exception as e: 
                    print("\033[91m" + "Error: " + str(e) + "\033[0m") # print red 
                    continue # loop는 죽이지 않는다. 
    else: 
        raise ValueError("Invalid << loop >> arguments. It must be True or False.")


