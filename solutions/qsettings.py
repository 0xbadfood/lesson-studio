"""Settings bank pilot: free models imagine mechanisms for questions, Sonnet keeps the sound and distinct ones.

Free models are chosen for different ways of thinking, not for accuracy (user, 2026-10-31), and are trusted with nothing:
what they receive is the generic instruction below and a seed, never a question, a key or a digest. Only Sonnet sees our
concept names. Usage: python solutions/qsettings.py generate|filter <run>
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REMOTION = Path('/home/nitin/remotion')
for p in (str(REMOTION), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import httpx  # noqa: E402
from infofilm.llm_settings import api_key  # noqa: E402
import qcreate  # noqa: E402
import qfigure  # noqa: E402

OUT = ROOT / 'questions-data' / 'settings'
SECRETS = REMOTION / 'artifacts' / 'interface'
MODELS = ['thinkingmachines/inkling:free', 'nvidia/nemotron-3-ultra-550b-a55b:free', 'dots-studio/dots-3-note-preview:free', 'recursive/flint-v1.0:free',
          'xingchen-agi/xing4.0-29b-a4b:free', 'poolside/laguna-s-2.1:free', 'google/gemma-4-31b-it:free', 'cohere/north-mini-code:free']
SEEDS = ['a body that can lose contact with what supports it', 'a constraint that slides inside a rotating or accelerating frame', 'a system whose mass moves or changes along the way',
         'two bodies that interact only for part of the motion', 'something released from a position that looks like equilibrium but is not', 'a rolling or spinning body meeting a surface or another body',
         'a support that is itself free to move or recoil', 'a flexible connector: a string, chain or rope that can go slack or wrap around something',
         'a collision or sudden event inside a larger motion', 'motion on or inside something curved that is itself moving', 'a rigid body pivoted or hinged in an unusual place', 'gravity that varies, or a body far from the ground']
CALLS_PER_MODEL = 4
PER_CALL = 12

ASK = """Imagine original physical mechanisms for hard school-level mechanics problems. A mechanism is an idealised arrangement of a few simple bodies (blocks, wedges, rods, discs, rings, beads, springs, strings, pulleys, tracks, tubes), not a story or a real-world scenario. Be unusual: avoid the standard textbook arrangements. Each must be physically possible and simple enough to sketch.

Theme for this batch: {seed}.

Return only a JSON object: {{"mechanisms": [{{"bodies": "what is there", "constraints": "how they are connected, guided or supported", "free": "what can move, and what starts the motion", "interesting": "what is not obvious about how it behaves"}}]}} with {n} different mechanisms. No numbers and no questions."""

FILTER = """Below are mechanisms for hard mechanics questions, proposed by weak and inconsistent models. Judge each as a strict physics examiner would. Return one JSON object and nothing else:
{{"verdicts": [{{"id": its id, "keep": true or false, "why_not": for a discard, one of "absurd", "impossible", "vague", "textbook", "too complex to sketch", "no real physics", "story not mechanism", "signature": for a keep, a few lowercase words naming the underlying physics rather than the look, such as "bead sliding in rotating guide, angular momentum exchange", "concepts": for a keep, 3 or more concept names from the list that the mechanism could really need, "drawable": for a keep, true if the figure kit below can draw it, "missing_parts": for a keep, parts the kit lacks}}]}}
Keep only a mechanism that could carry a real JEE Advanced question. Most should go.

Concepts:
{concepts}

Figure kit:
{kit}

Mechanisms:
{items}"""

DEDUPE = """These are mechanisms kept for hard mechanics questions, each with a signature naming its underlying physics. Two count as the same if a student would use the same principles at the same key step, however different they look. Group them, and choose the best of each group. Return one JSON object and nothing else: {{"groups": [{{"best": id, "others": [ids of the same physics], "signature": the shared physics in a few words}}]}}. Every id appears exactly once.

