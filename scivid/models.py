"""Model connections and per-step assignments.

Connections are typed; each type has one adapter. Today: OpenAI-compatible chat (any local server: llama.cpp,
vLLM, Ollama's /v1) and OpenAI Responses (Luna). Another cloud API = one adapter class + one TYPES entry.
API keys live in a separate mode-600 file and are never returned to the browser.
"""
import json
import os
import re
import time
from pathlib import Path

import httpx

from . import review
from .llm import Chat, Claude, Responses, claude_models

TYPES = {
    'openai_chat': {'label': 'Local LLM (OpenAI-compatible URL)', 'needs_key': False, 'detects_models': True,
                    'default_url': ''},
    'openai_responses': {'label': 'OpenAI (Luna)', 'needs_key': True, 'detects_models': True,
                         'default_url': 'https://api.openai.com/v1'},
    'anthropic': {'label': 'Claude (Anthropic)', 'needs_key': True, 'detects_models': True,
                  'default_url': 'https://api.anthropic.com', 'default_model': 'claude-opus-5-5'},
    'openrouter': {'label': 'OpenRouter', 'needs_key': True, 'detects_models': True,
                   'default_url': 'https://openrouter.ai/api/v1'},
}

# The workflow, in order. Each step belongs to a stage; "next" steps are configurable now and used once the
# scene-coding route is switched on; "dormant" steps (the retired image route) stay for old lessons, hidden.
STAGES = [
    ('research', 'Research', 'Gathers sources when web research is on (skipped for chapter-only or no-sources lessons).'),
    ('plan', 'Plan', 'Decides chapters, demonstrations and how hard each chapter is to animate.'),
    ('script', 'Script', 'Writes the narration and the cues that tie animation to words.'),
    ('scenes', 'Scenes', 'Turns each chapter into animation. Scene coders are chosen by the chapter\'s complexity tier.'),
    ('review', 'Review', 'Checks the rendered result: facts, sync with the narration, and layout from frames.'),
]
STEPS = [
    # id, stage, label, what it does, needs images, types allowed (None = any), status
    ('web_research', 'research', 'Web research', 'Searches and reads web pages (infofilm research agent)', False, ('openai_chat',), 'active'),
    ('plan', 'plan', 'Planner', 'Chooses chapters and demonstrations; will also rate each chapter routine, involved or novel', False, None, 'active'),
    ('plan_review', 'plan', 'Plan review', 'Checks the plan for accuracy, order, coverage and visual teaching', False, None, 'active'),
    ('script', 'script', 'Narration writer', 'Writes the narration and its word-anchored cues', False, None, 'active'),
    ('script_review', 'script', 'Script review', 'Checks facts, tone and cues', False, None, 'active'),
    ('numbers', 'script', 'Calculation check', 'Lists calculations for code to verify', False, None, 'active'),
    ('scene_code_routine', 'scenes', 'Scene coder · routine', 'Standard patterns: plots, worked equations, number lines, one labelled motion', False, None, 'active'),
    ('scene_code_involved', 'scenes', 'Scene coder · involved', 'Several synced moving parts, custom geometry, live vectors, transforms; takes over after two routine failures', False, None, 'active'),
    ('scene_code_novel', 'scenes', 'Scene coder · novel', 'Original constructions, perspective, physical simulation; the last escalation step', False, None, 'active'),
    ('diagram_design', 'scenes', 'Diagram designer', 'Diagram route only: designs or revises a chapter from the diagram vocabulary', False, None, 'active'),
    ('content_review', 'review', 'Scene content review', 'Coded route: checks each scene\'s code for facts, numbers and sync with the narration cues', False, None, 'active'),
    ('diagram_review', 'review', 'Frame review', 'Looks at frames taken at the cue moments for overlaps, crowding and correctness, and checks slide pictures', True, None, 'active'),
    ('review_audit', 'review', 'Review auditor', 'Judges past review findings right or wrong to measure each reviewer\'s false positives (Settings, on demand; never part of a lesson run)', True, None, 'active'),
    ('picture_check', 'scenes', 'Picture check (retired)', 'Image route, no longer used', True, None, 'dormant'),
]
STEP_IDS = [s[0] for s in STEPS]
# Review steps and the rubric kinds (scivid/review.py) each one scores; Settings shows them on the Reviews tab.
REVIEW_RUBRICS = {'plan_review': ['plan'], 'script_review': ['script'], 'content_review': ['scene_content'],
                  'diagram_review': ['scene_frames', 'diagram_frames', 'picture'], 'review_audit': []}
