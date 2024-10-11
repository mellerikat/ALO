#!/bin/bash

CURRENT_PATH=`readlink -f "${BASH_SOURCE:-$0}"`
CURRENT_DIR=`dirname $CURRENT_PATH`
cd $CURRENT_DIR
echo "Current Directory : `pwd`"

# 적용 대상 언어
# 첫번째 언어는 대표 언어를 의미
LOCALES=("en" "ko")
languages=$(IFS=, ; echo "${LOCALES[*]}")
export languages=$languages

# html 페이지 폴더
rm -rf html
mkdir -p html

for (( i=1; i<${#LOCALES[@]}; i++ )); do
  echo "Run build - ${LOCALES[i]}"
  # sphinx-build -M html . ./build -D language="${LOCALES[i]}"
  make clean
  make html SPHINXOPTS="-D language=${LOCALES[i]}"
  mv build/html html/${LOCALES[i]}
done

# make -e SPHINXOPTS="-D language='en'" html
# 첫번째 언어를 대표 언어로 적용
# sphinx-build -M html . ./build "-D language='${langs[0]}'"
make html SPHINXOPTS="-D language=${LOCALES[0]}"
mv build/html/* html/