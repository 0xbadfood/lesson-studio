"""GLM decides WHAT happens WHEN: word-anchored verbs on named parts, no coordinates."""
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
import os
GLM = os.environ.get('CUE_URL', 'http://10.8.0.4:18080/v1')
TAG = os.environ.get('CUE_TAG', 'glm')
THINK = os.environ.get('CUE_THINK', '0') == '1'
MAXTOK = int(os.environ.get('CUE_MAXTOK', '6000'))
SCENES = Path('/home/nitin/remotion/artifacts/experiments/four-stroke-image-mggen-manim/narration-scenes.json')

VERBS = '''Verbs (each cue names words, never positions or numbers of pixels):
- {"verb":"stroke","direction":"down"|"up","from":wordId,"to":wordId}  piston travels one stroke; the crank/rod follow automatically
- {"verb":"valve","part":partId,"state":"open"|"closed","at":wordId}
- {"verb":"highlight","part":partId,"from":wordId,"to":wordId}
- {"verb":"label","part":partId,"text":str,"from":wordId,"to":wordId}   short on-screen name (<=3 words)
- {"verb":"gas","kind":"fresh_mixture"|"compressed"|"burning"|"exhaust","from":wordId,"to":wordId}  colour the cylinder contents
- {"verb":"flow","through":partId,"direction":"in"|"out","from":wordId,"to":wordId}  arrows through a valve passage
- {"verb":"spark","at":wordId}
- {"verb":"title","text":str,"from":wordId,"to":wordId}  stage name banner'''


WORD = {'type': 'string', 'pattern': '^w[0-9]{4}$'}
CUE = {'type': 'object', 'properties': {
    'verb': {'enum': ['stroke', 'valve', 'highlight', 'label', 'gas', 'flow', 'spark', 'title']},
    'part': {'type': 'string'}, 'direction': {'enum': ['up', 'down', 'in', 'out']},
    'state': {'enum': ['open', 'closed']}, 'text': {'type': 'string', 'maxLength': 30},
    'kind': {'enum': ['fresh_mixture', 'compressed', 'burning', 'exhaust']}, 'through': {'type': 'string'},
    'from': WORD, 'to': WORD, 'at': WORD}, 'required': ['verb'], 'additionalProperties': False}
SCHEMA = {'type': 'object', 'properties': {'cues': {'type': 'array', 'items': CUE}, 'notes': {'type': 'string'}},
          'required': ['cues', 'notes'], 'additionalProperties': False}


def main(points=('N02', 'N03')):
    scenes = json.loads(SCENES.read_text())
    words = [w for w in scenes['words'] if w['point_id'] in points]
    parts = json.loads((ROOT / 'grounding/engine-parts.json').read_text())
    part_list = [{'id': p['id'], 'role': p['role'], 'motion': p['motion']} for p in parts['parts']]
    narration = ' '.join(f"{w['word']}[{w['id']}]" for w in words)
    prompt = ('You direct an animated cutaway for a narrated science lesson. The picture already exists; its moving '
              'parts were detected automatically. Decide what the viewer should SEE while each phrase is spoken, so '
              'the animation explains exactly what the narrator says at that moment. Make it lively but never '
              'contradict the physics. Use only these parts and verbs. Anchor every cue to word IDs from the '
              'narration; you never give coordinates, sizes or times.\n\nParts:\n' + json.dumps(part_list) +
              '\n\n' + VERBS + '\n\nNarration with word IDs:\n' + narration +
              '\n\nA motion such as a stroke should last as long as the narration is describing that stage, not just '
              'the words that name it. ' + '\n\nReturn JSON {"cues":[...],"notes":str}. Cues in chronological order.')
    with httpx.Client(timeout=600) as client:
        model = client.get(GLM + '/models').json()['data'][0]['id']
        raw = client.post(GLM + '/chat/completions', json={
            'model': model, 'temperature': 0.3, 'max_tokens': MAXTOK,
            'chat_template_kwargs': {'enable_thinking': THINK}, **({'thinking_budget_tokens': 2048} if 'QWEN' in TAG.upper() else {}),
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'cues', 'schema': SCHEMA}},
            'messages': [{'role': 'user', 'content': prompt}]}).raise_for_status().json()
    out = ROOT / 'cues'
    out.mkdir(exist_ok=True)
    (out / f'{TAG}-request.txt').write_text(prompt)
    (out / f'{TAG}-response.json').write_text(json.dumps(raw, indent=2))
    text = raw['choices'][0]['message']['content'] or ''
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S)
    text = text[text.find('{'):text.rfind('}') + 1]
    cues = json.loads(text)
    (out / f'{TAG}-cues.json').write_text(json.dumps(cues, indent=2))
    print(json.dumps(cues, indent=2))
    print('usage', raw.get('usage'))


if __name__ == '__main__':
    main(tuple(sys.argv[1:]) or ('N02', 'N03'))
