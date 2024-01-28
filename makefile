# 실행할 Python 파일 이름 설정
PYTHON_FILE = main.py
FOLDER_PATH = ./assets/

# 기본 타겟 설정
all : 
	run

# Python 프로그램 실행 규칙
run : 
	python $(PYTHON_FILE)

del :
	rm -rf ./alolib

# "make clean" 명령을 실행할 때 실행되는 규칙
clean : 
	rm -rf $(FOLDER_PATH)* ./.history ./.asset_interface ./.inference_artifacts ./.temp_artifacts_dir ./.train_artifacts ./input/ ./assets/ ./alolib ./.register_*

clean-cache:
	@find . -type d -name '__pycache__' -exec rm -r {} +

