import os
import sys
import logging
import random
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score
from sklearn.model_selection import train_test_split


"""
context = {
    'name': 'test',                                   # 이름
    'version': '3.0.0',                               # ALO 버전
    'id': 'c2d93251-2307-413f-90ba-d1ea72d5eef4',     # 요청 UID
    'startAt': datetime.datetime(2024, 6, 28, 8, 48, 11, 159265),  # 모든 날짜 포맷은 iso 포맷 형식 사용
    'finishAt': datetime.datetime(2024, 6, 24, 11, 27, 55, 324312, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400), 'KST')),  # 모든 날짜 포맷은 iso 포맷 형식 사용
    'host': 'eks-kuber-titanic-01',                   # 호스트명
    'workspace': '/data001/project/alo2/titanic',     # 작업 기본 경로
    'logger': logger,                                 # 로거
    'settings': {},                                   # settings 모델 object
}


'pipeline' = {
    'preprocess': {
        'input': '/data001/project/alo2/titanic/preprocess/train.csv',                 # 설정된 input 파일 경로 정보
        'output': {'data': None},                         # 함수 return 결과 object
        'parameter': None,                                # kwargs 모델 객체
        'startAt': datetime.datetime(2024, 6, 24, 11, 27, 55, 324312, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400), 'KST')),  # 함수 call 시각
        'finishAt': datetime.datetime(2024, 6, 24, 11, 27, 55, 324312, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400), 'KST')),    # 함수 종료 시각
        'statusCode': 200,
        'workspace': '/data001/project/alo2/titanic/preprocess',
        'art'
    },
    'train': {
        'input': None,                                    # 설정된 input 파일 경로 정보
        'output': {'data': None},                         # 함수 return 결과 object
        'parameter': None,                                # kwargs 모델 객체
        'startAt': datetime.datetime(2024, 6, 24, 11, 27, 55, 324312, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400), 'KST')),  # 함수 call 시각
        'finishAt': datetime.datetime(2024, 6, 24, 11, 27, 55, 324312, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400), 'KST')),    # 함수 종료 시각
        'workspace': '/data001/project/alo2/titanic/train',
    },
    'inference': {
        'workspace': 
        'input': None,                                    # 설정된 input 파일 경로 정보
        'output': {'data': None},                         # 함수 return 결과 object
        'parameter': None,                                # kwargs 모델 객체
        'startAt': datetime.datetime(2024, 6, 24, 11, 27, 55, 324312, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400), 'KST')),  # 함수 call 시각
        'finishAt': datetime.datetime(2024, 6, 24, 11, 27, 55, 324312, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400), 'KST')),    # 함수 종료 시각
        'workspace': '/data001/project/alo2/titanic/inference',
    },
}
"""


def preprocess(context: dict, pipeline: dict):
    logger = context['logger']
    logger.debug("preprocess")


def train(context: dict, pipeline: dict, x_columns=[], y_column=None, n_estimators=100):
    logger = context['logger']
    logger.debug("train")
    
    file_list = os.listdir(pipeline['dataset']['workspace'])
    csv_files = [file for file in file_list if file.endswith('.csv')]
 
    for csv_file in csv_files:
        file_path = os.path.join(pipeline['dataset']['workspace'], csv_file)
        df = pd.read_csv(file_path)

        logger.debug("\n%s", df)
        X = pd.get_dummies(df[x_columns])
        X_train, X_test, y_train, y_test = train_test_split(X, df[y_column], test_size=0.2, random_state=42)

        model = RandomForestClassifier(n_estimators=n_estimators, max_depth=5, random_state=1)
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        precision = precision_score(y_test, y_pred, average='macro')
        logger.debug("y_pred\n%s", y_pred)
        context['model']['n100_depth5'] = model  # save model
    return {
        'summary': {
            'result': f'precision: {precision}',
            'note': f'Test Titanic-demo (date: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")})',
            'score': random.uniform(0.1, 1.0),
        }
    }


