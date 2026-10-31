"""Question creation pilot: Opus writes a JEE-style question, code checks it, Sonnet tries it blind.

The method is unwrapping in reverse (user, 2026-10-23): at least three concepts packed into one setting, with a decoy,
and wrong options that are the mistakes students really make. Code proves the key and every wrong option from one set
of values; Sonnet's solves are a test of the question, not a pass mark, because a hard question and a broken one look
alike to a student. Sonnet checks the key once, Fable settles a disagreement, Haiku's tries are a gauge. Every call's tokens and cost are kept against the question, rejected or not.

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
ARBITER = {'model': 'claude-fable-5-1', 'reasoning_effort': 'high', 'timeout': 1200}
GAUGE = {'model': 'claude-haiku-5-5', 'reasoning_effort': 'high', 'timeout': 900}
PRICES = {'claude-opus-5-5': (4.0, 20.0, 0.20), 'claude-sonnet-5-5': (2.0, 10.0, 0.20), 'claude-haiku-5-5': (0.10, 0.50, 0.01), 'claude-fable-5-1': (10.0, 50.0, 0.25)}    # $ per MTok: input, output, cache read
MECHANICS = ['keph1-02', 'keph1-03', 'keph1-04', 'keph1-05', 'keph1-06', 'keph1-07']
REPAIRS = 3         # further writer rounds when code refuses a draft
OPEN_TRIES, MCQ_TRIES = 3, 3    # the Haiku gauge's tries
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
READ_FIGURE = """Here is a figure from a physics question. Using only what the figure shows, judge each statement. Return one JSON object and nothing else: {{"facts": [{{"statement": ..., "shown": true or false, "why": a few words}}], "defects": [only what would mislead a student or make the question unanswerable; leave out matters of neatness, and don't ask for units or words the question's text can carry]}}.

