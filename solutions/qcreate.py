"""Question creation pilot: Opus writes a JEE-style question, code checks it, Sonnet tries it blind.

The method is unwrapping in reverse (user, 2026-10-23): at least three concepts packed into one setting, with a decoy,
and wrong options that are the mistakes students really make. Code proves the key and every wrong option from one set
of values; Sonnet's solves are a test of the question, not a pass mark, because a hard question and a broken one look
alike to a student. Every call's tokens and cost are kept against the question, rejected or not.

Usage (from ~/remotion's venv, ANTHROPIC_API_KEY in the environment): python solutions/qcreate.py <run> [first last]
"""
from __future__ import annotations

import difflib
import json
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REMOTION = Path('/home/nitin/remotion')
for p in (str(REMOTION), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import cairosvg  # noqa: E402
import os  # noqa: E402
from infofilm.anthropic_llm import json_call  # noqa: E402
import qfigure  # noqa: E402

OUT = ROOT / 'questions-data' / 'created'
BANK = ROOT / 'questions-data' / 'jee-advanced' / 'bank'
DIGESTS = ROOT / 'textbook-digest'
WRITER = {'model': 'claude-opus-5-5', 'reasoning_effort': 'high', 'timeout': 1200}
SOLVER = {'model': 'claude-sonnet-5-5', 'reasoning_effort': 'high', 'timeout': 900}
PRICES = {'claude-opus-5-5': (4.0, 20.0, 0.20), 'claude-sonnet-5-5': (2.0, 10.0, 0.20)}    # $ per MTok: input, output, cache read
MECHANICS = ['keph1-02', 'keph1-03', 'keph1-04', 'keph1-05', 'keph1-06', 'keph1-07']
REPAIRS = 2         # further writer rounds when code refuses a draft
OPEN_TRIES, MCQ_TRIES = 3, 3
TOLERANCE = 0.01    # a solver's answer within 1% of the key is right
STYLE = ['2026-P1-phys-Q03', '2026-P1-phys-Q06', '2026-P2-phys-Q04']

# Pairs of chapters the pilot's questions must cross, so they don't all land on one favourite combination.
BRIEFS = [('keph1-05', 'keph1-06'), ('keph1-04', 'keph1-05'), ('keph1-03', 'keph1-05'), ('keph1-05', 'keph1-05'), ('keph1-04', 'keph1-06'), ('keph1-06', 'keph1-06'),
          ('keph1-02', 'keph1-04'), ('keph1-05', 'keph1-07'), ('keph1-03', 'keph1-04'), ('keph1-06', 'keph1-07'), ('keph1-02', 'keph1-05'), ('keph1-04', 'keph1-07')]

SYSTEM = f"""You write questions for JEE Advanced physics, the hardest school-level physics examination in India. Return one JSON object and nothing else. Write mathematics in plain Unicode (θ, √, ω, ₁), never LaTeX.

What makes a JEE Advanced question:
- A familiar principle in an unfamiliar setting. The student's real work is seeing what is going on; the algebra afterwards is short. It should take a strong student about 4 minutes.
- At least three concepts, each truly needed: remove any one and the answer can't be reached. Naming a concept that the solution barely touches does not count.
- A decoy: a detail, a quantity or a tempting route that looks relevant and isn't, or a familiar result that doesn't apply here. A student who pattern-matches should be led wrong.
- Four options, exactly one right. Every wrong option is what a real mistake gives, such as using energy but forgetting momentum, taking the wrong moment of inertia, or assuming the string stays taut. Each wrong option must be plausible and close enough that no estimate rules it out.
- Exact and complete: every quantity needed is given, the idealisations are stated, and nothing is left to guess. The setup must be physically possible all the way through the motion asked about (contact kept, string taut, no slipping where claimed).
- Your own setting. Never rework a well-known textbook or past-paper problem with new numbers.

The JSON fields:
- "concepts": at least 3 of {{"name": from the list you are given, "where_needed": the step that can't be done without it}}.
- "stem": the question without options. A symbolic question keeps its symbols in the stem, the options and the figure (R, m, ω₀), and uses no [[name]] at all. A numerical question prints each given value as [[name]], filled from params, never arithmetic on it such as [[R]]/4. The same goes for the figure's labels.
- "unwrap": what is really going on, in 2 to 4 sentences: the setting mapped onto the basic principles.
- "decoy": what tempts the student and why it fails.
- "params": {{name: number}}, SI values for every symbol the answer depends on, including g if used. Symbolic questions use these as test values.
- "params_alt": the same names with different values that keep the setup possible.
- "options": {{"A": {{"text": as printed, "expr": the same value as a sympy expression in the param names, or a plain number}}, "B":..., "C":..., "D":...}}.
- "key": the right letter.
- "mistakes": {{letter: the mistake that gives this wrong option}} for each of the three wrong options.
- "python": Python source, numpy and sympy available, no files or network, defining these functions of P (a dict of params):
    correct(P): the answer, a number, worked out from the physics step by step, numerically where you can (integrate, solve the equations), not by copying the option;
    wrong(P): {{letter: the number that mistake gives}}, computed by making that mistake;
    checks(P): {{name: bool}}, testing the assumptions the question relies on at P: contact kept, string taut, within the track, no slipping where claimed, and so on.
- "figure_needed": true if a printed question would show a figure. Most mechanics questions do.
- "figure": the figure when needed, or null. It shows the setup and the given labels, never the answer or a step of the solution. Values in it may be written [[name]].
- "figure_facts": 3 to 6 short statements a reader must be able to check from the figure alone, such as "the string passes over the pulley from the block to the hanging mass".
- "missing_parts": figure parts you need that the kit can't draw, as short names; empty if none. If the figure can't be drawn properly, say so here and still write the rest.

The figure is drawn by code from parts. It is {{"width": 100, "height": 60, "parts": [...]}} (make height larger if needed), in units, y up.
{qfigure.KIT}
A pivot is a side-view hinge on a support; in a top view mark an axle with a point. Connect things through anchors rather than coordinates wherever you can, and rest things with "on": the drawing then stays true. Labels must not overlap and must not sit on a line.

Your questions are tried by a very strong solver. A setting where the method is obvious once read will be solved every time; aim for one where choosing the right idea is the hard part."""

OPEN_SOLVE = """Solve this physics question carefully. Return one JSON object and nothing else: {{"working": brief steps, "answer": the final answer as one sympy expression or number{names}}}.

{stem}"""
MCQ_SOLVE = """Solve this physics question carefully. Exactly one option is correct. Return one JSON object and nothing else: {{"working": brief steps, "choice": "A", "B", "C" or "D"}}.

{stem}

{options}"""
READ_FIGURE = """Here is a figure from a physics question. Using only what the figure shows, judge each statement. Return one JSON object and nothing else: {{"facts": [{{"statement": ..., "shown": true or false, "why": a few words}}], "defects": [anything drawn wrongly or impossible to read]}}.

Statements:
{facts}"""


def parse(text):
    start, end = text.find('{'), text.rfind('}')
    return json.loads(text[start:end + 1], strict=False)


def cost(model, u):
    i, o, c = PRICES[model]
    return (u.get('input_tokens', 0) * i + u.get('cache_creation_input_tokens', 0) * i * 1.25 + u.get('cache_read_input_tokens', 0) * c + u.get('output_tokens', 0) * o) / 1e6


class Ledger:
    """Every call this question has cost."""

    def __init__(self):
        self.calls = []

    def ask(self, stage, conn, *, system, prompt, images=(), max_tokens=48000):
        t0 = time.time()
        key = os.environ['ANTHROPIC_API_KEY']
        raw, text, truncated = json_call(conn, key, system=system, prompt=prompt, images=list(images), max_tokens=max_tokens, label=stage)
        u = raw['usage']
        self.calls.append({'stage': stage, 'model': conn['model'], 'input': u.get('input_tokens', 0), 'output': u.get('output_tokens', 0),
                           'cost': round(cost(conn['model'], u), 5), 'seconds': round(time.time() - t0, 1), 'truncated': truncated})
        return text

    def total(self):
        return round(sum(c['cost'] for c in self.calls), 4)


def fill(value, params):
    """[[name]] filled from params; a figure field that is only [[name]] becomes the number."""
    if isinstance(value, dict):
        return {k: fill(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, params) for v in value]
    if isinstance(value, str):
        whole = re.fullmatch(r'\[\[(\w+)\]\]', value)
        if whole and whole.group(1) in params:
            return params[whole.group(1)]
        return re.sub(r'\[\[(\w+)\]\]', lambda m: f'{params[m.group(1)]:g}' if m.group(1) in params else m.group(0), value)
    return value


RUNNER = r"""
import json, sys
import sympy
spec = json.load(open(sys.argv[1]))
ns = {}
exec(spec['python'], ns)
out = {}
for tag, P in (('params', spec['params']), ('params_alt', spec['params_alt'])):
    r = {'correct': float(ns['correct'](dict(P)))}
    r['wrong'] = {k: float(v) for k, v in ns['wrong'](dict(P)).items()}
    r['checks'] = {k: bool(v) for k, v in ns['checks'](dict(P)).items()}
    r['options'] = {k: float(sympy.sympify(str(o['expr'])).subs(P).evalf()) for k, o in spec['options'].items()}
    out[tag] = r
print('RESULT' + json.dumps(out))
"""


def run_python(q):
    """The writer's solution, run with no network, a read-only disk and a time limit."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'spec.json').write_text(json.dumps({k: q.get(k) for k in ('python', 'params', 'params_alt', 'options')}))
        (tmp / 'run.py').write_text(RUNNER)
        cmd = ['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--ro-bind', str(tmp), str(tmp), '--unshare-net', '--unshare-pid', '--die-with-parent',
               str(REMOTION / '.venv/bin/python'), '-I', str(tmp / 'run.py'), str(tmp / 'spec.json')]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env={'PATH': '/usr/bin:/bin', 'OMP_NUM_THREADS': '2'})
        except subprocess.TimeoutExpired:
            return None, 'python: took over 120 s'
    m = re.search(r'RESULT(\{.*\})', r.stdout)
    if r.returncode or not m:
        return None, 'python failed: ' + r.stderr.strip()[-600:]
    return json.loads(m.group(1)), None


def near(a, b, tol=TOLERANCE):
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-12)


def code_errors(q, concepts):
    """What code refuses in a draft, in words the writer can fix. Returns (errors, numbers)."""
    e = []
    for f in ('stem', 'unwrap', 'decoy', 'params', 'params_alt', 'options', 'key', 'mistakes', 'python', 'concepts'):
        if not q.get(f):
            e.append(f'{f} is missing')
    if e:
        return e, None
    used = q['concepts']
    if len(used) < 3:
        e.append(f'concepts: {len(used)} named, at least 3 are needed')
    unknown = [c.get('name') for c in used if c.get('name') not in concepts]
    if unknown:
        e.append(f'concepts not on the list: {unknown}')
    if set(q['options']) != set('ABCD') or q['key'] not in 'ABCD':
        return e + ['options are A, B, C, D and key is one of them'], None
    if set(q['params']) != set(q['params_alt']):
        e.append('params and params_alt must have the same names')
    if re.search(r'\]\]\s*[/*×]|[/*×]\s*\[\[', q['stem']):
        e.append('stem does arithmetic on a [[name]]: give that value its own param, or keep it a symbol')
    missing = set(re.findall(r'\[\[(\w+)\]\]', q['stem'])) - set(q['params'])
    if missing:
        e.append(f'stem uses [[{sorted(missing)}]] with no params')
    if set(q['mistakes']) != set('ABCD') - {q['key']}:
        e.append('mistakes needs one entry for each wrong option')
    if e:
        return e, None
    numbers, err = run_python(q)
    if err:
        return [err], None
    symbolic = any(not re.fullmatch(r'[-+0-9.eE ]+', str(o['expr'])) for o in q['options'].values())
    for tag in ('params', 'params_alt') if symbolic else ('params',):
        r = numbers[tag]
        where = 'at params' if tag == 'params' else 'at params_alt'
        if not near(r['correct'], r['options'][q['key']]):
            e.append(f"key {q['key']} {where}: its expr gives {r['options'][q['key']]:.6g} but correct(P) gives {r['correct']:.6g}")
        for k in set('ABCD') - {q['key']}:
            if k not in r['wrong']:
                e.append(f'wrong(P) has no {k}')
            elif not near(r['wrong'][k], r['options'][k]):
                e.append(f"option {k} {where}: its expr gives {r['options'][k]:.6g} but the mistake computed in wrong(P) gives {r['wrong'][k]:.6g}")
        for name, ok in r['checks'].items():
            if not ok:
                e.append(f'check {name} is false {where}: the setup is not possible as written')
    if not numbers['params']['checks']:
        e.append('checks(P) tests nothing: test the assumptions the question relies on')
    vals = numbers['params']['options']
    letters = sorted(vals)
    for i, a in enumerate(letters):
        for b in letters[i + 1:]:
            if near(vals[a], vals[b], 0.03):
                e.append(f'options {a} and {b} are within 3% at params: make them distinct')
    right = vals[q['key']]
    for k, v in vals.items():
        if k != q['key'] and right and not (1 / 3 <= v / right <= 3):
            e.append(f'option {k} is {v / right:.2f} times the answer: too far off to tempt anyone')
    return e, numbers


def figure_errors(q, folder):
    """Draws the figure; returns errors, leaving figure.svg and figure.png when it is clean."""
    if not q.get('figure_needed'):
        return []
    if not q.get('figure'):
        return ['figure_needed is true but figure is empty']
    try:
        svg, errors = qfigure.render(fill(json.loads(json.dumps(q['figure'])), q.get('params') or {}))
    except Exception as exc:     # a malformed spec goes back to the writer rather than stopping the pilot
        return [f'figure: {type(exc).__name__}: {exc}']
    if errors:
        return errors
    (folder / 'figure.svg').write_text(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(folder / 'figure.png'))
    return []


def bank_questions():
    out = []
    for f in sorted(BANK.glob('*.json')):
        out += [q for q in json.loads(f.read_text()) if q.get('subject') == 'physics']
    return out


def words(text):
    return re.findall(r'[a-z]{3,}', text.lower())


def closest_in_bank(stem, bank):
    """How close the stem's wording is to any past question: a guard against a reskin, not a judge of originality."""
    mine = words(stem)
    best, who = 0.0, None
    for q in bank:
        r = difflib.SequenceMatcher(None, mine, words(q.get('text', '')), autojunk=False).ratio()
        if r > best:
            best, who = r, q['id']
    return round(best, 3), who


def judge_open(answer, q, numbers):
    import sympy
    try:
        v = float(sympy.sympify(str(answer)).subs(q['params']).evalf())
    except Exception:
        return None
    return v


def verdict(open_right, open_values, mcq_right, mcq_choices, q):
    """Reads the solves. The middle row is what we want; the last two need a person, because a broken question and a hard one look alike."""
    wrong_on_planned = [c for c in mcq_choices if c != q['key'] and c in q['options']]
    if open_right == OPEN_TRIES and mcq_right == MCQ_TRIES:
        return 'solved_every_time'
    if open_right or mcq_right:
        return 'accepted_decoys_bite' if wrong_on_planned else 'accepted'
    agreed = [v for v in open_values if v is not None]
    if len(agreed) >= 2 and all(near(agreed[0], v, 0.02) for v in agreed):
        return 'review_solver_disagrees_with_key'
    return 'review_hard_or_broken'


def make(n, brief, run_dir, concepts, style, bank):
    folder = run_dir / f'q{n:02d}'
    folder.mkdir(parents=True, exist_ok=True)
    done = folder / 'question.json'
    if done.exists():
        return json.loads(done.read_text())
    ledger = Ledger()
    result = {'n': n, 'brief': brief, 'status': None}
    listing = '\n'.join(f"- {c}: {CHAPTERS[chap]}" for chap, names in concepts.items() for c in names)
    need = ' and '.join(sorted({f'{b} ({CHAPTERS[b]})' for b in brief}))
    prompt = f'Concepts you may use (name: chapter):\n{listing}\n\nFor this question, draw at least one concept from {need}.\n\nThree real JEE Advanced questions, for style only; never reuse their settings:\n{style}'
    allowed = {c for names in concepts.values() for c in names}
    q, feedback = None, ''
    for round_no in range(REPAIRS + 1):
        try:
            text = ledger.ask(f'write-{round_no}', WRITER, system=SYSTEM, prompt=prompt + feedback)
            q = parse(text)
        except ValueError as exc:
            feedback = f'\n\nYour last reply was not valid JSON ({exc}). Write the whole object again.'
            result['errors'] = [str(exc)]
            continue
        errors, numbers = code_errors(q, allowed)
        if not errors:
            errors = figure_errors(q, folder)
        if not errors and q.get('figure_needed') and q.get('figure_facts'):
            # a figure that doesn't show what it must goes back to the writer, once code has passed everything else
            facts = '\n'.join(f'- {f}' for f in q['figure_facts'])
            read = parse(ledger.ask(f'read-figure-{round_no}', SOLVER, system='You check figures in physics questions.', prompt=READ_FIGURE.format(facts=facts), images=[folder / 'figure.png'], max_tokens=12000))
            result['figure_read'] = read
            faults = [f"the figure does not show: {f.get('statement')} ({f.get('why')})" for f in read.get('facts', []) if not f.get('shown')] + [f'figure defect: {d}' for d in read.get('defects', [])]
            result['figure_flag'] = bool(faults)
            if round_no < REPAIRS:
                errors = faults
        result['errors'], result['rounds'] = errors, round_no + 1
        result.setdefault('refusals', []).append(errors)
        if not errors:
            break
        feedback = '\n\nCode refused your last draft:\n' + '\n'.join(f'- {x}' for x in errors) + '\n\nYour last draft:\n' + json.dumps(q, ensure_ascii=False) + '\n\nFix these and write the whole object again. If the physics was wrong, change the question rather than the check.'
    result['question'] = q
    if q is None or result['errors']:
        result['status'] = 'rejected_missing_parts' if q and q.get('missing_parts') else 'rejected_by_code'
        return finish(done, result, ledger)
    result['numbers'] = numbers
    result['closest_in_bank'] = closest_in_bank(q['stem'], bank)
    if result['closest_in_bank'][0] > 0.6:
        result['status'] = 'rejected_too_close_to_bank'
        return finish(done, result, ledger)
    images = [folder / 'figure.png'] if q.get('figure_needed') else []
    stem = fill(q['stem'], q['params'])
    solver_system = 'You are an expert physics student sitting JEE Advanced.'
    names = ', using these names for any symbols: ' + ', '.join(sorted(q['params']))
    opens, values, right = [], [], 0
    for i in range(OPEN_TRIES):
        a = parse(ledger.ask(f'open-{i}', SOLVER, system=solver_system, prompt=OPEN_SOLVE.format(stem=stem, names=names), images=images, max_tokens=24000))
        v = judge_open(a.get('answer'), q, numbers)
        ok = v is not None and near(v, numbers['params']['correct'])
        right += ok
        opens.append({'answer': a.get('answer'), 'value': v, 'right': ok, 'working': a.get('working')})
        values.append(v)
    rng = random.Random(n)
    mcqs, mright = [], 0
    for i in range(MCQ_TRIES):
        letters = list('ABCD')
        rng.shuffle(letters)
        shown = dict(zip('ABCD', letters))     # printed letter -> writer's letter
        text = '\n'.join(f"({p}) {fill(q['options'][w]['text'], q['params'])}" for p, w in shown.items())
        a = parse(ledger.ask(f'mcq-{i}', SOLVER, system=solver_system, prompt=MCQ_SOLVE.format(stem=stem, options=text), images=images, max_tokens=24000))
        chosen = shown.get(str(a.get('choice', '')).strip()[:1])
        mright += chosen == q['key']
        mcqs.append({'choice': chosen, 'right': chosen == q['key'], 'working': a.get('working')})
    result['open'], result['mcq'] = opens, mcqs
    result['open_right'], result['mcq_right'] = right, mright
    result['status'] = verdict(right, values, mright, [m['choice'] for m in mcqs], q)
    return finish(done, result, ledger)


def finish(done, result, ledger):
    result['calls'], result['cost'] = ledger.calls, ledger.total()
    done.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"q{result['n']:02d} {result['status']} ${result['cost']:.2f}", flush=True)
    return result


