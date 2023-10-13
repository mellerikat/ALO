
import inspect
import json
import boto3
import enum

from alolib.exception import _check_string

VERSION='v.0.8.0'


################################################################################
# "   type        sub_type         summary                  msg"
# "[dataLoad][dataInput] 데이터가 입력되지 않았습니다. 데이터를 확인하세요"

# "[dataLoad][dataInput] 데이터가 입력되지 않았습니다. X_columns 를 입력하세요."

# "[dataLoad][dataInput] 데이터가 입력되지 않았습니다. y_columns 를 입력하세요."
################################################################################

""" Description
            -----------
                enum class

            Parameters
            -----------
                None

                option:
                    class method
                        enum to list

            example
            -----------
                Type.list()
"""
# enum 내부 value들을 enum타입이 아닌 지정된 타입으로 리턴 받는 경우 사용
class ExtendedEnum(enum.Enum): 

    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))

# level enum type 
class Level(ExtendedEnum): 
    ERROR = 'error'
    WARNING = 'warning'
    INFO = 'info'
    ETC = 'etc'

# type list    
class Type(ExtendedEnum): 
    DATALOAD = 'DataLoad'
    DATACHECK = 'DataCheck'
    DATAUPLOAD = 'DataUpload'
    DATASAVE = 'DataSave'
    STORAGECHECK = 'StorageCheck'
    DATAPREPROCESS = 'DataPreprocess'
    INFERENCERUN = 'InferenceRun'
    INFERENCEMODEL = 'InferenceModel'
    VERSIONCHECK = 'VersionCheck'
    LOGTYPE = 'LogType'
    UNKNOWN = 'UNKNOWN'

    ## check
    TRAIN = 'TRAIN'
    INFERENCE = 'INFERENCE'
    YAML = 'YAML'
    PARAMS = 'PARAMS'
    MODULE = 'MODULE'
    VALUE = 'VALUE'
    MODEL = 'MODEL'
    ASSET = 'ASSET'
    METADATA = 'Metadata'

# sub type list
class SubType(ExtendedEnum):

########################## interface : file, directory #####################################
    DATANOTFOUND = ('DataNotFound', '데이터를 찾을 수 없습니다.')
    DATANOTMAKE = ('DataNotMake', '파일 또는 폴더를 생성할 수 없습니다.')
    FILENOTFOUND = ('FileNotFound', '파일을 찾을 수 없습니다.')
    FILEFOUND = ('FileFound', '파일이 존재합니다.')
    FILEMAKE = ('FileMake', '파일을 생성합니다.')
    RESPONSENOTMAKE = ('ResponseNotMake', '파일 또는 폴더를 생성할 수 없습니다.')
    INTERFACENOTMAKE = ('InferfaceNotMake', '인터페이스 해당하는 데이터를 생성할 수 없습니다.')
    STORAGECONNECT = ('StorageInit', '저장공간에 연결할 수 없습니다.')
    STORAGEFULL = ('StorageFull', '저장공간의 남은 용량이 경고/에러 수준입니다.')
    STORAGEUNKNOWN = ('StorageUnknown', '저장공간의 위치 및 용량을 확인할 수 없습니다.')
    FILEREDUNDANCY = ('FileRedundancy', '중복되는 파일이 존재합니다.')
    PERMISSIONDINIED = ('PermissionDenied', '권한이 없습니다.')
    DATANOTDELETE = ('DataNotDelete', '파일 또는 폴더를 삭제할 수 없습니다.')


########################## data ############################################################
    DATAINCONSISTENCY= ('DataInconsistency', '데이터가 불일치합니다.')
    DATAREADSUCCESS = ('DataReadSuccess', '데이터 읽기에 성공하였습니다.')
    DATANOTCONVERSION = ('DataNotConversion', '데이터 변환 과정에서 문제가 발생하였습니다.')
    DATAEMPTY = ('DataEmpty', '데이터가 비어있습니다.')
    DATAUPDATE = ('DataUpdate', '데이터를 수정(업데이트) 합니다.')
    APIPARAMINVALID = ('apiParamInvalid', '유효하지 않은 API 입력입니다')    


########################## model ###########################################################
    MODELNOTLOAD = ('ModelNotLoad', '모델를 Load 할 수 없습니다.')
    MODELNOTSETUP = ('ModelNotSetup', '모델을 준비하는 과정에서 문제가 발생하였습니다.')


