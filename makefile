## python file name to be executed
PYTHON_FILE = main.py
FOLDER_PATH = ./assets/
## basic target
all : 
	run
## execution rule  
run : 
	python $(PYTHON_FILE)
del :
	rm -rf ./alolib
# "make clean" command rule 
clean : 
	rm -rf $(FOLDER_PATH)* ./.TEMP_MODEL_PATH ./history ./.asset_interface ./inference_artifacts ./.temp_artifacts_dir ./train_artifacts ./input/ ./assets/ ./alolib ./.register_* 
	rm -rf $(FOLDER_PATH)* ./solution
	rm -rf $(FOLDER_PATH)* Dockerfile solution_requirements.txt
	rm -rf $(FOLDER_PATH)* .package_list
clean-history : 
	rm -rf  ./history
clean-cache:
	@find . -type d -name '__pycache__' -exec rm -r {} +

