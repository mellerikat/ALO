from datetime import datetime

color_dict = {
   'PURPLE':'\033[95m',
   'CYAN':'\033[96m',
   'DARKCYAN':'\033[36m',
   'BLUE':'\033[94m',
   'GREEN':'\033[92m',
   'YELLOW':'\033[93m',
   'RED':'\033[91m',
   'BOLD':'\033[1m',
   'UNDERLINE':'\033[4m',
}

COLOR_END = '\033[0m'

def asset_error(msg):
    # time_utc = datetime.now(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')
    # time_kst = datetime.now(timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    print('\n\n')
    print_color("============================= ASSET ERROR =============================", 'red')
    # print_color(f"TIME(UTC)    : {time_utc} (KST : {time_kst})", 'red')
    # print_color(f"PIPELINES    : {self.asset_envs['pipeline']}", 'red')
    # print_color(f"ASSETS     : {self.asset_envs['step']}", 'red')
    print_color(f"ERROR(msg)   : {msg}", 'red')
    print_color("=======================================================================", 'red')
    print('\n\n')

    # save log at metadata
    # self.metadata._set_log(msg, self.context['metadata_table_version']['log'], 'error')

    # update execution(ERROR)
    # self.metadata._set_execution('ERROR')

    raise ValueError(msg)

def print_color(msg, _color):
    """ Description
        -----------
            Display text with color at ipynb

        Parameters
        -----------
            msg (str) : text
            _color (str) : PURPLE, CYAN, DARKCYAN, BLUE, GREEN, YELLOW, RED, BOLD, UNDERLINE

        example
        -----------
            print_color('Display color text', 'BLUE')
    """
    if _color.upper() in color_dict.keys():
        print(color_dict[_color.upper()]+msg+COLOR_END)
    else:
        raise ValueError('Select color : {}'.format(color_dict.keys()))