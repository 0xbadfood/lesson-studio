"""Pilot (2026-10-23): JEE Advanced 2026 physics questions that today's drawing aids can meet, plus controls that they
cannot. It tests two things: does the solving rule settle the right answer, and does the clip planning pick the right
aid (a verb where one fits, and no verb forced where none does).

    .venv/bin/python -m solutions.pilot            # writes questions-data/jee-advanced/runs/pilot-2026/
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import clips, solve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'questions-data' / 'jee-advanced'
# Expected aids, set by hand before the run. 'fits': at least one clip should use one of these (verb or
# missing:<family>); 'verbs': the verbs that are right here, any other verb is a false pick.
SET = {
    '2026-P1-phys-Q04': {'fits': ['graph'], 'verbs': ['graph'],
                         'note': 'lens power against n_L: P = 10(1.5/n - 1), a curve through 0 at n = 1.5'},
    '2026-P1-phys-Q05': {'fits': ['energy_ladder'], 'verbs': ['energy_ladder', 'graph'],
                         'note': 'hydrogen, a Lyman transition from level n'},
    '2026-P1-phys-Q06': {'fits': ['graph', 'missing:projectile'], 'verbs': ['graph', 'vector_add'],
                         'note': 'projectile through P(5, 1): the path y(x) and where its top falls'},
    '2026-P2-phys-Q02': {'fits': ['graph'], 'verbs': ['graph', 'area_under'],
                         'note': 'production and decay: N(t) = (alpha/lambda)(1 - e^-lambda t) saturates'},
    '2026-P2-phys-Q03': {'fits': ['extrema', 'graph'], 'verbs': ['extrema', 'graph'],
                         'note': 'n(lambda) = alpha lambda + beta/lambda^2 has a minimum; D_m = (n - 1)A there'},
    '2026-P1-phys-Q07': {'fits': ['graph', 'missing:pv_cycle'], 'verbs': ['graph'],
                         'note': 'a P-V cycle: isotherm, isochore, adiabat'},
    '2026-P2-phys-Q15': {'fits': ['graph', 'missing:fluid'], 'verbs': ['graph'],
                         'note': 'a draining tank: the level falls with time'},
    # Controls: no verb fits.
    '2026-P1-phys-Q01': {'control': True, 'fits': ['missing:rigid_body', 'missing:torque_and_balance',
                                                   'question_figure'], 'verbs': [],
                         'note': 'discs rolling on a disc'},
    '2026-P2-phys-Q01': {'control': True, 'fits': ['none'], 'verbs': [], 'note': 'drift velocity: numbers only'},
    '2026-P2-phys-Q12': {'control': True, 'fits': ['missing:ray_optics', 'question_figure'], 'verbs': [],
                         'note': 'Brewster angle through layers'},
    '2026-P2-phys-Q13': {'control': True, 'fits': ['missing:circuit', 'question_figure'], 'verbs': [],
                         'note': 'half-deflection circuit'},
    '2026-P2-phys-Q14': {'control': True, 'fits': ['none'], 'verbs': [], 'note': 'units and dimensions'},
}


def aid_label(aid):
    kind = aid.get('kind')
    return aid.get('verb') if kind == 'verb' else f'missing:{aid.get("family")}' if kind == 'missing' else kind


def run_one(q, out):
    record, solutions = solve.solve(q)
    (out / f'{q["id"]}.solutions.json').write_text(json.dumps(solutions, indent=1, ensure_ascii=False))
    if record['status'] == 'settled':
        try:
            plan, trail = clips.plan(q, record)
            record['clips'] = plan.get('clips')
            record['clip_errors'] = trail['errors']
            record['usage'].update({f'clips-{k}': v for k, v in trail['usage'].items()})
            (out / f'{q["id"]}.clips-trail.json').write_text(json.dumps(trail, indent=1, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - recorded, the run goes on
            record['clip_errors'] = [f'{type(exc).__name__}: {exc}'[:300]]
    expected = SET[q['id']]
    labels = [aid_label(c.get('aid') or {}) for c in record.get('clips') or []]
    verbs = [c['aid']['verb'] for c in record.get('clips') or [] if (c.get('aid') or {}).get('kind') == 'verb']
    record['score'] = {'expected': expected, 'aids': labels,
                       'hit': any(lbl in expected['fits'] for lbl in labels),
                       'false_picks': [v for v in verbs if v not in expected['verbs']]}
    (out / f'{q["id"]}.json').write_text(json.dumps(record, indent=1, ensure_ascii=False))
    return record


def usd(record):
    return sum((u or {}).get('usd') or 0 for u in record['usage'].values())


def report(records, out):
    lines = ['# Pilot: JEE Advanced 2026 physics', '',
             '| Question | Haiku | Luna | Route | Opus | Status | Aids chosen | Expected | Hit | False picks |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for r in records:
        s, t = r['students'], r.get('teacher') or {}
        opus = ('picked ' + str(t.get('chosen'))) if r['route'] == 'review' else (
            f'{t.get("answer")} {"✓" if t.get("right") else "✗"}')
        lines.append(f'| {r["id"]} (key {r["key"]}) | {s["haiku"]["answer"]} {"✓" if s["haiku"]["right"] else "✗"} | '
                     f'{s["luna"]["answer"]} {"✓" if s["luna"]["right"] else "✗"} | {r["route"]} | {opus} | '
                     f'{r["status"]} | {", ".join(r["score"]["aids"]) or "-"} | {", ".join(r["score"]["expected"]["fits"])} | '
                     f'{"yes" if r["score"]["hit"] else "no"} | {", ".join(r["score"]["false_picks"]) or "-"} |')
    settled = [r for r in records if r['status'] == 'settled']
    positives = [r for r in settled if not r['score']['expected'].get('control')]
    controls = [r for r in settled if r['score']['expected'].get('control')]
    lines += ['', f'- Settled: {len(settled)}/{len(records)}; needs review: '
              f'{", ".join(r["id"] for r in records if r["status"] != "settled") or "none"}',
              f'- Both students right: {sum(r["route"] == "review" for r in records)}; Opus solved: '
              f'{sum(r["route"] == "teacher_solves" for r in records)}',
              f'- Aid hits on questions a verb can meet: {sum(r["score"]["hit"] for r in positives)}/{len(positives)}',
              f'- Controls with no verb forced: {sum(not r["score"]["false_picks"] for r in controls)}/{len(controls)}; '
              f'false picks overall: {sum(len(r["score"]["false_picks"]) for r in settled)}',
              f'- OpenRouter cost (Haiku + Opus, as billed): ${sum(usd(r) for r in records):.2f}; Luna tokens: '
              f'{sum((r["usage"].get("luna") or {}).get("input", 0) + (r["usage"].get("luna") or {}).get("output", 0) + (r["usage"].get("clips-luna") or {}).get("input", 0) + (r["usage"].get("clips-luna") or {}).get("output", 0) for r in records):,}']
    (out / 'report.md').write_text('\n'.join(lines) + '\n')
    return '\n'.join(lines)


def main(argv=None):
    args = argv or sys.argv[1:]
    bank = {q['id']: q for q in json.loads((DATA / 'bank' / '2026.json').read_text())}
    ids = [i for i in SET if not args or i in args]
    out = DATA / 'runs' / 'pilot-2026'
    out = DATA / 'runs' / 'pilot-2026'
    out.mkdir(parents=True, exist_ok=True)
    if args[:1] == ['--report']:          # report what has finished, without calling any model
        records = [json.loads((out / f'{i}.json').read_text()) for i in SET if (out / f'{i}.json').exists()]
        print(report(records, out))
        return

    def safe(i):
        try:
            return run_one(bank[i], out)
        except Exception as exc:  # noqa: BLE001 - one question's failure (e.g. credits) must not lose the others
            print(f'{i}: {type(exc).__name__}: {exc}'[:300], file=sys.stderr)
            return None

    with ThreadPoolExecutor(2) as pool:
        records = [r for r in pool.map(safe, ids) if r]
    print(report(records, out))


if __name__ == '__main__':
    main()
