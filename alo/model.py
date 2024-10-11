"""
ALO input data model

ALO 입력 모델
"""

import collections
import os
import io
import sys
import time
import socket
import subprocess
import git
import json
import boto3
import botocore
import shutil
import re
import glob
import tarfile
import zipfile
import importlib
import dotenv
import shlex
from copy import deepcopy
from logging import getLogger
from abc import ABCMeta, abstractmethod
from pathlib import Path
from enum import IntEnum
from typing import Optional, Union, Dict, OrderedDict, List, Callable, ClassVar, Any
from pydantic_core import Url
from pydantic import (model_validator, field_validator, ValidationError, BaseModel, StrictStr,
                      Field, ValidationInfo, ConfigDict, RedisDsn, HttpUrl,
                      UrlConstraints, computed_field, ByteSize, field_serializer)
from pydantic_settings import BaseSettings, SettingsConfigDict

from alo.__version__ import __version__
from alo.logger import get_logger
from alo.yml_schema import load_yml
from alo.exceptions import AloErrors

try:
    from typing import Literal, Annotated
except ImportError:
    from typing_extensions import Literal, Annotated

S3Url = Annotated[Url, UrlConstraints(allowed_schemes=["s3"])]
GitUrl = Annotated[Url, UrlConstraints(allowed_schemes=['git'])]


S3_URL_PATTERN = re.compile(r"^s3:\/\/([^\/]+)\/(.+)$")

EXP_FILE_NAME = "experimental_plan.yaml"


def import_module(value: str):
    """ python 모듈을 동적으로 로딩하기 위한 함수

    Args:
        value (str): 로딩 대상 python 파일명.함수명

    Returns:
        object: 동적 로딩 모듈

    Raises:
        AloErrors: ALO-PIP-002

    Examples:
        >>> import_module("titanic.train")
    """
    package_names = value.split('.')
    try:
        module = importlib.import_module(".".join(package_names[:-1]))
        return getattr(module, package_names[-1])
    except ModuleNotFoundError as e:
        raise AloErrors["ALO-PIP-002"](str(e), module=value) from e
    except AttributeError as e:
        raise AloErrors["ALO-PIP-002"](str(e), module=value) from e
    except Exception as e:
        raise e


def extract_bucket_key(url: str):
    """ s3 url에서 bucket과 key 값을 추출하기 위한 함수

    Args:
        url: s3 url

    Returns:
        버킷명과, 경로

        example:
        {'bucket': 'aws_s3_bucket', 'key': "test/abc/file.txt"}

    """
    match = S3_URL_PATTERN.search(url)
    if match:
        groups = match.groups()
        if len(groups) != 2:
            raise ValueError(f"{url} is not s3 url pattern. ex) s3://bucketname/dir/example.txt")
        return {
            'bucket': groups[0],
            'key': groups[1]
        }
    raise ValueError(f"{url} is not s3 url pattern. ex) s3://bucketname/dir/example.txt")


def aws_client(client: str, credential: dict):
    """ aws client 객체 전달 함수

    Args:
        client (str): AWS Resource 유형
        credential (dict): boto3 client 옵션

    Returns: boto3 client

    """

    if credential.get('profile_name'):
        try:
            return boto3.Session(profile_name=credential['profile_name']).client(client)
        except botocore.exceptions.ProfileNotFound:
            settings.logger.warning("Profile not found : %s. using default.", credential['profile_name'])
            del credential['profile_name']
    return boto3.client(client, **credential)


def update_s3_credential(aws_credential: dict, stage):
    """ Cloud 서비스 제공자의 인증 정보 업데이트

    Args:
        aws_credential: 기본 credential 정보
        stage: train or inference

    """
    if not update_s3_credential:
        return
    for j in ['dataset_uri', 'model_uri', 'artifact_uri']:
        for file in getattr(stage, j):
            if isinstance(file, S3File) and not file.credential:
                file.credential = {k: v for k, v in aws_credential.items()}


