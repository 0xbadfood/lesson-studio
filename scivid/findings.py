"""Reviewer accuracy: every failed review criterion in the run history is a finding that can be judged right or wrong.

A finding is a FALSE POSITIVE when the problem is not really there, is only a difference of wording, stage, detail or
style, comes from a frame caught mid-animation, or would not mislead or block a learner. Verdicts come from people
(in the portal) or from the review auditor model step; a person's verdict always wins. Statistics per reviewer model,
review and criterion show where reviews cost retries for nothing.

Old-format reviews (before scored criteria) count their "major" issues as findings under the criterion "(old format)".
"""
import hashlib
import json
from pathlib import Path
import threading
import time

from . import review as rubric

KINDS = {'content-review': 'scene_content', 'frame-review': 'scene_frames', 'plan-review': 'plan',
         'script-review': 'script', 'diagram-review': 'diagram_frames', 'picture': 'picture'}
VERDICTS = ('right', 'wrong', 'unsure')
_lock = threading.Lock()
_rules = threading.Lock()   # rubric minimums are module state: one lesson's rules at a time


def _kind(name):
    return next((k for prefix, k in KINDS.items() if name.startswith(prefix + '-')), None)


def collect(data_root):
    """All findings in the run history, newest first."""
    out = []
    for call in sorted(Path(data_root, 'lessons').glob('*/llm/*/result.json')):
        folder, kind = call.parent, _kind(call.parent.name)
        if not kind:
            continue
        lesson = folder.parents[1]
        try:
            result = json.loads(call.read_text())
            request = json.loads((folder / 'request.json').read_text())
        except (OSError, json.JSONDecodeError):
            continue
        models = _read(lesson / 'models.json') or {}
        base = {'lesson': lesson.name, 'lesson_title': (_read(lesson / 'plan.json') or {}).get('plan', {}).get('title', ''),
                'review': kind, 'review_label': rubric.KIND_LABELS.get(kind, kind), 'call': str(folder),
                'reviewer': request.get('provider') or '?', 'reviewer_model': request.get('model') or '?',
                'images': request.get('images') or [], 'time': call.stat().st_mtime}
        if isinstance(result.get('scores'), dict):
            route = (models.get('options') or {}).get('scene_route') if kind == 'plan' else None
            with _rules:
                rubric.configure(models.get('review_rules'))
                try:
                    failed = rubric.decide(kind, result, route)['failed']
                finally:
                    rubric.configure({})
            items = [{'criterion': f['criterion'], 'label': f['label'], 'score': f['score'], 'minimum': f['minimum'],
                      'reason': f['reason'], 'fix': f['fix']} for f in failed]
        else:
            items = [{'criterion': '(old format)', 'label': 'Old-format major issue', 'score': None, 'minimum': None,
                      'reason': str(i.get('problem', '')), 'fix': str(i.get('fix', ''))}
                     for i in result.get('issues', []) if isinstance(i, dict) and i.get('severity') == 'major']
        for item in items:
            key = hashlib.sha256(f"{folder}|{item['criterion']}|{item['reason']}".encode()).hexdigest()[:16]
            out.append({'id': key, **base, **item})
    return sorted(out, key=lambda f: -f['time'])


def _read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def labels_path(data_root):
    return Path(data_root) / 'finding-labels.json'


def labels(data_root):
    return _read(labels_path(data_root)) or {}


def set_label(data_root, fid, verdict, by='teacher', note=''):
    if verdict not in VERDICTS:
        raise ValueError(f'verdict must be one of {list(VERDICTS)}')
    with _lock:
        values = labels(data_root)
        entry = values.setdefault(fid, {})
        entry['human' if by == 'teacher' else 'auditor'] = {'verdict': verdict, 'by': by, 'note': str(note)[:600],
                                                           'at': time.time()}
        path = labels_path(data_root)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(values, indent=1))
        tmp.replace(path)
    return entry


