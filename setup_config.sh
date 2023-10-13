#!/bin/bash

# 제거할 디렉토리 경로
config_dir="./config/"

# Git 저장소 URL을 스크립트 인수로 받기
if [ $# -eq 0 ]; then
    echo "사용법: $0 <Git 저장소 URL>"
    exit 1
fi

git_url="$1"

# ./config/ 디렉토리가 존재하는지 확인하고 제거
if [ -d "$config_dir" ]; then
    echo "기존 $config_dir 디렉토리를 제거합니다."
    rm -rf "$config_dir"
fi

# Git 저장소 복제
echo "Git 저장소를 복제합니다: $git_url"
git clone "$git_url" "$config_dir"


