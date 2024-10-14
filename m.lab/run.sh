#!/bin/bash

# 기본 프로파일 설정
DEFAULT_PROFILE="meerkat-dev"

# 인자로 받은 AWS_PROFILE 값을 저장합니다
if [ -z "$1" ]; then
  echo -e "\033[33mNo AWS profile provided. Using default profile: $DEFAULT_PROFILE\033[0m"  # 노란색으로 안내 메시지 출력
  AWS_PROFILE=$DEFAULT_PROFILE
else
  AWS_PROFILE=$1
fi

# 현재 시스템의 IP 주소를 가져옵니다
HOST_IP=$(hostname -I | awk '{print $1}')

# 사용 중이지 않은 포트를 찾는 함수
find_free_port() {
  local PORT=$1
  while ss -tuln | grep -q ":$PORT "; do
    PORT=$((PORT+1))
  done
  echo $PORT
}

# 기본 포트 설정
JUPYTER_PORT=8888
VSCODE_PORT=8080
STREAMLIT_PORT=39002

# 사용 가능한 포트 찾기
JUPYTER_PORT=$(find_free_port $JUPYTER_PORT)
VSCODE_PORT=$(find_free_port $VSCODE_PORT)
STREAMLIT_PORT=$(find_free_port $STREAMLIT_PORT)

# 실행된 포트 정보 출력
echo -e "\033[1mJupyter Lab is running on port $JUPYTER_PORT\033[0m"  # 굵게
echo -e "\033[1mVSCode Server is running on port $VSCODE_PORT\033[0m"  # 굵게

# Streamlit 접속 정보 출력
echo -e "\033[1;33m*************************************************\033[0m" # 노란색 ****
echo -e "\033[1;31mStreamlit is running\033[0m"                      # 굵고 빨간색
echo -e "\033[1;32mon ${HOST_IP}\033[0m"                      # 굵고 초록색
echo -e "\033[1;33mon port ${STREAMLIT_PORT}\033[0m"          # 굵고 노란색
echo -e "\033[1;33mYou can enjoy M.LAB in ${HOST_IP}:${STREAMLIT_PORT} !!!!!!!\033[0m"          # 굵고 노란색
echo -e "\033[1;31mYou can ignore any irrelevant output that comes out below.\033[0m"                      # 굵고 빨간색
echo -e "\033[1;33m*************************************************\033[0m" # 노란색 ****

# ECR 레지스트리 URL
ECR_URL="339713051385.dkr.ecr.ap-northeast-2.amazonaws.com/mellerilab/dev/m.lab:latest"

# ECR에서 최신 Docker 이미지를 가져옵니다
echo -e "\033[33mPulling the latest Docker image from ECR: $ECR_URL\033[0m"
aws ecr get-login-password --profile $AWS_PROFILE --region ap-northeast-2 | docker login --username AWS --password-stdin 339713051385.dkr.ecr.ap-northeast-2.amazonaws.com
docker pull $ECR_URL

# Docker 컨테이너를 실행합니다
docker run -v ~/.aws:/root/.aws \
  -e AWS_PROFILE=$AWS_PROFILE \
  -e HOST_IP=$HOST_IP \
  -e JUPYTER_PORT=$JUPYTER_PORT \
  -e VSCODE_PORT=$VSCODE_PORT \
  -e STREAMLIT_PORT=$STREAMLIT_PORT \
  -p $JUPYTER_PORT:8888 \
  -p $VSCODE_PORT:8080 \
  -p $STREAMLIT_PORT:39002 \
  $ECR_URL \
  /bin/bash -c "\
  jupyter lab --ip=0.0.0.0 --port=$JUPYTER_PORT --no-browser & \
  code-server --bind-addr 0.0.0.0:$VSCODE_PORT & \
  streamlit run --server.port $STREAMLIT_PORT"