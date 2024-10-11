# MAKEFILE FOR CONTROLLER DOCKER IMAGE
###### Modify TAG when solution version update #####
NS='ecr-repo-an2-cism-dev-aic'
REPO='alo-test-swj'
TAG='latest'
TYPE='train'
URL='086558720570.dkr.ecr.ap-northeast-2.amazonaws.com/$(NS)/$(TYPE)/$(REPO)'
###########################################################################

DOCKERFILE='Dockerfile'

PYTHON_FILE = main.py
FOLDER_PATH = ./assets/
 
login:
	aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 086558720570.dkr.ecr.ap-northeast-2.amazonaws.com
 
logout:
	docker logout
 
ecr:
	aws ecr create-repository --repository-name $(NS)/$(TYPE)/$(REPO) --image-scanning-configuration scanOnPush=true --region ap-northeast-2

chk:
	aws ecr describe-repositories --repository-names $(NS)/$(TYPE)/$(REPO) --region ap-northeast-2
 
build:
	docker build . -t $(URL):$(TAG) -f $(DOCKERFILE)
 
push:
	docker push $(URL):$(TAG)
	docker push $(URL):latest
 
tag:
	docker tag $(URL):$(TAG) $(URL):latest

delete:
	aws ecr batch-delete-image --repository-name $(NS)/$(TYPE)/$(REPO) --image-ids imageTag=latest

clean : 
	rm -rf $(FOLDER_PATH)* ./history ./.asset_interface ./inference_artifacts ./train_artifacts ./input/ ./assets/ ./main.py ./src/ ./config/ ./solution_metadata.yaml
 
ecr: login ecr
sync: login build tag delete push logout
