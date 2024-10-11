import os
from alo import settings

PROJECT_HOME = settings.home
SOURCE_HOME = PROJECT_HOME + "alo/"
SOLUTION_HOME = PROJECT_HOME + "solution/"

ASSET_PACKAGE_DIR = ".package_list/"
ASSET_PACKAGE_PATH = PROJECT_HOME + ASSET_PACKAGE_DIR

COMPRESSED_TRAIN_ARTIFACTS_FILE = 'train_artifacts.tar.gz'
COMPRESSED_MODEL_FILE = 'model.tar.gz'

REGISTER_SOURCE_PATH = PROJECT_HOME + ".register_source/"
REGISTER_EXPPLAN = REGISTER_SOURCE_PATH + "solution/experimental_plan.yaml"
REGISTER_ARTIFACT_PATH = PROJECT_HOME + ".register_artifacts/"
REGISTER_MODEL_PATH = PROJECT_HOME + ".register_model/"
REGISTER_INTERFACE_PATH = PROJECT_HOME + ".register_interface/"

AWS_CODEBUILD_S3_SOLUTION_FILE = "codebuild_solution"
AWS_CODEBUILD_ZIP_PATH = PROJECT_HOME + ".codebuild_solution_zip/"
AWS_CODEBUILD_S3_PROJECT_FORMAT_FILE = SOURCE_HOME + "ConfigFormats/aws_codebuild_s3_project_format.json"
AWS_CODEBUILD_BUILDSPEC_FORMAT_FILE = SOURCE_HOME + "ConfigFormats/aws_codebuild_buildspec_format.yaml"
AWS_CODEBUILD_BUILDSPEC_FILE = 'buildspec.yml'
AWS_CODEBUILD_BUILD_SOURCE_PATH = AWS_CODEBUILD_ZIP_PATH + ".register_source/"

REGISTER_WRANGLER_PATH = SOLUTION_HOME + "wrangler/wrangler.py"
SOLUTION_META = PROJECT_HOME + "solution_metadata.yaml"

DEFAULT_INFRA_SETUP = PROJECT_HOME + "setting/infra_config.yaml"
DEFAULT_SOLUTION_INFO = PROJECT_HOME + "setting/solution_info.yaml"

INPUT_DATA_HOME = settings.history_path + "/latest/"

TRAIN_INPUT_DATA_HOME = settings.history_path + "/latest/train/dataset/"
INFERENCE_INPUT_DATA_HOME = settings.history_path + "/latest/inference/dataset/"

REGISTER_DOCKER_PATH = SOURCE_HOME + "Dockerfiles/register/"
