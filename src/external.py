from src.constants import *
import shutil
from datetime import datetime
from src.s3handler import *
from src.message import print_color, asset_error

# FIXME pipeline name까지 추후 반영해야할지? http://clm.lge.com/issue/browse/DXADVTECH-352?attachmentSortBy=dateTime&attachmentOrder=asc
def external_load_data(pipe_mode, external_path, external_path_permission): 
    """ Description
        -----------
            - external_path로부터 데이터를 다운로드 
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
    
    ## FIXME 진짜 input 데이터 지우고 시작하는게 맞을지 검토필요 
    # fetch_data 할 때는 항상 input 폴더 비우고 시작한다 
    if os.path.exists(INPUT_DATA_HOME):
        for file in os.scandir(INPUT_DATA_HOME):
            print_color(f">> Start removing pre-existing input data before fetching external data: {file.name}", "blue") # os.DirEntry.name 
            shutil.rmtree(file.path)
            
    # external path가 train, inference 둘다 존재 안하는 경우 
    if ( external_path['load_train_data_path'] is None) and (external_path['load_inference_data_path'] is None): 
        # 이미 input 폴더는 무조건 만들어져 있는 상태임 
        # FIXME input 폴더가 비어있으면 프로세스 종료, 뭔가 서브폴더가 있으면 사용자한테 존재하는 서브폴더 notify 후 yaml의 input_path에는 그 서브폴더들만 활용 가능하다고 notify
        # 만약 input 폴더에 존재하지 않는 서브폴더 명을 yaml의 input_path에 작성 시 input asset에서 에러날 것임   
        if len(os.listdir(INPUT_DATA_HOME)) == 0: # input 폴더 빈 경우 
            asset_error(f'External path (load_train_data_path, load_inference_data_path) in experimental_plan.yaml are not written & << input >> folder is empty.') 
        else: 
            print_color('[NOTICE] You can write only one of the << {} >> at << input_path >> parameter in your experimental_plan.yaml'.format(os.listdir(INPUT_DATA_HOME)), 'yellow')
        return
    
    # load할 데이터 경로 가져오기 
    # 대전제 : 중복 이름의 데이터 폴더명은 복사 허용 x 
    load_data_path = None 
    if pipe_mode == "train_pipeline": 
        load_data_path = external_path['load_train_data_path'] # 0개 일수도(None), 한 개 일수도(str), 두 개 이상 일수도 있음(list) 
    elif pipe_mode == "inference_pipeline":
        load_data_path = external_path['load_inference_data_path']
    else: 
        asset_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")

    print_color(f">> Start loading external << {load_data_path} >> data into << input >> directory.", "blue")
    
    try:
        load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
        print_color(f'>> s3 private key file << load_s3_key_path >> loaded successfully.', 'green')   
    except:
        print_color('[NOTICE] You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment.' , 'yellow')
        load_s3_key_path = None
        
    # None일 시 type을 list로 통일 
    if load_data_path is None:
        load_data_path = []

    # external path가 존재하는 경우 
    def _get_ext_path_type(_ext_path: str): # inner function 
        if 's3:/' in _ext_path: 
            return 's3'
        elif os.path.isabs(_ext_path) == True: # 절대경로. nas, local 둘다 가능 
            return 'absolute'
        elif os.path.isabs(_ext_path) == False: 
            asset_error(f'<< {_ext_path} >> is relative path. This is unsupported type of external load data path. Please enter the absolute path.')
        else: 
            asset_error(f'<< {_ext_path} >> is unsupported type of external load data path.')
    
    # 1개여서 str인 경우도 list로 바꾸고, 여러개인 경우는 그냥 그대로 list로 
    # None (미입력) 일 땐 별도처리 필요 
    load_data_path = [load_data_path] if type(load_data_path) == str else load_data_path

    for ext_path in load_data_path: 
        print_color(f'>> [@ {pipe_mode}] Start fetching external data from << {ext_path} >> into << input >> directory.', 'blue')
        ext_type = _get_ext_path_type(ext_path) # absolute / s3
        
        if ext_type  == 'absolute':
            # 해당 nas 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
            # nas 접근권한 없으면 에러 발생 
            # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
            try: 
                # 사용자가 실수로 yaml external path에 마지막에 '/' 쓰든 안쓰든, (즉 아래 코드에서 '/'이든 '//' 이든 동작엔 이상X)
                # [참고] https://stackoverflow.com/questions/3925096/how-to-get-only-the-last-part-of-a-path-in-python
                mother_path = os.path.basename(os.path.normpath(ext_path)) # 가령 /nas001/test/ 면 test가 mother_path, ./이면 .가 mother_path 
                if mother_path in os.listdir(INPUT_DATA_HOME): 
                    asset_error(f"You already have duplicated sub-folder name << {mother_path} >> in the << input >> folder. Please rename your sub-folder name if you use multiple data sources.")
                shutil.copytree(ext_path, PROJECT_HOME + f"input/{mother_path}", dirs_exist_ok=True) # 중복 시 덮어쓰기 됨 
            except: 
                asset_error(f'Failed to copy data from << {ext_path} >>. You may have written wrong NAS path (must be existing directory!) \n / or You do not have permission to access \n / or You used duplicated sub-folder names for multiple data sources.')
        elif ext_type  == 's3':  
            # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
            # 해당 s3 경로에 데이터 폴더 존재하는지 확인 후 폴더 통째로 가져오기, 부재 시 에러 발생 (서브폴더 없고 파일만 있는 경우도 부재로 간주, 서브폴더 있고 파일도 있으면 어짜피 서브폴더만 사용할 것이므로 에러는 미발생)
            # s3 접근권한 없으면 에러 발생 
            # 기존에 사용자 환경 input 폴더에 외부 데이터 경로 폴더와 같은 이름의 폴더가 있으면 notify 후 덮어 씌우기 
            s3_downloader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
            try: 
                s3_downloader.download_folder(INPUT_DATA_HOME)
            except:
                asset_error(f'Failed to download s3 data folder from << {ext_path} >>')
        else: 
            # 미지원 external data storage type
            asset_error(f'{ext_path} is unsupported type of external data path.') 
            
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
        print_color('[NOTICE] None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path.', 'yellow')
        return
    
    save_artifacts_path = None 
    if pipe_mode == "train_pipeline": 
        save_artifacts_path = external_path['save_train_artifacts_path'] 
    elif pipe_mode == "inference_pipeline":
        save_artifacts_path = external_path['save_inference_artifacts_path']
    else: 
        asset_error(f"You entered wrong pipeline in your expermimental_plan.yaml: << {pipe_mode} >>")

    if save_artifacts_path == None: 
        print_color('f[NOTICE][@{pipe_mode}] None of external path is written in your experimental_plan.yaml. Skip saving artifacts into external path.', 'yellow')
        return  
        
    # get s3 key 
    try:
        load_s3_key_path = external_path_permission['s3_private_key_file'] # 무조건 1개 (str)
        print_color(f'>> s3 private key file << load_s3_key_path >> loaded successfully.', 'green')   
    except:
        print_color('[NOTICE] You did not write any << s3_private_key_file >> in the config yaml file. When you wanna get data from s3 storage, \n you have to write the s3_private_key_file path or set << ACCESS_KEY, SECRET_KEY >> in your os environment.' , 'yellow')
        load_s3_key_path = None

    # external path가 존재하는 경우 
    def _get_ext_path_type(_ext_path: str): # inner function 
        if 's3:/' in _ext_path: 
            return 's3'
        elif os.path.isabs(_ext_path) == True: # 절대경로. nas, local 둘다 가능 
            return 'absolute'
        elif os.path.isabs(_ext_path) == False: # file이름으로 쓰면 에러날 것임 
            asset_error(f'<< {_ext_path} >> is relative path. This is unsupported type of external save artifacts path. Please enter the absolute path.')
        else: 
            asset_error(f'<< {_ext_path} >> is unsupported type of external save artifacts path.')

    # save artifacts 
    print_color(f">> Start saving generated artifacts into external path << {save_artifacts_path} >>.", "blue")
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
            asset_error(f'Failed to copy compressed artifacts from {tar_path} to << {ext_path} >>.')
        finally: 
            os.remove(tar_path)
    elif ext_type  == 's3':  
        # s3 key path가 yaml에 작성 돼 있으면 해당 key 읽어서 s3 접근, 작성 돼 있지 않으면 사용자 환경 aws config 체크 후 key 설정 돼 있으면 사용자 notify 후 활용, 없으면 에러 발생 
        # s3 접근권한 없으면 에러 발생 
        s3_uploader = S3Handler(s3_uri=ext_path, load_s3_key_path=load_s3_key_path)
        try: 
            s3_uploader.upload_file(tar_path)
        except:
            asset_error(f'Failed to upload {tar_path} onto << {ext_path} >>')
        finally: 
            os.remove(tar_path)
    else: 
        # 미지원 external data storage type
        asset_error(f'{ext_path} is unsupported type of external data path.') 
    
    print_color(f">> Successfully done saving << {tar_path} >> into << {save_artifacts_path} >> \n & removing << {tar_path} >>.", "green")  
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