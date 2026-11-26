import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')
base = os.environ.get('LLM_BASE_URL', 'https://api.deepseek.com/v1').rstrip('/')
key = os.environ['LLM_API_KEY']
model = os.environ.get('LLM_MODEL', 'deepseek-chat')
headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

plain = httpx.post(
    f'{base}/chat/completions',
    headers=headers,
    json={
        'model': model,
        'messages': [{'role': 'user', 'content': '只回答四个字：连接成功'}],
        'max_tokens': 20,
        'temperature': 0,
    },
    timeout=60,
)
print('plain_status=', plain.status_code)
if plain.status_code == 200:
    data = plain.json()
    print('plain_reply=', data['choices'][0]['message'].get('content', '')[:100])
else:
    print('plain_error=', plain.text[:500])

tools = [{
    'type': 'function',
    'function': {
        'name': 'record_mastery',
        'description': '记录一个知识点的掌握度',
        'parameters': {
            'type': 'object',
            'properties': {
                'knowledge_point': {'type': 'string'},
                'score': {'type': 'number'},
            },
            'required': ['knowledge_point', 'score'],
        },
    },
}]
tool_resp = httpx.post(
    f'{base}/chat/completions',
    headers=headers,
    json={
        'model': model,
        'messages': [{'role': 'user', 'content': '请调用工具记录：算法基础得分 0.4'}],
        'tools': tools,
        'tool_choice': 'auto',
        'max_tokens': 100,
        'temperature': 0,
    },
    timeout=60,
)
print('tool_status=', tool_resp.status_code)
if tool_resp.status_code == 200:
    message = tool_resp.json()['choices'][0]['message']
    calls = message.get('tool_calls') or []
    print('tool_call_count=', len(calls))
    if calls:
        print('tool_name=', calls[0]['function']['name'])
else:
    print('tool_error=', tool_resp.text[:500])
