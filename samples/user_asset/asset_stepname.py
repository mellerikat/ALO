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
        # self.asset.load_summary()   : 이미 이전 Asset에서 save_summary를 통해 만들어진 summary.yaml이 존재한다면 해당 yaml을 dict로 load한다.
        
        #######################################  save 관련  ###################################
        # self.asset.save_config(updated_config)                         : 다음 Asset 에 필요한 설정값을 저장한다.
        # self.asset.save_data(data_dict)                                : 다음 Asset 에 필요한 데이터를 저장한다.
        # self.asset.save_summary(result, score, note, probability)      : 추론 결과에 대한 정규 포맷을 yaml파일로 저장한다.
        #                                                                 [참고] save_summary 관련 문서: 
        #                                                                 http://collab.lge.com/main/pages/viewpage.action?pageId=2210629363
        
        ##################################  input data 경로 관련  ##############################
        # self.asset.get_input_path()       : input data가 존재하는 base 경로를 반환합니다. 
        #                                     (ex. ~/alo/input/train(혹은 inference)/)  
        
        ##################################  model, artifacts 관련  #############################
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