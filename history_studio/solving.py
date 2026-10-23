"""Solve (Physics Studio, 2026-10-23): exam questions from the bank, solved by the rule in solutions/solve.py and
planned as worked-solution clips (solutions/clips.py).

One question is solved at a time in a background thread: each solve calls cloud models (two students, Opus as
reviewer or solver), so the spend stays visible. Records live in questions-data/jee-advanced/runs/solved/<id>.json;
the pilot's records (runs/pilot-2026) are shown too until a question is solved again here.

A clip whose aid is "missing" has hit a snag: no Linkwork verb fits. The page offers two ways on (user, 2026-10-23):
proceed with manim, or retry the Linkwork search (new verbs may exist). Decisions live in runs/decisions.json, keyed
'<question>:<clip>', so a re-solve does not lose them; the snag tally by family is the evidence for deciding whether a
family deserves a Linkwork verb or stays with manim.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from solutions import clips, solve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'questions-data' / 'jee-advanced'
SOLVED = DATA / 'runs' / 'solved'
EARLIER = [DATA / 'runs' / 'pilot-2026']
DECISIONS = DATA / 'runs' / 'decisions.json'


class Solver:
    def __init__(self, subject):
        self.subject = subject
        self.waiting = queue.Queue()
        self.busy, self.failed, self.queued, self.flow = None, {}, [], {}
        self.lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True).start()

    def questions(self):
        out = []
        for path in sorted((DATA / 'bank').glob('*.json')):
            out += [q for q in json.loads(path.read_text()) if q['subject'] == self.subject]
        return out

    def question(self, qid):
        found = next((q for q in self.questions() if q['id'] == qid), None)
        if found is None:
            raise KeyError(qid)
        return found

    def record(self, qid):
        for folder in [SOLVED] + EARLIER:
            path = folder / f'{qid}.json'
            if path.exists():
                record = json.loads(path.read_text())
                solutions = folder / f'{qid}.solutions.json'
                record['attempts'] = json.loads(solutions.read_text()) if solutions.exists() else {}
                trail = folder / f'{qid}.clips-trail.json'
                record['clip_trail'] = json.loads(trail.read_text()).get('trail') if trail.exists() else None
                return record
        return None

    def state(self, qid):
        with self.lock:
            if self.busy == qid:
                return 'solving'
            if qid in self.queued:
                return 'queued'
        if qid in self.failed:
            return 'failed'
        record = self.record(qid)
        return record['status'] if record else 'new'

    def start(self, qid):
        self.question(qid)
        with self.lock:
            if self.busy == qid or qid in self.queued:
                return
            self.queued.append(qid)
            self.failed.pop(qid, None)
        self.waiting.put(qid)

    def _work(self):
        while True:
            qid = self.waiting.get()
            with self.lock:
                self.queued.remove(qid)
                self.busy = qid
            try:
                self._solve(self.question(qid))
            except Exception as exc:  # noqa: BLE001 - shown on the page; the worker goes on
                self.failed[qid] = f'{type(exc).__name__}: {exc}'[:400]
            finally:
                with self.lock:
                    self.busy = None

    def _solve(self, q):
        flow = self.flow[q['id']] = []

        def say(text):
            flow.append({'at': time.strftime('%H:%M:%S'), 'text': text})

        say('Haiku and Luna solve the question on their own')
        record, attempts = solve.solve(q, say)
        trail = None
        if record['status'] == 'settled':
            plan, trail = clips.plan(q, record, say)
            record['clips'] = plan.get('clips')
            record['clip_errors'] = trail['errors']
            record['usage'].update({f'clips-{k}': v for k, v in trail['usage'].items()})
        record['flow'] = flow
        SOLVED.mkdir(parents=True, exist_ok=True)
        if trail:
            (SOLVED / f'{q["id"]}.clips-trail.json').write_text(json.dumps(trail, indent=1, ensure_ascii=False))
        (SOLVED / f'{q["id"]}.solutions.json').write_text(json.dumps(attempts, indent=1, ensure_ascii=False))
        (SOLVED / f'{q["id"]}.json').write_text(json.dumps(record, indent=1, ensure_ascii=False))

    # ------------------------------------------------------------ snags: clips without a Linkwork aid
    def decisions(self):
        return json.loads(DECISIONS.read_text()) if DECISIONS.exists() else {}

    def _decide(self, qid, n, decision):
        with self.lock:
            saved = self.decisions()
            saved[f'{qid}:{n}'] = {**decision, 'at': time.strftime('%Y-%m-%d %H:%M')}
            DECISIONS.parent.mkdir(parents=True, exist_ok=True)
            DECISIONS.write_text(json.dumps(saved, indent=1, ensure_ascii=False))

    def _clip(self, qid, n):
        record = self.record(qid)
        clip = next((c for c in (record or {}).get('clips') or [] if c.get('n') == n), None)
        if clip is None:
            raise KeyError(n)
        return record, clip

    def to_manim(self, qid, n):
        self._clip(qid, n)
        self._decide(qid, n, {'route': 'manim'})

    def retry(self, qid, n):
        record, clip = self._clip(qid, n)
        aid, _ = clips.retry(self.question(qid), record, clip)
        if aid.get('kind') == 'verb':
            self._decide(qid, n, {'route': 'linkwork', 'verb': aid['verb'], 'shows': aid.get('shows'),
                                  'why': aid.get('why')})
        else:
            self._decide(qid, n, {**self.decisions().get(f'{qid}:{n}', {}), 'retried': True,
                                  'retry_why': aid.get('retry_why')})
        return aid

    def snags(self):
        """Clips that hit a snag, by missing family: how many, and how many went to manim or found a verb."""
        decided, out = self.decisions(), {}
        for q in self.questions():
            record = self.record(q['id'])
            for c in (record or {}).get('clips') or []:
                aid = c.get('aid') or {}
                if aid.get('kind') != 'missing':
                    continue
                row = out.setdefault(aid.get('family') or 'unknown', {'clips': 0, 'manim': 0, 'linkwork': 0})
                row['clips'] += 1
                route = decided.get(f'{q["id"]}:{c.get("n")}', {}).get('route')
                if route in row:
                    row[route] += 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]['clips']))

    # ------------------------------------------------------------ what the page gets
    def listing(self):
        out = []
        for q in self.questions():
            out.append({'id': q['id'], 'year': q['year'], 'paper': q['paper'], 'number': q['number'],
                        'type': q['type'], 'state': self.state(q['id']),
                        'preview': ' '.join(q['text'].split())[4:150]})
        return out

    def detail(self, qid):
        q = self.question(qid)
        record = self.record(qid)
        known = clips.concepts()
        if record:
            decided = self.decisions()
            for c in record.get('clips') or []:
                c['concept_names'] = [known.get(ref, ref) for ref in c.get('concepts') or []]
                c['decision'] = decided.get(f'{qid}:{c.get("n")}')
        return {'id': q['id'], 'year': q['year'], 'paper': q['paper'], 'number': q['number'], 'type': q['type'],
                'key': q['answer']['raw'], 'pages': len(q.get('pages', [])), 'state': self.state(qid),
                'error': self.failed.get(qid), 'record': record,
                'flow': self.flow.get(qid) if self.state(qid) in ('solving', 'failed') else None}

    def page(self, qid, n):
        pages = self.question(qid).get('pages', [])
        if not 0 <= n < len(pages):
            raise KeyError(n)
        return ROOT / pages[n]

