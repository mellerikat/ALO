from src.constants import *
import shutil
from datetime import datetime
from src.s3handler import *
import tarfile 
from alolib import logger 
#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = logger.ProcessLogger(PROJECT_HOME)

#--------------------------------------------------------------------------------------------------------------------------

# FIXME pipeline name까지 추후 반영해야할지? http://clm.lge.com/issue/browse/DXADVTECH-352?attachmentSortBy=dateTime&attachmentOrder=asc
def external_load_data(pipe_mode, external_path, external_path_permission, get_external_data): 
    """ Description
        -----------
            - external_path로부터 데이터를 다운로드 
        Parameters
        -----------
            - pipe_mode: 호출 시의 파이프라인 (train_pipeline, inference_pipeline)
            - external_path: experimental_plan.yaml에 적힌 external_path 전체를 dict로 받아옴 
            - external_path_permission: experimental_plan.yaml에 적힌 external_path_permission 전체를 dict로 받아옴 
            - get_external_data: external data를 load하는 행위를 한 번만 할 지 여러번 할지 (once, every)
        Return
        -----------
            - 
        Example
        -----------
            - external_load_data(pipeline, self.external_path, self.external_path_permission, self.control['get_external_data'])
    """
    # None일 시, 혹은 str로 입력 시 type을 list로 통일하여 내부 변수화 
    ################################################################################################################
    train_data_path = [] if external_path['load_train_data_path'] is None else external_path['load_train_data_path']
    inference_data_path = [] if external_path['load_inference_data_path'] is None else external_path['load_inference_data_path']
    # 1개여서 str인 경우도 list로 바꾸고, 여러개인 경우는 그냥 그대로 list로 
    train_data_path = [train_data_path] if type(train_data_path) == str else train_data_path
    inference_data_path = [inference_data_path] if type(inference_data_path) == str else inference_data_path
    
    # yaml 오기입 관련 체크 
    ################################################################################################################
    # external path가 train, inference 둘다 존재 안하고, input 폴더도 비워져 있는 경우 체크 
    if (len(train_data_path) == 0) and (len(inference_data_path) == 0): 
        # 이미 input 폴더는 무조건 만들어져 있는 상태임 
        # FIXME input 폴더가 비어있으면 프로세스 종료, 뭔가 서브폴더가 있으면 사용자한테 존재하는 서브폴더 notify 후 yaml의 input_path에는 그 서브폴더들만 활용 가능하다고 notify
        # 만약 input 폴더에 존재하지 않는 서브폴더 명을 yaml의 input_path에 작성 시 input asset에서 에러날 것임   
        if len(os.listdir(INPUT_DATA_HOME)) == 0: # input 폴더 빈 경우 
            PROC_LOGGER.process_error(f'External path (load_train_data_path, load_inference_data_path) in experimental_plan.yaml are not written & << input >> folder is empty.') 
        else: 
            PROC_LOGGER.process_info('You can write only one of the << {} >> at << input_path >> parameter in your experimental_plan.yaml \n'.format(os.listdir(INPUT_DATA_HOME)), 'blue')
        return
    else: # load_train_data_path나 load_train_data_path 둘 중 하나라도 존재시 
        # load_train_data_path와 load_train_data_path 내 중복 mother path (마지막 서브폴더 명) 존재 시 에러 
        all_data_path = train_data_path + inference_data_path
        base_dir_list = [] 
        for ext_path in all_data_path: 
            base_dir = os.path.basename(os.path.normpath(ext_path)) 
            base_dir_list.append(base_dir)
        if len(set(base_dir_list)) != len(base_dir_list): # 중복 mother path 존재 경우 
            PROC_LOGGER.process_error(f"You may have entered paths which have duplicated base directory names. \n \
                                        For example, these are not allowed: \n \
                                        - load_train_data_path: /users/train/data/ \n \
                                        - load_inference_data_path: /users/inference/data/ \n \
                                        which have << data >> as duplicated base directory name.")
    
    # 미입력 시 every로 default 설정 
    if get_external_data is None:
        get_external_data = 'every'
        PROC_LOGGER.process_info('You did not entered << get_external_data >> control parameter in your experimental_plan.yaml \n << every >> is automatically set as default. \n', 'blue') 
    # once 나 every로 입력하지 않고 이상한 값 입력 시 혹은 비워놨을 시 에러 
    if get_external_data not in ['once', 'every']:
        PROC_LOGGER.process_error(f"Check your << get_external_data >> control parameter in experimental_plan.yaml. \n You entered: {get_external_data}. Only << once >> or << every >> is allowed.")
    ################################################################################################################
    # 현재 pipeline에 대해서 load할 데이터 경로 가져오기 
    # 대전제 : 중복 이름의 데이터 폴더명은 복사 허용 x 
    load_data_path = None 
    if pipe_mode == "train_pipeline": 
        load_data_path = train_data_path # 0개 일수도(None), 한 개 일수도(str), 두 개 이상 일수도 있음(list) 
    elif pipe_mode == "inference_pipeline":
        load_data_path = inference_data_path
    else: 
        PROC_LOGGER.process_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")

    # s3 key 경로 가져오기 
    load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str) or None 
    if load_s3_key_path is None: 
        PROC_LOGGER.process_info('You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n \
                                you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment. \n' , 'blue')
    else: 
        if type(load_s3_key_path) != str: 
            PROC_LOGGER.process_error(f"You entered wrong type of << s3_private_key_file >> in your expermimental_plan.yaml: << {load_s3_key_path} >>. \n Only << str >> type is allowed.")
        
    ################################################################################################################
    #  load external data 
    def _get_ext_path_type(_ext_path: str): # inner function 
        if 's3:/' in _ext_path: 
            return 's3'
        elif os.path.isabs(_ext_path) == True: # 절대경로. nas, local 둘다 가능 
            return 'absolute'
        elif os.path.isabs(_ext_path) == False: 
            PROC_LOGGER.process_error(f'<< {_ext_path} >> is relative path. This is unsupported type of external load data path. Please enter the absolute path.')
        else: 
            PROC_LOGGER.process_error(f'<< {_ext_path} >> is unsupported type of external load data path.')

    # copy (절대경로) or download (s3) data (input 폴더로)
    # get_external_data (once, every) 관련 처리
    for ext_path in load_data_path: 
        ext_type = _get_ext_path_type(ext_path)
        base_dir = os.path.basename(os.path.normpath(ext_path)) 
        if (base_dir in os.listdir(INPUT_DATA_HOME)) and (get_external_data == 'once'): # 이미 input 폴더에 존재하고, once인 경우 
            PROC_LOGGER.process_info(f" Skip loading external data. << {ext_path} >> \n << {base_dir} >> already exists in << {INPUT_DATA_HOME} >>. \n & << get_external_data >> is set as << once >>. \n", 'blue')
            continue 
        elif (base_dir in os.listdir(INPUT_DATA_HOME)) and (get_external_data == 'every'): # 이미 input 폴더에 존재하고, every인 경우 기존 거 지우고 다시 다운로드 
            PROC_LOGGER.process_info(f" << {base_dir} >> already exists in << {INPUT_DATA_HOME} >>. \n & << get_external_data >> is set as << every >>. \n Start re-loading external data. << {ext_path} >> : pre-existing directory is deleted ! \n", 'blue')
            shutil.rmtree(INPUT_DATA_HOME + base_dir, ignore_errors=True)
            _load_data(pipe_mode, ext_type, ext_path, load_s3_key_path)
        elif (base_dir not in os.listdir(INPUT_DATA_HOME)): # input 폴더에 부재하면, once던 every던 무조건 loading 함
            PROC_LOGGER.process_info(f" Start loading external data. << {ext_path} >>  \n << {base_dir} >> does not exist in << {INPUT_DATA_HOME} >>. \n & << get_external_data >> is set as << {get_external_data} >>. \n", 'blue')
            _load_data(pipe_mode, ext_type, ext_path, load_s3_key_path)
     
    return             

            
