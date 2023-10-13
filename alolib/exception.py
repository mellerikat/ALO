import os
import sys
import inspect

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
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

TYPE_LIST = ('str', 'dataframe', 'numpy', 'int', 'float', 'bool', 'list', 'dict', 'class')
DTYPE_LIST = ('numeric', 'categorical', 'bool', 'time') 


#--------------------------------------------------------------------------------------------------------------------------
#    INTERNAL FUNCTION
#--------------------------------------------------------------------------------------------------------------------------
def _check_string(_value):
    if type(_value) != str:
        raise ValueError('only string type')


# def _check_series(_value):
#     if type(_value) != pd.Series:
#         raise ValueError('only Series')


# def _check_time_series(_value):
#     try:
#         pd.to_datetime(_value)
#         return True
#     except:
#         return False
    
#--------------------------------------------------------------------------------------------------------------------------
#    EXTERNAL FUNCTION
#--------------------------------------------------------------------------------------------------------------------------
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
    _check_string(msg)
    _check_string(_color)
 
    if _color.upper() in color_dict.keys():
        print(color_dict[_color.upper()]+msg+COLOR_END)
    else:
        raise ValueError('Select color : {}'.format(color_dict.keys()))


def print_error(msg):
    """ Description
        -----------
            Display Error Message with caller and line

        Parameters
        -----------
            msg (str) : text

        example
        -----------
            print_error('Display error text')
    """
    _check_string(msg)

    # 0 : print_error 함수
    # 1 : print_error 를 call 한 함수
    caller = inspect.stack()[1]

    print('  {}, def {}'.format(caller.filename, caller.function))
    print(color_dict['BLUE']+'  line : {}, {}'.format(caller.lineno, caller.code_context[0].lstrip())+COLOR_END, end='')
    print('')
    sys.exit(color_dict['RED']+'[ERROR] : ' + msg+COLOR_END)


def value_error(msg):
    """ Description
        -----------
            Customize Message and aip_error

        Parameters
        -----------
            msg (str) : text

        example
        -----------
            value_error('Display error text')
    """
    _check_string(msg)
    raise ValueError(msg)


def add_warning_log(log, msg):
    """ Description
        -----------
            Add Warning Message in log

        Parameters
        -----------
            log (dict) : log variable
            msg (str) : text

        example
        -----------
            add_warning_log(self.log, 'Display error text')
    """
    check_type('dict', log)
    _check_string(msg)

    try:
        #init : log[warning] = []
        log['warning'].append(msg)
    except KeyError:
        #init : empty
        log['warning'] = [msg]
    except AttributeError:
        #init : log[warning] = 123
        if len(str(log['warning'])) > 0:
            #init : log[warning] = [123]
            log['warning'] = [log['warning']] 
            #init : log[warning] = [123, msg]
            log['warning'].append(msg)
        #init : log[warning] = ''
        else:
            log['warning'] = [msg]
    
    print(msg)
 

# def check_type
def check_type(str_type, value):
    """ Description
        -----------
            Check the type of variable

        Parameters
        -----------
            str_type (str) : str, dataframe, int, float, bool, list, dict, class
            value (variable) : variable

        example
        -----------
            check_type('int', var1)
    """
    _check_string(str_type)
    
    if str_type.lower() in TYPE_LIST:
        if str_type.lower() in str(type(value)).lower():
            pass
        else:
            raise ValueError('only use {} type (used type : {})'.format(str_type, str(type(value))))
    else:
         raise ValueError('Support Type {}'.format(TYPE_LIST))
    

# def check dtype
# def check_dtype(str_dtype, _series):
#     """ Description
#         -----------
#             Check the dtype of series

#         Parameters
#         -----------
#             str_type (str) : numeric, categorical, bool, time
#             _series (series) : series

#         example
#         -----------
#             check_dtype('numeric', series1)
#     """
 
#     _check_string(str_dtype)
#     _check_series(_series)
    
#     if str_dtype.lower() in DTYPE_LIST:
#         if str_dtype.lower() == 'numeric':
#             if 'int' in str(_series.dtypes) or 'float' in str(_series.dtypes):
#                 pass
#             else:
#                 raise ValueError('Series type : {}'.format(_series.dtypes))
#         elif str_dtype.lower() == 'categorical':
#             if 'object' in str(_series.dtypes):
#                 pass
#             else:
#                 raise ValueError('Series type : {}'.format(_series.dtypes))
#         elif str_dtype.lower() == 'bool':
#             if 'bool' in str(_series.dtypes):
#                 pass
#             else:
#                 raise ValueError('Series type : {}'.format(_series.dtypes))
#         elif str_dtype.lower() == 'time':
#             if 'ns' in str(_series.dtypes):
#                 pass
#             elif 'object' in str(_series.dtypes):
#                 if _check_time_series(_series) == True:
#                     pass
#                 else:
#                     raise ValueError('Series type : {}'.format(_series.dtypes))
#             else:
#                 raise ValueError('Series type : {}'.format(_series.dtypes))
#     else:
#          raise ValueError('Support Dtype {}'.format(DTYPE_LIST))
