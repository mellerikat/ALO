"""
Exception list

    errors:



"""


class AloError(Exception):
    """
    Raised when undefined error.
    Read the error message and fix it.
    If you cannot fix the error, Please contact the administrator with log file.

    정의되지 않은 예외 발생.
    에러 메시지를 읽고, 해당 내용을 수정하세요.
    에러의 원인을 찾거나, 수정할 수 없다면, 로그 파일을 관리자에게 전달 후 조치 방법을 문의하세요.
    """

    codes = {}
    code = None  # error code
    fmt = '[{code}] : {message}'

    def __init__(self, message, exception=None, doc={}, **kwargs):
        try:
            msg = f"{self.fmt.format(code=self.code, message=message, **kwargs)}\n{self.__doc__.format(**{'code':self.code, **doc}) if doc else self.__doc__ }"
            Exception.__init__(self, msg)
        except Exception:
            Exception.__init__(self, message + "\nCheck error format.")

        self.kwargs = kwargs

    def __init_subclass__(cls, **kwargs):
        if not cls.code:
            raise Exception("A constant value must be assigned to the 'code' variable as a class member variable.")
        if AloError.codes.get(cls.code):
            raise Exception(f"{cls.code} is duplicated : {[AloError.codes.get(cls.code).__name__, cls.__name__]}")

        AloError.codes[cls.code] = cls

    @classmethod
    def print(cls):
        print("code,name,description,document")
        print(f"{cls.code},{cls.__name__},{cls.fmt}")
        for k, v in cls.codes.items():
            print(f"{v.__name__},{k},{v.fmt}")


class AloValueError(AloError):
    """
    Raised when found invalid key or value error.
    Check key or value
    """
    code = "ALO-VAL-000"
    fmt = '[{code}] Found invalid value : {message}'


#################
# Alo Init Error
class AloInitError(AloError):
    """
    Raised when function initialization fails.
    Check required field, network, git, redis, experimental plan or solution meta...
    """

    code = "ALO-INI-000"
    fmt = '[{code}] Failed alo init : {message}'


class AloInitGitError(AloError):
    """
    Raised when branch not found in upstream origin.
    Check the same branch name exists in the upstream origin.
    """

    code = "ALO-INI-001"
    fmt = '[{code}] Failed install alolib : {message}'


class AloInitRequirementError(AloError):
    """
    Raised when the 3rd party library cannot be installed.
    Check the 3rd party library list and version in the requirements.txt file..
    """

    code = "ALO-INI-002"
    fmt = '[{code}] Failed installing alolib requirements.txt : {message}'


class AloInitFileNotFountError(AloError):
    """
    Raised when no such file or directory.
    Check file path.
    """

    code = "ALO-INI-003"
    fmt = '[{code}] The file or directory does not exist: {message}'


class AloInitRedisError(AloError):
    """
    Raised when unable to connect to redis.
    Check redis config, or redis status
    """

    code = "ALO-INI-004"
    fmt = '[{code}] Failed to connect redis : {message}'


class AloInitInvalidKeyValueError(AloError):
    """
    Raised when set an invalid key or value.
    Check the key and value values in the yaml(or value).
    """

    code = "ALO-INI-005"
    fmt = '[{code}] Found an invalid keys or values in file : {file}\n{message}'


class AloInitJsonInvalidError(AloError):
    """
    Raised when set an invalid json string.
    Check json string.
    """

    code = "ALO-INI-006"
    fmt = '[{code}] Found an invalid keys or values in json string : {message}'


#################
# pipeline Error
class AloPipelineInitError(AloError):
    """
    Raised when initializing the pipeline.
    """

    code = "ALO-PIP-000"
    fmt = '[{code}] Check the yaml file : {message}'


class AloPipelineAssetError(AloError):
    """
    Raised when failed to set up the assets in the scripts folder based on whether the code source is local or git.
    """

    code = "ALO-PIP-001"
    fmt = '[{code}] Check the code source of asset or git : {message}'


class AloPipelineImportError(AloError):
    """
    Raised when failed to import module/function.
    Check the library name and version in the requirements.
    Or Add the library path to the PYTHONPATH environment variable.
    """

    code = "ALO-PIP-002"
    fmt = '[{code}] Failed to import module/function - {module} : {message}'


class AloPipelineBatchError(AloError):
    """
    Raised when failed operate batch job.
    """

    code = "ALO-PIP-003"
    fmt = '[{code}] Check the {pipeline}(pipeline) : {message}'


