from openai import AzureOpenAI
from dotenv import load_dotenv, find_dotenv
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')

load_dotenv(dotenv_path = dotenv_path, override=True)



def get_gpt_client():

    api_type = os.getenv("OPENAI_API_TYPE")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("OPENAI_API_VERSION")
    
    client = AzureOpenAI(
        api_version =api_version,
        api_key = api_key,
        azure_endpoint =api_base # "http://Endpoint 주소"
    )
    return client
 
def chatgpt_query(prompt):

    model_id = os.getenv("OPENAI_MODEL_ID")

    client = get_gpt_client()
    try:
        completion = client.chat.completions.create(
            model= model_id,
            messages=[
                {
                    "role":"system",
                    "content": "당신은 유용한 도우미입니다.",
                },
                {
                    "role":"user",
                    "content": prompt,
                },
            ],
        )
    except Exception as e:
        print(f"oepnai instance 생성 실패.\n{e}")
    answer = completion.choices[0].message.content
    print("\nchatgpt answer:\n" + answer)

    return answer
