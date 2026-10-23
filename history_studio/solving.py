"""Solve (Physics Studio, 2026-10-23): exam questions from the bank, solved by the rule in solutions/solve.py and
planned as worked-solution clips (solutions/clips.py).

One question is solved at a time in a background thread: each solve calls cloud models (two students, Opus as
reviewer or solver), so the spend stays visible. Records live in questions-data/jee-advanced/runs/solved/<id>.json;
the pilot's records (runs/pilot-2026) are shown too until a question is solved again here.
"""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from solutions import clips, solve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'questions-data' / 'jee-advanced'
SOLVED = DATA / 'runs' / 'solved'
EARLIER = [DATA / 'runs' / 'pilot-2026']


class Solver:
    def __init__(self, subject):
        self.subject = subject
        self.waiting = queue.Queue()
        self.busy, self.failed, self.queued = None, {}, []
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
        record, attempts = solve.solve(q)
        if record['status'] == 'settled':
            plan, trail = clips.plan(q, record)
            record['clips'] = plan.get('clips')
            record['clip_errors'] = trail['errors']
            record['usage'].update({f'clips-{k}': v for k, v in trail['usage'].items()})
        SOLVED.mkdir(parents=True, exist_ok=True)
        (SOLVED / f'{q["id"]}.solutions.json').write_text(json.dumps(attempts, indent=1, ensure_ascii=False))
        (SOLVED / f'{q["id"]}.json').write_text(json.dumps(record, indent=1, ensure_ascii=False))

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
            for c in record.get('clips') or []:
                c['concept_names'] = [known.get(ref, ref) for ref in c.get('concepts') or []]
        return {'id': q['id'], 'year': q['year'], 'paper': q['paper'], 'number': q['number'], 'type': q['type'],
                'key': q['answer']['raw'], 'pages': len(q.get('pages', [])), 'state': self.state(qid),
                'error': self.failed.get(qid), 'record': record}

    def page(self, qid, n):
        pages = self.question(qid).get('pages', [])
        if not 0 <= n < len(pages):
            raise KeyError(n)
        return ROOT / pages[n]

