from src.utils import set_args, init_redis
from src.alo import ALO

# self.experimental_plan.user_parameters['x_col'] = 'aa'
# pipeline = alo.pipeline()
# pipeline.experimental_plan['input']['x_cols']
# ***
# pipeline.user_parameters[step_name][args]
# 위에 내용을 작동하는 함수작성

def main():
    # ALO 실행 전 필요한 args를 받아옴
    kwargs = vars(set_args())
    alo = ALO(**kwargs)
    alo.main()

if __name__ == "__main__":
    main()