class AloPipelineArtifactError(AloError):
    """
    Raised when Failed to empty & re-make artifacts.
    """

    code = "ALO-PIP-004"
    fmt = '[{code}] Check pipeline : {pipeline} - {message}'


class AloPipelineRequirementsError(AloError):
    """
    Raised when the 3rd party library cannot be installed.
    Check the library version or network.
    """

    code = "ALO-PIP-005"
    fmt = '[{code}] Found error when installing the package : {pipeline} - {message}'


class AloPipelineBackupError(AloError):
    """
    Raised when backup error history & save error artifacts.
    """

    code = "ALO-PIP-006"
    fmt = '[{code}] Check : {pipeline} - {message}'


class AloPipelineLoadError(AloError):
    """
    Raised when loading external data or duplicated basename in the same pipeline.
    """

    code = "ALO-PIP-007"
    fmt = '[{code}] Failed to load(get) : {pipeline} - {message}'


class AloPipelineSaveError(AloError):
    """
    Raised when save artifacts.
    """

    code = "ALO-PIP-008"
    fmt = '[{code}] Failed to save : {pipeline} - {message}'


class AloPipelineConversionError(AloError):
    """
    Raised when converting data in the execution unit.
    Check solutioin_metadata or experimental_plan.
    """

    code = "ALO-PIP-009"
    fmt = '[{code}] Error : {pipeline} - {message}'


class AloPipelineSerializeError(AloError):
    """
    Raised when the object serialization(pickling) operation fails.
    Check if the object supports serialization by default when save(pickling)/load(unpickling).
    If the default serialization operation is not supported,
    implement the function to directly save/load the object in the path below context['model']['workspace'].
    """

    code = "ALO-PIP-010"
    fmt = '[{code}] Error : {message}'


class AloPipelineSummaryError(AloError):
    """
    Raised when create summary report.
    Check the values of result, score, note, probability
    """

    code = "ALO-PIP-011"
    fmt = '[{code}] Error : {message}'


class AloPipelineCompressError(AloError):
    """
    Raised when an error occurs while compressing/decompressing a file.
    Check the file extension to make sure it is a valid format.
    """

    code = "ALO-PIP-012"
    fmt = '[{code}] Compress/Decompress Error : {message}'


class AloPipelineArgumentError(AloError):
    """
    Raised when an argument value is invalid.
    Check the argument's settings.
    """

    code = "ALO-PIP-013"
    fmt = '[{code}] {message}'


#################
# Package Error
class AloPackageRequirementsError(AloError):
    """
    Raised when the 3rd party library cannot be installed.
    Check the library version or network.
    """

    code = "ALO-PAC-000"
    fmt = '[{code}] Found error when installing the package : {message}'


#################
# Sagemaker Error
class AloSagemakerInitError(AloError):
    """
    Raised when initialize various SageMaker-related config information as class variables.
    """

    code = "ALO-SAG-000"
    fmt = '[{code}] Message : {message}'


class AloSagemakerSetupError(AloError):
    """
    Raised when copy the elements required for docker build into the sagemaker directory for the given list of pipelines.
    """

    code = "ALO-SAG-001"
    fmt = '[{code}] Message : {message}'


class AloSagemakerBuildError(AloError):
    """
    Raised when docker build, ecr push, create s3 bucket for sagemaker.
    """

    code = "ALO-SAG-002"
    fmt = '[{code}] Message : {message}'


class AloSagemakerEstimatorError(AloError):
    """
    Raised when fit sagemaker estimator (execute on cloud resource).
    """

    code = "ALO-SAG-003"
    fmt = '[{code}] Message : {message}'


class AloSagemakerTrainError(AloError):
    """
    Raised when failed to download sagemaker trained model.
    """

    code = "ALO-SAG-004"
    fmt = '[{code}] Message : {message}'


#################
# Asset Error
class AloAssetSetupError(AloError):
    """
    Raised when failed to install asset.
    Check for duplicate step names and raise an error if any exist.
    """

    code = "ALO-ASS-000"
    fmt = '[{code}] Message : {message}'


class AloAssetRunError(AloError):
    """
    Raised when failed to user asset run.
    Check source code of user asset.
    """

    code = "ALO-ASS-001"
    fmt = '[{code}] Message : {message}'