{items}"""


def key():
    for cid, c in json.loads((SECRETS / 'llm-settings.json').read_text())['connections'].items():
        if c.get('type') == 'openrouter':
            found = api_key(SECRETS, cid, c)
            if found:
                return found
    raise SystemExit('no OpenRouter key saved')


def ask_free(model, seed, secret):
    """One batch from one free model. These fail often and that is fine: a failure loses a batch, not the run."""
    body = {'model': model, 'max_tokens': 6000, 'messages': [{'role': 'user', 'content': ASK.format(seed=seed, n=PER_CALL)}]}
    for attempt in range(3):
        t0 = time.time()
        try:
            r = httpx.post('https://openrouter.ai/api/v1/chat/completions', headers={'Authorization': f'Bearer {secret}'}, json=body, timeout=300)
            if r.status_code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            r.raise_for_status()
            text = r.json()['choices'][0]['message'].get('content') or ''
            items = qcreate.parse(text, 'mechanisms')['mechanisms']
            return {'model': model, 'seed': seed, 'seconds': round(time.time() - t0, 1), 'items': [i for i in items if isinstance(i, dict) and i.get('bodies')]}
        except Exception as exc:
            error = f'{type(exc).__name__}'     # never the message: an HTTP error can carry the request's header
            time.sleep(5)
    return {'model': model, 'seed': seed, 'error': locals().get('error', 'rate limited'), 'items': []}


def generate(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    secret, rng, jobs = key(), random.Random(1), []
    for model in MODELS:
        jobs += [(model, s) for s in rng.sample(SEEDS, CALLS_PER_MODEL)]
    with ThreadPoolExecutor(8) as pool:
        batches = list(pool.map(lambda j: ask_free(*j, secret), jobs))
    bank, n = [], 0
    for b in batches:
        for item in b['items']:
            n += 1
            bank.append({'id': f'm{n:04d}', 'model': b['model'], 'seed': b['seed'], **{k: str(item.get(k, ''))[:600] for k in ('bodies', 'constraints', 'free', 'interesting')}})
    (run_dir / 'raw.json').write_text(json.dumps(bank, ensure_ascii=False, indent=1))
    (run_dir / 'batches.json').write_text(json.dumps([{k: v for k, v in b.items() if k != 'items'} | {'n': len(b['items'])} for b in batches], indent=1))
    print('generated', len(bank), 'from', len({b['model'] for b in bank}), 'models;', sum(1 for b in batches if b.get('error')), 'batches failed', flush=True)


def filter_bank(run_dir):
    bank, ledger = json.loads((run_dir / 'raw.json').read_text()), qcreate.Ledger()
    names = sorted({c for names in qcreate.load_concepts().values() for c in names})
    verdicts, size = {}, 50
    for i in range(0, len(bank), size):
        chunk = [{k: m[k] for k in ('id', 'bodies', 'constraints', 'free', 'interesting')} for m in bank[i:i + size]]
        text = ledger.ask(f'filter-{i}', qcreate.SOLVER, system='You are a strict examiner of JEE Advanced physics.', prompt=FILTER.format(concepts='\n'.join(names), kit=qfigure.KIT, items=json.dumps(chunk, ensure_ascii=False)), max_tokens=32000)
        verdicts.update({v['id']: v for v in qcreate.parse(text, 'verdicts')['verdicts'] if v.get('id')})
    kept = [{**m, **verdicts[m['id']]} for m in bank if verdicts.get(m['id'], {}).get('keep')]
    groups = []
    if kept:
        items = json.dumps([{'id': m['id'], 'signature': m.get('signature'), 'bodies': m['bodies'], 'constraints': m['constraints']} for m in kept], ensure_ascii=False)
        groups = qcreate.parse(ledger.ask('dedupe', qcreate.SOLVER, system='You are a strict examiner of JEE Advanced physics.', prompt=DEDUPE.format(items=items), max_tokens=32000), 'groups')['groups']
    by_id = {m['id']: m for m in kept}
    final = [{**by_id[g['best']], 'same_physics': g.get('others', []), 'signature': g.get('signature')} for g in groups if g.get('best') in by_id]
    (run_dir / 'verdicts.json').write_text(json.dumps(verdicts, ensure_ascii=False, indent=1))
    (run_dir / 'bank.json').write_text(json.dumps(final, ensure_ascii=False, indent=1))
    print('kept', len(kept), 'distinct', len(final), f'of {len(bank)}, ${ledger.total():.2f}', flush=True)


if __name__ == '__main__':
    {'generate': generate, 'filter': filter_bank}[sys.argv[1]](OUT / sys.argv[2])
