import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api_server.main import _clean_learning_response

text = Path('chat_test.sse').read_text(encoding='utf-8')
parts = []
for match in re.finditer(r'data: (\{.*?\})\n\n', text):
    payload = json.loads(match.group(1))
    if 'content' in payload:
        parts.append(payload['content'])
cleaned = _clean_learning_response(''.join(parts))
print('cleaned_length=', len(cleaned))
print('cleaned_prefix=', cleaned[:120])
assert '获取' not in cleaned[:80]
assert '{' not in cleaned[:80]