# Steps that only one scene route uses (the rest run on every lesson).
ROUTE_STEPS = {'scene_code_routine': 'coded', 'scene_code_involved': 'coded', 'scene_code_novel': 'coded',
               'content_review': 'coded', 'diagram_design': 'diagram'}
OPTIONS = {
    'scene_route': {'label': 'How chapters are animated', 'default': 'coded', 'choices': [
        ['coded', 'Coded scenes: a tiered coder writes each scene, timed to the narration'],
        ['diagram', 'Diagram vocabulary: a fixed renderer draws declared elements']]},
    'voice_server': {'label': 'Voice server', 'default': 'local', 'choices': [
        ['local', 'Local RTX 3090 (shares the GPU with pictures; the picture model is unloaded while recording)'],
        ['spark', 'Spark VibeVoice (10.8.0.4, same checkpoint and LoRA): the local GPU stays hot for pictures']]},
    'chapter_workers': {'label': 'Chapters animated at once', 'default': '1', 'choices': [
        ['1', 'One at a time (use when reviews run on a shared local model)'],
        ['2', 'Two at once'], ['3', 'Three at once'],
        ['4', 'Four at once (cloud models; scene reviews also run side by side)']]},
}


def _id(label):
    return re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:40] or 'connection'


class Registry:
    def __init__(self, data_root, defaults):
        self.path = Path(data_root) / 'model-settings.json'
        self.secret_path = Path(data_root) / 'model-secrets.json'
        self.defaults = defaults

    # ------------------------------------------------------------ storage
    def load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text())
        else:
            data = self.defaults()
        data.setdefault('connections', {})
        data.setdefault('steps', {})
        data.setdefault('presets', {})
        data.setdefault('review_rules', {})
        options = data.setdefault('options', {})
        for key, spec in OPTIONS.items():
            options.setdefault(key, spec['default'])
        for step in STEP_IDS:
            data['steps'].setdefault(step, next(iter(data['connections']), None))
        return data

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    def secrets(self):
        return json.loads(self.secret_path.read_text()) if self.secret_path.exists() else {}

    def set_secret(self, cid, value):
        values = self.secrets()
        if value:
            values[cid] = value
        else:
            values.pop(cid, None)
        fd = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(values, f)

    def api_key(self, cid, connection):
        """A key saved in Settings wins; otherwise the service environment (OpenAI also accepts OPENAI_TOKEN)."""
        names = [connection['key_env']] if connection.get('key_env') else []
        if connection.get('type') == 'openai_responses':
            names.append('OPENAI_TOKEN')
        return self.secrets().get(cid) or next((os.environ[n] for n in names if os.environ.get(n)), None)

    # ------------------------------------------------------------ public view (no secrets)
    def public(self):
        data = self.load()
        connections = {}
        for cid, c in data['connections'].items():
            connections[cid] = {**c, 'key_set': bool(self.api_key(cid, c)) if TYPES[c['type']]['needs_key'] else None,
                                'in_use': [s for s, v in data['steps'].items() if v == cid]}
        return {'types': TYPES, 'stages': [{'id': i, 'label': l, 'description': d} for i, l, d in STAGES],
                'steps': [{'id': s, 'stage': g, 'label': l, 'description': d, 'needs_images': v, 'status': st,
                           'route': ROUTE_STEPS.get(s), 'allowed_types': list(t) if t else list(TYPES),
                           'rubrics': REVIEW_RUBRICS.get(s)}
                          for s, g, l, d, v, t, st in STEPS if st != 'dormant'],
                'connections': connections, 'assignments': data['steps'], 'option_specs': OPTIONS,
                'options': data['options'], 'presets': data['presets'], 'active_preset': self.matching_preset(data),
                'reviews': review.public(data['review_rules'])}

    # ------------------------------------------------------------ changes
    def upsert(self, payload):
        data = self.load()
        kind = payload.get('type')
        if kind not in TYPES:
            raise ValueError(f'Unknown connection type; choose one of {list(TYPES)}')
        label = str(payload.get('label') or '').strip()
        url = str(payload.get('url') or '').strip().rstrip('/')
        model = str(payload.get('model') or '').strip()
        if not label or not url.startswith(('http://', 'https://')) or not model:
            raise ValueError('Give a name, an http(s) URL and a model')
        cid = payload.get('id') or _id(label)
        if not payload.get('id') and cid in data['connections']:
            cid = f'{cid}-{len(data["connections"]) + 1}'
        connection = {'type': kind, 'label': label, 'url': url, 'model': model,
                      'vision': bool(payload.get('vision')), 'timeout': int(payload.get('timeout') or 600)}
        if kind in ('openai_responses', 'anthropic'):
            effort = payload.get('reasoning_effort', 'medium')
            if effort not in ('low', 'medium', 'high'):
                raise ValueError('Reasoning effort must be low, medium or high')
            connection['reasoning_effort'] = effort
        if TYPES[kind]['needs_key']:
            default_env = {'openai_responses': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY',
                           'openrouter': 'OPENROUTER_API_KEY'}[kind]
            connection['key_env'] = payload.get('key_env') or default_env
        if kind == 'anthropic':
            connection['vision'] = True
        data['connections'][cid] = connection
        if 'api_key' in payload and payload['api_key'] is not None:
            self.set_secret(cid, str(payload['api_key']).strip())
        self.save(data)
        return cid

    def delete(self, cid):
        data = self.load()
        users = [s for s, v in data['steps'].items() if v == cid]
        if users:
            raise ValueError(f'In use by: {", ".join(users)}. Assign those steps elsewhere first.')
        data['connections'].pop(cid, None)
        self.save(data)
        self.set_secret(cid, None)

    def assign(self, assignments):
        data = self.load()
        allowed = {s: t for s, _, _, _, _, t, _ in STEPS}
        vision = {s: v for s, _, _, _, v, _, _ in STEPS}
        for step, cid in assignments.items():
            if step not in allowed or cid not in data['connections']:
                raise ValueError(f'Unknown step or connection: {step} → {cid}')
            c = data['connections'][cid]
            if allowed[step] and c['type'] not in allowed[step]:
                raise ValueError(f'{step} only works with: {", ".join(TYPES[t]["label"] for t in allowed[step])}')
            if vision[step] and not c.get('vision'):
                raise ValueError(f'{step} looks at images; choose a connection marked as supporting images')
            data['steps'][step] = cid
        self.save(data)

    def set_options(self, options):
        data = self.load()
        for key, value in options.items():
            if key not in OPTIONS or value not in [c[0] for c in OPTIONS[key]['choices']]:
                raise ValueError(f'Unknown option or value: {key} = {value}')
            data['options'][key] = value
        self.save(data)

    def set_review_rules(self, rules):
        """Global minimum scores per review criterion (code decides pass/fail from them)."""
        data = self.load()
        data['review_rules'] = review.clean_rules(rules)
        self.save(data)

    # ------------------------------------------------------------ presets: named model configurations
    @staticmethod
    def matching_preset(data):
        """The preset the current assignments and options equal, if any."""
        for pid, p in data['presets'].items():
            if all(data['steps'].get(s) == c for s, c in p['steps'].items()) and \
                    all(data['options'].get(k) == v for k, v in p.get('options', {}).items()) and \
                    review.clean_rules(p.get('review_rules')) == review.clean_rules(data.get('review_rules')):
                return pid
        return None

    def save_preset(self, label, note='', benchmark=False):
        data = self.load()
        label = str(label or '').strip()
        if not label:
            raise ValueError('Name the configuration')
        pid = _id(label)
        data['presets'][pid] = {'label': label[:60], 'note': str(note or '').strip()[:400], 'benchmark': bool(benchmark),
                                'steps': dict(data['steps']), 'options': dict(data['options']),
                                'review_rules': dict(data.get('review_rules', {})), 'created': time.time()}
        self.save(data)
        return pid

    def preset_choice(self, data, pid):
        if pid not in data['presets']:
            raise ValueError('Unknown configuration: ' + str(pid))
        preset = data['presets'][pid]
        missing = sorted({c for c in preset['steps'].values() if c not in data['connections']})
        if missing:
            raise ValueError(f'This configuration uses deleted connections: {", ".join(missing)}')
        return preset

    def apply_preset(self, pid):
        data = self.load()
        preset = self.preset_choice(data, pid)
        data['steps'].update(preset['steps'])
        data['options'].update(preset.get('options', {}))
        data['review_rules'] = dict(preset.get('review_rules', {}))
        self.save(data)

    def delete_preset(self, pid):
        data = self.load()
        data['presets'].pop(pid, None)
        self.save(data)

    # ------------------------------------------------------------ runtime
    def snapshot(self, preset=None):
        """Frozen copy for one lesson (secrets excluded; they are read again at run time). With a preset id the
        lesson runs that configuration instead of the current assignments."""
        data = self.load()
        if preset:
            chosen = self.preset_choice(data, preset)
            data['steps'] = {**data['steps'], **chosen['steps']}
            data['options'] = {**data['options'], **chosen.get('options', {})}
            if 'review_rules' in chosen:
                data['review_rules'] = dict(chosen['review_rules'])
        pid = preset or self.matching_preset(data)
        data['preset'] = {'id': pid, 'label': data['presets'][pid]['label']} if pid else None
        data.pop('presets')
        return data


