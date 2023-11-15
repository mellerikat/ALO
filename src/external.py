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
# artifacts.tar.gz (혹은 model.tar.gz) 압축 파일을 외부 업로드하기 전 로컬 임시 저장 경로 
TEMP_TAR_DIR = PROJECT_HOME + '.temp_tar_dir/'
# 외부 model.tar.gz (혹은 부재 시 해당 경로 폴더 통째로)을 .train_artifacts/models 경로로 옮기기 전 임시 저장 경로 
TEMP_MODEL_DIR = PROJECT_HOME + '.temp_model_dir/'
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
            - external_load_data(pipe_mode, self.external_path, self.external_path_permission, self.control['get_external_data'])
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
            PROC_LOGGER.process_info('External paths are not written. You can write only one of the << {} >> at << input_path >> parameter in your experimental_plan.yaml \n'.format(os.listdir(INPUT_DATA_HOME)), 'blue')
        return
    else: # load_train_data_path나 load_train_data_path 둘 중 하나라도 존재시 
        # load_train_data_path와 load_train_data_path 내 중복 mother path (마지막 서브폴더 명) 존재 시 에러 
        for data_path in  [train_data_path, inference_data_path]:
            base_dir_list = [] 
            for ext_path in data_path: 
                base_dir = os.path.basename(os.path.normpath(ext_path)) 
                base_dir_list.append(base_dir)
            if len(set(base_dir_list)) != len(base_dir_list): # 중복 mother path 존재 경우 
                PROC_LOGGER.process_error(f"You may have entered paths which have duplicated basename in the same pipeline. \n \
                                            For example, these are not allowed: \n \
                                            - load_train_data_path: [/users/train1/data/, /users/train2/data/] \n \
                                            which have << data >> as duplicated basename of the path.")
        
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
                                you have to write the s3_private_key_file path or set << AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY >> in your os environment. \n' , 'blue')
    else: 
        if type(load_s3_key_path) != str: 
            PROC_LOGGER.process_error(f"You entered wrong type of << s3_private_key_file >> in your expermimental_plan.yaml: << {load_s3_key_path} >>. \n Only << str >> type is allowed.")
    
    data_path = ""
    if "train" in pipe_mode:
        data_path = INPUT_DATA_HOME + "train/"
    elif "inf" in pipe_mode:
        data_path = INPUT_DATA_HOME + "inference/"
    if not os.path.exists(data_path):
        os.mkdir(data_path)
    
    # copy (절대경로) or download (s3) data (input 폴더로)
    # get_external_data (once, every) 관련 처리
    for idx, ext_path in enumerate(load_data_path): 
        ext_type = _get_ext_path_type(ext_path)
        base_dir = os.path.basename(os.path.normpath(ext_path)) 
        if (base_dir in os.listdir(data_path)) and (get_external_data == 'once'): # 이미 input 폴더에 존재하고, once인 경우 
            PROC_LOGGER.process_info(f" Skip loading external data. << {ext_path} >> \n << {base_dir} >> already exists in << {data_path} >>. \n & << get_external_data >> is set as << once >>. \n", 'blue')
            continue 
        elif (get_external_data == 'every'): # every인 경우 무조건 기존 거 처음에 다 지우고 다시 다운로드 
            PROC_LOGGER.process_info(f" << {base_dir} >> already exists in << {data_path} >>. \n & << get_external_data >> is set as << every >>. \n Start re-loading external data. << {ext_path} >> : pre-existing directory is deleted ! \n", 'blue')
            if idx ==0: 
                shutil.rmtree(data_path, ignore_errors=True)
            _load_data(pipe_mode, ext_type, ext_path, load_s3_key_path)
        elif (base_dir not in os.listdir(data_path)) and (get_external_data == 'once'): # 특정 base folder가 input 폴더에 부재하고, once면 input을 다 비우진 않고 해당 base folder만 새로 loading 함
            PROC_LOGGER.process_info(f" Start loading external data. << {ext_path} >>  \n << {base_dir} >> does not exist in << {data_path} >>. \n & << get_external_data >> is set as << {get_external_data} >>. \n", 'blue')
            _load_data(pipe_mode, ext_type, ext_path, load_s3_key_path)
     
    return             

            
