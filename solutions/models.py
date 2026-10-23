"""The models of the solving rule, on the film engine's saved connections (keys are read at call time, never logged).

students: the film engine's planner (Haiku, OpenRouter) and reviewer (Luna, OpenAI Responses);
teacher: Opus on the same OpenRouter connection as Haiku.
Calls are cached by request hash under questions-data/jee-advanced/runs/cache, so a rerun costs nothing.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import httpx

REMOTION = Path('/home/nitin/remotion')
if str(REMOTION) not in sys.path:
    sys.path.insert(0, str(REMOTION))
from infofilm.llm_settings import api_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SECRETS = REMOTION / 'artifacts' / 'interface'          # the film engine's LLM settings folder
CACHE = ROOT / 'questions-data' / 'jee-advanced' / 'runs' / 'cache'
OPENROUTER = {'type': 'openrouter', 'url': 'https://openrouter.ai/api/v1', 'key_env': 'OPENROUTER_API_KEY',
              'id': 'haiku'}
MODELS = {
    'haiku': {**OPENROUTER, 'model': 'anthropic/claude-haiku-5.5', 'effort': 'medium'},
    'luna': {'type': 'openai_responses', 'url': 'https://api.openai.com/v1', 'model': 'gpt-6-luna',
             'key_env': 'OPENAI_API_KEY', 'id': 'luna', 'effort': 'medium'},
    'opus': {**OPENROUTER, 'model': 'anthropic/claude-opus-5.5', 'effort': 'high'},
}
SYSTEM = 'Return only the requested valid JSON object. Be exact; check your working before you answer.'


def _image(path):
    return base64.b64encode((ROOT / path).read_bytes()).decode()


def ask(who, prompt, images=(), *, max_tokens=12000, name='call'):
    """One JSON answer from a model, cached. Returns (value, usage)."""
    m = MODELS[who]
    identity = hashlib.sha256(json.dumps({'who': who, 'model': m['model'], 'effort': m['effort'], 'prompt': prompt,
                                          'images': [hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                                                     for p in images], 'max_tokens': max_tokens}).encode()).hexdigest()
    cached = CACHE / f'{name}-{who}-{identity[:16]}.json'
    if cached.exists():
        saved = json.loads(cached.read_text())
        return saved['value'], {**saved['usage'], 'cached': True}
    key = api_key(SECRETS, m['id'], m)
    if not key:
        raise RuntimeError(f'No API key for {who} (film engine LLM settings)')
    if m['type'] == 'openai_responses':
        content = [{'type': 'input_text', 'text': prompt + '\n\nRespond with one JSON object.'}] + [
            {'type': 'input_image', 'image_url': 'data:image/png;base64,' + _image(p)} for p in images]
        path, body = '/responses', {'model': m['model'], 'instructions': SYSTEM,
                                    'input': [{'role': 'user', 'content': content}],
                                    'reasoning': {'effort': m['effort']}, 'max_output_tokens': max_tokens * 3,
                                    'text': {'format': {'type': 'json_object'}}, 'store': False}
    else:
        content = [{'type': 'text', 'text': prompt}] + [
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + _image(p)}} for p in images]
        path, body = '/chat/completions', {'model': m['model'], 'temperature': 0,
                                           'messages': [{'role': 'system', 'content': SYSTEM},
                                                        {'role': 'user', 'content': content}],
                                           'max_tokens': max_tokens + 16000, 'reasoning': {'effort': m['effort']},
                                           'response_format': {'type': 'json_object'}, 'usage': {'include': True}}
    start, delay = time.monotonic(), 5
    with httpx.Client(timeout=900, headers={'Authorization': 'Bearer ' + key}) as client:
        for attempt in range(6):
            try:
                response = client.post(m['url'] + path, json=body)
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
            except (httpx.TransportError,):
                if attempt == 5:
                    raise
            time.sleep(delay)
            delay = min(delay * 2, 120)
        raw = response.json()
    if response.status_code >= 400:
        raise RuntimeError(f'{who}: HTTP {response.status_code}: {str(raw.get("error", raw))[:300]}')
    if m['type'] == 'openai_responses':
        text = ''.join(part.get('text', '') for item in raw.get('output', []) if item.get('type') == 'message'
                       for part in item.get('content', []) if part.get('type') == 'output_text')
        u = raw.get('usage') or {}
        usage = {'input': u.get('input_tokens', 0), 'output': u.get('output_tokens', 0)}
    else:
        text = raw['choices'][0]['message'].get('content') or ''
        u = raw.get('usage') or {}
        usage = {'input': u.get('prompt_tokens', 0), 'output': u.get('completion_tokens', 0), 'usd': u.get('cost')}
    usage['seconds'] = round(time.monotonic() - start, 1)
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip())
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r'\{.*\}', text, re.S)
        try:
            value = json.loads(match.group(0)) if match else None
        except json.JSONDecodeError:
            value = None
        if value is None:
            if name.endswith('-format'):
                raise RuntimeError(f'{who} returned invalid JSON twice: {exc}') from exc
            # One format retry, as the film engine does: escape backslashes and quotes inside strings.
            return ask(who, prompt + '\n\nYour previous reply was not valid JSON (' + str(exc) + '). Return one '
                       'valid JSON object; escape every backslash and double quote inside strings.', images,
                       max_tokens=max_tokens, name=name + '-format')
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({'value': value, 'usage': usage, 'model': m['model']}, indent=1, ensure_ascii=False))
    return value, usage
