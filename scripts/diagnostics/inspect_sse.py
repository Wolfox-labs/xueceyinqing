import json
import re
from pathlib import Path

text = Path('chat_test.sse').read_text(encoding='utf-8')
parts = []
for match in re.finditer(r'data: (\{.*?\})\n\n', text):
    data = json.loads(match.group(1))
    if 'content' in data:
        parts.append(data['content'])
content = ''.join(parts)
print(content[:2000])