Statements:
{facts}"""


def parse(text, need=None):
    """The JSON object in a reply: the last one that decodes (and has `need`), so words or a stray brace before it do no harm."""
    dec, found, i = json.JSONDecoder(strict=False), [], 0
    while (i := text.find('{', i)) != -1:
        try:
            value, end = dec.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        found.append(value)
        i = end
    found = [v for v in found if isinstance(v, dict) and (need is None or need in v)]
    if not found:
        raise ValueError('no JSON object in the reply')
    return found[-1]


def salvage(text, need):
    """The named field from JSON a stray LaTeX backslash has broken (Gemma on Q3: \\frac made a right answer unreadable)."""
    m = list(re.finditer(rf'"{need}"\s*:\s*"((?:[^"\\]|\\.)*)"', text)) or list(re.finditer(rf'"{need}"\s*:\s*(-?[\d.]+(?:[eE][-+]?\d+)?)', text))
    return m[-1].group(1) if m else None


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


def settle(sonnet, fable, key):
    """accepted: Sonnet reached the key. accepted_hard: only Fable did. Otherwise discarded: both differ from the key the same way (the key is probably wrong) or each its own way (probably unclear)."""
    same = lambda a, b: a is not None and b is not None and near(a, b)
    if same(sonnet, key):
        return 'accepted'
    if same(fable, key):
        return 'accepted_hard'
    return 'discarded_key_disputed' if same(sonnet, fable) else 'discarded_unclear'


def solve_call(ledger, stage, need, prompt, images, conn=SOLVER):
    """One blind solve. A reply with no readable answer is an attempt with no answer, not the end of the run."""
    text = ledger.ask(stage, conn, system='You are an expert physics student sitting JEE Advanced.', prompt=prompt, images=images, max_tokens=24000)
    try:
        return parse(text, need)
    except ValueError:
        return {'working': text[-1500:]}


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
    q, feedback, best = None, '', None
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
            facts = '\n'.join(f"- {fill(f, q['params'])}" for f in q['figure_facts'])
            read = parse(ledger.ask(f'read-figure-{round_no}', SOLVER, system='You check figures in physics questions.', prompt=READ_FIGURE.format(facts=facts), images=[folder / 'figure.png'], max_tokens=12000))
            result['figure_read'] = read
            faults = [f"the figure does not show: {f.get('statement')} ({f.get('why')})" for f in read.get('facts', []) if not f.get('shown')] + [f'figure defect: {d}' for d in read.get('defects', [])]
            result['figure_flag'] = bool(faults)
            if faults and not best:     # one figure repair; the draft is kept, so a slip in the repair can't lose a sound question
                best = (q, numbers)
                errors = faults
        result['errors'], result['rounds'] = errors, round_no + 1
        result.setdefault('refusals', []).append(errors)
        if not errors:
            break
        feedback = '\n\nCode refused your last draft:\n' + '\n'.join(f'- {x}' for x in errors) + '\n\nYour last draft:\n' + json.dumps(q, ensure_ascii=False) + '\n\nFix these and write the whole object again. If the physics was wrong, change the question rather than the check.'
    if best and result.get('errors'):
        q, numbers = best
        result['errors'], result['figure_flag'] = [], True
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
    names = ', using these names for any symbols: ' + ', '.join(sorted(q['params']))
    # Verification (user, 2026-10-31): one blind Sonnet solve; Fable, also blind and told nothing of the dispute, only when Sonnet differs from the key.
    # In production nobody is there to judge, so what can't be confirmed is discarded, never shipped.
    prompt = OPEN_SOLVE.format(stem=stem, names=names)
    a = solve_call(ledger, 'verify', 'answer', prompt, images)
    v = judge_open(a.get('answer'), q, numbers)
    result['open'] = [{'answer': a.get('answer'), 'value': v, 'right': v is not None and near(v, numbers['params']['correct']), 'working': a.get('working')}]
    result['open_right'] = int(result['open'][0]['right'])
    fable = None
    if not result['open_right']:
        f = solve_call(ledger, 'arbiter', 'answer', prompt, images, ARBITER)
        fable = judge_open(f.get('answer'), q, numbers)
        result['fable'] = {'answer': f.get('answer'), 'value': fable, 'working': f.get('working')}
    result['status'] = settle(v, fable, numbers['params']['correct'])
    if result.get('fable'):
        result['fable']['outcome'] = result['status']
    return finish(done, result, ledger)


def gauge(run_dir):
    """Haiku tries every question that passed, the same blind way: a weaker solver, as a pointer to how hard each one is. It decides nothing."""
    for f in sorted(run_dir.glob('q*/question.json')):
        r = json.loads(f.read_text())
        if not str(r.get('status')).startswith(('accepted', 'solved')) or 'haiku' in r:
            continue
        q, ledger = r['question'], Ledger()
        images = [f.parent / 'figure.png'] if q.get('figure_needed') else []
        stem = fill(q['stem'], q['params'])
        names = ', using these names for any symbols: ' + ', '.join(sorted(q['params']))
        opens, mcqs, rng = [], [], random.Random(r['n'] + 1000)
        for i in range(OPEN_TRIES):
            a = solve_call(ledger, f'haiku-open-{i}', 'answer', OPEN_SOLVE.format(stem=stem, names=names), images, GAUGE)
            v = judge_open(a.get('answer'), q, r['numbers'])
            opens.append({'answer': a.get('answer'), 'value': v, 'right': v is not None and near(v, r['numbers']['params']['correct'])})
        for i in range(MCQ_TRIES):
            letters = list('ABCD')
            rng.shuffle(letters)
            shown = dict(zip('ABCD', letters))
            text = '\n'.join(f"({p}) {fill(q['options'][w]['text'], q['params'])}" for p, w in shown.items())
            a = solve_call(ledger, f'haiku-mcq-{i}', 'choice', MCQ_SOLVE.format(stem=stem, options=text), images, GAUGE)
            chosen = shown.get(str(a.get('choice', '')).strip()[:1])
            mcqs.append({'choice': chosen, 'right': chosen == q['key']})
        r['haiku'] = {'open': opens, 'mcq': mcqs, 'open_right': sum(o['right'] for o in opens), 'mcq_right': sum(m['right'] for m in mcqs), 'cost': ledger.total()}
        r['calls'] += ledger.calls
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"q{r['n']:02d} haiku open {r['haiku']['open_right']}/{OPEN_TRIES} mcq {r['haiku']['mcq_right']}/{MCQ_TRIES} picks {[m['choice'] for m in mcqs]} key {q['key']} ${ledger.total():.3f}", flush=True)
    print('gauge-finished', flush=True)


QWEN = {'url': 'http://10.8.0.5:8001/v1', 'model': 'Qwen3.8-27B-Q4_K_M.gguf', 'timeout': 900}
GEMMA = {'url': 'http://10.8.0.5:8001/v1', 'model': 'gemma4-12b-it-mtp', 'timeout': 2400, 'temperature': 0.7, 'workers': 4, 'limit': 30000}     # 12B needs the room: about 32,000 tokens of context a slot
E4B = {**GEMMA, 'url': 'http://10.8.0.5:8002/v1', 'model': 'gemma4-e4b', 'timeout': 900, 'limit': 16000}
LOCAL = {'qwen': QWEN, 'gemma': GEMMA, 'e4b': E4B}
LOCAL_LIMIT = 16000     # tokens, thinking included; an attempt that reaches it is unfinished, not wrong


def qwen_call(prompt, images, conn=QWEN):
    """One answer from a local model. Returns (text, seconds, completion tokens)."""
    import base64
    import httpx
    content = [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(Path(p).read_bytes()).decode()}} for p in images]
    t0 = time.time()
    headers = {'Authorization': f"Bearer {os.environ['VLLM_API_KEY']}"} if os.environ.get('VLLM_API_KEY') else {}
    r = httpx.post(conn['url'] + '/chat/completions', headers=headers, timeout=conn['timeout'], json={
        'model': conn['model'], 'max_tokens': conn.get('limit', LOCAL_LIMIT), **({'temperature': conn['temperature']} if 'temperature' in conn else {}), 'messages': [
            {'role': 'system', 'content': 'You are an expert physics student sitting JEE Advanced.'},
            {'role': 'user', 'content': content + [{'type': 'text', 'text': prompt}]}]})
    r.raise_for_status()
    body = r.json()
    return body['choices'][0]['message'].get('content') or '', round(time.time() - t0, 1), (body.get('usage') or {}).get('completion_tokens')


def local_gauge(run_dir, name, first=1, last=99):
    """A local model tries each accepted question the blind way, as a gauge that Claude models were too strong to be (user, 2026-10-31)."""
    from concurrent.futures import ThreadPoolExecutor
    conn = LOCAL[name]
    pool = ThreadPoolExecutor(conn.get('workers', 1))
    for f in sorted(run_dir.glob('q*/question.json')):
        r = json.loads(f.read_text())
        if not first <= r['n'] <= last or not str(r.get('status')).startswith(('accepted', 'solved')) or name in r:
            continue
        q = r['question']
        images = [f.parent / 'figure.png'] if q.get('figure_needed') else []
        stem = fill(q['stem'], q['params'])
        names = ', using these names for any symbols: ' + ', '.join(sorted(q['params']))
        rng = random.Random(r['n'] + 2000)

        def ask(prompt, need):
            try:
                text, seconds, tokens = qwen_call(prompt, images, conn)
            except Exception as exc:     # a busy or slow server costs this attempt, not the run
                return {}, {'error': f'{type(exc).__name__}: {exc}'[:200]}
            info = {'seconds': seconds, 'tokens': tokens, 'unfinished': (tokens or 0) >= LOCAL_LIMIT}
            try:
                return parse(text, need), info
            except ValueError:
                found = salvage(text, need)
                return ({need: found}, info) if found else ({}, {**info, 'unread': text[-400:]})
        t0 = time.time()
        open_jobs = [pool.submit(ask, OPEN_SOLVE.format(stem=stem, names=names), 'answer') for _ in range(OPEN_TRIES)]
        maps, mcq_jobs = [], []
        for _ in range(MCQ_TRIES):
            letters = list('ABCD')
            rng.shuffle(letters)
            shown = dict(zip('ABCD', letters))
            text = '\n'.join(f"({p}) {fill(q['options'][w]['text'], q['params'])}" for p, w in shown.items())
            maps.append(shown)
            mcq_jobs.append(pool.submit(ask, MCQ_SOLVE.format(stem=stem, options=text), 'choice'))
        opens, mcqs = [], []
        for job in open_jobs:
            a, info = job.result()
            v = judge_open(a.get('answer'), q, r['numbers'])
            opens.append({'answer': a.get('answer'), 'value': v, 'right': v is not None and near(v, r['numbers']['params']['correct']), **info})
        for job, shown in zip(mcq_jobs, maps):
            a, info = job.result()
            chosen = shown.get(str(a.get('choice', '')).strip()[:1])
            mcqs.append({'choice': chosen, 'right': chosen == q['key'], **info})
        r[name] = {'open': opens, 'mcq': mcqs, 'open_right': sum(o['right'] for o in opens), 'mcq_right': sum(m['right'] for m in mcqs)}
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"q{r['n']:02d} {name} open {r[name]['open_right']}/{OPEN_TRIES} {[o['value'] for o in opens]} key {r['numbers']['params']['correct']:.6g} mcq {r[name]['mcq_right']}/{MCQ_TRIES} picks {[m['choice'] for m in mcqs]} key {q['key']} tokens {[x.get('tokens') for x in opens + mcqs]} {time.time() - t0:.0f}s", flush=True)
    print(f'{name}-finished', flush=True)


STEPS = """Solve this physics question as you would in an examination, showing all your working. Name each principle you use and why it applies here, write each equation, and carry the algebra through to the result. Then return one JSON object and nothing else: {{"steps": ["step one", "step two", ...], "answer": the final answer{extra}}}. Write mathematics in plain text, not LaTeX.