class AloArtifactFileNoneError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Stage: {stage}

    에러 원인(제약 사항)
        추론 실행 결과 파일을 찾을 수 없습니다.
        저장할 수 있는 파일 개수는 2개 이하로 제한 되며, 반드시 1개 이상의 파일을 생성해야 합니다.

    조치 가이드
        참고 사항과 같이 한 개 이상의 파일이 저장될 수 있도록 기능을 구현하세요.

    참고 사항
        pipeline['artifact']['workspace'] 의 경로 정보를 참조하여 파일 생성
        >>> with open(os.path.join(pipeline['artifact']['workspace'], "inference1.csv"), "w") as f:
        >>>     f.write("inference1")
    """

    code = "ALO-ART-001"


class AloArtifactFileLimitError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Stage:     {stage}
        Artifacts: {files}

    에러 원인(제약 사항)
        추론 결과 파일은 2개를 초과하여 저장할 수 없습니다.
        저장할 수 있는 파일 개수는 2개 이하로 제한 되며, 반드시 1개 이상의 파일을 생성해야 합니다.

    조치 가이드
        에러 정보의 Artifacts 항목을 참고하여 파일 개수를 2개 이하로 제한하세요.
        불필요한 파일이 존재한다면 삭제하세요.

    참고 사항
        pipeline['artifact']['workspace'] 는 추론 파일을 저장하기 위한 경로 정보를 제공합니다.
        >>> print(pipeline['artifact']['workspace']) # /var/alo/workspace/train/output/result.csv

        pipeline['artifact']['workspace'] 값을 참조하여 파일 저장 로직을 구현한 부분이 있다면
        파일 저장 개수 제약 사항에 위반되지 않도록 불필요한 파일 저장 로직은 삭제하세요.
    """

    code = "ALO-ART-002"


class AloArtifactFileExtensionError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Stage:    {stage}
        Artifact: {files}

    에러 원인(제약 사항)
        허용되지 않는 파일 유형이 추론 결과 파일에 포함되어 있습니다.
        csv, jpg, jpeg, png, svg 파일 유형만 저장 가능합니다.

    조치 가이드
        에러 정보의 Artifacts 항목을 참고하여 허용되지 않는 파일 유형을 확인 후
        해당 파일 유형을 변경 또는 삭제하세요.

    참고 사항
        pipeline['artifact']['workspace'] 는 추론 파일을 저장하기 위한 경로 정보를 제공합니다.
        >>> print(pipeline['artifact']['workspace']) # /var/alo/workspace/train/output/result.csv
    """

    code = "ALO-ART-003"


class AloUserPipelineError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        File:     {file}
        Function: {function}
        Message:  {message}

    에러 원인
        사용자 파이프라인 함수(python 코드) 실행중에 runtime 에러가 발생하였습니다.

    조치 가이드
        에러 정보의 File(python 코드)에서의 에러가 발생하였습니다.
        에러 메시지 상단의 Traceback을 참고하여 에러 발생 위치 및 exception 메시지를 확인 후
        코드를 수정하세요.

    참고 사항
        ALO에서 제공되는 context, pipeline 두 참조 dict 객체는 아래와 같은 정보를 가지고 있습니다.
        context: ALO 수행과 관련된 정보를 조회하거나, 저장할 수 있는 객체
            context['stage']: 현재 수행중인 단계(train 또는 inference) 리턴
                >>> print(context['stage']) # train or inference
            context['model']['workspace']: 모델 저장 경로 반환.
                >>> print(os.path.join(context['model']['workspace'], 'model.pickle')) # /var/alo/workspace/model/model.pickle
            context['model'][파일명]: 파일명(pickle 확장자 제외)에 해당하는 model을 메모리로 로딩 후 객체로 반환하거나, 저장(pickling 지원 대상만 해당)
                >>> context['model']['titanic'] = RandomForestClassifier(n_estimators=n_estimators, max_depth=5, random_state=1)  # titanic 이라는 이름으로 모델 객체를 파일로 저장
                >>> model = context['model']['titanic'] # titanic 이름으로 저장된 모델을 객체로 로딩 후 반환
        pipeline: train, interence 단계 수행시 dataset, artiface 파일 정보를 조회할 수 있는 객체
            pipeline['dataset']['workspace' 또는 파일명]: dataset 파일이 저장된 경로를 반환
                >>> print(os.path.join(pipeline['dataset']['workspace'], 'dataset.csv')) # /var/alo/workspace/train/dataset/file.csv
                >>> print(pipeline['dataset']['file.csv'])                               # /var/alo/workspace/train/dataset/file.csv (위와 동일)
            pipeline['artifact']['workspace']: artifact 파일을 저장하기 위한 경로를 반환
                >>> print(os.path.join(pipeline['artifact']['workspace'])) # /var/alo/workspace/train/output
    """

    code = "ALO-USR-001"


