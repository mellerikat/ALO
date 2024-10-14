#!/bin/bash

# 사용 방법 안내
if [ "$#" -ne 1 ]; then
    echo "No AWS profile provided. Using default profile: meerkat-dev"
    PROFILE="meerkat-dev"
else
    PROFILE=$1
fi

REGION="ap-northeast-2"
ACCOUNT_ID="339713051385"
REPOSITORY_NAME="mellerilab/dev/m.lab"
TAG="latest"

# ECR 리포지토리 URI
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPOSITORY_NAME}:${TAG}"

# AWS ECR 로그인
aws ecr get-login-password --profile $PROFILE --region $REGION | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Docker 이미지 Pull
docker pull $ECR_URI

# 로그인과 다운로드의 성공 여부 확인
if [ $? -eq 0 ]; then
    echo "Successfully pulled the Docker image: $ECR_URI"
else
    echo "Failed to pull the Docker image: $ECR_URI"
fi