def _load_data(pipeline, ext_type, ext_path, load_s3_key_path): 
    # 실제로 데이터 복사 (절대 경로) or 다운로드 (s3) 
    data_path = ""
    if "train" in pipeline:
        data_path = INPUT_DATA_HOME + "train/"
    elif "inf" in pipeline:
        data_path = INPUT_DATA_HOME + "inference/"
    if ext_type  == 'absolute':
        # 해당 nas 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
        # nas 접근권한 없으면 에러 발생 
        # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
        try: 
            # 사용자가 실수로 yaml external path에 마지막에 '/' 쓰든 안쓰든, (즉 아래 코드에서 '/'이든 '//' 이든 동작엔 이상X)
            # [참고] https://stackoverflow.com/questions/3925096/how-to-get-only-the-last-part-of-a-path-in-python
            base_dir = os.path.basename(os.path.normpath(ext_path)) # 가령 /nas001/test/ 면 test가 mother_path, ./이면 .가 mother_path 
            # [참고] python 3.7에서는 shutil.copytree 시 dirs_exist_ok라는 인자 없음 
            os.makedirs(data_path, exist_ok=True) 
            shutil.copytree(ext_path, f"{data_path}{base_dir}", dirs_exist_ok=True) # 중복 시 덮어쓰기 됨 
        except: 
            PROC_LOGGER.process_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong absolute path (must be existing directory!) \n / or You do not have permission to access.')
    elif ext_type  == 's3':  
        # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
        # 해당 s3 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
        # s3 접근권한 없으면 에러 발생 
        # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
        try: 
            s3_downloader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
            s3_downloader.download_folder(data_path)
        except:
            PROC_LOGGER.process_error(f'Failed to download s3 data folder from << {ext_path} >>')
    else: 
        # 미지원 external data storage type
        PROC_LOGGER.process_error(f'{ext_path} is unsupported type of external data path.') 
        
    PROC_LOGGER.process_info(f'Successfully fetched external data: \n {ext_path} --> {f"{data_path}"}', color='green')
    return 


