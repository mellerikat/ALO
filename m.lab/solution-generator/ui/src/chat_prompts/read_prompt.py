import os

def read_prompt(file_name):
    """프롬프트 파일 읽기"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, file_name)
    with open(template_path, 'r', encoding='utf-8') as file:
        template = file.read()
    return template