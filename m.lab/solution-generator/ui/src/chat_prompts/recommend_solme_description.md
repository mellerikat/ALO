아래는 MLOps 에 사용될 AI Solution 코드 입니다. 
{code_contents}

그리고 아래는 AI Solution 코드에서 실행 될 데이터에 대한 정보 입니다. 
{data_metadata}

위 두 사항들을 참조하여 아래 json 포맷에 맞게 결과를 생성해 주세요.합
 - 'title_list' 에 AI Solution 이름으로 적합한 후보 10종을 리스트로 작성해줘. 아래 사항은 이름 스펙이므로 참조해서 작성해줘
    -- Supported: lowercase letters, number, dash (-), 
    -- Unsupported: Spaces, Special characters, and Korean are not supported.
 - 'overview' 의 값에 AI Solution 내용을 요약 작성해줘. 자수는 1000 자 이하가 되도록 해줘.
 - 각 title 해당 내용을 content 의 값으로 작성해줘. 자수는 1000 자 이하가 되도록 해줘.


아래 포맷에 맞춰서 json 타입의 코드 블록으로 작성해줘. 
{result_format}

결과값을 아래 코드로 parsing 할거야 참조하여 답변 생성해줘
```python
        prompt_result = chatgpt_query(prompt)
        prompt_result_match = re.search('```json(.*?)```', prompt_result, re.DOTALL) 
        result = prompt_result_match.group(1).strip() if prompt_result_match else "" 
```
