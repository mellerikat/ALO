from src.utils import set_args
from src.alo import ALO

def main():
    kwargs = vars(set_args())
    alo = ALO(**kwargs)
    alo.main()

if __name__ == "__main__":
    main()