class AloDatasetKeyNotFoundError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Stage: {stage}
        Key:   {key}

    에러 원인
        찾고자 하는 dataset 파일명({key})이 잘못되었거나,
        또는 파일이 누락된 경우에 해당합니다.

    조치 가이드
        Key는 experimental_plan.yaml 파일의 solution.{stage}.dataset_uri에 설정된 경로 이하 또는 압축 파일 내에 폴더명 및 확장자명을 포함한 경로 형태여야 합니다. Ex) pipeline['dataset']['path/train.csv']
        아래 각 항목을 점검하세요.
        1. experimental_plan.yaml의 solution.{stage}.dataset_uri 설정 유무 확인
        2. 압축 파일인 경우 파일 내부에 파일 포함 여부 확인
        3. 압축 파일 내부 폴더 이하에 파일이 존재하는 경우 경우
            >>> print(pipeline['dataset']['파일명.csv'])       # 오류 발생
            >>> print(pipeline['dataset']['폴더명/파일명.csv']) # /var/alo/workspace/train/dataset/폴더명/파일명.csv
        4. key에 파일 확장자명 누락된 경우
            >>> print(pipeline['dataset']['파일명'])           # 오류 발생
            >>> print(pipeline['dataset']['파일명.csv'])       # /var/alo/workspace/train/dataset/파일명.csv

    참고 사항
        pipeline['dataset'] 객체는 train/inference의 필요한 파일들에 대한 경로 정보를 제공합니다.
        >>> print(pipeline['dataset']['workspace']) # /var/alo/workspace/train/dataset
        >>> print(pipeline['dataset']['file.csv'])  # /var/alo/workspace/train/dataset/file.csv
    """

    code = "ALO-DTS-001"


class AloDatasetFileNotFoundError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Stage: {stage}
        Key:   {key}
        File:  {file}

    에러 원인
        에러 정보의 Key 경로에 해당하는 File이 삭제되어 찾을 수 없습니다.

    조치 가이드
        사용자 파이프라인 함수(python 코드) 등록된 파일을 삭제한 로직이 없는지 검토가 필요합니다.

    참고 사항
        pipeline['dataset'] 객체는 train/inference의 필요한 파일들에 대한 경로 정보를 제공합니다.
        >>> print(pipeline['dataset']['workspace']) # /var/alo/workspace/train/dataset
        >>> print(pipeline['dataset']['file.csv'])  # /var/alo/workspace/train/dataset/file.csv
    """

    code = "ALO-DTS-002"