def copytree(src, dst):
    if not os.path.exists(dst):
        Path(dst).mkdir(parents=True, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


class AloModel(BaseModel):
    """

    """
    model_config = ConfigDict(use_enum_values=True, use_attribute_docstrings=True)


class ControlBackup(AloModel, metaclass=ABCMeta):
    @abstractmethod
    def retain(self, path) -> list:
        pass


class BackupRetainSize(ControlBackup):
    type: Literal['size']
    value: ByteSize = Field(default=10**9, description="최대 저장 공간 사이즈(1024000000 또는 1GB)")

    def retain(self, path):
        size = 0
        result = []
        for name in sorted([name for name in os.listdir(path)], reverse=True)[1:]:
            target = f'{path}/{name}'
            size += sum(p.stat().st_size for p in Path(target).rglob('*'))
            if size < self.value:
                continue
            shutil.rmtree(target, ignore_errors=True)
            result.append(target)
        return result

    @model_validator(mode='after')
    def backup_value(self):
        assert self.value > 0, f'{self.value} of a must be greater than 0'
        return self


class BackupRetainCount(ControlBackup):
    type: Literal['count']
    value: int = Field(default=1000, description="최대 저장 개수")

    @field_validator('value')
    @classmethod
    def backup_value(cls, val: int, info: ValidationInfo) -> int:
        assert val > 0, f'{info.field_name} of a must be greater than 0'
        return val

    def retain(self, path):
        result = []
        for name in sorted([name for name in os.listdir(path) if not name.startswith('latest')])[:-self.value]:
            target = f'{path}/{name}'
            shutil.rmtree(target, ignore_errors=True)
            result.append(target)
        return result


class BackupRetainDay(ControlBackup):
    type: Literal['day']
    value: int = Field(default=7, description="수행 이력 최대 저장 일수")

    @field_validator('value')
    @classmethod
    def backup_value(cls, val: int, info: ValidationInfo) -> int:
        assert val > 0, f'{info.field_name} of a must be greater than 0'
        return val

    def retain(self, path):
        result = []
        for name in os.listdir(path):
            target = f'{path}/{name}'
            create_time = os.path.getctime(target)
            current_time = time.time()
            if create_time < current_time - self.value * 86400:
                shutil.rmtree(target, ignore_errors=True)
                result.append(target)
        return result


class Control(AloModel):
    backup: Union[BackupRetainSize, BackupRetainCount, BackupRetainDay] = Field(default=BackupRetainSize(type='size'), discriminator='type',
                                                                                description="백업 방식 정의(default: 최대 1GB 보관)")
    check_resource: bool = Field(default=False, description="CPU/Memory 리소스 사용량 정보 출력 여부")


class GitOption(AloModel):
    reset: bool = Field(False, description="관리 대상 파일이 수정된 경우 원상태로 복구 여부")
    clean: bool = Field(False, description="관리 대상 파일이 아닌 항목 삭제 여부")
    refresh: bool = Field(True, description="패키지 설치 및 asset 존재 여부를 실험 시마다 체크 할지, 한번만 할지 결정")


class Git(AloModel):
    url: Union[HttpUrl, GitUrl] = Field(description="git repository url")
    # urls: List[AnyUrl] = Field(default=None, description="git repository url")
    branch: str = Field(default='main', description="브랜치명")
    id: str = Field(default=None, description="로그인 ID")
    password: str = Field(default=None, description="로그인 패스워드")
    option: GitOption = Field(default=GitOption(), description="git 정책 적용")

    # @model_validator(mode='after')
    # def check_url_or_urls(self):
    #     if not (self.url or self.urls):
    #         raise ValueError('Either url or urls is required')
    #     return self

    def checkout(self, source_path):
        if os.path.exists(source_path):
            repo = git.Repo(source_path)
            if self.option.reset:
                repo.git.reset('--hard')
            if self.option.clean:
                repo.git.clean('-fdx')
            if self.option.refresh:
                repo.remotes.origin.fetch()
                repo.git.reset('--hard')
                repo.remotes.origin.pull()
        else:
            repo = git.Repo.clone_from(self.url, source_path)
            repo.git.checkout(self.branch)
        sys.path.append(source_path)


class Pip(AloModel):
    options: Optional[List[str]] = Field(default=None, description="Install Options")
    requirements: Union[bool, List[str]] = Field(default=False, description="Package Names")

    def install(self, package_name: str):
        args = [sys.executable, '-m', 'pip', 'install']
        args.extend(shlex.split(package_name))
        if self.options:
            args.extend(self.options)
        subprocess.check_call(args)
        settings.logger.info("[PIP] Install complete : %s", package_name)


class FileStorage(metaclass=ABCMeta):
    @abstractmethod
    def get(self, destination) -> str:
        pass

    @abstractmethod
    def put(self, source, file_name: str = None, filter=None) -> str:
        pass

    @abstractmethod
    def extension(self) -> str:
        pass

    @abstractmethod
    def url(self) -> str:
        pass


class FileCompress(BaseModel):
    enable: bool = Field(True, description="압축 유무")
    type: Literal['tar.gz', 'zip'] = Field("tar.gz", description="압축 파일 유형")

    def compress(self, file_io, path: str, filter=None):
        len_prefix_source = len(os.sep.join(path.split(os.sep)[:-1]))
        compressed_files = []
        with (tarfile.open(fileobj=file_io, mode="w|gz") if self.type == 'tar.gz' else zipfile.ZipFile(file_io, mode='w')) as f:
            len_dir_path = len(path)
            for root, _, files in os.walk(path):
                if filter and not filter(root[len_prefix_source + 1:]):
                    continue
                for file in files:
                    file_path = os.path.join(root, file)
                    compressed_files.append(file_path)
                    (f.add if self.type == 'tar.gz' else f.write)(file_path, arcname=file_path[len_dir_path:])
        file_io.seek(0)
        return compressed_files


class LocalFile(AloModel, FileStorage):
    path: str = Field(description="파일명")
    compress: Union[bool, FileCompress] = Field(FileCompress(), description="파일 압축 여부")

    def get(self, destination) -> str:
        if os.path.isfile(self.path):
            shutil.copy2(self.path, destination)
        elif os.path.isdir(self.path):
            copytree(self.path, destination)
        else:
            raise AloErrors['ALO-INI-003'](self.path)
        file_name = f'{destination}{os.sep}{self.path.split(os.sep)[-1]}'
        settings.logger.debug('[FILE] Import complete: %s to %s', self.path, file_name)
        return file_name

    def put(self, source, file_name: str = None, filter=None) -> str:
        target_path = os.path.join(self.path, file_name) if file_name else self.path
        target_dir = os.sep.join(target_path.split(os.sep)[:-1])
        if not os.path.exists(target_dir):
            Path(target_dir).mkdir(parents=True, exist_ok=True)
        if os.path.isfile(source):
            shutil.copy2(source, target_path)
            settings.logger.debug('[FILE] Export complete: %s to %s', source, self.path)
        elif os.path.isdir(source):
            save_name = os.path.join(target_dir, f'{file_name}.{self.compress.type}')
            with io.BytesIO() as file_io, open(save_name, "wb") as binary_file:
                compressed_files = self.compress.compress(file_io, source, filter)
                binary_file.write(file_io.getbuffer())
            if compressed_files:
                settings.logger.debug('[FILE] Compressed(%s) and Export complete: %s to %s', compressed_files, source, save_name)
            else:
                os.remove(save_name)
                settings.logger.warning('[FILE] Compressed Files is empty: %s', source)
        else:
            raise AloErrors['ALO-INI-003'](self.path)

    def extension(self) -> str:
        return self.path.split(os.sep)[-1]

    def url(self):
        return self.path


class S3File(AloModel, FileStorage):
    bucket: str = Field(description="버킷명")
    key: str = Field(description="path")
    compress: Union[bool, FileCompress] = Field(FileCompress(), description="파일 압축 여부")
    credential: Dict[str, str] = Field(default={}, repr=False, description="접근 환경 정보")
    config: dict = Field(default=None, description="S3 config 옵션")

    @field_validator('compress')
    def convert_compress(cls, value) -> str:
        if isinstance(value, bool):
            return FileCompress(enable=value)
        return value

    @field_validator('credential')
    def check_profile(cls, value) -> str:
        if isinstance(value, dict) and 'profile_name' in value:
            try:
                boto3.Session(profile_name=value['profile_name'])
            except botocore.exceptions.ProfileNotFound as e:
                raise ValueError(f""""{value['profile_name']}" not found in aws credential. Run this command to quickly set and view your credentials: aws configure""") from e
        return value

    def get(self, destination) -> str:
        try:
            s3 = aws_client('s3', self.credential)
            paginator = s3.get_paginator('list_objects_v2')
            page_iter = paginator.paginate(Bucket=self.bucket, Prefix=self.key, PaginationConfig={'PageSize': 1000})
            contents = [content for page in page_iter for content in page.get('Contents', [])]
            if len(contents) == 0:
                raise ValueError(f"[S3] Not found object in S3 : s3://{self.bucket}/{self.key}")
            for content in contents:
                if '//' in content['Key']:
                    settings.logger.warning("[S3] Not allow path. Skip: %s", content['Key'])
                    continue
                post_fix = content['Key'].replace('/'.join(self.key.split('/')[:-1]), '')
                post_fix = post_fix.replace('/', '', 1) if post_fix.startswith('/') else post_fix
                if not post_fix:
                    path = destination
                    name = content['Key'].split('/')[-1]
                else:
                    post_keys = post_fix.split('/')
                    name = post_keys[-1]
                    path = destination if len(post_keys) == 1 else os.path.join(destination, os.sep.join(post_keys[:-1]))
                    if not os.path.exists(path):
                        Path(path).mkdir(parents=True, exist_ok=True)
                target = os.path.join(path, name)
                with open(target, 'wb') as f:
                    s3.download_fileobj(self.bucket, content['Key'], f, Config=self.config)
                    settings.logger.debug('[S3] Download complete: s3://%s/%s to %s', self.bucket, content['Key'], target)
        except botocore.exceptions.ClientError as e:
            raise AloErrors['ALO-PIP-007'](str(e), pipeline=f"s3://{self.bucket}/{self.key}") from e

        return destination

    def put(self, source, file_name: str = None, filter=None) -> str:
        prefix_key = self.key.rstrip("/")
        s3 = aws_client('s3', self.credential)

        if not os.path.exists(source):
            raise AloErrors['ALO-INI-003'](source)

        if os.path.isfile(source):  # 파일인 경우 압축 없이 업로드
            s3.upload_file(source, self.bucket, f'{prefix_key}/{file_name}' if file_name else self.key, Config=self.config)
            settings.logger.debug('[S3] Upload %s to s3://%s/%s', source, self.bucket, f'{prefix_key}/{file_name}' if file_name else self.key)
            return source

        if self.compress.enable:  # 압축인 경우
            arcname = file_name if file_name else os.path.basename(source)
            with io.BytesIO() as file_io:
                compressed_files = self.compress.compress(file_io, source, filter)
                if compressed_files:
                    s3.upload_fileobj(file_io, self.bucket, f'{prefix_key}/{arcname}.{self.compress.type}', Config=self.config)
                    settings.logger.debug('[S3] Compress %s and upload to s3://%s/%s', source, self.bucket, f'{prefix_key}/{arcname}.{self.compress.type}')
                else:
                    settings.logger.warning('[S3] compressed Files is empty and skip upload : %s', source)
        else:
            for root, dirs, files in os.walk(source):
                for filename in files:
                    local_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(local_path, source)
                    key_path = os.path.join(prefix_key, relative_path)
                    s3.upload_file(local_path, self.bucket, key_path, Config=self.config)
                    settings.logger.debug('[S3] Upload %s to s3://%s/%s', source, self.bucket, key_path)
        return source

    def extension(self) -> str:
        return self.key.split('/')[-1]

    def url(self):
        return f's3://{self.bucket}/{self.key}'


def file_discriminator(v):
    if isinstance(v, dict):
        return v.get('pet_type', v.get('pet_kind'))
    return getattr(v, 'pet_type', getattr(v, 'pet_kind', None))


class ArgType(AloModel, metaclass=ABCMeta):
    description: str = Field(None, description="설명")

    @abstractmethod
    def valid(self) -> any:
        pass


class NumberType(ArgType):
    default: Union[int, float] = Field(description="기본 값")
    range: List[Union[int, float]] = Field(min_length=2, max_length=2, description="min, max 범위")

    @model_validator(mode='after')
    def validate_choices(self):
        first_type = type(self.default)
        try:
            assert all([type(v) is first_type for v in self.range])
        except Exception as e:
            raise AloErrors['ALO-PIP-013'](f"The data type of range({self.range}:{[type(v).__name__ for v in self.range]}) "
                                           f"and the default({self.default}:{type(self.default).__name__}) data type must both be the same type.")
        self.valid()
        return self

    def valid(self, val=None):
        if val is None:
            val = self.default
        try:
            assert self.range[0] <= val <= self.range[1]
        except Exception as e:
            raise AloErrors['ALO-PIP-013'](f"The argument value({val}) must be between {self.range[0]} and {self.range[1]}.")

        return val


class SingleSelectType(ArgType):
    default: Union[int, float, str] = Field(description="기본 값")
    choices: List[Union[int, float, str]] = Field(description="선택 대상")

    @model_validator(mode='after')
    def validate_choices(self):
        first_type = type(self.choices[0])
        try:
            assert all([type(v) is first_type for v in self.choices])
        except Exception as e:
            raise AloErrors['ALO-PIP-013'](f"All choices values({self.choices}:{[type(v).__name__ for v in self.choices]})"
                                           f" in A must be of the same data type.") from e

        self.valid()
        return self

    def valid(self, val=None):
        if val is None:
            val = self.default
        try:
            assert val in self.choices
        except Exception as e:
            raise AloErrors['ALO-PIP-013'](f"The argument value({val}) must be one of {self.choices}.") from e

        return self.default


class MultiSelectType(ArgType):
    default: List[Union[int, float, str]] = Field(description="기본 값")
    choices: List[Union[int, float, str]] = Field(description="선택 대상")

    @model_validator(mode='after')
    def validate_choices(self):
        first_type = type(self.choices[0])
        try:
            assert all([type(v) is first_type for v in self.choices])
        except Exception as e:
            raise AloErrors['ALO-PIP-013'](f"All choices values({self.choices}:{[type(v).__name__ for v in self.choices]})"
                                           f" in A must be of the same data type.") from e

        self.valid()
        return self

    def valid(self, val=None):
        if val is None:
            val = self.default
        try:
            assert all([v in self.choices for v in val])
        except Exception as e:
            raise AloErrors['ALO-PIP-013'](f"The argument value({val}) must be a subset of {self.choices}.") from e

        return val


class Function(AloModel):
    def_: Union[str, Callable] = Field(description="python 모듈(module_name.function_name", alias='def')
    argument: dict = Field(default={}, description="모듈 전달 인자명과 값(default값에 해당함)")
    schema: Dict[str, Union[NumberType, SingleSelectType, MultiSelectType, Any]] = Field(default={}, description="argument에 대한 정의")

    def load_module(self) -> None:
        self.def_ = import_module(self.def_)

    @field_serializer('def_')
    def serialize_dt(self, def_: Union[str, Callable], _info):
        if callable(def_):
            return f'{def_.__module__}.{def_.__name__}'
        return def_

    @model_validator(mode='after')
    def update_schema(self):
        for k, v in self.argument.items():
            if k in self.schema:
                s = self.schema[k]
                if isinstance(s, ArgType):
                    s.valid(v)
            else:
                self.schema[k] = v
        return self

    def get_argument(self):
        kwargs = deepcopy(self.argument)
        for k, v in self.schema.items():
            if k not in kwargs:
                kwargs[k] = v.default if isinstance(v, ArgType) else v
        self.argument = kwargs
        return kwargs

    def update(self, sol_args: dict):
        for k, v in sol_args.items():
            if k in self.schema and isinstance(self.schema[k], ArgType):
                self.schema[k].valid(v)
        self.argument.update(sol_args)


def convert_str_to_file(value):
    if isinstance(value, str):
        if value.startswith("s3://"):
            return S3File(**extract_bucket_key(value))
        else:
            return LocalFile(path=value.replace("/" if os.name.lower() == 'nt' else "\\", os.sep))
    elif isinstance(value, FileStorage):
        return value
    else:
        raise ValueError(f"Not Allowed value type: {value}")


# class Step(AloModel):
#     # workspace: str = Field(default=None, description="작업 경로")
#     module: Function = Field(description="실행 모듈(함수)")
#     output: Union[str, LocalFile, S3File] = Field(default=None, description="output data 파일")
#
#     @field_validator('output')
#     def inout_to_file(cls, value) -> str:
#         return convert_str_to_file(value)
#
#     @model_validator(mode='after')
#     def file_extension(self):
#         if not self.output:
#             return self
#         if not self.output.extension().lower().endswith(('.zip', '.tar.gz')):
#             raise ValueError(f"'{self.file.path}' extension is not allowed. Allowable extensions are zip and tar.gz.")
#         return self


class NotificationWhen(IntEnum):
    ERROR = 1
    START = 4
    END = 16
    COMPLETE = 64
    ALLWAYS = ERROR + START + END + COMPLETE


class SolutionData(AloModel):
    train: Union[str, LocalFile, S3File, List[Union[str, LocalFile, S3File]]] = Field([], description="학습용 dataset 파일 정보")
    inference: Union[str, LocalFile, S3File, List[Union[str, LocalFile, S3File]]] = Field([], description="추론 dataset 파일 정보")

    @field_validator("train", 'inference')
    def convert_to_list(cls, value) -> str:
        if isinstance(value, list):
            return [convert_str_to_file(v) for v in value]
        else:
            return [convert_str_to_file(value)]

    def get(self, name, destination):
        if getattr(self, name, None):
            for data in getattr(self, name):
                data.get(destination)


class Pipeline(AloModel):
    model_config = ConfigDict(protected_namespaces=())
    dataset_uri: Union[str, LocalFile, S3File, List[Union[str, LocalFile, S3File]]] = Field([], description="학습용 dataset 경로 정보")
    model_uri: Union[str, LocalFile, S3File, List[Union[str, LocalFile, S3File]]] = Field([], description="추론 model 경로 정보")
    artifact_uri: Union[str, LocalFile, S3File, List[Union[str, LocalFile, S3File]]] = Field([], description="결과 저장용 dataset 파일 정보")
    pipeline: Union[List[str], OrderedDict[str, Function]] = Field(description="파이프라인 구성 정보")

    @field_validator("dataset_uri", "model_uri", "artifact_uri")
    def convert_to_files(cls, value) -> str:
        if isinstance(value, list):
            return [convert_str_to_file(v) for v in value]
        else:
            return [convert_str_to_file(value)]

    def get_dataset(self, destination):
        for file in self.dataset_uri:
            file.get(destination)
        return [name for name in glob.iglob(f'{destination}{os.sep}**', recursive=True) if os.path.isfile(name)]

    def get_model(self, destination):
        for file in self.model_uri:
            file.get(destination)
        files = [name for name in glob.iglob(f'{destination}{os.sep}**', recursive=True) if os.path.isfile(name)]
        return files

    def put_data(self, source, file_name: str = None, filter=None):
        for file in self.artifact_uri:
            file.put(source, file_name, filter)
        return [name for name in glob.iglob(f'{source}{os.sep}**', recursive=True) if os.path.isfile(name)]


class Solution(AloModel):
    RESERVED_KEYWORD: ClassVar[tuple] = ("dataset", "models", "summary", "log", "extra_output", "workspace", "name")

    git: Union[Git, None] = Field(default=None, description="실행 코드 다운로드를 위한 git 정보")
    pip: Pip = Field(default=None, description="필수 라이브러리 목록")
    credential: Dict[str, str] = Field(default={}, repr=False, description="접근 환경 정보")
    function: OrderedDict[str, Function] = Field(description="사용자 정의 함수 input, readiness, preprocess,, 등 ex) 단계명: {...} ")
    train: Union[Pipeline, None] = Field(default=None, description="파이프라인 구성 정보")
    inference: Union[Pipeline, None] = Field(default=None, ddescription="파이프라인 구성 정보")
    version: str = Field(default="", description="solution metadata version")

    @field_validator("function")
    def validate_reserved_keyword(cls, value) -> str:
        for k in value.keys():
            if k in cls.RESERVED_KEYWORD:
                raise AloErrors['ALO-INI-005'](f"solution.function.{k} not allowed. The '{k}' is reserved keyword. {cls.RESERVED_KEYWORD} are reserved words",
                                               file=EXP_FILE_NAME)
        return value

    @model_validator(mode='after')
    def override(self):
        for i in ['train', 'inference']:
            stage = getattr(self, i)
            if not stage:
                continue
            # credential override
            update_s3_credential(self.credential, stage)

        return self

    def update_pipeline(self):
        for i in ['train', 'inference']:
            stage = getattr(self, i)
            if not stage:
                continue
            # function override
            if isinstance(stage.pipeline, OrderedDict):
                for name, func in stage.pipeline.items():
                    if isinstance(func.def_, str):
                        func.load_module()
            elif isinstance(stage.pipeline, list):
                pipeline = collections.OrderedDict()
                for func_name in stage.pipeline:
                    if isinstance(func_name, str) and func_name in self.function:
                        if isinstance(self.function[func_name].def_, str):
                            self.function[func_name].load_module()
                        pipeline[func_name] = self.function[func_name].model_copy(deep=True)
                    else:
                        raise AloErrors['ALO-PIP-000'](f'"solution.{i}.pipeline.[{func_name}]" not found in solution.function, Must be defined in the function.')
                stage.pipeline = pipeline
            else:
                raise AloErrors['ALO-PIP-000'](f'"solution.{i}.pipeline is required.')


class AwsConfig(AloModel):
    profile: str = Field(default=None, description="사용자 정의 profile명")
    accessKeyId: str = Field(default=None, description="access key")
    secretAccessKey: str = Field(default=None, description="secret key")
    arn: str = Field(description="ARN")


class AwsCloudwatch(AwsConfig):
    logGroupName: str
    logStreamName: str


class ExperimentalPlan(AloModel):
    name: StrictStr = Field(description="솔루션 이름")
    version: str = Field(default=None, description="동작 설정")
    control: Control = Field(default=Control(), description="동작 설정")
    solution: Solution = Field(description="실행 환경 구성")
    uri: str = None


###################
# Solution Meta
###################
class EdgeAppInterface(BaseModel):
    redis_db_number: int = Field(0)
    redis_server_uri: Union[str, RedisDsn] = Field("0.0.0.0:8080")

    @field_validator("redis_server_uri")
    def convert_to_url(cls, value) -> str:
        if not value:
            url = "0.0.0.0:8080"
            return RedisDsn(f"redis://{url}")
        if isinstance(value, str):
            settings.logger.info("Redis host : redis://%s", value)
            return RedisDsn(f"redis://{value}")
        else:
            return value


class StepArgs(BaseModel):
    args: Union[List[dict], dict] = Field([], description="단계의 인자 값")
    step: str = Field(description="단계명")


class ParametersType(BaseModel):
    candidate: List[StepArgs] = Field([], description="후보 인자 정보", alias='candidate_parameters')
    selected_user: List[StepArgs] = Field([], description="선택 인자 정보", alias='selected_user_parameters')
    user: List[StepArgs] = Field([], description="사용자 인자 정보", alias='user_parameters')

    def get_type_args(self, type_name, step_name):
        type_params = getattr(self, type_name)
        for type_param in type_params:
            if type_param.step == step_name:
                return type_param.args
        return None


class SolutionPipeline(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    type: str = Field(description="pipeline 유형")
    artifact_uri: Union[str, S3File, LocalFile, None, List[Union[None, str, LocalFile, S3File]]] = Field(default=None, description="저장 저장 위치")
    model_uri: Union[str, S3File, LocalFile, None, List[Union[None, str, LocalFile, S3File]]] = Field(default=None, description="모델 파일 저장 위치")
    dataset_uri: Union[str, S3File, LocalFile, None, List[Union[None, str, LocalFile, S3File]]] = Field(default=None, description="데이터셋 저장 위치")
    parameters: ParametersType = Field(None, description="인자 정보")

    @field_validator("artifact_uri", "model_uri", "dataset_uri")
    def convert_to_list(cls, value) -> str:
        if isinstance(value, list):
            return [convert_str_to_file(v) for v in value]
        elif value is None:
            return []
        else:
            return [convert_str_to_file(value)]


class SolutionMetadata(BaseModel):
    # 필요한 속성들만 정의함
    edgeapp_interface: EdgeAppInterface = Field(description="EdgeApp Interface 정보")
    pipeline: List[SolutionPipeline] = Field(description="실행 파이프 라인 정보")
    version: str = Field(default="", description="버전", alias="metadata_version", coerce_numbers_to_str=True)
    uri: str = None

    def get_pipeline(self, name: str):
        for pipe in self.pipeline:
            if pipe.type == name:
                return pipe
        return None

    def to_plan_model(self) -> dict:
        pass


###################
# End Solution Meta
###################

########################
# global variable
class Settings(BaseSettings):
    model_config = SettingsConfigDict(cli_parse_args=True, env_prefix='ALO_', cli_prog_name='ALO')  # priority : 1. cli args, 2. ENV Environment variables, 3.env
    name: str = Field(default="alo", env='NAME')
    home: str = Field(os.getcwd(), env='HOME')
    host: str = socket.gethostname()
    version: str = Field(__version__, exclude=True)
    time_zone: Union[str, None] = Field('UTC', description="set time zone")
    # origin cli args
    config: Union[str, None] = Field(None, description=f"config option: {EXP_FILE_NAME}")
    git: Union[Git, None] = Field(default=None, description="git url/branch")
    system: Union[str, None] = Field(None, description="system option: jsonized solution_metadata.yaml")
    mode: Union[Literal['train', 'inference'], None] = Field(None, description="ALO mode: train, inference. if not set, execute both.")
    mode_pipeline: List[str] = Field([], description="List of pipeline function names to be executed for each mode (train, inference)")
    loop: bool = Field(False, description="On/off infinite loop: True, False")
    computing: Literal['local', 'sagemaker', 'daemon'] = Field('local', description="training resource: local, sagemaker, ..")
    logging: Union[str, None] = Field(None, description='custom logger option: logging.yaml')
    log_level: Literal['NOTSET', 'DEBUG', 'INFO', 'WARNING', 'ERROR'] = Field(default='DEBUG', env='LOG_LEVEL', description="When NOTSET is set, all logs are output.")
    logger: object = Field(getLogger(), validate_default=False, exclude=True)
    register: bool = Field(False, description="On/Off registration flag")
    experimental_plan: Union[ExperimentalPlan, None] = Field(None, description=f"Model of {EXP_FILE_NAME}", exclude=True)
    solution_metadata: Union[SolutionMetadata, None] = Field(None, description="Model of solution_metadata.yaml", exclude=True)

    @field_validator('time_zone')
    @classmethod
    def init_time_zone(cls, value: str):
        if value:
            os.environ['TZ'] = value  # 'UTC'
            if hasattr(time, "tzset"):
                time.tzset()
        return value

    @computed_field
    @property
    def workspace(self) -> str:
        return os.path.join(self.home, '.workspace', self.name)

    @computed_field
    @property
    def libs(self) -> str:
        return os.path.join(self.workspace, 'libs')

    @computed_field
    @property
    def log_path(self) -> str:
        return os.path.join(self.workspace, 'log')

    @computed_field
    @property
    def history_path(self) -> str:
        return os.path.join(self.workspace, 'history')

    @computed_field
    @property
    def latest_path(self) -> str:
        return os.path.join(self.history_path, 'latest')

    @computed_field
    @property
    def latest_train(self) -> str:
        return os.path.join(self.latest_path, 'train')

    @computed_field
    @property
    def latest_inference(self) -> str:
        return os.path.join(self.latest_path, 'inference')

    @computed_field
    @property
    def v1_train_artifacts_path(self) -> str:
        return os.path.join(self.home, 'train_artifacts')

    @computed_field
    @property
    def v1_inference_artifacts_path(self) -> str:
        return os.path.join(self.home, 'inference_artifacts')

    @computed_field
    @property
    def v1_model_artifacts_path(self) -> str:
        return os.path.join(self.home, 'model_artifacts')

    @model_validator(mode='after')
    def init(self):
        return self

    def update_validate(self):
        if self.mode_pipeline:
            if self.mode is None:
                raise AloErrors['ALO-INI-005']("To apply the --mode_pipline option, enter the --mode [train, inference] option value.",
                                               file=EXP_FILE_NAME)
            if not all([i in self.experimental_plan.solution.function.keys() for i in self.mode_pipeline]):
                raise AloErrors['ALO-INI-005'](f"--mode_pipeline {self.mode_pipeline} must have a value of one of the keys contained "
                                               f"in solution.function.{list(self.experimental_plan.solution.function.keys())}",
                                               file=EXP_FILE_NAME)
            if getattr(self.experimental_plan.solution, self.mode) is None:
                raise AloErrors['ALO-INI-005'](f"--mode {self.mode} is not defined.",
                                               file=EXP_FILE_NAME)

    def update(self, yaml_path=None):
        if not yaml_path and self.config:
            yaml_path = self.config
        if not yaml_path and self.git:
            name = self.git.url.path.split("/")[-1].split(".")[0]
            workspace = os.path.join(self.home, ".workspace", name)
            self.git.checkout(workspace)
            if os.path.isfile(os.path.join(workspace, EXP_FILE_NAME)):
                yaml_path = os.path.join(workspace, EXP_FILE_NAME)
        if not yaml_path:
            yaml_path = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), "solution", EXP_FILE_NAME)
            if not os.path.exists(yaml_path):
                yaml_path = os.path.join(self.home, EXP_FILE_NAME)
        if not os.path.exists(yaml_path):
            raise AloErrors['ALO-INI-003'](yaml_path + """\n
   You can specify the yaml file path as follows.
   1. --config /mellerikat/experimental_plan.yaml
   2. --git.url http://mellerikat.com/repository/titanic.git --git.branch main
   3. (automatic detection) If the solution/experimental_plan.yaml file was created during alo setup
   4. (automatic detection) If the experimental_plan.yaml file exists in the current directory""")

        sys.path.append(os.sep.join(yaml_path.split(os.sep)[:-1]))  # Add a path of experimental_plan.yaml to the PYTHONPATH.
        self.experimental_plan = load_model(yaml_path, ExperimentalPlan)
        self.name = self.name if self.experimental_plan.name is None else self.experimental_plan.name
        self.logger = get_logger(self.log_path, self.log_level)

        self.update_validate()

        Path(self.libs).mkdir(parents=True, exist_ok=True)
        Path(self.log_path).mkdir(parents=True, exist_ok=True)
        Path(self.history_path).mkdir(parents=True, exist_ok=True)

        if self.system:
            self.solution_metadata = load_model(self.system, SolutionMetadata)