########################## unsupport #######################################################
    UNSUPPORTEDITEM = ('UnsupportedItem', '지원하지 않는 값입니다.')
    UNSUPPORTEDTYPE = ('UnsupportedType', '지원하지 않는 데이터 형식입니다.')
    UNSUPPORTEDMODE = ('UnsupportedMode', '지원하지 않는 모드입니다.')
    UNSUPPORTEDMODEL = ('UnsupportedModel', '지원하지 않는 모델입니다.')


########################## run #############################################################
    RUNTIMEOVER = ('RunTimeOver', '계산 과정이 예상시간을 초과하였습니다.' )
    RUNERROR = ('RunError', '계산 과정 중에 에러가 발생하였습니다.')
    INITERROR = ('InitError', '초기화 과정에서 에러가 발생하였습니다.')


########################## info ############################################################
    INFERENCEINFO = ('InferenceInfo', '추론 정보를 출력합니다.')
    STORAGEINFO = ('StorageInfo', '저장공간 정보를 출력합니다.')
    RESTAPIINFO = ('RestApiInfo', 'REST API 정보를 출력합니다.')
    PREPROCESSINFO = ('PreprocessInfo', '전처리 진행 정보 입니다.')
    DATACUSTOMINFO = ('DataCustomInfo', '계산된 데이터 정보를 출력합니다.')
    UNDERTHRESHOLD = ('UnderThreshold','결과값이 Threshold 를 만족하지 못했습니다.' )
    ORIGININFO = ('OriginInfo', '원본 데이터 정보를 출력합니다.')
    OUTPUTINFO = ('OutputInfo', '데이터 Output 정보를 출력합니다.')


########################## etc #############################################################
    UNKNOWN = ('UNKNOWN', 'collab을 문의해주세요')
    SUBTYPEERROR = ('SubTypeError', 'not support SubType')
    KEYERROR = ('KeyError', 'Dictionary Key가 없습니다.')



########################## check ###########################################################
    DATAINPUT = ('DATAINPUT', '데이터가 입력되지 않았습니다')
    DATAVOLUME = ('DATAVOLUME', '데이터 볼륨을 확인하세요')
    DATASPLIT = ('DATASPLIT', 'No Summary')
    INGNORECOLUMN = ('INGNORECOLUMN', 'ignore_columns를 입력해주세요')
    GROUPKEY = ('GROUPKEY', 'No Summary')
    ARGS = ('ARGS', 'No Summary')
    MODULE = ('MODULE', '모듈을 확인하세요')
    NOTFOUND = ('NOTFOUND', '파일이 없습니다')
    TRAIN = ('TRAIN', 'No Summary')
    CSV = ('CSV', 'No Summary')
    FUNCTION = ('FUNCTION', 'No Summary')
    LOSSFUNCTION = ('LOSSFUNCTION', 'No Summary')


    def __init__(self, title, summary):
        self.title = title
        self.summary = summary

    @classmethod
    def list(cls):
        return list(map(lambda c: c.title, cls))



# error 를 발생하는 경우에만 사용(문법 적인 오류 등에서 사용하는 enum)
class ErrorType(ExtendedEnum):
    CRITICAL = 'CRITICAL'


class ErrorSubType(ExtendedEnum):
    CRITICAL = ('CRITICAL', '사용 함수에 사용 방법을 확인하세요')

    def __init__(self, title, summary):
        self.title = title
        self.summary = summary

    @classmethod
    def list(cls):
        return list(map(lambda c: c.title, cls))


