import json
import sys

transcript_path = '/root/.gemini/antigravity-ide/brain/d409e386-fc3c-476f-8e3f-06d084cc241a/.system_generated/logs/transcript.jsonl'

dialogs = []

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get('type') in ('USER_INPUT', 'MODEL_RESPONSE'):
                # Extract text content if it exists
                content = data.get('content', '')
                if not content and 'tool_calls' in data:
                    content = f"[Tool calls: {len(data['tool_calls'])}]"
                dialogs.append({
                    'type': data.get('type'),
                    'content': content[:1000] # Truncate to avoid massive output
                })
        except json.JSONDecodeError:
            pass

# Get the last 10 messages (which would be ~5 dialogs)
last_dialogs = dialogs[-10:]

for i, d in enumerate(last_dialogs):
    print(f"--- {d['type']} ---")
    print(d['content'])
    print("\n")