def inference(context: dict, pipeline: dict, x_columns=[]):
    logger = context['logger']
    logger.debug("inference")
    # context['model_path'] 모델이 저장될 전체 경로 리턴
    model = context['model']['n100_depth5']
    
    file_list = os.listdir(pipeline['dataset']['workspace'])
    csv_files = [file for file in file_list if file.endswith('.csv')]
    
    for csv_file in csv_files:
        file_path = os.path.join(pipeline['dataset']['workspace'], csv_file)
        df = pd.read_csv(file_path)

        logger.debug("\n%s", df)
        X = pd.get_dummies(df[x_columns])

        # load trained model
        predict_class = model.predict(X)
        predict_proba = model.predict_proba(X)

        result = pd.concat([df, pd.DataFrame(predict_class, columns=['predicted'])], axis=1)
        print(result)

        # result csv 저장
        result.to_csv(f"{pipeline['artifact']['workspace']}/result.csv")
        logger.debug("Save : %s", f"{pipeline['artifact']['workspace']}/result.csv")

        # summary
        num_survived = len(result[result['predicted'] == 1])
        num_total = len(result)
        survival_ratio = num_survived / num_total
        avg_proba = np.average(predict_proba, axis=0)
        avg_proba_survived = avg_proba[1].item()  # float
        avg_proba_dead = avg_proba[0].item()

    return {
        'extraOutput': '',
        'summary': {
            'result': f"#survived:{num_survived} / #total:{num_total}",
            'score': round(survival_ratio, 3),
            'note': "Score means titanic survival ratio",
            'probability': {"dead": avg_proba_dead, "survived": avg_proba_survived}
        }
    }



if __name__ == '__main__':
    logger = logging.getLogger("")

    # ALO 실행시 2개(context, pipeline) 의존 객체 주입
    # context : 실행 환경에 대한 정보를 담고 있음
    # pipeline: 사용자 정의 함수를 실행하기 위한 단계별 실행 전/후 정보담고 있는 객체
    #
    #
    # context = {
    #     'version': '3.0.0',                               # ALO 버전
    #     'id': 'c2d93251-2307-413f-90ba-d1ea72d5eef4',     # 요청 UID
    #     'startAt': '2024-06-25T00:00:00.000000+09:00',    # 모든 날짜 포맷은 iso 포맷 형식 사용 datetime.now().astimezone().isoformat()
    #     'host': 'eks-kuber-titanic-01',                   # 호스트명
    #     'workspace': '/data001/project/alo2/titanic',     # 작업 기본 경로
    #     'logger': logger,                                 # 로거
    #     'settings': {},                                   # settings 모델 object
    # }

    # 로컬 테스트
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    train_pipeline = {
        'dataset': {
            'workspace': 'test/titanic/train/dataset',
            'train.csv': 'test/titanic/train/dataset/train.csv'
        },
        'artifact': {
            'workspace': 'test/titanic/train/artifact'
        },
        'preprocess': {'argument': {}, 'result': {}},
        'train': {
            'argument': {
                'x_columns': ['Pclass', 'Sex', 'SibSp', 'Parch'],
                'y_column': 'Survived'
            },
            'result': {}},
    }
    inference_pipeline = {
        'dataset': {                                        # 학습에 사용되어질 파일 경로 또는 폴더
            'workspace': 'test/titanic/inference/dataset',
            'test.csv': 'test/titanic/inference/dataset/test.csv'
        },
        'artifact': {
            'workspace': 'test/titanic/inference/artifact'  # 결과물 저장 경로
        },
        'preprocess': {'argument': {}, 'result': {}},
        'inference': {
            'argument': {
                'x_columns': ['Pclass', 'Sex', 'SibSp', 'Parch']
            },
            'result': {}},
    }
    context = {
        'logger': logging.getLogger(),
        'train': train_pipeline,
        'inference': inference_pipeline,
        'model': {},
    }

    #####################
    # ####### train
    context['train']['preprocess']['result'] = preprocess(context, train_pipeline, **context['train']['preprocess']['argument'])
    context['train']['train']['result'] = train(context, train_pipeline, **context['train']['train']['argument'])

    #####################
    # ####### inference
    context['inference']['preprocess']['result'] = preprocess(context, train_pipeline, **context['inference']['preprocess']['argument'])
    context['inference']['inference']['result'] = inference(context, inference_pipeline, **context['inference']['inference']['argument'])