class AipLogger:
    

    def __init__(self, name=None, version=None):

        """ Description
            -----------
                logger class

            Parameters
            -----------
                name(str) : module name
                version(str) : module version

            example
            -----------
                log = AipLogger() or
                log = AipLogger(name, version)
    """

        self.level = ''

        self.log = {
            "name":name,
            "version":version
        }
        
        
    def _log_type_error(self, _msg): 
        
        # 추가 필요한 log type이 있는 경우
        error_msg = f'[Error] {_msg}'
        print(error_msg)


    def aip_error_body(self, _type, _sub_type, _msg):

        self.level = Level.ERROR.value

        # log 하기전 type들을 체크
        self._check_type(_type.value, _sub_type.title) 
        msg = f"[{_type.value}][{_sub_type.title}][{_sub_type.summary}] {_msg}"

        # 1 : caller aip_error_body
        # 2 : caller aip_error
        caller = inspect.stack()[2] 

        # {msg}
        # filename 에 func 함수에서 에러가 발생했습니다
        # line xx를 확인해주세요
        error_msg = f'{msg} \n {caller.filename} 에 {caller.function} 함수에서 에러가 발생했습니다. \n \
        (line : {caller.lineno})을 확인해 주세요'
        return error_msg 


    def aip_error(self, _type, _sub_type, _msg):
        """ Description
            -----------
                error 발생시 log에 저장하고 valueError를 호출한다

            Parameters
            -----------
                _type (enum, str): log의 대분류 타입 (class Type 중 입력)
                _sub_type (enum, str): log의 소분류 타입 (class SubType 중 입력)
                _msg (str) : 로그 메시지

            example
            -----------
                aip_error(_type, _sub_type, _msg)
        """
        error_msg = self.aip_error_body(_type, _sub_type, _msg)
        raise ValueError(error_msg)


    def aip_warning_body(self, _type, _sub_type, _msg): 
        self.level = Level.WARNING.value
       
        self._check_type(_type.value, _sub_type.title)
                
        msg = f"[{_type.value}][{_sub_type.title}][{_sub_type.summary}] {_msg}"
        _check_string(msg)

        print(f'aiplib.logger.{Level.WARNING.value} : {msg}')
        return msg


    def aip_warning(self, _type, _sub_type, _msg): 
        """ Description
            -----------
                warning msg를 log 에 추가

            Parameters
            -----------
                _type (enum, str): log의 대분류 타입 (class Type 중 입력)
                _sub_type (enum, str): log의 소분류 타입 (class SubType 중 입력)
                _msg (str) : 로그 메시지

            example
            -----------
                aip_warning(_type, _sub_type, _msg)
        """
        msg = self.aip_warning_body(_type, _sub_type, _msg)
        self.add_log(Level.WARNING, self.log, msg)


    def aip_info_body(self, _type, _sub_type, _msg):
        self.level = Level.INFO.value
        
        self._check_type(_type.value, _sub_type.title)

        msg = f"[{_type.value}][{_sub_type.title}][{_sub_type.summary}] {_msg}"
        _check_string(msg)

        print(f'aiplib.logger.{Level.INFO.value} : {msg}')
        return msg


    def aip_info(self, _type, _sub_type, _msg):
        """ Description
            -----------
                info msg를 log 에 추가

            Parameters
            -----------
                _type (enum, str): log의 대분류 타입 (class Type 중 입력)
                _sub_type (enum, str): log의 소분류 타입 (class SubType 중 입력)
                _msg (str) : 로그 메시지

            example
            -----------
                aip_info(_type, _sub_type, _msg)
        """
        msg = self.aip_info_body(_type, _sub_type, _msg) 
        self.add_log(Level.INFO, self.log, msg)


    def add_log(self, _level, _log, _msg):
        """ Description
            -----------
                msg를 level에 맞게 log에 삽입해준다

            Parameters
            -----------
                _level (eunm, str) : 현재 로그의 레벨 (error, warning, info, etc)
                _log (dict, str) : 현재 작성중인 log dict
                _msg (str) : 로그 메시지

            example
            -----------
                add_log("_level", _log, _msg)
        """
        # 현재 levels는 enum 타입의 str
        if _level.value in Level.list():
            try:
                _log[_level.value].append(_msg)
            except KeyError:
                _log[_level.value] = [_msg] #init: empty
            except AttributeError:
                #init : _log[warning] = 123
                if len(str(_log[_level.value])) > 0:
                    #init : _log[warning] = [123]
                    _log[_level.value] = [_log[_level.value]] 
                    #init : _log[warning] = [123, msg]
                    _log[_level.value].append(_msg)
                #init : _log[warning] = ''
                else:
                    _log[_level.value] = [_msg]
        # 현재 Level enum에 입력되지 않은 값을 넣었을 경우
        else:
            self.aip_error(Type.DATACHECK, SubType.DATAINCONSISTENCY, '로그 dict의 key레벨은 Level enum에서 선택하셔야 합니다')


    def _check_type(self, _type, _sub_type_title):

        # type, subtype 이 ErrorType, ErrorSubType 인경우
        if _type is ErrorType.CRITICAL:
            if _sub_type_title is ErrorSubType.CRITICAL.title:
                # level이 error인 경우는 pass
                if self.level is Level.ERROR:
                    pass
                # level이 error가 아닌 경우
                else:
                    self.aip_error(Type.DATACHECK, SubType.DATAINCONSISTENCY, 'ErrorType은 Error에서만 사용 가능합니다')
            # sub_type이 ErrorSubType이 아닌 경우는 현재 지원하지 않기 떄문에 error
            else:
                self.aip_error(Type.DATACHECK, SubType.DATAINCONSISTENCY, 'Critical은 현재 sub Critical만 존재 합니다. collab에 문의해주세요')
        else:
            pass

        #입력된 log type이 TYPE enum의 튜플에 있으면 하위 type을 비교    
        if _type in Type.list(): 
            # 입력된 하위 log type이 sub type enum 튜플과 비교
            if _sub_type_title in SubType.list(): 
                pass
            else: # _sub_type_title else
                self.aip_error(Type.LOGTYPE, SubType.SUBTYPEERROR, f'{_sub_type_title}은 지정된 SubType이 아닙니다. collab을 문의해주세요')

        # 내가 에러라는 레벨에서 타입을 크리티컬로 썻을 때
        # warning, info 에서는 사용하면 안됨
        elif _type in ErrorType.list():
            if _sub_type_title in ErrorSubType.list():
                if _sub_type_title == 'CRITICAL':
                    pass
                else:
                    self.aip_error(Type.LOGTYPE, SubType.SUBTYPEERROR, f'{_sub_type_title}은 지정된 SubType이 아닙니다. collab을 문의해주세요')
            else:
                self.aip_error(Type.UNKNOWN, SubType.UNKNOWN, 'Critical Error는 aip_error에서만 사용 가능합니다')

        else: # log_type else
            self.aip_error(Type.LOGTYPE, SubType.TYPEERROR, f'{_type}은 지정된 Type이 아닙니다. collab을 문의해주세요')


    def save_log(self, _json_data, _json_file):
        """ Description
            -----------
                저장된 log를 파일로 저장한다

            Parameters
            -----------
                _json_data (dict, str) : log 데이터
                _json_file (str) : 저장되는 log 파일 name

            example
            -----------
                save_log(log_data, log_file_name)
        """
        try:
            if self.input_mode == 's3':
                # ready
                if _json_file.startswith('/'):
                    # _json_file : /bucket_name/index_code/
                    _json_file = _json_file[1:]
                else:
                    # _json_file : bucket_name/index_code/
                    pass

                bucket_name = _json_file.split('/')[0]
                # NOTE : +1 -> remove '/'
                index_code = _json_file[len(bucket_name) + 1:]
                encode_data = bytes(json.dumps(_json_data).encode('UTF-8'))

                s3_client = boto3.client('s3')
                s3_client.put_object(Body=encode_data, Bucket=bucket_name, Key=index_code)
            # self.input_mode == 'nas'
            else:
                self.check_path(_json_file)
                with open(_json_file, "w") as f:
                    # ensure_ascii=False : 한글 지원
                    json.dump(_json_data, f, indent=4, ensure_ascii=False)

            print('saved : {}'.format(_json_file))
        except:
            raise ValueError('Failed to save : {}'.format(_json_file))
   

if __name__ == "__main__":
    log = AipLogger()
    
    print(type(SubType.NOTFOUND))

    # 잘 진행되는 예제
    log.aip_warning(Type.DATALOAD, SubType.NOTFOUND, '데이터가 값이 입력되지 않았습니다')
    # 현재 입력되어 있지 않은 SubType으로 collab에 문의 해 달라는 에러가 나오는 예제
    log.aip_info(Type.MODEL, SubType.LOSSFUNCTION, "현제 모델에 성능을 확신 할 수 없습니다") 
    # 잘 진행되는 Critical error 예제 -> try catch로 잡아서 사용
    log.aip_error(ErrorType.CRITICAL, ErrorSubType.CRITICAL, "코딩 에러 입니다")
    