class AloModelFileNotFoundError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Key:   {key}
        File:  {file}

    에러 원인
        에러 정보의 Key에 해당하는 모델 파일(pickle)을 찾을 수 없습니다.

    조치 가이드
        key 및 모델 파일이 존재하는지 확인이 필요합니다.
        1. experimental_plan.yaml 파일의 solution.[stage].model_uri에 모델 파일 여부 확인
        2. 모델 파일의 확장자명이 .pkl 인지 여부 확인
        3. key명 오탈자 여부 확인
        4. key명에 확장자 포함 여부 확인

    참고 사항
        context['model'] 객체는 모델 파일(pickle)에 대한 정보를 제공하고 있습니다.
        >>> model = context['model']['titanic']     # titanic 이름으로 저장된 모델을 객체로 로딩 후 반환
        >>> model = context['model']['titanic.pkl'] # 오류 발생
    """

    code = "ALO-MDL-001"


class AloModelUnpicklingError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Key:   {key}
        File:  {file}

    에러 원인
        에러 정보의 Key에 해당하는 모델 파일(pickle)을 메모리를 로드(unpickling)할 수 없습니다.
        일부 모델 객체는 python pickling/unpickling 기능이 지원되지 않습니다.

    조치 가이드
        1. requirements.txt의 모델에 해당하는 library가 동일 버전인지 확인
            -> train시 pickle 파일로 저장시 library 버전과 unpickle시 library 버전이 상이한 경우
            Ex) scikit-learn==1.4.0 의 모델 객체를 pickle 파일로 저장 후 scikit-learn==1.5.0 버전으로 unpickle 시 오류 발생

        2. 모델 객체에 대해 pickling/unpickling을 지원하지 않는 경우
        2-1. pickling/unpickling 기능을 직접 구현하는 방법
        >>> import os
        >>> def pickle(context, model: object):
        >>>     # model_bytes =  ...(변환 로직 구현)
        >>>     with open(os.path.join(context['model']['workspace'], "my_custom_model.pkl"), "wb") as f:  # 모델 경로 이하에 저장
        >>>         f.write(model_bytes)
        >>> model = None
        >>> def unpickle(context):
        >>>     global model  # 모델 객체 생성에 대한 cost를 줄이기 위해 global 변수를 통해 재사용
        >>>     # model_bytes =  ...(변환 로직 구현)
        >>>     if model is None:
        >>>         with open(os.path.join(context['model']['workspace'], "my_custom_model.pkl"), "rb") as f:  # 모델 경로 이하에 저장
        >>>             model_bytes = f.read()
        >>>             model = ...(변환 로직 구현)
        >>>     return model
        2-2. 모델 객체의 parameter 만 pickle 파일로 저장 후 모델 객체의 parameter로 전달하는 방법
        >>> def train(context: dict, pipeline: dict):
        >>>     context['model']['titanic_param'] = ("n_estimators": 100, "max_depth": 5, "random_state": 1)  # model parameter pickle로 저장
        >>>     model = RandomForestClassifier(**context['model']['titanic_param'])
        >>> model = None
        >>> def inference(context: dict, pipeline: dict):
        >>>     global model  # 모델 객체 생성에 대한 cost를 줄이기 위해 global 변수를 통해 재사용
        >>>     if model is None:
        >>>         titanic_param = context['model']['titanic_param']
        >>>         model = RandomForestClassifier(**titanic_param)

    참고 사항
        ALO에서는 python pickle library 를 사용하여
        pickling(객체 -> 파일) 또는 unpickling(파일 -> 객체) 하는 기능을 기본 지원하고 있습니다.
        >>> def train(context: dict, pipeline: dict):
        >>>     model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=1)
        >>>     context['model']['titanic'] = model  # 모델을 파일로 pickling
        >>>
        >>> def inference(context: dict, pipeline: dict):
        >>>     model = context['model']['titanic']  # 파일을 RandomForestClassifier 객체로 unpickling

        일부 모델 객체들에 대해서는 python pickle 기능이 적용되지 않음으로
        조치 가이드 2번 항목을 참고하세요.

    """

    code = "ALO-MDL-002"