def external_load_model(external_path, external_path_permission): 
    '''
    # external_load_model은 inference pipeline에서만 실행함 (alo.py에서)
    # external_load_model은 path 하나만 지원 (list X --> str only)
    # external_path에 (local이든 s3든) model.tar.gz이 있으면 해당 파일을 .train_artifacts/models/ 에 압축해제 
    # model.tar.gz이 없으면 그냥 external_path 밑에 있는 파일(or 서브폴더)들 전부 .train_artifacts/models/ 로 copy
    '''
    ####################################################################################################
    models_path = PROJECT_HOME + '.train_artifacts/models/'
    # .train_artifacts/models 폴더 비우기
    try: 
        if os.path.exists(models_path) == False: 
             os.makedirs(models_path)
        else:    
            shutil.rmtree(models_path, ignore_errors=True)
            os.makedirs(models_path)
            PROC_LOGGER.process_info(f"Successfully emptied << {models_path} >> ")
    except: 
        PROC_LOGGER.process_error(f"Failed to empty & re-make << {models_path} >>")
    ####################################################################################################  
    ext_path = external_path['load_model_path']

    # get s3 key 
    try:
        load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
        PROC_LOGGER.process_info(f's3 private key file << load_s3_key_path >> loaded successfully. \n', 'green')   
    except:
        PROC_LOGGER.process_info('You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment. \n' , 'blue')
        load_s3_key_path = None
    
    PROC_LOGGER.process_info(f"Start load model from external path: << {ext_path} >>. \n", "blue")
    
    ext_type = _get_ext_path_type(ext_path) # absolute / s3

    # temp model dir 생성 
    if os.path.exists(TEMP_MODEL_DIR):
        shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
        os.makedirs(TEMP_MODEL_DIR)
    else: 
        os.makedirs(TEMP_MODEL_DIR)
        
    if ext_type  == 'absolute':
        try: 
            if 'model.tar.gz' in os.listdir(ext_path):
                shutil.copy(ext_path + 'model.tar.gz', TEMP_MODEL_DIR)  
                tar = tarfile.open(TEMP_MODEL_DIR + 'model.tar.gz') # model.tar.gz은 models 폴더를 통째로 압축한것 
                # FIXME [주의] 만약 models를 통째로 압축한 model.tar.gz 이 아니고 내부 구조가 다르면 이후 진행과정 에러날 것임 
                #압축시에 절대경로로 /home/~ ~/models/ 경로 전부 다 저장됐다가 여기서 해제되므로 models/ 경로 이후 것만 압축해지 필요  
                tar.extractall(TEMP_MODEL_DIR) 
                tar.close() 
                if 'models' in os.listdir(TEMP_MODEL_DIR):
                    for i in os.listdir(TEMP_MODEL_DIR + 'models/'):
                        shutil.move(TEMP_MODEL_DIR + 'models/' + i, models_path + i) 
                else: 
                    PROC_LOGGER.process_error(f'No << models >> directory exists in the model.tar.gz extracted path << {TEMP_MODEL_DIR} >>') 
            else: 
                base_norm_path = os.path.basename(os.path.normpath(ext_path)) + '/' # ex. 'aa/bb/' --> bb/
                os.makedirs(TEMP_MODEL_DIR + base_norm_path)
                shutil.copytree(ext_path, TEMP_MODEL_DIR + base_norm_path, dirs_exist_ok=True)
                for i in os.listdir(TEMP_MODEL_DIR + base_norm_path):
                    shutil.move(TEMP_MODEL_DIR + base_norm_path + i, models_path + i) 
            PROC_LOGGER.process_info(f'Success << external load model >> from << {ext_path} >> \n into << {models_path} >>', color='green')
        except:
            PROC_LOGGER.process_error(f'Failed to external load model from {ext_path} into {models_path}')
        finally:
            # TEMP_MODEL_DIR는 삭제 
            shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
            
    elif ext_type  == 's3':
        try: 
            s3_downloader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
            model_existence = s3_downloader.download_model(TEMP_MODEL_DIR) # 해당 s3 경로에 model.tar.gz 미존재 시 False, 존재 시 다운로드 후 True 반환
            if model_existence: # TEMP_MODEL_DIR로 model.tar.gz 이 다운로드 된 상태 
                tar = tarfile.open(TEMP_MODEL_DIR + 'model.tar.gz')
                #압축시에 절대경로로 /home/~ ~/models/ 경로 전부 다 저장됐다가 여기서 해제되므로 models/ 경로 이후 것만 옮기기 필요  
                tar.extractall(TEMP_MODEL_DIR)
                tar.close()

                if 'models' in os.listdir(TEMP_MODEL_DIR):
                    for i in os.listdir(TEMP_MODEL_DIR + 'models/'):
                        shutil.move(TEMP_MODEL_DIR + 'models/' + i, models_path + i) 
                else: 
                    PROC_LOGGER.process_error(f'No << models >> directory exists in the model.tar.gz extracted path << {TEMP_MODEL_DIR} >>') 
            else:
                PROC_LOGGER.process_warning(f"No << model.tar.gz >> exists in the path << ext_path >>. \n Instead, try to download the all of << ext_path >> ")
                s3_downloader.download_folder(models_path)  
            PROC_LOGGER.process_info(f'Success << external load model >> from << {ext_path} >> \n into << {models_path} >>', color='green')
        except:
            PROC_LOGGER.process_error(f'Failed to external load model from {ext_path} into {models_path}')
        finally:
            # TEMP_MODEL_DIR는 삭제 
            shutil.rmtree(TEMP_MODEL_DIR, ignore_errors=True)
    else: 
        # 미지원 external model storage type
        PROC_LOGGER.process_error(f'{ext_path} is unsupported type of external model path.') 
        
