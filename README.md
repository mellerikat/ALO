# Welcome to ALO (AI Learning Organizer)

⚡ AI Advisor 에서 AI Solution 이 실행 가능하게 하는 ML framework 입니다. ⚡

[![Generic badge](https://img.shields.io/badge/release-v1.0.0-green.svg?style=for-the-badge)](http://링크)
[![Generic badge](https://img.shields.io/badge/last_update-2023.10.16-002E5F?style=for-the-badge)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Generic badge](https://img.shields.io/badge/python-3.10.12-purple.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Generic badge](https://img.shields.io/badge/dependencies-up_to_date-green.svg?style=for-the-badge&logo=python&logoColor=white)](requirement링크)
[![Generic badge](https://img.shields.io/badge/collab-blue.svg?style=for-the-badge)](http://collab.lge.com/main/display/AICONTENTS)
[![Generic badge](https://img.shields.io/badge/request_clm-green.svg?style=for-the-badge)](http://collab.lge.com/main/pages/viewpage.action?pageId=2157128981)

# Contents 
- [설치가이드](#설치가이드)
- [AI Contents 에 Custom Asset 추가하기](#ai-contents-에-custom-asset-추가하기) 
  - [파이프라인 수정하기](#파이프라인-수정하기)
  - [Custom Asset 추가하기](#custom-asset-추가하기)
- [신규 AI Contents 제작 가이드](#신규-ai-contents-제작-가이드)    
  - [파이프라인 설정하기](#파이프라인-설정하기)
  - [새로운 Asset 제작하기](#새로운-asset-제작하기)
- [문제 해결 방법](#문제-해결-방법)

## 설치가이드 
### Sample Titanic 실행하기 
```console
git clone http://mod.lge.com/hub/dxadvtech/aicontents-framework/alo.git
cd alo
conda create -n alo python=3.10 ## 3.10 필수 
conda activate alo 
python main.py --config samples/config/Titanic/experimental_plan.yaml 
```

### AI Contents 실행하기 (Example: TCR)

```console
git clone http://mod.lge.com/hub/dxadvtech/aicontents-framework/alo.git
cd alo
conda create -n alo python=3.10 ## 3.10 필수 
conda activate alo 

## TCR 용 experimental_plan.yaml 을 git clone 하여 config 에 저장 (다른 contents git 주소로 변경하여 사용 가능)
./setup_config.sh http://mod.lge.com/hub/dxadvtech/aicontents/tcr.git

## config/experimental_plan.yaml 을 default 로 인식 함
python main.py  
```

<br/><br/>
## 파이프라인 설정하기 
### experimental_plan.yaml 구성요소
Train/Inference pipeline 을 어떻게 구성할지를 결정하는 configuration 파일 입니다. 4 가지 파트로 구성됩니다. 
1. **external_path** : 외부에 데이터를 내부로 copy 하며, nas/s3 를 지원합니다. 
  - s3 에 접근해야 할 경우 s3_private_key_file 에 access & sceret key 를 기록해 두어야 합니다. 

2. **user_parameters** : asset 내부에서 사용할 변수값을 지정합니다. dict, list, str 을 지원합니다. 

3. **asset_source** : step name 별 source code 의 위치를 지정합니다. 설치하고 싶은 패키지를 지정할 수 있으며, requirements.txt 로 작성할 경우 git 에 존재하는 파일을 읽어와서 설치합니다. 

4. **control** : resource 제어 용이며, 설치과정을 중복 실행하지 않도록 하여 파이프라일 실행 속도를 빠르게 합니다.

<br/><br/>
### experimental_plan.yaml 의 template 
./config/experimental_plan.yaml 

```yaml 
## 외부에서 데이터 가져오기 / 결과 저장하는 경우 해당 위치에 지정
external_path:
    - load_train_data_path: /nas001/users/ruci.sung/alo_sample_data/titanic_data/train/
    - load_inference_data_path: /nas001/users/ruci.sung/alo_sample_data/titanic_data/test/
    - save_train_artifacts_path:
    - save_inference_artifacts_path:

external_path_permission:
    - s3_private_key_file:

## 실험에 필요한 파라미터를 설정함 
## - 해당 위치에서 삭제되면, code 의 default 로 실행
user_parameters:
    - train_pipeline:
        - step: input  ## step_name 입력 
          args:
            - input_path: train/ #load_train_data 의 마지막 폴더명. 하위폴더 선택 가능 
              x_columns: ["Pclass", "Sex", "SibSp", "Parch"] # table 데이터의 column
              use_all_x: False  ## 모든 column 을 x 로 지정
              y_column: Survived # y 값이 있을 경우 사용
              groupkey_columns:   ## group 별 모델링이 필요한 경우
              drop_columns:  ## 삭제할 column 이 있을 경우 
              time_column:  ## time column 이 있을 경우 (single)

        - step: train ## 필수
          args:
            - model_type: regression ## asset 의 설정값. dict, list, str 을 지원

    - inference_pipeline:
      - step: input  
        args:
          - input_path: train
            x_columns: ["Pclass", "Sex", "SibSp", "Parch"]
            use_all_x: False
            y_column: Survived 
            groupkey_columns:
            drop_columns:
            time_column:
      
      - step: inference 
        args:
          - model_type: regression 
 
## asset 의 설치 정보를 기록       
asset_source:
    - train_pipeline:
        - step: input
          source:  ## git / local 지원
            code: http://mod.lge.com/hub/smartdata/ml-framework/alov2-module/input.git
            # code: local  -- local 에서 asset 개발을 진행할 때 사용
            branch: tabular
            requirements:
              - pandas==1.5.3

        - step: train
          source:
            code: http://mod.lge.com/hub/dxadvtech/assets/titanic_tutorial.git
            # code: local
            branch: main
            requirements:
              - pandas==1.5.3
              - scikit-learn
      
    - inference_pipeline:
      - step: input
        source:  ## git / local 지원
          code: http://mod.lge.com/hub/smartdata/ml-framework/alov2-module/input.git
          # code: local
          branch: tabular
          requirements:
            - pandas==1.5.3

      - step: inference
        source:
          code: http://mod.lge.com/hub/dxadvtech/assets/titanic_tutorial.git
          # code: local
          branch: main
          requirements:
            - pandas==1.5.3

control:
    ## 1. 패키지 설치 및 asset 존재 여부를 실험 시마다 체크할지, 한번만 할지 결정
    ## 1-2 requirements.txt 및 종속 패키지들 한번만 설치할 지 매번 설치할지도 결정 
    - get_asset_source: once ## once, every
    # pipeline 실행 할 때 마다 데이터 가져올지를 결정 
    - get_external_data: once ## once, every
    ## 2. 생성된 artifacts 를 backup 할지를 결정 True/False
    - backup_artifacts: True
    ## 3. pipeline 로그를 backup 할지를 결정 True/False
    - backup_log: True
    ## 4. 저장 공간 사이즈를 결정 (단위 MB)
    - backup_size: 1000
 
    ## 5. Asset 사이 데이터 전달 방법으로 memory, file 를 지원
    - interface_mode: memory

```


<br/><br/>

## Asset 파일 생성하기

### asset_{step_name}.py 에 제공되는 사용자 API
1. **user parameter 의 default 값 설정 (필수)**
```python
self.asset.check_args(arg_key, is_required=False, default="", chng_type="str" )
``` 
User parameter 의 type 을 변경하거나, default 값을 변경하기 위해 사용합니다. 
experimental_plan.yaml 에서 Asset 의 user parameter 를 삭제경우에도 정상적인 실행을 위해 필수로 삽입 합니다. 
AI Conductor 로 upload 시, 삽입 여부를 check 합니다. 
- args (dict) : Asset self.args 
- arg_key (str) : 사용자 라미미터 이름 
- is_required (bool) : 필수 존재 여부 
- default (str) : 사용자 파라미터가 존재하지 않을 경우, 강제로 입력될 값
- chng_type (str): 타입 변경 list, str, int, float, bool,      

<br/><br/>    
2. **학습 및 추론 결과값 저장 (필수)**
```python
self.asset.save_summary(result='OK', score=0.613, note='aloalo.csv', probability={'OK':0.715, 'NG':0.135, 'NG1':0.15}  )
``` 
추론 결과를 Edge App 에 전달하여 Display 하기 위해 사용. Edge Conductor 에서는 결과를 누적하여 재학습 필요 여부를 사용자가 선택 하도록 함.AI Conductor 에 등록 시, 함수 사용 여부 체크.

- result (str, length limit: 25) : Inference result summarized info. 
- score (float, 0 ~ 1.0) : model performance score to be used for model retraining 
- note (str, length limit: 100): optional & additional info. for inference result (optional)
- probability (dict - key:str, value:float): Classification Solution의 경우 라벨 별로 확률 값을 제공합니다. (optional) >> (ex) {'OK': 0.6, 'NG':0.4}
<br/><br/>

3. **학습 및 추론 모델 파일 저장 (필수)**
```python
model_path = self.asset.get_model_path(use_inference_path=False)     
```
Train pipeline 에서 생성한 모델 파일을 Inference pipeline 에 전달하고 싶을 경우에 사용하며, 동일한 step name (experimental_plan.yaml) 끼리만 전달할 수 있다.  
- use_inference_path (bool, default=False): inference pipeline 진행 시, 생성된 모델을 inference storage 
영역에 저장하고 싶을 때 사용     
---- Return   
- model_path (str): 저장 공간 경로를 반환 한다. 
<br/><br/>

4. **학습 결과 리포트 파일 저장 (옵션)**

```python
report_path = self.asset.get_report_path() 
```
Train pipeline 에서 생성한 report.html 을 저장하기 위한 사용. html 파일모델 파일을 Inference pipeline 에 전달하고 싶을 경우에 사용하며, 동일한 step name (experimental_plan.yaml) 끼리만 전달할 수 있다.  

---- Return    
- model_path (str): 저장 공간 경로를 반환 한다. 
<br/><br/>

5. **학습 및 추론 결과 파일 저장 (추론만 필수)**

```python
output_path = self.asset.get_output_path()
```
Train pipeline 또는 Inference pipeline 실행 결과를 저장할 때 사용한다. 
Inference pipeline 은 output.csv, output.jpg, output.csv & output.jpg 중에 하나를 포함하고 있어야 한다 (필수). Inference 결과는 Model Conductor 로 수집되어 re-train 시 학습데이터롤 사용된다. 

---- Return   
- model_path (str): 저장 공간 경로를 반환 한다.  
<br/><br/>      

### asset_{step_name}.py 의 skeleton code
./samles/user_asset/asset_stepname.py 를 copy 하여 사용

```python
# -*- coding: utf-8 -*-
import os
import sys
from alolib.asset import Asset
import alolib.common as common
from alolib.exception import * 

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
## 동일 위치의 *.py 를 제작한 경우 해당 위헤서는 import
# from algorithm_engine import TITANIC

#--------------------------------------------------------------------------------------------------------------------------
#    CLASS
#--------------------------------------------------------------------------------------------------------------------------
class UserAsset(Asset):
    def __init__(self, envs, argv, data, config):
        super().__init__(envs, argv, version=1.0)
        ############################ ASSET API (v.1.0) ####################################
        # collab : http://mod.lge.com/hub/dxadvtech/aicontents-framework/alo

        # self.asset.check_args(arg_key, is_required=False, default="", chng_type="str")

        # self.asset.save_summary(result='OK', score=0.613, note='aloalo.csv', probability={'OK':0.715, 'NG':0.135, 'NG1':0.15}  )
        # model_path = self.asset.get_model_path(use_inference_path=False)     
        # report_path = self.asset.get_report_path() 
        # output_path = self.asset.get_output_path()
        ###################################################################################### 

        ## experimental_plan.yaml 에서 작성한 user parameter 를 dict 로 저장
        self.args = self.asset.load_config('args')

        ## Asset 간에 전달해야 정보를 dict 로 저장
        ##  - self.config['new_key'] = 'new_value' 로 next asset 으로 정보 전달 가능 
        self.config = config

        ## 이전 step 의 데이터 가져오기
        self.input_data = data['dataframe']  # 이전 Asset 의 데이터를 가져온다.

    @Asset.decorator_run
    def run(self):
        
        ## 데이터 전달하기 
        output_data = self.input_data 

        return output_data, self.config
        
if __name__ == "__main__":
    ua = UserAsset(envs={}, argv={}, data={}, config={})
    ua.run()

``` 
## AI Contents 에 Custom Asset 추가하기
[파이프라인 설정하기](#파이프라인-설정하기) 와 [Asset 파일 생성하기](#asset-파일-생성하기) 를 활용하여 진행 가능합니다. 

###### Step1. experimental_plan 에 step 을 추가 합니다. 
```yaml
...
user_parameters:
    - train_pipeline:
        - step: input  ## step_name 입력 
          args:
            - input_path: train/ #load_train_data 의 마지막 폴명. 하위폴더 선택 가능 
              x_columns: ["Pclass", "Sex", "SibSp", "Parch"] # table 데이터의 column
           
        - step: custom_preprcoess  ## 자유롭게 기술 가능 
          args:
            - new_param: "test" 

...
asset_source:
    - train_pipeline:
        - step: input
          source:  ## git / local 지원
            code: http://mod.lge.com/hub/smartdata/ml-framework/alov2-module/input.git
            # code: local  -- local 에서 asset 개발을 진행할 때 사용
            branch: tabular
            requirements:
              - pandas==1.5.3

        - step: custom_preprocess ## user_parameter 에서의 step name 과 동일해야 함 
          source:
            code: local ## git 없이 local 경로에서 제작
            branch: main  ## local 일 경우 참조되지 않음
            requirements:
              - pandas==1.5.3
              - scikit-learn
```
###### Step 2. user_asset 을 copy 하기 
```console
## mina.py 위치에서 시작 
cd assets 
mkdir custom_preprcoess  ## step name 과 동일 폴더 생성 
cd custom_preprcoess 
cp ../../samples/user_asset/asset_stepname.py ./asset_custom_preprocess.py 

## asset_custom_preprocess 파일을 수정합니다. 
```

###### Step 3. user_asset 파일 수정 
```python
# -*- coding: utf-8 -*-
import os
import sys
from alolib.asset import Asset
import alolib.common as common
from alolib.exception import * 

import pandas as pd 

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class UserAsset(Asset):
    def __init__(self, envs, argv, data, config):
        super().__init__(envs, argv, version=1.0)

        self.args = self.asset.load_config('args') 
        self.config = config
        self.input_data = data['dataframe']  

    @Asset.decorator_run
    def run(self):

        #####################        
        #### 내용추가하기 ####
        ##################### 


        output_data = pd.dataframe() ## 생성된 dataframe 을 output 으로 전달한다.  

        return output_data, self.config
        
if __name__ == "__main__":
    ua = UserAsset(envs={}, argv={}, data={}, config={})
    ua.run()

``` 

## License
ALO is Free software, and may be redistributed under the terms of specified in the [LICENSE]() file.