def verdict(entry):
    """The verdict that counts: a person's, else the auditor's."""
    entry = entry or {}
    return (entry.get('human') or entry.get('auditor') or {}).get('verdict')


def stats(found, marks):
    """Per reviewer connection, review and criterion: findings, judged, judged wrong, false-positive rate."""
    rows = {}
    for f in found:
        key = (f['reviewer'], f['review'], f['criterion'])
        row = rows.setdefault(key, {'reviewer': f['reviewer'], 'review': f['review'], 'review_label': f['review_label'],
                                    'criterion': f['criterion'], 'label': f['label'], 'findings': 0, 'judged': 0,
                                    'wrong': 0, 'unsure': 0})
        row['findings'] += 1
        v = verdict(marks.get(f['id']))
        if v in ('right', 'wrong'):
            row['judged'] += 1
            row['wrong'] += v == 'wrong'
        elif v == 'unsure':
            row['unsure'] += 1
    for row in rows.values():
        row['false_positive_rate'] = round(row['wrong'] / row['judged'], 3) if row['judged'] else None
    return sorted(rows.values(), key=lambda r: (r['reviewer'], r['review'], -r['findings']))


AUDIT = ('You are auditing ONE finding a reviewer made about part of an educational video (a lesson plan, a narration '
         'script, a scene\'s code, frames from a scene, or a slide picture). You see exactly what the reviewer saw. '
         'Decide whether the finding is RIGHT (the problem is really there and would mislead or block a learner, or '
         'breaks a stated rule) or WRONG, a false positive: the problem is not there; it is only a difference of wording, '
         'coordinates, stage, level of detail or style from the plan or cue text; it comes from a frame caught '
         'mid-animation; or it would not mislead a learner. Use "unsure" only if the material shown cannot settle it. '
         'Return {"verdict":"right"|"wrong"|"unsure","reason":"one or two sentences"}.')


def audit_one(model, finding):
    request = _read(Path(finding['call']) / 'request.json') or {}
    images = [p for p in finding.get('images') or [] if Path(p).exists()]
    reply = model.call(f"audit-{finding['id']}", (
        AUDIT + '\nFINDING:\n' + json.dumps({k: finding[k] for k in ('review_label', 'label', 'score', 'reason', 'fix')},
                                            ensure_ascii=False) +
        '\nWHAT THE REVIEWER SAW (its full prompt):\n' + str(request.get('prompt', ''))[:24000]),
        images=images, thinking=3000, max_tokens=4000,
        validate=lambda r: None if r.get('verdict') in VERDICTS else (_ for _ in ()).throw(
            ValueError('verdict must be right, wrong or unsure')))
    return reply['verdict'], str(reply.get('reason', ''))


class Auditor:
    """One background audit at a time (portal button); progress is readable while it runs."""

    def __init__(self, data_root, client_for_step):
        self.data_root, self.client_for_step = Path(data_root), client_for_step
        self.state = {'running': False, 'done': 0, 'total': 0, 'errors': 0, 'last': None}
        self._thread = None

    def start(self, limit=40):
        if self.state['running']:
            raise ValueError('An audit is already running')
        marks = labels(self.data_root)
        todo = [f for f in collect(self.data_root) if not verdict(marks.get(f['id']))][:max(1, min(int(limit), 200))]
        self.state = {'running': True, 'done': 0, 'total': len(todo), 'errors': 0, 'last': None, 'started': time.time()}
        model = self.client_for_step('review_audit')

        def run():
            try:
                for f in todo:
                    try:
                        v, reason = audit_one(model, f)
                        set_label(self.data_root, f['id'], v, by='auditor', note=reason)
                        self.state['last'] = {'id': f['id'], 'verdict': v}
                    except Exception as exc:   # noqa: BLE001 - one failed audit must not stop the rest
                        self.state['errors'] += 1
                        self.state['last'] = {'id': f['id'], 'error': str(exc)[:200]}
                    self.state['done'] += 1
            finally:
                self.state['running'] = False
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return self.state