def load_model(yml_path: Union[str, dict], model: AloModel) -> AloModel:
    try:
        if not yml_path:
            raise FileNotFoundError(yml_path)

        if isinstance(yml_path, str):
            # JSON 형식의 문자열인지 확인
            try:
                json_loaded = json.loads(yml_path)
            except json.JSONDecodeError:
                # JSON 디코딩에 실패하면 YAML로 시도
                json_loaded = load_yml(yml_path) if isinstance(yml_path, str) and yml_path.lower().endswith(('.yaml', '.yml')) else yml_path
        elif isinstance(yml_path, dict):
            json_loaded = yml_path
        else:
            raise TypeError(f"json_loaded must be a file or dictionary : {str(yml_path)}")

        alo_model = model(**json_loaded)
        alo_model.uri = yml_path if isinstance(yml_path, str) else None
        return alo_model
    except FileNotFoundError as e:
        raise AloErrors['ALO-INI-003'](yml_path) from e
    except json.decoder.JSONDecodeError as e:
        raise AloErrors['ALO-INI-006'](yml_path) from e
    except ValidationError as e:
        raise AloErrors['ALO-VAL-000'](f"{yml_path}: {e}") from e
    except Exception as e:
        raise e


# v1 호환 옵션
if '--loop' in sys.argv:
    sys.argv.insert(sys.argv.index('--loop') + 1, "true")  # do nothing. prevent error
    sys.argv.extend(['--computing', 'daemon'])  # add same loop option

dotenv.load_dotenv()
settings = Settings()

try:
    assert sys.version_info >= (3, 8)
except Exception as e:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None, help="config option: experimental_plan.yaml")
    parser.add_argument("--system", type=str, default=None, help="system option: jsonized solution_metadata.yaml")
    parser.add_argument("--mode", type=str, default="all", help="ALO mode: train, inference, all")
    parser.add_argument("--loop", dest='loop', action='store_true', help="On/off infinite loop: True, False")
    parser.add_argument("--computing", type=str, default="local", help="training resource: local, sagemaker, ..")
    args = parser.parse_args()
    settings.config = args.config
    settings.system = args.system
    settings.computing = args.computing
    if args.mode == 'all':
        settings.mode = None
    if args.loop:
        settings.computing = 'daemon'
    print(args)