{stem}{options}"""
GRADE = """A student attempted this physics question. Find where the attempt went right or wrong by reading its steps, not only its answer. Return one JSON object and nothing else:
{{"verdict": one of "correct" (right method, right result), "right_method_slip" (right principles, an algebra, arithmetic or copying slip), "fell_for_decoy" (followed the tempting route or one of the planned mistakes below), "wrong_principle" (used a principle that doesn't apply, not one of the planned mistakes), "missing_concept" (never used a concept the question needs), "misread" (misread the setup or figure), "guessing" (the steps don't lead to the answer given, or are empty or circular), "lucky" (the right answer from wrong working),
"first_wrong_step": the step's number, or null, "planned_mistake": the option letter of the planned mistake it matches, or null, "concepts_missing": [concepts it never used], "why": one sentence}}

The question: {stem}
{options}
Key: {key}
What is really going on: {unwrap}
The decoy: {decoy}
Planned mistakes: {mistakes}
Concepts needed: {concepts}

The student's steps: {steps}
The student's answer: {answer}"""


def steps_test(run_dir, name, tries=3, blind_only=False):
    """Each local attempt shows its working and Sonnet grades it: is the model guessing, falling for decoys, or short of a concept? (user, 2026-10-31)"""
    from concurrent.futures import ThreadPoolExecutor
    conn = LOCAL[name]
    pool, key = ThreadPoolExecutor(conn.get('workers', 1)), f'{name}_steps'
    for f in sorted(run_dir.glob('q*/question.json')):
        r = json.loads(f.read_text())
        if not str(r.get('status')).startswith(('accepted', 'solved')) or key in r:
            continue
        q, ledger, rng = r['question'], Ledger(), random.Random(r['n'] + 3000)
        images = [f.parent / 'figure.png'] if q.get('figure_needed') else []
        stem = fill(q['stem'], q['params'])
        all_options = '\n'.join(f"({k}) {fill(v['text'], q['params'])}" for k, v in q['options'].items())

        def attempt(prompt):
            try:
                text, seconds, tokens = qwen_call(prompt, images, conn)
            except Exception as exc:
                return {'error': f'{type(exc).__name__}: {exc}'[:200]}
            info = {'seconds': seconds, 'tokens': tokens, 'unfinished': (tokens or 0) >= conn.get('limit', LOCAL_LIMIT)}
            try:
                return {**parse(text, 'answer'), **info}
            except ValueError:
                return {'steps': text[-6000:], 'answer': salvage(text, 'answer'), **info}
        jobs, maps = [], []
        for mode in ['open'] * tries + ['mcq'] * (0 if blind_only else tries):
            shown = None
            extra, options = ' as one sympy expression or number', ''
            if mode == 'mcq':
                letters = list('ABCD')
                rng.shuffle(letters)
                shown = dict(zip('ABCD', letters))
                extra = ': the letter A, B, C or D'
                options = '\n\nOptions (exactly one is correct):\n' + '\n'.join(f"({p}) {fill(q['options'][w]['text'], q['params'])}" for p, w in shown.items())
            maps.append((mode, shown))
            jobs.append(pool.submit(attempt, STEPS.format(stem=stem, options=options, extra=extra)))
        out = []
        for job, (mode, shown) in zip(jobs, maps):
            a = job.result()
            given = a.get('answer')
            if mode == 'mcq':     # a letter is put back as the writer's letter, and the option's text, so the grader reads it plainly
                letter = (shown or {}).get(str(given or '').strip().strip('()')[:1])
                a['choice'], a['right'] = letter, letter == q['key']
                given = f"{letter}: {fill(q['options'][letter]['text'], q['params'])}" if letter else given
            else:
                v = judge_open(given, q, r['numbers'])
                a['value'], a['right'] = v, v is not None and near(v, r['numbers']['params']['correct'])
            grade = {'verdict': 'no_working'}
            if a.get('steps'):
                try:
                    grade = parse(ledger.ask('grade', SOLVER, system='You mark physics examination scripts, strictly and fairly.', prompt=GRADE.format(
                        stem=stem, options=all_options, key=q['key'], unwrap=fill(q['unwrap'], q['params']), decoy=fill(q['decoy'], q['params']), mistakes=json.dumps(q['mistakes'], ensure_ascii=False),
                        concepts=', '.join(c['name'] for c in q['concepts']), steps=json.dumps(a['steps'], ensure_ascii=False)[:12000], answer=given), images=images, max_tokens=12000), 'verdict')
                except ValueError:
                    grade = {'verdict': 'ungraded'}
            out.append({'mode': mode, **a, 'grade': grade})
        r[key] = {'attempts': out, 'cost': ledger.total()}
        r['calls'] += ledger.calls
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"q{r['n']:02d} done ${ledger.total():.3f}", flush=True)     # results stay in the file: the user's difficulty scores are still to come
    print('steps-finished', flush=True)


JUDGE = """Two students, one weak and one stronger, attempted this physics question blind, with no options, several times each. From how they went wrong, judge how hard the question is for a well-prepared JEE Advanced aspirant. Weigh how far each got, whether the idea or only the algebra stopped them, and whether they ran out of room. Return one JSON object and nothing else: {{"difficulty": 0 to 100, "hard_part": the step or idea that stops people, "kind": "idea" or "working" or "both", "why": one or two sentences}}. The question and its key are already verified, so if neither student solves it, it is very hard.

Question: {stem}
What is really going on: {unwrap}

Weak student's attempts:
{weak}

Stronger student's attempts:
{strong}"""


def judge(run_dir, weak='e4b', strong='gemma'):
    """Difficulty from two students' blind scripts (user, 2026-10-31). Kept out of reports until the user's own 0 to 100 scores are in, to test it against them."""
    total = 0.0
    for f in sorted(run_dir.glob('q*/question.json')):
        r = json.loads(f.read_text())
        if 'judge' in r or f'{strong}_steps' not in r or f'{weak}_steps' not in r:
            continue
        q, ledger = r['question'], Ledger()

        def scripts(name):
            out = []
            for a in r[f'{name}_steps']['attempts']:
                if a['mode'] == 'open':
                    out.append(json.dumps({'grade': a['grade'].get('verdict'), 'why': a['grade'].get('why'), 'first_wrong_step': a['grade'].get('first_wrong_step'), 'tokens': a.get('tokens'), 'ran_out_of_room': a.get('unfinished'), 'answer': a.get('answer')}, ensure_ascii=False))
            return '\n'.join(out)
        r['judge'] = parse(ledger.ask('judge', WRITER, system='You have marked JEE Advanced for many years.', prompt=JUDGE.format(stem=fill(q['stem'], q['params']), unwrap=fill(q['unwrap'], q['params']), weak=scripts(weak), strong=scripts(strong)), max_tokens=16000), 'difficulty')
        r['calls'] += ledger.calls
        total += ledger.total()
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(f'judge-finished ${total:.2f}', flush=True)


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
    if argv[0] == 'judge':
        return judge(OUT / argv[1])
    if argv[0] == 'steps':
        return steps_test(OUT / argv[2], argv[1], blind_only=argv[1] == 'gemma')     # the students solve blind: options only invite guessing (user, 2026-10-31)
    if argv[0] in LOCAL:
        return local_gauge(OUT / argv[1], argv[0], *(int(x) for x in argv[2:4]))
    if argv[0] == 'gauge':
        return gauge(OUT / argv[1])
    run = argv[0]
    first, last = (int(argv[1]), int(argv[2])) if len(argv) > 2 else (1, len(BRIEFS))
    run_dir = OUT / run
    run_dir.mkdir(parents=True, exist_ok=True)
    concepts = load_concepts()
    bank = bank_questions()
    by_id = {q['id']: q for q in bank}
    style = '\n\n'.join(re.sub(r'[ \t]+', ' ', by_id[i]['text']).strip() for i in STYLE if i in by_id)
    for n in range(first, last + 1):
        try:
            make(n, BRIEFS[n - 1], run_dir, concepts, style, bank)
        except Exception as exc:     # one question's failure is a finding; the rest still run (its folder has no question.json, so a rerun retries it)
            print(f'q{n:02d} crashed {type(exc).__name__}: {exc}', flush=True)
    results = [json.loads(f.read_text()) for f in sorted(run_dir.glob('q*/question.json'))]
    print('pilot-finished', len(results), 'questions', f"${sum(r['cost'] for r in results):.2f}", flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
