from src.utils import set_args, init_redis
from src.alo import ALO


def main():
    # ALO 실행 전 필요한 args를 받아옴
    args = set_args()
    kwargs = vars(args)
    alo = ALO(kwargs)
    alo.runs()

if __name__ == "__main__":
    main()