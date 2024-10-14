import os 
# graph_ruuner 와 이 파일은 같은 디렉토리에 존재한다고 가정
LANGGRAPH_RUN_PATH = os.path.abspath(os.path.dirname(__file__))
PROMPT_INTER_PATH = 'prompts/'

PROMPT_PATH_DATA_ADAPT= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_data_adapt.md'
)
PROMPT_PATH_CLASSIFY_ERROR= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_classify_error.md'
)
PROMPT_PATH_FIND_METHOD_IN_PY= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_find_method_in_py.md'
)
PROMPT_PATH_SUMMARIZE_CODES= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_summarize_codes.md'
)

PROMPT_PATH_PWC_TYPE_1_FIX= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_pwc_type_1_fix.md'        
)
PROMPT_PATH_PWC_TYPE_1_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_pwc_type_1_analyze.md'
)
PROMPT_PATH_PWC_TYPE_3_FIX= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_pwc_type_3_fix.md'
)
PROMPT_PATH_PWC_TYPE_3_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_pwc_type_3_analyze.md'
)

PROMPT_PATH_SINGLE_TYPE_1_FIX= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_single_type_1_fix.md'
)
PROMPT_PATH_SINGLE_TYPE_1_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_single_type_1_analyze.md'
)

PROMPT_PATH_SINGLE_TYPE_3_FIX= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_single_type_3_fix.md'
)
PROMPT_PATH_SINGLE_TYPE_3_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_single_type_3_analyze.md'
)

PROMPT_PATH_MULTI_TYPE_1_FIX= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_multi_type_1_fix.md'
)
PROMPT_PATH_MULTI_TYPE_1_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_multi_type_1_analyze.md'
)
PROMPT_PATH_MULTI_TYPE_3_FIX= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_multi_type_3_fix.md'
)
PROMPT_PATH_MULTI_TYPE_3_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_multi_type_3_analyze.md'
)

PROMPT_PATH_TYPE_2_FIX= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_type_2_fix.md'
)
PROMPT_PATH_TYPE_2_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_type_2_analyze.md'
)

PROMPT_PATH_TYPE_4_ANALYZE= os.path.join(
    LANGGRAPH_RUN_PATH,
    PROMPT_INTER_PATH,
    'prompt_type_4_analyze.md'
)

if __name__ == '__main__':
    print(f'PROMPT_PATH_DATA_ADAPT exists: {os.path.exists(PROMPT_PATH_DATA_ADAPT)}')
    print(f'PROMPT_PATH_CLASSIFY_ERROR exists: {os.path.exists(PROMPT_PATH_CLASSIFY_ERROR)}')
    print(f'PROMPT_PATH_FIND_METHOD_IN_PY exists: {os.path.exists(PROMPT_PATH_FIND_METHOD_IN_PY)}')
    print(f'PROMPT_PATH_SUMMARIZE_CODES exists: {os.path.exists(PROMPT_PATH_SUMMARIZE_CODES)}')
    print(f'PROMPT_PATH_PWC_TYPE_1_FIX exists: {os.path.exists(PROMPT_PATH_PWC_TYPE_1_FIX)}')
    print(f'PROMPT_PATH_PWC_TYPE_1_ANALYZE exists: {os.path.exists(PROMPT_PATH_PWC_TYPE_1_ANALYZE)}')
    print(f'PROMPT_PATH_PWC_TYPE_3_FIX exists: {os.path.exists(PROMPT_PATH_PWC_TYPE_3_FIX)}')
    print(f'PROMPT_PATH_PWC_TYPE_3_ANALYZE exists: {os.path.exists(PROMPT_PATH_PWC_TYPE_3_ANALYZE)}')
    print(f'PROMPT_PATH_SINGLE_TYPE_1_FIX exists: {os.path.exists(PROMPT_PATH_SINGLE_TYPE_1_FIX)}')
    print(f'PROMPT_PATH_SINGLE_TYPE_1_ANALYZE exists: {os.path.exists(PROMPT_PATH_SINGLE_TYPE_1_ANALYZE)}')
    print(f'PROMPT_PATH_SINGLE_TYPE_3_FIX exists: {os.path.exists(PROMPT_PATH_SINGLE_TYPE_3_FIX)}')
    print(f'PROMPT_PATH_SINGLE_TYPE_3_ANALYZE exists: {os.path.exists(PROMPT_PATH_SINGLE_TYPE_3_ANALYZE)}')
    print(f'PROMPT_PATH_MULTI_TYPE_1_FIX exists: {os.path.exists(PROMPT_PATH_MULTI_TYPE_1_FIX)}')
    print(f'PROMPT_PATH_MULTI_TYPE_1_ANALYZE exists: {os.path.exists(PROMPT_PATH_MULTI_TYPE_1_ANALYZE)}')
    print(f'PROMPT_PATH_MULTI_TYPE_3_FIX exists: {os.path.exists(PROMPT_PATH_MULTI_TYPE_3_FIX)}')
    print(f'PROMPT_PATH_MULTI_TYPE_3_ANALYZE exists: {os.path.exists(PROMPT_PATH_MULTI_TYPE_3_ANALYZE)}')
    print(f'PROMPT_PATH_TYPE_2_FIX exists: {os.path.exists(PROMPT_PATH_TYPE_2_FIX)}')
    print(f'PROMPT_PATH_TYPE_2_ANALYZE exists: {os.path.exists(PROMPT_PATH_TYPE_2_ANALYZE)}')
    print(f'PROMPT_PATH_TYPE_4_ANALYZE exists: {os.path.exists(PROMPT_PATH_TYPE_4_ANALYZE)}')
    