def _load_data(pipeline, ext_type, ext_path, load_s3_key_path): 
    # 실제로 데이터 복사 (절대 경로) or 다운로드 (s3) 
    if ext_type  == 'absolute':
        # 해당 nas 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
        # nas 접근권한 없으면 에러 발생 
        # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
        try: 
            # 사용자가 실수로 yaml external path에 마지막에 '/' 쓰든 안쓰든, (즉 아래 코드에서 '/'이든 '//' 이든 동작엔 이상X)
            # [참고] https://stackoverflow.com/questions/3925096/how-to-get-only-the-last-part-of-a-path-in-python
            base_dir = os.path.basename(os.path.normpath(ext_path)) # 가령 /nas001/test/ 면 test가 mother_path, ./이면 .가 mother_path 
            # [참고] python 3.7에서는 shutil.copytree 시 dirs_exist_ok라는 인자 없음 
            data_path = ""
            if "train" in pipeline:
                data_path = "./input/train/"
                if os.path.exists(data_path):
                    shutil.rmtree(data_path)
                os.makedirs(data_path, exist_ok=True) 
            elif "inf" in pipeline:
                data_path = "./input/inference/"
                if os.path.exists(data_path):
                    shutil.rmtree(data_path)
                os.makedirs(data_path, exist_ok=True) 
            shutil.copytree(ext_path, PROJECT_HOME + f"{data_path}{base_dir}", dirs_exist_ok=True) # 중복 시 덮어쓰기 됨 
        except: 
            PROC_LOGGER.process_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong absolute path (must be existing directory!) \n / or You do not have permission to access.')
    elif ext_type  == 's3':  
        # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
        # 해당 s3 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
        # s3 접근권한 없으면 에러 발생 
        # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
        s3_downloader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
        try: 
            s3_downloader.download_folder(INPUT_DATA_HOME)
        except:
            PROC_LOGGER.process_error(f'Failed to download s3 data folder from << {ext_path} >>')
    else: 
        # 미지원 external data storage type
        PROC_LOGGER.process_error(f'{ext_path} is unsupported type of external data path.') 
            
    return 

