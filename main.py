import argparse
from src.alo import ALO

# --------------------------------------------------------------------------------------------------------------------------
#    MAIN
# --------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    # while(1):

    parser = argparse.ArgumentParser(description="Enter the path of << experimental_plan.yaml >> (ex) ./config/experimental_plan.yaml")
    parser = argparse.ArgumentParser(description="Script for dealing with specific file")
    parser.add_argument("--config", type=str, default=None, help="config option")
    parser.add_argument("--system", type=str, default=None, help="system option")
    parser.add_argument("--mode", type=str, default="all", help="ALO mode, train, inf, inference, all")
    
    args = parser.parse_args()

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
        
    alo.runs()
