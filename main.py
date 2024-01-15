import json
from src.alo import ALO
from src.utils import set_args, init_redis

# --------------------------------------------------------------------------------------------------------------------------
#    MAIN
# --------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    """ALO 는 --config 옵션으로 실험 설명 (experimental_plan.yaml) 파일을 입력 받는다. --config 선언 없을 시, ./config/ 에 존재하는 파일을 참조 한다. 
    실험 조건에 따라 추론만 반복해서 할 경우가 있는데, --mode 로 inference 모드를 선언 할 수 있다.
    또한, 운영 과정에서 aiadvisor (시스템)가 설정한 값들을 처리해야 할 때는 --system 옵션으로 "solution_metadata (type:string)" 를 입력 받는다. 
    운영 과정에서 tacktime 을 줄이기 위해 ALO 가 always-on 상태이기 위해서는 --loop True 로 설정한다. 

    1) --config,  
        type=str, default=None, help="config option: experimental_plan.yaml
    2) --system, 
        type=str, default=None, help="system option: jsonized solution_metadata.yaml"
    3) --mode, 
        type=str, default="all", help="ALO mode: train, inference, all, sagemaker_train"
    4) --loop, 
        type=bool, default=False, help="On/off infinite loop: True, False"
    5) --computing
    """
    
    # ALO 실행 전 필요한 args를 받아옴
    args = set_args()
    if args.loop == False:  ## batch mode 
        try:
            kwargs = {'sol_meta_str': args.system, 'alo_mode': args.mode, 'exp_plan_file': args.config, 'boot_on': args.loop, 'computing': args.computing}
            alo = ALO(**kwargs)
            if args.computing == 'sagemaker':
                # sagemaker boot-on >> assets, alolib 등 설치하기 위해 필요 (실제 asset run함수 실행은 X)
                ALO(alo_mode = 'train', boot_on = True).runs() 
                print('\033[92m==================== Finish ALO boot-on ====================\033[0m \n')
                # sagemaker 자원으로 학습 
                alo.sagemaker_runs()
            else: 
                alo.runs()
        except Exception as e: 
            raise NotImplementedError(str(e))
        
    elif args.loop == True: 
        # EdgeApp 과의 통신을 위한 redis 초기화
        q = init_redis()

        ################################### 
        ##### Step1. Boot-on sequence #####
        ################################### 

        # TODO http://clm.lge.com/issue/browse/DXADVTECH-520?attachmentSortBy=dateTime&attachmentOrder=asc 11.16 댓글 (boot-on 완료 메시지관련)
        # [주의] boot-on을 위해선 solution meta yaml 과 일치하는 experimental plan yaml 이 이미 존재해야한다. 
        # boot-on: inference alo_mode로 하면 약 3.xx 초 
        # FIXME alo_mode train-inference 인 경우 검증 필요 
        try: 
            alo = ALO(alo_mode = args.mode, boot_on = True)
            alo.runs() 
            print('\033[92m==================== Finish ALO boot-on ====================\033[0m \n')
        except: 
            raise NotImplementedError("Failed to ALO boot-on.")

        ################################ 
        ##### Step2. Infinite loop ##### 
        ################################ 
        while True: 
            ## EdgeApp 이 추론 요청을 대기 (waiting 상태 유지)
            start_msg = q.lget(isBlocking=True) # 큐가 비어있을 때 대기 / lget, rput으로 통일 
            if start_msg is not None:
                try: 
                    # http://clm.lge.com/issue/browse/AIADVISOR-705?attachmentSortBy=dateTime&attachmentOrder=asc
                    msg_dict = json.loads(start_msg.decode('utf-8')) # dict 
                    ## 운영시에만 사용되는 solution_metadata 는 string 으로 입력 받는다. 
                    sol_meta_str = msg_dict['solution_metadata']

                    kwargs = {'sol_meta_str': args.system, 'alo_mode': args.mode, 'exp_plan_file': args.config, 'boot_on': False}
                    alo = ALO(**kwargs)
                    alo.runs()
                except Exception as e: 
                    ## always-on 모드에서는 Error 가 발생해도 종료되지 않도록 한다. 
                    print("\033[91m" + "Error: " + str(e) + "\033[0m") # print red 
                    continue  
            else:
                msg = "EdgeApp 에서 추론 요청 시, Empty message 로 전달 됨."
                print("\033[91m" + "Error: " + str(msg) + "\033[0m") # print red 

    else: 
        raise ValueError("Invalid << loop >> arguments. It must be True or False.")