def detect_models(url, api_key=None, timeout=8, kind='openai_chat'):
    """List model ids: Anthropic's Models API for Claude, an OpenAI-compatible /models endpoint otherwise."""
    if kind == 'anthropic':
        if not api_key:
            raise ValueError('Enter the Claude API key first; the model list needs it')
        return claude_models(api_key, timeout)
    url = url.rstrip('/')
    headers = {'Authorization': 'Bearer ' + api_key} if api_key else {}
    response = httpx.get(url + '/models', timeout=timeout, headers=headers)
    response.raise_for_status()
    ids = [m.get('id') for m in response.json().get('data', []) if m.get('id')]
    if not ids:
        raise ValueError('The server answered but listed no models')
    return ids


def client_for(snapshot, step, root, secrets_root):
    """Build the client for a step from a lesson's frozen model settings."""
    cid = snapshot['steps'][step]
    c = snapshot['connections'][cid]
    key = Registry(secrets_root, dict).api_key(cid, c) if TYPES[c['type']]['needs_key'] else None
    if c['type'] == 'openai_chat':
        return Chat(c['url'], root, timeout=c.get('timeout', 600), label=cid, model=c['model'])
    if c['type'] == 'openrouter':
        return Chat(c['url'], root, timeout=c.get('timeout', 600), label=cid, model=c['model'], api_key=key, local=False)
    if c['type'] == 'openai_responses':
        return Responses(c['url'], c['model'], root, api_key=key, reasoning_effort=c.get('reasoning_effort', 'medium'),
                         timeout=c.get('timeout', 600), label=cid)
    if c['type'] == 'anthropic':
        return Claude(c['model'], root, api_key=key, effort=c.get('reasoning_effort', 'medium'),
                      timeout=c.get('timeout', 600), label=cid)
    raise ValueError(f'No adapter for connection type {c["type"]}')


def default_settings(settings):
    """First-run settings: the configured local endpoints plus Luna."""
    def build():
        connections = {}
        for url in dict.fromkeys([settings.planner_url, settings.reviewer_url]):
            try:
                model = detect_models(url)[0]
            except (httpx.HTTPError, ValueError):
                model = 'unknown'
            connections[_id('local ' + url.split('//')[1].split('/')[0])] = {
                'type': 'openai_chat', 'label': 'Local · ' + url.split('//')[1].split('/')[0], 'url': url,
                'model': model, 'vision': True, 'timeout': 600}
        connections['luna'] = {'type': 'openai_responses', 'label': 'Luna (OpenAI)', 'url': settings.luna_url,
                               'model': settings.luna_model, 'vision': True, 'reasoning_effort': 'medium',
                               'key_env': 'OPENAI_API_KEY', 'timeout': 600}
        first = next(iter(connections))
        return {'connections': connections, 'steps': {s: first for s in STEP_IDS}}
    return build