def external_save_artifacts(pipe_mode, external_path, external_path_permission):
    """ Description
        -----------
            - 생성된 .train_artifacts, /inference_artifacts를 압축하여 (tar.gzip) 외부 경로로 전달  
        Parameters
        -----------
            - pipe_mode: 호출 시의 파이프라인 (train_pipeline, inference_pipeline)
            - external_path: experimental_plan.yaml에 적힌 external_path 전체를 dict로 받아옴 
            - external_path_permission: experimental_plan.yaml에 적힌 external_path_permission 전체를 dict로 받아옴 
        Return
        -----------
            - 
        Example
        -----------
            - load_data(self.external_path, self.external_path_permission)
    """
    
    # external path가 train, inference 둘다 존재 안하는 경우 
    if (external_path['save_train_artifacts_path'] is None) and (external_path['save_inference_artifacts_path'] is None): 
        PROC_LOGGER.process_info('None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path. \n', 'blue')
        return
    
    save_artifacts_path = None 
    if pipe_mode == "train_pipeline": 
        save_artifacts_path = external_path['save_train_artifacts_path'] 
    elif pipe_mode == "inference_pipeline":
        save_artifacts_path = external_path['save_inference_artifacts_path']
    else: 
        PROC_LOGGER.process_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")

    if save_artifacts_path == None: 
        PROC_LOGGER.process_info(f'[@{pipe_mode}] None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path. \n', 'blue')
        return  
        
    # get s3 key 
    try:
        load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
        PROC_LOGGER.process_info(f's3 private key file << load_s3_key_path >> loaded successfully. \n', 'green')   
    except:
        PROC_LOGGER.process_info('You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment. \n' , 'blue')
        load_s3_key_path = None

    # external path가 존재하는 경우 
    def _get_ext_path_type(_ext_path: str): # inner function 
        if 's3:/' in _ext_path: 
            return 's3'
        elif os.path.isabs(_ext_path) == True: # 절대경로. nas, local 둘다 가능 
            return 'absolute'
        elif os.path.isabs(_ext_path) == False: # file이름으로 쓰면 에러날 것임 
            PROC_LOGGER.process_error(f'<< {_ext_path} >> is relative path. This is unsupported type of external save artifacts path. Please enter the absolute path.')
        else: 
            PROC_LOGGER.process_error(f'<< {_ext_path} >> is unsupported type of external save artifacts path.')

    # save artifacts 
    PROC_LOGGER.process_info(f" Start saving generated artifacts into external path << {save_artifacts_path} >>. \n", "blue")
    ext_path = save_artifacts_path
    ext_type = _get_ext_path_type(ext_path) # absolute / s3
    tar_path = None 
    if pipe_mode == "train_pipeline":
        tar_path = _tar_dir(".train_artifacts") 
    elif pipe_mode == "inference_pipeline": 
        tar_path = _tar_dir(".inference_artifacts") 
                
    if ext_type  == 'absolute':
        try: 
            os.makedirs(save_artifacts_path, exist_ok=True) 
            shutil.copy(tar_path, save_artifacts_path)
        except: 
            PROC_LOGGER.process_error(f'Failed to copy compressed artifacts from {tar_path} to << {ext_path} >>.')
        finally: 
            os.remove(tar_path)
    elif ext_type  == 's3':  
        # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
        # s3 접근권한 없으면 에러 발생 
        s3_uploader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
        try: 
            s3_uploader.upload_file(tar_path)
        except:
            PROC_LOGGER.process_error(f'Failed to upload {tar_path} onto << {ext_path} >>')
        finally: 
            os.remove(tar_path)
    else: 
        # 미지원 external data storage type
        PROC_LOGGER.process_error(f'{ext_path} is unsupported type of external data path.') 
    
    PROC_LOGGER.process_info(f" Successfully done saving << {tar_path} >> into << {save_artifacts_path} >> \n & removing << {tar_path} >>. \n", "green")  
    return 

def _tar_dir(_path): # inner function 
    # _path: .train_artifacts / .inference_artifacts 
    timestamp_option = True
    hms_option = True
    if timestamp_option == True:  
        if hms_option == True : 
            timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
        else : 
            timestamp = datetime.now().strftime("%y%m%d")      
    _save_path = PROJECT_HOME + f'{timestamp}_{_path}.tar.gz'
    
    tar = tarfile.open(_save_path, 'w:gz')
    for root, dirs, files in os.walk(PROJECT_HOME  + _path):
        for file_name in files:
            tar.add(os.path.join(root, file_name))
    tar.close()
    
    return _save_path