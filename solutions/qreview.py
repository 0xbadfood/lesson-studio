"""Created questions for review in the studio: read a run's results, keep a person's flags (the human in the loop)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

CREATED = Path(__file__).resolve().parents[1] / 'questions-data' / 'created'
RUN = re.compile(r'^[\w-]+$')


def fill(value, params):
    """[[name]] filled from params, in any text shown to a reader."""
    if isinstance(value, str):
        return re.sub(r'\[\[(\w+)\]\]', lambda m: f'{params[m.group(1)]:g}' if m.group(1) in params else m.group(0), value)
    return value


class Review:
    def __init__(self, data, created=CREATED):
        self.flags_file, self.created = Path(data) / 'question-flags.json', Path(created)

    def flags(self):
        return json.loads(self.flags_file.read_text()) if self.flags_file.exists() else {}

    def set_flag(self, qid, flagged, reason=''):
        flags = self.flags()
        if flagged:
            flags[qid] = {'reason': reason.strip()[:600], 'at': time.time()}
        else:
            flags.pop(qid, None)
        self.flags_file.write_text(json.dumps(flags, ensure_ascii=False, indent=1))

    def runs(self):
        dirs = [d for d in self.created.glob('*') if d.is_dir() and any(d.glob('q*/question.json'))]
        return [d.name for d in sorted(dirs, key=lambda d: d.stat().st_mtime, reverse=True)]

    def figure(self, run, q):
        if not RUN.match(run) or not re.fullmatch(r'q\d+', q):
            return None
        path = self.created / run / q / 'figure.png'
        return path if path.is_file() else None

    def listing(self, run):
        """Every question of a run, printed as a student would see it, with the answer and the checks alongside."""
        if not RUN.match(run):
            return []
        flags, out = self.flags(), []
        for f in sorted((self.created / run).glob('q*/question.json')):
            r = json.loads(f.read_text())
            q = r.get('question') or {}
            if not q.get('options'):
                out.append({'id': f'{run}/{f.parent.name}', 'q': f.parent.name, 'status': r.get('status'), 'cost': r.get('cost'), 'errors': r.get('errors'), 'broken': True})
                continue
            p, h = q.get('params') or {}, r.get('haiku') or {}
            qid = f'{run}/{f.parent.name}'
            out.append({'id': qid, 'q': f.parent.name, 'status': r.get('status'), 'cost': r.get('cost'), 'rounds': r.get('rounds'),
                        'stem': fill(q['stem'], p), 'options': {k: fill(v['text'], p) for k, v in q['options'].items()}, 'key': q['key'],
                        'unwrap': fill(q.get('unwrap'), p), 'decoy': fill(q.get('decoy'), p), 'mistakes': {k: fill(v, p) for k, v in (q.get('mistakes') or {}).items()},
                        'concepts': q.get('concepts') or [], 'figure': (f.parent / 'figure.png').is_file(), 'figure_flag': bool(r.get('figure_flag')),
                        'defects': (r.get('figure_read') or {}).get('defects') or [], 'solves': {
                            'sonnet': {'open': r.get('open_right'), 'mcq': r.get('mcq_right')}, 'haiku': {'open': h.get('open_right'), 'mcq': h.get('mcq_right')}, 'fable': r.get('fable')},
                        'tries': {'open': len(r.get('open') or []), 'mcq': len(r.get('mcq') or [])}, 'flag': flags.get(qid)})
        return out
