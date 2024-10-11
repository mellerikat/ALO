# ----------------------------------------------------------------------
# Copyright (C) 2024, mellerikat. LGE
# ----------------------------------------------------------------------

"""
ALO
"""

import os
import json
import redis
import uuid
import shutil
import pickle
import tarfile
import re
import yaml
import pkg_resources  # todo deprecated. should be fixed.
import zipfile
import psutil
import glob
import pyfiglet
import hashlib
import inspect
from abc import ABCMeta, abstractmethod
from enum import Enum
from copy import deepcopy
from datetime import datetime
from collections import OrderedDict
from pathlib import Path
from functools import wraps
from threading import Thread
from pytz import timezone

from alo import settings, AloError, AloErrors
from alo.logger import LOG_PROCESS_FILE_NAME, create_pipline_handler, log_start_finish
from alo.model import load_model, SolutionMetadata, update_s3_credential, EXP_FILE_NAME, copytree
from alo.utils import ResourceProfile, ColorMessage, print_table
from alo.__version__ import __version__, COPYRIGHT

from alo.solution_register import SolutionRegister as solution_register
from alo.constants import ASSET_PACKAGE_PATH


logger = settings.logger
TRAIN = 'train'
INFERENCE = 'inference'
MODES = [TRAIN, INFERENCE]
LOG_PIPELINE_FILE_NAME = "pipeline.log"
ARTIFACT = 'artifact'
HISTORY_FOLDER_FORMAT = "%Y%m%dT%H%M%S.%f"
HISTORY_PATTERN = re.compile(r'([0-9]{4}[0-9]{2}[0-9]{2}T[0-9]{2}[0-9]{2}[0-9]{2}.[0-9]{6})($|-error$)')
RUN_PIPELINE_NAME = '__pipeline_names__'
RESULT_INFO_FILE = 'result_info.json'


def extract_file(file_paths: list, destination: str):
    """ 지정된 경로에 압축 파일을 해제합니다.

    Args:
        file_paths: 파일 경로 목록
        destination: 압축 해제된 파일을 저장할 경로

    Raises:
        AloErrors: ALO-PIP-012

    """
    for file_path in file_paths:
        try:
            if file_path.lower().endswith(('.tar.gz', '.tgz')):
                with tarfile.open(file_path) as file:
                    file.extractall(os.sep.join(file_path.split(os.sep)[:-1]))
                    logger.debug("[FILE] Extract %s: %s ", file_path, file.getnames())
            elif file_path.lower().endswith('.zip'):
                with zipfile.ZipFile(file_path) as file:
                    file.extractall(os.sep.join(file_path.split(os.sep)[:-1]))
                    logger.debug("[FILE] Extract %s: %s ", file_path, file.namelist())
        except Exception as e:
            raise AloErrors['ALO-PIP-012'](file_path) from e


def tar_dir(_path, _save_path, last_dir):
    """ compress directory as tar.gz

    Args:
        _path       (str): path tobe compressed
        _save_path  (str): tar.gz file save path
        last_dir   (str): last directory for _path

    Returns: -

    """
    tar = tarfile.open(_save_path, 'w:gz')
    for root, dirs, files in os.walk(_path):
        base_dir = root.split(last_dir)[-1] + '/'
        for file_name in files:
            # Arcname: Compress starting not from the absolute path beginning with /home,
            # but from train_artifacts/ or models/
            tar.add(os.path.join(root, file_name), arcname=base_dir + file_name)
    tar.close()


def zip_dir(_path, _save_path):
    """ compress directory as zip

    Args:
        _path       (str): path tobe compressed
        _save_path  (str): zip file save path
        _last_dir   (str): last directory for _path

    Returns: -

    """
    # remove .zip extension
    _save_path = os.path.splitext(_save_path)[0]
    shutil.make_archive(_save_path, 'zip', _path)


def add_logger_handler(func):
    """ 데코레이터 함수

    특정 함수의 로그를 별로도 분리하기 위해 default logger에
    파일 핸들러를 추가 후 자동 제거 합니다.

    Args:
        func    (function): original function

    Returns:
        wrapper (function): wrapped function

    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        _handler = create_pipline_handler(os.path.join(args[2], "log", LOG_PIPELINE_FILE_NAME), logger.level)
        _logger = logger
        _logger.addHandler(_handler)
        try:
            result = func(self, *args, **kwargs)
            return result
        finally:
            _logger.removeHandler(_handler)
            _handler.close()
    return wrapper


RESOURCE_MESSAGE_FORMAT = "".join(["\033[93m",
                                   "\n------------------------------------ %s < CPU/MEMORY/SUMMARY> Info ------------------------------------",
                                   "\n%s",
                                   "\n%s",
                                   "\n%s",
                                   "\033[0m"])


def profile_resource(func):
    """ cpu/memory profiling decorator

    Args:
        func    (function): original function

    Returns:
        wrapper (function): wrapped function

    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not settings.experimental_plan.control.check_resource:
            return func(*args, **kwargs)
        pid = os.getpid()
        ppid = psutil.Process(pid)
        cpu_usage_start = ppid.cpu_percent(interval=None)  # 단순 cpu 사용률
        mem_usage = ResourceProfile(ppid, cpu_usage_start)
        thread = Thread(target=mem_usage.run, daemon=True)
        thread.start()
        result = func(*args, **kwargs)
        mem_usage.enable = False
        cpu, mem = mem_usage.info()
        msg_cpu = "- CPU (min/max/avg) : {:5.1f}% / {:5.1f}% / {:5.1f}%".format(*cpu)
        msg_mem = "- MEM (min/max/avg) : {} / {} / {}".format(*mem)
        pipes = []
        context = args[1]
        stage_name = args[2]
        for pipe_name in context[stage_name][RUN_PIPELINE_NAME]:
            pipes.append(f"{stage_name} - {pipe_name:<15} : "
                         f"Elapsed time ({(context[stage_name][pipe_name]['finishAt'] - context[stage_name][pipe_name]['startAt']).total_seconds():8.3f}) "
                         f"[{context[stage_name][pipe_name]['finishAt'].strftime('%Y-%m-%d %H:%M:%S.%f')}"
                         f" - {context[stage_name][pipe_name]['startAt'].strftime('%Y-%m-%d %H:%M:%S.%f')}]")
        logger.debug(RESOURCE_MESSAGE_FORMAT, stage_name, msg_cpu, msg_mem, "\n".join(pipes))
        return result

    return wrapper


