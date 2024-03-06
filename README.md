# Welcome to ALO (AI Learning Organizer)

⚡ AI Advisor 에서 AI Solution 이 실행 가능하게 하는 ML framework 입니다. ⚡

[![Generic badge](https://img.shields.io/badge/release-v1.0.0-green.svg?style=for-the-badge)](http://링크)
[![Generic badge](https://img.shields.io/badge/last_update-2023.10.16-002E5F?style=for-the-badge)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Generic badge](https://img.shields.io/badge/python-3.10.12-purple.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Generic badge](https://img.shields.io/badge/dependencies-up_to_date-green.svg?style=for-the-badge&logo=python&logoColor=white)](requirement링크)
[![Generic badge](https://img.shields.io/badge/collab-blue.svg?style=for-the-badge)](http://collab.lge.com/main/display/AICONTENTS)
[![Generic badge](https://img.shields.io/badge/request_clm-green.svg?style=for-the-badge)](http://collab.lge.com/main/pages/viewpage.action?pageId=2157128981)

# ALO Manual
- [설치가이드](#설치가이드)
- [AI Contents 에 Custom Asset 추가하기](#ai-contents-에-custom-asset-추가하기) 
  - [파이프라인 수정하기](#파이프라인-수정하기)
  - [Custom Asset 추가하기](#custom-asset-추가하기)
- [신규 AI Contents 제작 가이드](#신규-ai-contents-제작-가이드)    
  - [파이프라인 설정하기](#파이프라인-설정하기)
  - [새로운 Asset 제작하기](#새로운-asset-제작하기)
- [문제 해결 방법](#문제-해결-방법)

## 설치가이드 
### ALO 기본 설치 
```console
git clone http://mod.lge.com/hub/dxadvtech/aicontents-framework/alo.git
cd alo
conda create -n alo python=3.10 ## 3.10 필수 
conda activate alo 
```

### AI Contents 실행하기
> [**AI Contents 들의 git 입니다.**]    
> :loud_sound: Contents 별로 다른 virtualenv 를 사용하세요. ~~  (Package 충돌 주의 !! :sob: :sob:)    
> :scroll: TCR : http://mod.lge.com/hub/dxadvtech/aicontents/tcr.git    
> :scroll: GCR : http://mod.lge.com/hub/dxadvtech/aicontents/gcr.git      
> :scroll: Forecast: http://mod.lge.com/hub/dxadvtech/aicontents/biz_forecasting.git

```console
## ALO 기본 설치 이후 진행

## 위의 url 을 <<git url>> 에 삽입
source setup_config.sh <<git url>>

python main.py  ## cf.: config/experimental_plan.yaml 를 실행
```
[:point_up: Go First ~ ](#alo-manual)
<br/><br/>
<br/><br/>


## AI Contents 에 Custom Asset 추가하기
AI Contents 가 과제 진행하는데 기능 추가를 해야 할 경우 AI Contents 제작자에게 의뢰 ([기능개발 의뢰하기](http://collab.lge.com/main/pages/viewpage.action?pageId=2157128981))를 하거나, 파이프라인에 Asset 을 추가하여 과제를 진행 할 수 있습니다. 

ALO 기본 설명은 [파이프라인 설정하기](#파이프라인-설정하기) 와 [Asset 파일 생성하기](#asset-파일-생성하기) 를 참조하세요. 

#### Step1. experimental_plan.yaml 에 step 을 추가 합니다. 
custom_preprocss 이라는 Asset 을 추가 하고 싶은 경우, user_parameters 와 asset_source 에 동일한 step name 으로 추가 합니다. 
- asset_source 의 requirements 에 requirements.txt 를 작성할 경우 git 에 존재하는 requirements 를 추가로 설치 합니다. 
```yaml
...
## TCR 일부 내용 .... 
user_parameters:
    - train_pipeline:
        - step: input  
          args:
            - input_path: train_multiclass
              x_columns: [input_x0, input_x1, input_x2, input_x3]
              use_all_x: False
              y_column: target 
              groupkey_columns:
              drop_columns:
              time_column:

        - step: custom_preprocess  ## <- 추가 Asset 
          args:
            - handling_missing: dropna 

## (내용 생략)
...
asset_source:
    - train_pipeline:
        - step: input
          source:  
            code: http://mod.lge.com/hub/smartdata/ml-framework/alov2-module/input.git
            branch: tabular
            requirements:
              - pandas==1.5.3

        - step: custom_preprocess ## <-추가 Asset
          source:  
            code: http://mod.lge.com/hub/smartdata/custom-preprocess.git
            branch: master 
            requirements:
              - pandas==1.5.3
              - requirements.txt
        
## (내용 생략)
```

#### Step 2. user_asset 제작하기  
추가하려는 asset 파일은 아래와 같은 규칙으로 코딩 되어야 합니다. 
- :warning: **규칙1** : asset_{step_name}.py 파일명을 유지해야 합니다.    
  - Ex: asset_custom_preprocess.py  
- :warning: **규칙2** : python=3.10 으로 작성되어야 합니다.
- 아래의 skeleton code 를 사용합니다. 

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


        df = pd.dataframe() 
        output_data = {'dataframe': df} ## dict 형태로 전달한다. (key 명은 dataframe 을 사용한다.)

        return output_data, self.config
        
if __name__ == "__main__":
    ua = UserAsset(envs={}, argv={}, data={}, config={})
    ua.run()

``` 
[:point_up: Go First ~ ](#alo-manual)

--------------
--------------



<br/><br/>
# 신규 AI Contents 제작 가이드
쉽게 접근할 수 있는 Titanic 예제를 이용하여 신규 AI Contents 제작을 따라해 볼 수 있습니다. 

### Sample Titanic 실행하기 
ALO 기본 설치 ([설치가이드](#설치가이드)) 이후 진행합니다. 
```console
## ALO 기본 설치 이후 진행

python main.py --config samples/config/Titanic/experimental_plan.yaml 
```


### 파이프라인 설정하기 
AI Contents 는 Asset 들의 집합인 파이프라인 형태로 구동되는데, ./config/experimental_plan.yaml 에 작성할 수 있습니다. 

##### experimental_plan.yaml 구성요소
Train/Inference pipeline 을 어떻게 구성할지를 결정하는 configuration 파일 입니다. 4 가지 파트로 구성됩니다. 
1. **external_path** : 외부에 데이터를 내부로 copy 하며, nas/s3 를 지원합니다. 
  - s3 에 접근해야 할 경우 s3_private_key_file 에 access & sceret key 를 기록해 두어야 합니다. 

2. **user_parameters** : asset 내부에서 사용할 변수값을 지정합니다. dict, list, str 을 지원합니다. 

3. **asset_source** : step name 별 source code 의 위치를 지정합니다. 설치하고 싶은 패키지를 지정할 수 있으며, requirements.txt 로 작성할 경우 git 에 존재하는 파일을 읽어와서 설치합니다. 

4. **control** : resource 제어 용이며, 설치과정을 중복 실행하지 않도록 하여 파이프라일 실행 속도를 빠르게 합니다.

<br/><br/>
##### experimental_plan.yaml 의 template 
아무 내용도 기술되어 있지 않은 파이프라인은  [config/experimental_plan.yaml](./config/experimental_plan.yaml) 를 참조하면 됩니다. 아래는 Titanic sample 로 각 기능을 설명합니다. 

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
[:point_up: Go First ~ ](#alo-manual)
<br/><br/>

## Asset 파일 생성하기

파이프라인의 실행 결과를 저장하기 위해서는 ALO 가 제공하는 API 를 이용하여 코딩해야 합니다. Train 파이프라인은 /train_artifacts/* 에 결과물을 저장하고 Inference 파이프라인은 /inference_artifacts/* 에 결과물을 저장합니다. 결과물 별 저장 방법은 아래 API 를 참조 하세요. 

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

[:point_up: Go First ~ ](#alo-manual)
<br/><br/>      


### asset_{step_name}.py 의 skeleton code
Sample 로 제공되는 [./samples/user_asset/asset_stepname.py](./samples/user_asset/asset_stepname.py) 파일를 copy 하여 제작하시기 바랍니다. 

```python
# -*- coding: utf-8 -*-
import os
import sys
from alolib.asset import Asset

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
## 동일 위치의 *.py 를 제작한 경우 해당 위헤서는 import
# from algorithm_engine import TITANIC

#--------------------------------------------------------------------------------------------------------------------------
#    CLASS
#--------------------------------------------------------------------------------------------------------------------------
class UserAsset(Asset):
    def __init__(self, asset_structure):
        super().__init__(asset_structure)
        ############################# ASSET API (alolib v 2.1) ################################
        
        #######################################  load 관련  ###################################
        # self.asset.load_config()    : 이번 Asset 에 필요한 설정값을 가져온다.
        # self.asset.load_data()      : 이번 Asset 에 필요한 데이터를 가져온다.
        # self.asset.load_args()      : 이번 Asset 에 필요한 사용자 파라미터를 가져온다.
        # self.asset.load_envs()      : 이번 Asset 에 필요한 환경변수를 가져온다.
        # self.asset.load_summary()   : 이미 이전 Asset에서 save_summary를 통해 만들어진 summary.yaml이 존재한다면 해당 yaml을 dict로 load한다.
        
        #######################################  save 관련  ###################################
        # self.asset.save_config(updated_config)                         : 다음 Asset 에 필요한 설정값을 저장한다.
        # self.asset.save_data(data_dict)                                : 다음 Asset 에 필요한 데이터를 저장한다.
        # self.asset.save_summary(result, score, note, probability)      : 추론 결과에 대한 정규 포맷을 yaml파일로 저장한다.
        #                                                                 [참고] save_summary 관련 문서: 
        #                                                                 http://collab.lge.com/main/pages/viewpage.action?pageId=2210629363
        
        ####################################### model, artifacts 관련  #########################
        # self.asset.get_model_path()       : 학습된 모델을 save (학습 시)하거나 load (추론 시)할 경로를 가져온다. 
        # self.asset.get_output_path()      : 학습 or 추론 결과를 저장할 경로를 가져온다. 
        #                                     [참고] 결과는 output.csv 혹은 output.jpg 각각은 하나씩만 있어야 한다. 
        # self.asset.get_report_path()      : 학습 report를 저장할 경로를 가져온다. 
        #                                     [참고] get_report_path()는 train 에서만 사용 가능하다.
        
        ######################################  logging 관련  #################################
        # self.asset.save_info(msg)          :  사용자에게 제공할 '정보'를 logging한다. 
        # self.asset.save_warning(msg)       :  사용자에게 제공할 '경고'를 logging한다. 
        # self.asset.save_error(msg)         :  사용자에게 제공할 '오류'를 logging한다. 
        
        ####################################################################################### 

        ## experimental_plan.yaml 에서 작성한 user parameter 를 dict 로 저장
        self.args       = self.asset.load_args()
        self.config     = self.asset.load_config()

        ## Asset 간에 전달해야 정보를 dict 로 저장
        ##  - self.config['new_key'] = 'new_value' 로 next asset 으로 정보 전달 가능 
        ## 이전 step 의 데이터 가져오기
        self.input_data    = self.asset.load_data()['dataframe'].copy()

    @Asset.decorator_run
    def run(self):
        
        ## 다음 Asset으로 데이터 전달하기 
        ## 아래 예시는 이전 Asset으로부터 전달 받은 input_data를 그대로 output_data에 담아서 다음 Asset에 전달  
        output_data = self.input_data 

        self.asset.save_data(output_data)
        self.asset.save_config(self.config)


#--------------------------------------------------------------------------------------------------------------------------
#    MAIN
#--------------------------------------------------------------------------------------------------------------------------  
if __name__ == "__main__":
    ua = UserAsset(envs={}, argv={}, data={}, config={})
    ua.run()

``` 
[:point_up: Go First ~ ](#alo-manual)

## 문제 해결 방법
(TBD)










## License
ALO is Free software, and may be redistributed under the terms of specified in the [LICENSE]() file.