def external_save_artifacts(pipe_mode, external_path, external_path_permission):
    """ Description
        -----------
            - 생성된 .train_artifacts, /inference_artifacts를 압축하여 (tar.gzip) 외부 경로로 전달  
        Parameters
        -----------
            - proc_start_time: alo runs start 시간 
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
    # save artifacts 
    PROC_LOGGER.process_info(f" Start saving generated artifacts into external path << {save_artifacts_path} >>. \n", "blue")
    ext_path = save_artifacts_path
    ext_type = _get_ext_path_type(ext_path) # absolute / s3
    artifacts_tar_path = None 
    model_tar_path = None 
    if pipe_mode == "train_pipeline":
        artifacts_tar_path = _tar_dir(".train_artifacts") 
        model_tar_path = _tar_dir(".train_artifacts/models") 
    elif pipe_mode == "inference_pipeline": 
        artifacts_tar_path = _tar_dir(".inference_artifacts") 
        model_tar_path = _tar_dir(".inference_artifacts/models") 
                
    if ext_type  == 'absolute':
        try: 
            os.makedirs(save_artifacts_path, exist_ok=True) 
            shutil.copy(artifacts_tar_path, save_artifacts_path)
            shutil.copy(model_tar_path, save_artifacts_path)
        except: 
            PROC_LOGGER.process_error(f'Failed to copy compressed artifacts from << {artifacts_tar_path} >> & << {model_tar_path} >> into << {ext_path} >>.')
        finally: 
            os.remove(artifacts_tar_path)
            os.remove(model_tar_path)
            # [중요] 압축 파일 업로드 끝나면 TEMP_TAR_DIR 삭제 
            shutil.rmtree(TEMP_TAR_DIR, ignore_errors=True)
            
    elif ext_type  == 's3':  
        try: 
            # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
            # s3 접근권한 없으면 에러 발생 
            s3_uploader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
            s3_uploader.upload_file(artifacts_tar_path)
            s3_uploader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
            s3_uploader.upload_file(model_tar_path)
        except:
            PROC_LOGGER.process_error(f'Failed to upload << {artifacts_tar_path} >> & << {model_tar_path} >> onto << {ext_path} >>')
        finally: 
            os.remove(artifacts_tar_path)
            os.remove(model_tar_path)
            # [중요] 압축 파일 업로드 끝나면 TEMP_TAR_DIR 삭제 
            shutil.rmtree(TEMP_TAR_DIR, ignore_errors=True)
    else: 
        # 미지원 external data storage type
        PROC_LOGGER.process_error(f'{ext_path} is unsupported type of external data path.') 
    
    PROC_LOGGER.process_info(f" Successfully done saving << {artifacts_tar_path} >> & << {model_tar_path} >> \n onto << {save_artifacts_path} >> & removing local files.", "green")  
    
    return 

## Common Func. 
def _get_ext_path_type(_ext_path: str): # inner function 
    if 's3:/' in _ext_path: 
        return 's3'
    elif os.path.isabs(_ext_path) == True: # 절대경로. nas, local 둘다 가능 
        return 'absolute'
    elif os.path.isabs(_ext_path) == False: # file이름으로 쓰면 에러날 것임 
        PROC_LOGGER.process_error(f'<< {_ext_path} >> is relative path. This is unsupported type of external save artifacts path. Please enter the absolute path.')
    else: 
        PROC_LOGGER.process_error(f'<< {_ext_path} >> is unsupported type of external save artifacts path.')
            
def _tar_dir(_path): 
    ## _path: .train_artifacts / .inference_artifacts     
    os.makedirs(TEMP_TAR_DIR, exist_ok=True)
    last_dir = None
    if 'models' in _path: 
        _save_path = TEMP_TAR_DIR + 'model.tar.gz'
        last_dir = 'models/'
    else: 
        _save_file_name = _path.strip('.') 
        _save_path = TEMP_TAR_DIR +  f'{_save_file_name}.tar.gz' 
        last_dir = _path # ex. .train_artifacts/
    tar = tarfile.open(_save_path, 'w:gz')
    for root, dirs, files in os.walk(PROJECT_HOME  + _path):
        base_dir = last_dir + root.split(last_dir)[-1] + '/' # ex. /home/~~/models/ --> models/
        for file_name in files:
            #https://stackoverflow.com/questions/2239655/how-can-files-be-added-to-a-tarfile-with-python-without-adding-the-directory-hi
            tar.add(os.path.join(root, file_name), arcname = base_dir + file_name) # /home부터 시작하는 절대 경로가 아니라 .train_artifacts/ 혹은 moddels/부터 시작해서 압축해야하므로 
    tar.close()
    
    return _save_path