def save_summary(solution_metadata_version: str, file_path: str, result="", score="", note="", probability={}):
    """ Save train_summary.yaml (when summary is also conducted during train) or inference_summary.yaml.
        e.g. self.asset.save_summary(result='OK', score=0.613, note='alo.csv', probability={'OK':0.715, 'NG':0.135, 'NG1':0.15}

    Args:
        solution_metadata_version (str) : version of solution_metadata
        file_path   (str): Path where the file will be saved
        result      (str): Inference result summarized info. (length limit: 25)
        score       (float): model performance score to be used for model retraining (0 ~ 1.0)
        note        (str): optional & additional info. for inference result (length limit: 100) (optional)
        probability (dict): probability per class prediction if the solution is classification problem.  (optional)
                            e.g. {'OK': 0.6, 'NG':0.4}

    Returns:
        summaray_data   (dict): data tobe saved in summary yaml

    """
    result_len_limit = 32
    note_len_limit = 128
    if not isinstance(result, str) or len(result) > result_len_limit:  # check result length limit 12
        logger.warning("The summary['result'] value must be a str type and the length must be less than %d characters. Any characters exceeding the string length are ignored.", result_len_limit)
        result = str(result)[:result_len_limit]
    if not type(score) in (int, float) or not 0 <= score <= 1.0:  # check score range within 0 ~ 1.0
        logger.warning(f"The summary['score'] value must be python float or int. Also, the value must be between 0.0 and 1.0. Your current score value: %s", score)
        score = 0.0
    if not isinstance(note, str) or len(note) > note_len_limit:  # check note length limit 100
        logger.warning(f"The summary['note'] value must be a str type and the length must be less than %d characters. Any characters exceeding the string length are ignored.", note_len_limit)
        note = str(note)[:note_len_limit]
    if (probability is not None) and (not isinstance(probability, dict)):  # check probability type (dict)
        raise AloErrors['ALO-PIP-011']("The type of argument << probability >> must be << dict >>")
    if len(probability.keys()) > 0:  # check type - probability key: string,value: float or int
        key_chk_str_set = set([isinstance(k, str) for k in probability.keys()])
        value_type_set = set([type(v) for v in probability.values()])
        if key_chk_str_set != {True}:
            raise AloErrors['ALO-PIP-011']("The key of dict argument << probability >> must have the type of << str >> ")
        if not value_type_set.issubset({float, int}):
            raise AloErrors['ALO-PIP-011']("The value of dict argument << probability >> must have the type of << int >> or << float >> ")
        if round(sum(probability.values())) != 1:  # check probability values sum = 1
            raise AloErrors['ALO-PIP-011']("The sum of probability dict values must be << 1.0 >>")
    else:
        pass
        # FIXME e.g. 0.50001, 0.49999 case?

    # FIXME it is necessary to check whether the sum of the user-entered dict is 1, anticipating a floating-point error
    def make_addup_1(prob):
        # Process the probabilities to sum up to 1, displaying up to two decimal places
        max_value_key = max(prob, key=prob.get)
        proc_prob_dict = dict()
        for k, v in prob.items():
            if k == max_value_key:
                proc_prob_dict[k] = 0
                continue
            proc_prob_dict[k] = round(v, 2)
        proc_prob_dict[max_value_key] = round(1 - sum(proc_prob_dict.values()), 2)
        return proc_prob_dict

    if (probability is not None) and (probability != {}):
        probability = make_addup_1(probability)
    else:
        probability = {}

    summary_data = {
        'result': result,
        'score': round(score, 2),
        'date': datetime.now(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S'),
        'note': note,
        'probability': probability,
        'version': solution_metadata_version
    }

    try:
        with open(file_path, 'w') as file:
            yaml.dump(summary_data, file, default_flow_style=False)
        logger.debug("[SUMMARY] Successfully saved summary yaml : %s", file_path)
    except Exception as e:
        raise AloErrors['ALO-PIP-011'](f"Failed to save summary yaml file \n @ << {file_path} >>") from e

    return summary_data


class WorkspaceDict(dict):
    """workspace 이하의 파일 관리를 위한 객체

    Keys:
        - workspace (str): 작업 경로

    """
    def __init__(self, workspace: str):
        """
        작업 경로 폴더를 생성 후 workspace를 등록합니다.
        Args:
            workspace: 작업 기본 경로
        """
        super().__init__()
        self.update_workspace(workspace)
        Path(self['workspace']).mkdir(exist_ok=True)

    def update_workspace(self, value):
        super().__setitem__('workspace', value)

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise AloErrors['ALO-CTX-001'](f'"{str(key)}({type(key)})" is not allowed as a key value. The key value must be of type string.',
                                           doc={'key': key, 'type': type(key).__name__})
        if key == 'workspace' and key in self:
            raise AloErrors['ALO-CTX-002']('The word "workspace" is a system reserved word and cannot be update. Change the "workspace" keyword to another name.',
                                           doc={'key': 'workspace'})
        super().__setitem__(key, value)

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return self['workspace']

    def __radd__(self, other):
        return other + str(self)

    def __add__(self, other):
        return str(self) + other


class ArtifactModel(WorkspaceDict):
    def __init__(self, stage_name: str, stage_workspace: str):
        super().__init__(f"{stage_workspace}{os.sep}output")
        self.__stage_name = stage_name

    def __setitem__(self, key, value):
        super().__setitem__(key, value)

    def validate(self):
        files = [file.lower() for file in os.listdir(self['workspace']) if os.path.isfile(os.path.join(self['workspace'], file))]
        if self.__stage_name == INFERENCE and not files:
            raise AloErrors['ALO-ART-001']("The output file could not be found. In the inference phase, you must create one or two files under the path `pipeline['artifact']['workspace']`.",
                                           doc={"stage": self.__stage_name})
        if not files:
            return
        if len(files) > 2:
            raise AloErrors['ALO-ART-002']('You have to save inference output file. The number of output files must be 1 or 2.',
                                           doc={"stage": self.__stage_name, "files": files})
        if not all([file.lower().endswith((".csv", ".jpg", ".jpeg", ".png", ".svg")) for file in files]):
            raise AloErrors['ALO-ART-003']('output file extension must be one of ["csv", "jpg", "jpeg", "png", "svg"].',
                                           doc={"stage": self.__stage_name, "files": files})


class TrainModel(WorkspaceDict):
    """학습의 모델과 관련된 파일 및 workspace 경로 정보를 관리하기 위한 객체

    workspace이하의 pkl(pickle) 파일을 메모리로 로드 후 해당 객체를 전달한다.

    Keys:
        - workspace (str): 작업 경로

    Raises:
        AloErrors: ALO-PIP-007 (저장된 모델이 없는 경우 예외 발생)

    Examples:
        >>> context['model']['workspace']
           /home/alo/test
        >>> str(context['model'])  # context['model']['workspace'] 와 동일한 값을 리턴함
           /home/alo/test
        >>> context['model']['titanic_model']
           RandomForestClassifier 객체를 리턴함
        >>> context['model']['titanic_model'] = RandomForestClassifier(n_estimators=n_estimators, max_depth=5, random_state=1)
           RandomForestClassifier 객체를 titanic_model 이름으로 파일로 저장됨

    """
    MODEL_FILE_NAME_FORMAT = "{0}.pkl"

    def __init__(self, workspace: str):
        super().__init__(workspace)

    def __getitem__(self, key):
        if key in self:
            return super().get(key)

        file = f"{super().get('workspace')}{os.sep}{self.MODEL_FILE_NAME_FORMAT.format(key)}"
        if not os.path.isfile(file):
            raise AloErrors['ALO-MDL-001'](f'"{key}" cannot be found in context["model"]. Check model name or model_uri',
                                           doc={"key": key, "file": file})

        with open(file, 'rb') as f:
            try:
                self[key] = pickle.load(f)
            except Exception as e:
                raise AloErrors['ALO-MDL-002'](f'Failed to unpickle : {key}',
                                               doc={"key": key, "file": file}) from e
        logger.debug('[MODEL] Load context["model"]["%s"] : %s', key, file)
        return super().get(key)

    def __setitem__(self, key, value):
        try:
            with open(os.path.join(self['workspace'], self.MODEL_FILE_NAME_FORMAT.format(key)), 'wb') as f:
                pickle.dump(value, f)
                super().__setitem__(key, value)
                logger.debug('[MODEL] save context["model"]["%s"] : %s/%s', key, self['workspace'], self.MODEL_FILE_NAME_FORMAT.format(key))
        except Exception as e:
            raise AloErrors['ALO-MDL-003'](f'Failed to save model "{key}".',
                                           doc={"key": key,
                                                "file": os.path.join(self['workspace'], self.MODEL_FILE_NAME_FORMAT.format(key))}) from e

    def __deepcopy__(self, memodict={}):
        return self

    def validate(self, phase: str = None):
        files = [file.lower() for file in os.listdir(self['workspace']) if os.path.isfile(os.path.join(self['workspace'], file))]
        if phase == TRAIN and not files:
            raise AloErrors['ALO-MDL-004']("When training, you must save at least one model or config files.",
                                           doc={"phase": phase})


class Dataset(WorkspaceDict):
    """
    train/inference 시 입력 데이터셋으로 활용할 파일들에 대한 폴더 및 파일 목록

    Keys:
        - workspace (str): 작업 경로
    """

    def __init__(self, stage_name: str, stage_workspace: str):
        super().__init__(f"{stage_workspace}{os.sep}dataset")
        self.__stage_name = stage_name

    def __getitem__(self, key):
        if key not in self:
            raise AloErrors['ALO-DTS-001'](f'"{key}" not exists in pipeline["dataset"]. Check dataset in {self.__stage_name}',
                                           doc={"stage": self.__stage_name, "key": key})
        if key == 'workspace':
            return super().__getitem__(key)
        if not os.path.isfile(f'{self["workspace"]}{os.sep}{key}'):
            raise AloErrors['ALO-DTS-002'](f'"{key}" file cannot be found in {self["workspace"]}.',
                                           doc={"stage": self.__stage_name, "key": key, "file": f'{self["workspace"]}{os.sep}{key}'})
        return super().__getitem__(key)

    def add(self, files: list):
        prefix_len = len(f'{self["workspace"]}{os.sep}')
        for file in files:
            self[file[prefix_len:]] = file

    def __deepcopy__(self, memodict={}):
        return self


class Context(WorkspaceDict):
    """ ALO 수행과 관련된 환경 정보를 담고 있는 객체

    Keys:
        - workspace (str): 작업 경로
        - startAt (datetime): 시작 시각
        - finishAt (datetime): 종료 시각(완료된 후 key 값이 추가됨)

    """
    def __init__(self):
        start_at = datetime.now()
        super().__init__(f"{settings.history_path}{os.sep}{start_at.strftime(HISTORY_FOLDER_FORMAT)}")
        self['startAt'] = start_at
        Path(self['workspace']).mkdir(parents=True, exist_ok=True)
        self['id'] = str(uuid.uuid4())
        self['name'] = settings.name
        self['version'] = settings.version
        self['host'] = settings.host
        self['logger'] = logger
        self['logging'] = {
            'name': 'alo',
            'level': settings.log_level,
        }
        self['model'] = TrainModel(settings.v1_model_artifacts_path)
        self['external'] = WorkspaceDict(f"{self['workspace']}{os.sep}external")
        self['stage'] = None
        self['solution_metadata_version'] = settings.experimental_plan.solution.version

    def __enter__(self):
        return self

    def __getitem__(self, key):
        if key not in self and key in MODES:
            stage_ws = f"{self['workspace']}{os.sep}{key}"
            Path(stage_ws).mkdir(parents=True, exist_ok=True)
            self[key] = {
                'name': key,
                'workspace': stage_ws,
                'dataset': Dataset(key, stage_ws),
                ARTIFACT: ArtifactModel(key, stage_ws),
                RUN_PIPELINE_NAME: []
            }
            Path(os.path.join(stage_ws, "score")).mkdir()
        return super().__getitem__(key)

    def __create_result_info(self):
        def order_dict(dictionary: dict):
            return {k: order_dict(v) if isinstance(v, dict) else v for k, v in sorted(dictionary.items())}

        shutil.copy2(settings.experimental_plan.uri, self['workspace'])
        with open(settings.experimental_plan.uri, 'rb') as plan_f, open(os.path.join(self['workspace'], RESULT_INFO_FILE), 'w') as json_f:
            info = {
                'start_time': self['startAt'].isoformat() if self.get('startAt') else None,
                'end_time': self['finishAt'].isoformat() if self.get('finishAt') else None,
                EXP_FILE_NAME: {
                    'modify_date': datetime.fromtimestamp(os.path.getmtime(settings.experimental_plan.uri)).isoformat()
                },
                **{mode: {'start_time': self[mode]['startAt'].isoformat() if self[mode].get('startAt') else None,
                          'end_time': self[mode]['finishAt'].isoformat() if self[mode].get('finishAt') else None,
                          'argument': {pipe: order_dict(self[mode][pipe].get('argument', {})) for pipe in self[mode][RUN_PIPELINE_NAME]}
                          }
                   for mode in MODES if mode in self}
            }
            json.dump(info, json_f)

    def __exit__(self, exc_type, exc_val, exc_tb):
        latest = 'latest'
        if isinstance(exc_val, Exception):
            logger.error("An error occurred: %s", exc_val)
            rename_ws = f"{self['workspace']}-error"
            os.rename(self['workspace'], rename_ws)
            self.update_workspace(rename_ws)
            latest = f'{latest}-error'
            logger.error("Please check the detailed log: %s", rename_ws)
            for stage_name in MODES:
                if stage_name in self:
                    self[stage_name]['workspace'] = f"{self['workspace']}{os.sep}{stage_name}"
        latest_link = os.path.join(settings.history_path, latest)
        if os.path.islink(latest_link):
            os.unlink(latest_link)
        os.symlink(self['workspace'], latest_link)
        self['finishAt'] = datetime.now()
        if settings.experimental_plan.uri:
            self.__create_result_info()

        logger.info('[CONTEXT] Total elapsed second : %.2f', self.elapsed_seconds)
        self.retain_history()

    def retain_history(self):
        paths = settings.experimental_plan.control.backup.retain(settings.history_path)
        logger.debug("[HISTORY] remove old directory : %s", paths)

    @property
    def elapsed_seconds(self):
        return ((self['finishAt'] if self.get('finishAt') else datetime.now()) - self['startAt']).total_seconds()

    def summary(self, phase_name: str):
        phase = self.get(phase_name)
        if not phase:
            return None
        summaries = {}
        for pipe_name in phase.get(RUN_PIPELINE_NAME, []):
            summary = phase.get(pipe_name, {}).get('summary', None)
            if summary:
                summaries[pipe_name] = summary
        if len(summaries) == 1:
            for _, v in summaries.items():
                return v
        return summaries


def _v1_convert_sol_args(stage_name, _args):
    """ - Delete any args in the selected user parameters that have empty values.
        - Convert string type comma splits into a list.

    Args:
        _args   (dict): args tobe converted

    Returns:
        _args   (dict): converted args
    """
    # TODO Should we check the types of user parameters to ensure all selected_user_parameters types are validated?
    if not isinstance(_args, dict):
        raise AloErrors['ALO-PIP-009'](f"selected_user_parameters args. in solution_medata must have << dict >> type : {_args}", pipeline=stage_name)
    if not _args:
        return _args
    # when a multi-selection comes in empty, the key is still sent \
    # e.g. args : { "key" : [] }
    _args_copy = deepcopy(_args)
    for k, v in _args_copy.items():
        # single(multi) selection
        # FIXME Although a dict type might not exist, just in case... \
        # (perhaps if a dict needs to be represented as a str, it might be possible?)
        if isinstance(v, list) or isinstance(v, dict):
            if len(v) == 0:
                del _args[k]
        elif isinstance(v, str):
            if (v is None) or (v == ""):
                del _args[k]
            else:
                # 'a, b' --> ['a', 'b']
                converted_string = [i.strip() for i in v.split(',')]
                if len(converted_string) == 1:
                    # ['a'] --> 'a'
                    _args[k] = converted_string[0]
                elif len(converted_string) > 1:
                    # ['a', 'b']
                    _args[k] = converted_string
                    # int, float
        else:
            if v is None:
                del _args[k]
    return _args


def print_copyright():
    ColorMessage.bold_cyan(f"""{"=" * 80}\n{pyfiglet.figlet_format(" Let's ALO  -  ! !", font="slant")}\n{"=" * 80}""")
    ColorMessage.bold(COPYRIGHT)


class Computing(metaclass=ABCMeta):
    """ 학습/추론 기능 구현을 위한 추상클래스

    """

    def __init__(self):
        self.experimental_plan = None
        self.solution_metadata = None
        print_copyright()
        self.init()
        

    def init(self):
        settings.update()
        self.experimental_plan = settings.experimental_plan
        self.solution_metadata = settings.solution_metadata
        if not self.experimental_plan:
            raise AloErrors['ALO-INI-000']('experimental_plan.yaml information is missing.')

    def install(self):
        source_path = self.checkout_git()
        self.install_pip(source_path)
        self.load_module()

    def reload(self):
        """ 환경 설정 정보 및 library 재설정
        """
        self.init()
        self.install()
        self.show_version()

    def run(self):
        try:
            self.solve()
        except Exception as e:
            error = e if isinstance(e, AloError) else AloError(str(e))
            logger.exception(error)
            raise error
        if settings.register:  # check the register flag
            self.register_solution()

    def show_version(self):
        logger.info("\033[96m\n=========================================== Info ==========================================="
                    f"\n- Time (UTC)        : {datetime.now(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')}"
                    f"\n- Alo               : {__version__}"
                    f"\n- Solution Name     : {self.experimental_plan.name}"
                    f"\n- Solution Version  : {self.experimental_plan.version}"
                    f"\n- Solution Plan     : {self.experimental_plan.uri}"
                    f"\n- Solution Meta     : {self.solution_metadata.uri if self.solution_metadata else ''}"
                    f"\n- Home Directory    : {settings.home}"
                    "\n============================================================================================\033[0m")

    def load_module(self):
        self.experimental_plan.solution.update_pipeline()

    @abstractmethod
    def solve(self):
        pass

    def exec_stage(self, context, stage_name):
        context['stage'] = stage_name
        context[stage_name] = self.stage(context, stage_name, f'{context["workspace"]}/{stage_name}')
        context['model'].validate(stage_name)
        context[stage_name][ARTIFACT].validate()

    @add_logger_handler
    @log_start_finish(logger, "{}", highlight=True, args_indexes=[1])
    @profile_resource
    def stage(self, context, stage_name, stage_workspace):
        stage = getattr(self.experimental_plan.solution, stage_name)
        if not stage:
            logger.debug("[PIPELINE] Empty %s info. Skip %s", stage_name, stage_name)
            return
        for pipe_name, function in stage.pipeline.items():
            logger.debug("[PIPELINE] %10s : %15s - %s.%s", stage_name, pipe_name, function.def_.__module__, function.def_.__name__)

        pipeline = context[stage_name]
        dataset_files = stage.get_dataset(pipeline['dataset']['workspace'])
        pipeline['dataset'].add(dataset_files)

        logger.debug('[PIPELINE] List of imported dataset:\n%s', "\n".join(dataset_files))
        extract_file(dataset_files, pipeline['dataset']['workspace'])
        model_files = stage.get_model(context['model']['workspace'])
        logger.debug('[PIPELINE] List of imported model:\n%s', "\n".join(model_files))
        extract_file(model_files, context['model']['workspace'])
        pipeline['startAt'] = datetime.now()
        for pipe_name, function in stage.pipeline.items():
            if settings.mode_pipeline and pipe_name not in settings.mode_pipeline:
                logger.warning("[PIPELINE] Skip solution.%s.%s : --mode_pipeline %s", stage_name, pipe_name, settings.mode_pipeline)
                continue
            pipeline[pipe_name] = {
                'startAt': datetime.now(),
                'workspace': pipeline['workspace'],
                ARTIFACT: pipeline[ARTIFACT],
            }
            # Get data files
            self.pipeline(context, pipeline, pipeline[pipe_name], pipe_name, function)
            pipeline[pipe_name]['finishAt'] = datetime.now()
            pipeline[RUN_PIPELINE_NAME].append(pipe_name)
        pipeline['finishAt'] = datetime.now()

        return pipeline

    @log_start_finish(logger, "{} pipline", highlight=False, args_indexes=[3])
    def pipeline(self, context: dict, pipeline: OrderedDict, pipe: dict, name: str, function) -> dict:
        func_kwargs = function.get_argument()
        # before
        pipeline[name]['argument'] = func_kwargs
        clone_context = deepcopy(context)
        logger_fn = logger.error
        try:
            result = function.def_(clone_context, clone_context[context['stage']], **func_kwargs)
            context['model'].update(clone_context['model'])
            context['external'].update(clone_context['external'])
            pipeline[name]['result'] = result
            # after
            summary = self.save_output(context, name, pipe, result)
            logger_fn = logger.info
        except AloError as e:
            raise e
        except Exception as e:
            raise AloErrors["ALO-USR-001"](str(e), doc={"file": inspect.getfile(function.def_), "function": f"{function.def_.__name__}()", "message": str(e)}) from e
        finally:
            logger_fn(
                "[PIPELINE] function call info\n"
                "***************************** Invoke Pipline Function *****************************\n"
                "* Target File             : %s\n"
                "* function[name]          : %s\n"
                "* function[name].def      : %s.%s\n"
                "* function[name].argument : %s\n"
                "* summary                 : %s\n"
                "***********************************************************************************",
                inspect.getfile(function.def_), name, function.def_.__module__, function.def_.__name__, func_kwargs, pipe.get('summary', ''))

    def checkout_git(self):
        try:
            if self.experimental_plan.solution.git is None:
                logger.info('[GIT] "git" property is not set.')
                return
            name = self.experimental_plan.solution.git.url.path.split('/')[-1].split('.')[0]
            path = f"{settings.workspace}/{name}"
            self.experimental_plan.solution.git.checkout(path)
            logger.debug("[GIT] checkout : %s -> %s", self.experimental_plan.solution.git.url, path)
            return path
        except Exception as e:
            raise AloErrors["ALO-PIP-001"](str(e)) from e

    def install_pip(self, source_path: str):
        installed_packages_file = os.path.join(ASSET_PACKAGE_PATH, "installed_packages.txt")
        
        if not os.path.exists(ASSET_PACKAGE_PATH):
            os.makedirs(ASSET_PACKAGE_PATH, exist_ok=True)

        try:
            if not self.experimental_plan.solution.pip:
                return
            if source_path is None:
                source_path = os.path.dirname(self.experimental_plan.uri)
            req_file = os.path.join(source_path, 'requirements.txt')
            if self.experimental_plan.solution.pip.requirements is True and not os.path.exists(req_file):
                raise AloErrors["ALO-INI-003"](req_file)

            install_packages = []
            if self.experimental_plan.solution.pip.requirements is True:
                install_packages.append(f"-r {req_file}")
            elif isinstance(self.experimental_plan.solution.pip.requirements, list):
                for req in self.experimental_plan.solution.pip.requirements:
                    if req.endswith('.txt'):
                        req_file = os.path.join(os.path.dirname(self.experimental_plan.uri), req)
                        if not os.path.exists(req_file):
                            raise AloErrors["ALO-INI-003"](req_file)
                        req = f"-r {req_file}"
                    install_packages.append(req)
            else:
                logger.debug("[PIP] Skip pip install")
                return
            
            installed_packages = []
            for package in install_packages:
                try:
                    exists_package = pkg_resources.get_distribution(package)
                    installed_packages.append(package)
                    logger.debug("[PIP] %s already installed: %s", package, exists_package)
                except Exception:
                    logger.debug("[PIP] Start installing package - %s", package)
                    self.experimental_plan.solution.pip.install(package)
                    installed_packages.append(package)

            with open(installed_packages_file, 'w') as f:
                for package in installed_packages:
                    f.write(f"{package}\n")
                logger.debug("[PIP] Installed packages written to %s", installed_packages_file)
        except Exception as e:
            raise AloErrors['ALO-INI-002'](str(e)) from e

    def save_output(self, context: dict, pipe_name: str, pipe: dict, output):
        if output is None:
            return
        if isinstance(output, dict):
            if output.get('summary'):
                summary_data = save_summary(context['solution_metadata_version'], os.path.join(pipe['workspace'], "score", f"{pipe_name}_summary.yaml"),
                                            **output.get('summary'))
                pipe['summary'] = summary_data

    def backup_to_v1(self, workspace, stage_name):
        if not workspace:
            return
        # edge app의 지정된 경로에 복사
        v1_path = f'{getattr(settings, f"v1_{stage_name}_artifacts_path")}'
        shutil.rmtree(v1_path, ignore_errors=True)
        copytree(workspace, v1_path)
        logger.debug("[ARTIFACTS] Copy %s to %s", workspace, v1_path)

        # train 인 경우 model 폴더를 workspace train 폴더로 복사
        if stage_name == TRAIN:
            copytree(settings.v1_model_artifacts_path, os.path.join(workspace, "model"))

    def artifact(self, context, stage_name):
        stage = getattr(self.experimental_plan.solution, stage_name)
        pipeline = context[stage_name]
        put_files = []

        def filter_compress(info):  # dataset 폴더는 압축 대상에서 제외
            if re.search(r'^[^\/]+\/dataset(\/|$)', info if isinstance(info, str) else info.name):
                return None
            else:
                return info

        if stage_name == TRAIN:
            put_files.extend(stage.put_data(settings.v1_model_artifacts_path, "model"))  # model.tar.gz
        put_files.extend(stage.put_data(os.path.join(pipeline['workspace'], "log", LOG_PIPELINE_FILE_NAME), LOG_PIPELINE_FILE_NAME))  # pipeline.log
        put_files.extend(stage.put_data(os.path.join(settings.log_path, LOG_PROCESS_FILE_NAME), LOG_PROCESS_FILE_NAME))  # process.log
        put_files.extend(stage.put_data(pipeline['workspace'], f"{stage_name}_artifacts", filter=filter_compress))  # train_artifacts.tar.gz
        logger.debug('[ARTIFACT] List of artifacts :\n%s', "\n".join(put_files))
        logger.debug("[ARTIFACT] Success save to : %s", stage.artifact_uri)

    def update_experimental_plan(self, stage_name: str):
        # todo overwrite plan.
        # todo Hardcoded.
        # todo Need more generic convention method.
        if not self.solution_metadata:
            logger.info("[YAML] Skip update experimental_plan property:  Empty solution_metadata.")
            return
        source = self.solution_metadata.get_pipeline(stage_name)
        if not source:
            logger.info("[YAML] Skip update experimental_plan property: Empty %s pipeline information in solution_metadata.", stage_name)
            return
        target = getattr(self.experimental_plan.solution, stage_name)
        if not target:
            logger.info("[YAML] Skip update experimental_plan property: Empty %s pipeline information in experimental_plan.", stage_name)
            return

        # update uri, aws credential
        for uri in ['dataset_uri', 'model_uri', 'artifact_uri']:
            source_uri = getattr(source, uri, None)
            if not source_uri:
                setattr(target, uri, [])  # None 인 경우 미동작으로 설정
                continue
            setattr(target, uri, source_uri)
            update_s3_credential(self.experimental_plan.solution.credential, target)

        # update selected_user_parameters
        for func_name, function in target.pipeline.items():
            if not source.parameters or not source.parameters.get_type_args("selected_user", func_name):
                logger.debug("[YAML] Skip update: pipeline.paramters.[%s] not define in solution_metadata.", func_name)
                continue
            sol_args = _v1_convert_sol_args(stage_name, source.parameters.get_type_args("selected_user", func_name))
            if sol_args:
                function.update(sol_args)  # 정의되지 않은 속성의 경우 기존 값을 그대로 사용하게 됨 v1 로직 유지

        self.experimental_plan.solution.version = self.solution_metadata.version

    def register_solution(self, id = None, pw = None, description = None):

        try:
            logger.info("[REGISTER] Starting solution registration...")
            # 솔루션 등록 로직 추가
            # experimental_plan = object_to_dict(self.experimental_plan)
            register = SolutionRegister(self.experimental_plan, description)
            register.execute(id, pw)
            logger.info("[REGISTER] Solution registration completed.")
        except Exception as e:
            logger.exception(e)
            raise AloErrors['ALO-REG-001'](str(e)) from e

    def history(self, data_id="", param_id="", code_id="", parameter_steps=[], type=MODES, head: int = None, tail: int = None, show_table=False):
        """ Deliver the experiment results stored in history as a table,
            allowing for solution registration by history id.
            After verifying the identity between experimental_plan.yaml in the
            history folder and each id, create a table.

        Args:
            data_id         (str): data id
            param_id        (str): parameters id
            code_id         (str): source code id
            parameter_steps (list): decide which step's parameters to display when creating a table
            type            (str): train or inference (default: [train, inference])
            head            (int): output the first part of history
            tail            (int): output the first part of history

        Returns: -

        """
        if self.experimental_plan is None:
            self.init()
        scores = []

        def make_score(event: str, mode: str, status: str, result_info: dict, summary: dict):
            score = {
                'id': event,
                'status': status,
                'type': mode,
                **result_info.get(mode, {}),
                **{i: summary.get(i, None) for i in ['pipeline_name', 'score', 'result', 'note', 'probability', 'version']},
                'checksum': {**summary.get('checksum', {}),
                             EXP_FILE_NAME: result_info.get('checksum', None)}
            }
            scores.append(score)

        pipeline_type = type if isinstance(type, list) else [type]
        dirs = [(folder, os.path.join(settings.history_path, folder),) for folder in os.listdir(settings.history_path) if not folder.startswith('latest')]
        dirs = sorted(dirs, key=lambda x: x[0])
        dir_size = len(dirs)
        if head:
            dirs = dirs[:head]
        if tail:
            dirs = dirs[-tail:]
        for folder, folder_path in dirs:
            name_group = HISTORY_PATTERN.search(folder)
            if not name_group:
                continue

            result_info_file = os.path.join(folder_path, RESULT_INFO_FILE)
            if not os.path.exists(result_info_file):
                scores.append({'id': name_group[1], 'status': 'error' if name_group[2] else 'success'})
                continue
            with open(result_info_file, 'r') as f, open(os.path.join(folder_path, EXP_FILE_NAME), 'r') as plan_f:
                print(result_info_file)
                try:
                    result_info = json.load(f)
                except Exception as e:
                    result_info = {}
                result_info['checksum'] = hashlib.md5(plan_f.read().encode()).hexdigest()[:8]

            for mode in [pipe for pipe in pipeline_type if pipe in MODES]:
                if mode not in result_info:
                    continue
                summary_files = [(os.path.join(folder_path, mode, "score", temp), temp.replace('_summary.yaml', ''))
                                 for temp in os.listdir(os.path.join(folder_path, mode, "score")) if not folder.endswith('_summary.yaml')]
                for file_path, pipeline_name in summary_files:
                    summary = {'pipeline_name': pipeline_name}
                    if os.path.isfile(file_path):
                        try:
                            with open(file_path, 'r') as f:
                                summary = yaml.safe_load(f)
                                summary['pipeline_name'] = pipeline_name
                        except Exception as e:
                            logger.warning("An error occurred while reading the file : %s", file_path)
                    summary['checksum'] = {'argument': hashlib.md5(json.dumps(result_info.get(mode, {}).get('argument', {})).encode()).hexdigest()[:8],
                                           'dataset': {}}
                    len_dir_path = len(os.path.join(folder_path, mode, 'dataset'))
                    for root, _, files in os.walk(os.path.join(folder_path, mode, 'dataset')):
                        for file in files:
                            file_path = os.path.join(root, file)
                            with open(file_path, 'r') as f:
                                summary['checksum']['dataset'][file_path[len_dir_path + 1:]] = hashlib.md5(f.read().encode()).hexdigest()[:8]
                    make_score(name_group[1], mode, 'error' if name_group[2] else 'success', result_info, summary)

        logger.debug("Search history : %s/%s", len(dirs), dir_size)
        if show_table:
            print_table(scores, **(show_table if isinstance(show_table, dict) else {}))

        return scores


class OneTime(Computing, metaclass=ABCMeta):
    """ 학습/추론 과정을 1회만 수행하는 클래스

    프로그램 종료됨

    """

    def solve(self, modes: list = MODES if settings.mode is None else settings.mode):
        with Context() as context:
            for name in MODES:
                if name not in modes:
                    logger.info("Skip %s()", name)
                    continue
                if not getattr(self.experimental_plan.solution, name):
                    logger.info("Skip solution.%s : Not define in experimental_plan.yaml", name)
                    continue
                try:
                    if name == TRAIN:
                        self.init_train()
                    self.update_experimental_plan(name)
                    self.exec_stage(context, name)
                    self.artifact(context, name)
                except Exception as e:
                    raise e
                finally:
                    self.backup_to_v1(context[name]['workspace'], name)

    def init_train(self):
        files = glob.glob(os.path.join(settings.v1_model_artifacts_path, "*"))
        for f in files:
            os.remove(f)

    def __update_func_kwargs(self, stage_name: str, argument: dict):
        stage = getattr(self.experimental_plan.solution, stage_name, None)
        if stage is None or argument is None:
            return
        if not isinstance(argument, dict):
            raise ValueError("""train/inference function argument must be dict type. Ex)
{
    'preprocess': {
        'x_columns': [ 'Pclass', 'Sex', 'SibSp', 'Parch' ],
        'y_column': 'Survived',
        'n_estimators': 100
    },
    'train': {
        'x_columns': [ 'Pclass', 'Sex', 'SibSp', 'Parch' ]
    }
}""")
        for k, v in argument.items():
            if k not in stage.pipeline:
                continue
            stage.pipeline[k].update(v)

    def train(self, argument: dict = None):
        self.__update_func_kwargs(TRAIN, argument)
        self.solve([TRAIN])

    def inference(self, argument: dict = None):
        self.__update_func_kwargs(TRAIN, argument)
        self.solve([INFERENCE])


class Standalone(OneTime):
    pass


class Sagemaker(OneTime):
    pass


class DaemonStatusType(Enum):
    """ 백그라운드 작업 상태 코드

    """
    WAITING = 'waiting'
    SETUP = 'setup'
    LOAD = 'load'
    RUN = 'run'
    SAVE = 'save'
    FAIL = 'fail'


class Daemon(Computing):
    """ 백그라운드에서 실행되며, redis를 통해 추론 데이터 수신시 작업 수행하는 데몬 클래스

    """
    CHANNEL_STATUS = "alo_status"
    CHANNEL_FAIL = "alo_fail"

    def __init__(self, **kwargs):
        self.__redis_status = None
        self.__redis_pubsub = None
        self.__status = None
        super().__init__(**kwargs)
        with open(f'{settings.home}/alo/config/redis_error_table.json', 'r', encoding='utf-8') as file:
            self.redis_error_table = json.load(file)

    def init(self):
        super().init()
        if self.solution_metadata is None:
            raise AloErrors['ALO-INI-000']('solution_meta.yaml information is missing. "--system solution_meta.yaml option" must be specified.')
        try:
            self.__redis_status = redis.Redis(self.solution_metadata.edgeapp_interface.redis_server_uri.host,
                                              self.solution_metadata.edgeapp_interface.redis_server_uri.port,
                                              self.solution_metadata.edgeapp_interface.redis_db_number)
            self.__redis_pubsub = redis.StrictRedis(self.solution_metadata.edgeapp_interface.redis_server_uri.host,
                                                    self.solution_metadata.edgeapp_interface.redis_server_uri.port,
                                                    self.solution_metadata.edgeapp_interface.redis_db_number)
            logger.debug("Redis Server(DB): %s(%s)",
                         self.solution_metadata.edgeapp_interface.redis_server_uri,
                         self.solution_metadata.edgeapp_interface.redis_db_number)
        except Exception as e:
            raise AloErrors['ALO-INI-004'](str(e)) from e
        self.pubsub_edgeapp('publish', self.CHANNEL_STATUS, "booting")

    def __send_edgeapp(self, redis, method, *args, **kwargs):
        try:
            result = getattr(redis, method)(*args, **kwargs)
            logger.debug("[REDIS] %s(%s, %s) : %s", method, args, kwargs, result)
            return result
        except Exception as e:
            raise AloErrors['ALO-INI-004'](f"{method}({args},{kwargs})") from e

    def interface_edgeapp(self, method, *args, **kwargs):
        return self.__send_edgeapp(self.__redis_status, method, *args, **kwargs)

    def pubsub_edgeapp(self, method, *args, **kwargs):
        if len(args) >= 2 and args[0] == self.CHANNEL_STATUS:
            self.__status = args[1]
        return self.__send_edgeapp(self.__redis_pubsub, method, *args, **kwargs)

    def error_to_code(self, error):
        code = "E000"
        comment = None
        if isinstance(error, AloError):
            # todo
            # error.code == ''
            comment = str(error)

        return {**self.redis_error_table[code], 'COMMENT': comment} if comment else self.redis_error_table[code]

    def solve(self):
        try:
            self.update_experimental_plan(INFERENCE)
            stage = getattr(self.experimental_plan.solution, INFERENCE)
            model_files = stage.get_model(settings.v1_model_artifacts_path)
            logger.debug('[MODEL] List of imported model:\n%s', "\n".join(model_files))
            extract_file(model_files, settings.v1_model_artifacts_path)
        except Exception as e:
            logger.exception(e)
            self.interface_edgeapp('rpush', 'inference_summary', json.dumps({'status': 'fail', 'message': str(e)}))
            self.interface_edgeapp('rpush', 'inference_artifacts', json.dumps({'status': 'fail', 'message': str(e)}))
            raise e

        logger.debug('[DAEMON] Get ready.')
        while True:
            try:
                self.pubsub_edgeapp('publish', self.CHANNEL_STATUS, DaemonStatusType.WAITING.value)
                response = self.interface_edgeapp('blpop', "request_inference", timeout=0)
                if response is None:
                    continue
                self.pubsub_edgeapp('publish', self.CHANNEL_STATUS, DaemonStatusType.SETUP.value)
                with Context() as context:
                    self.solution_metadata = load_model(json.loads(response[1].decode('utf-8')).get('solution_metadata'), SolutionMetadata)
                    self.update_experimental_plan(INFERENCE)
                    self.pubsub_edgeapp('publish', self.CHANNEL_STATUS, DaemonStatusType.RUN.value)
                    self.exec_stage(context, INFERENCE)
                    summary = json.dumps({'status': 'success', 'message': context.summary(INFERENCE)})
                    self.interface_edgeapp('rpush', 'inference_summary', summary)
                    self.pubsub_edgeapp('publish', self.CHANNEL_STATUS, DaemonStatusType.SAVE.value)
                    self.artifact(context, INFERENCE)
                    self.interface_edgeapp('rpush', 'inference_artifacts', summary)
            except Exception as e:
                logger.exception(e)
                logger.error('[DAEMON] Due to an error, the current step is skipped. Waiting for the next request')
                self.pubsub_edgeapp('publish', self.CHANNEL_STATUS, DaemonStatusType.FAIL.value)
                self.pubsub_edgeapp("publish", self.CHANNEL_FAIL, json.dumps(self.error_to_code(e)))
                self.interface_edgeapp('rpush', 'inference_summary', json.dumps({'status': 'fail', 'message': str(e)}))
                if self.__status == DaemonStatusType.SAVE.value:
                    self.interface_edgeapp('rpush', 'inference_artifacts', json.dumps({'status': 'fail', 'message': str(e)}))
                else:
                    self.interface_edgeapp('rpush', 'inference_summary', json.dumps({'status': 'fail', 'message': str(e)}))
                    self.interface_edgeapp('rpush', 'inference_artifacts', json.dumps({'status': 'fail', 'message': str(e)}))
                # backoff 적용시 현재 위치에 적용
            finally:
                self.backup_to_v1(context[INFERENCE].get('workspace'), INFERENCE)


class SolutionRegister:
    """ 솔루션 등록 기능을 담당하는 class

    """

    def __init__(self, experimental_plan, description):
        self.experimental_plan = experimental_plan
        self.description = description

    def execute(self, id, pw):
        # 솔루션 등록 로직 구현
        logger.info(f"Registering solution: {self.experimental_plan.name}")
        register = solution_register(infra_setup=None, solution_info=None, experimental_plan=self.experimental_plan, description = self.description)
        register.login(id, pw)
        register.run()


__alo = {
    'local': Standalone,
    'standalone': Standalone,
    'sagemaker': Sagemaker,
    'loop': Daemon,
    'batch': Daemon,
    'daemon': Daemon,
}


def Alo():
    """ 실행 옵션에 따른 실행 방식 선택

    Returns: alo 객체

    """
    return __alo.get(settings.computing)()


def main():
    alo = Alo()
    alo.reload()
    alo.run()