CHAPTERS = {}


def load_concepts():
    out = {}
    for c in MECHANICS:
        d = json.loads((DIGESTS / c / 'digest.json').read_text())
        title = (d.get('source') or {}).get('title') or (d.get('outline') or {}).get('title') or c
        CHAPTERS[c] = title if isinstance(title, str) else c
        out[c] = [x['name'] for x in d['concepts'] if x.get('filmable', True) and not re.search(r'^(Summary|Introduction to)', x['name'])]
    return out


def main(argv):
    run = argv[0]
    first, last = (int(argv[1]), int(argv[2])) if len(argv) > 2 else (1, len(BRIEFS))
    run_dir = OUT / run
    run_dir.mkdir(parents=True, exist_ok=True)
    concepts = load_concepts()
    bank = bank_questions()
    by_id = {q['id']: q for q in bank}
    style = '\n\n'.join(re.sub(r'[ \t]+', ' ', by_id[i]['text']).strip() for i in STYLE if i in by_id)
    for n in range(first, last + 1):
        make(n, BRIEFS[n - 1], run_dir, concepts, style, bank)
    results = [json.loads(f.read_text()) for f in sorted(run_dir.glob('q*/question.json'))]
    print('pilot-finished', len(results), 'questions', f"${sum(r['cost'] for r in results):.2f}", flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
