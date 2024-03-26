import json
# 파일에서 JSON으로 저장된 데이터 불러오기
with open('combined.json', 'r') as f:
    data = json.load(f)

# 원래 딕셔너리에 접근
a_loaded = data['API']
b_loaded = data['REGISTER_SOLUTION']
c = 0