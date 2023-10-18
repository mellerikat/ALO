import argparse
import time

from core.alo import ALOv2
# from alolib.asset import Asset

# --------------------------------------------------------------------------------------------------------------------------
#    MAIN
# --------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    # while(1):

    parser = argparse.ArgumentParser(description="exp yaml의 경로를 입력하세요(ex:)./config/experimental_plan.yaml")

    parser = argparse.ArgumentParser(description="특정 파일을 처리하는 스크립트")
    parser.add_argument("--config", type=str, default=0, help="config 옵션")
    parser.add_argument("--system", type=str, default="system", help="system 옵션")

    args = parser.parse_args()
    start_time = time.time()

    try:
        alo = ALOv2(exp_plan = args.config)  # exp plan path
    except:
        alo = ALOv2()  # exp plan path
    alo.runs()
    end_time = time.time()
    execution_time = end_time - start_time

    # print_color(f"Total Program run-time: {execution_time} sec", 'yellow')