class AloModelPicklingError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Key:   {key}
        File:  {file}

    에러 원인
        에러 정보의 Key에 해당하는 객체(모델)를 파일(pickle)로 저장(pickling)할 수 없습니다.
        일부 모델 객체는 python pickling/unpickling 기능이 지원되지 않습니다.

    조치 가이드
        1. 사용중인 library에서의 pickling 제공 여부를 확인하거나, 제 3의 library(Ex. fickling 등) 적용
        2. 모델 객체에 대해 pickling/unpickling을 지원하지 않는 경우
        2-1. pickling/unpickling 기능을 직접 구현하는 방법
        >>> import os
        >>> def pickle(context, model: object):
        >>>     # model_bytes =  ...(변환 로직 구현)
        >>>     with open(os.path.join(context['model']['workspace'], "my_custom_model.pkl"), "wb") as f:  # 모델 경로 이하에 저장
        >>>         f.write(model_bytes)
        >>> model = None
        >>> def unpickle(context):
        >>>     global model  # 모델 객체 생성에 대한 cost를 줄이기 위해 global 변수를 통해 재사용
        >>>     # model_bytes =  ...(변환 로직 구현)
        >>>     if model is None:
        >>>         with open(os.path.join(context['model']['workspace'], "my_custom_model.pkl"), "rb") as f:  # 모델 경로 이하에 저장
        >>>             model_bytes = f.read()
        >>>             model = ...(변환 로직 구현)
        >>>     return model
        2-2. 모델 객체의 parameter 만 pickle 파일로 저장 후 모델 객체의 parameter로 전달하는 방법
        >>> def train(context: dict, pipeline: dict):
        >>>     context['model']['titanic_param'] = ("n_estimators": 100, "max_depth": 5, "random_state": 1)  # model parameter pickle로 저장
        >>>     model = RandomForestClassifier(**context['model']['titanic_param'])
        >>> model = None
        >>> def inference(context: dict, pipeline: dict):
        >>>     global model  # 모델 객체 생성에 대한 cost를 줄이기 위해 global 변수를 통해 재사용
        >>>     if model is None:
        >>>         titanic_param = context['model']['titanic_param']
        >>>         model = RandomForestClassifier(**titanic_param)

    참고 사항
        ALO에서는 python pickle library 를 사용하여
        pickling(객체 -> 파일) 또는 unpickling(파일 -> 객체) 하는 기능을 기본 지원하고 있습니다.
        >>> def train(context: dict, pipeline: dict):
        >>>     model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=1)
        >>>     context['model']['titanic'] = model  # 모델을 파일로 pickling
        >>>
        >>> def inference(context: dict, pipeline: dict):
        >>>     model = context['model']['titanic']  # 파일을 RandomForestClassifier 객체로 unpickling

        일부 모델 객체들에 대해서는 python pickle 기능이 적용되지 않음으로
        조치 가이드 내용을 참고하세요.
    """

    code = "ALO-MDL-003"


class AloModelTrainFileNotFoundError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Phase: {phase}

    에러 원인(제약 사항)
        학습(Train) pipline 에서 모델 관련 output 파일이 없습니다.
        조치 가이드와 같이 1개 이상의 모델 관련 파일을 저장하세요.

    조치 가이드
        1. 모델 객체를 pickle 파일로 저장
        >>> model = RandomForestClassifier(n_estimators=n_estimators, max_depth=5, random_state=1)
        >>> context['model']['titanic'] = model

        2. config 정보(dict)를 파일로 저장
        >>> context['model']['model_config'] = dict(n_estimators=100, max_depth=5, random_state=1)

    참고 사항
        context['model'] 객체는 모델 관련 정보를 제공하고 있습니다.
        예제) 모델 관련 객체 또는 설정 정보를 메모리로 로드
        >>> model = context['model']['titanic']     # titanic 이름으로 저장된 모델을 객체로 로딩 후 반환

        예제) 모델 관련 객체 또는 설정 정보를 파일로 쓰기
        >>> context['model']['titanic'] = model     # model 객체를 titanic 파일 정보로 저장

        예제) 사용자 정의 model 관련 파일 생성시 context['model']['workspace'] 경로 정보를 참고하여 파일 생성
        >>> with open(os.path.join(context['model']['workspace'], "titanic.pkl"), "wb") as f:  # 모델 경로 이하에 저장 직접 파일로 저장
        >>>     f.write(model_bytes)  # model 관련 정보를 파일로 저장

    """

    code = "ALO-MDL-004"


class AloContextWrongKeyTypeError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Key: {key}
        Type: {type}

    에러 원인(제약 사항)
        사용자 정의 key로 등록 가능한 데이터 유형은 문자열만 가능합니다.
        '{type}' 데이터 유형은 key로 사용할 수 없습니다.

    조치 가이드
        >>> context['model'][1] = 'abc'    # 오류 발생. 숫자 1은 key로 사용 불가
        >>> context['model']['1'] = 'abc'  # 정상 수행
        상기 라인을 수정 또는 삭제하세요.

    참고 사항
        시스템에서 제공되는 데이터 key는 모두 문자형 타입입니다.
        - context['model']['workspace']
        - context['model']['example_model']
        - pipeline['dataset']['workspace']
        - pipeline['dataset']['train.csv']
        - pipeline['artifact']['workspace']
    """

    code = "ALO-CTX-001"


class AloContextNotAllowKeyError(AloError):
    """
    에러 코드
        {code}

    에러 정보
        Key: {key}

    에러 원인(제약 사항)
        '{key}' key는 시스템에서 제공되는 key명이며, 읽기만 가능한 key 입니다.
        key에 해당하는 값을 업데이트 할 수 없습니다.

    조치 가이드
        >>> context[...]['{key}'] = '값'
        >>> 또는
        >>> pipeline[...]['{key}'] = '값'
        상기 라인을 수정 또는 삭제하세요.

    참고 사항
        시스템에서 제공되는 일부 key는 임의로 수정할 수 없습니다.
        값 변경 불가한 key 목록입니다.
        - context['model']['workspace']
        - pipeline['dataset']['workspace']
        - pipeline['artifact']['workspace']
    """

    code = "ALO-CTX-002"


AloErrors = {code: cls for code, cls in AloError.codes.items()}
