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
MODELS = ['thinkingmachines/inkling:free', 'thinkingmachines/inkling-small:free', 'nvidia/nemotron-3-ultra-550b-a55b:free', 'nvidia/nemotron-3.5-super-vl:free', 'nvidia/nemotron-3.5-lightning:free',
          'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', 'dots-studio/dots-3-note-preview:free', 'recursive/flint-v1.0:free', 'xingchen-agi/xing4.0-29b-a4b:free', 'poolside/laguna-s-2.1:free',
          'poolside/laguna-xs-2.1:free', 'google/gemma-4-31b-it:free', 'google/gemma-4-26b-a4b-it:free', 'cohere/north-mini-code:free', 'liquid/lfm-2.5-2.6b:free']
SEEDS = ['a body that can lose contact with what supports it', 'a constraint that slides inside a rotating or accelerating frame', 'a system whose mass moves or changes along the way',
         'two bodies that interact only for part of the motion', 'something released from a position that looks like equilibrium but is not', 'a rolling or spinning body meeting a surface or another body',
         'a support that is itself free to move or recoil', 'a flexible connector: a string, chain or rope that can go slack or wrap around something',
         'a collision or sudden event inside a larger motion', 'motion on or inside something curved that is itself moving', 'a rigid body pivoted or hinged in an unusual place', 'gravity that varies, or a body far from the ground']
CALLS_PER_MODEL = 4
PER_CALL = 12
TRIES = 4
PAUSE = 30     # seconds between a model's batches

ASK = """Imagine original physical mechanisms for hard school-level mechanics problems. A mechanism is an idealised arrangement of a few simple bodies (blocks, wedges, rods, discs, rings, beads, springs, strings, pulleys, tracks, tubes), not a story or a real-world scenario. Be unusual: avoid the standard textbook arrangements. Each must be physically possible and simple enough to sketch.

Theme for this batch: {seed}.

Return only a JSON object: {{"mechanisms": [{{"bodies": "what is there", "constraints": "how they are connected, guided or supported", "free": "what can move, and what starts the motion", "interesting": "what is not obvious about how it behaves"}}]}} with {n} different mechanisms. No numbers and no questions."""

FILTER = """Below are mechanisms for hard mechanics questions, proposed by weak and inconsistent models. A stronger physicist will later turn a kept one into a question, and may refuse it, so an idea need not be finished: keep a rough idea if there is real, non-obvious physics in it, and say how to firm it up. Return one JSON object and nothing else:
{{"verdicts": [{{"id": its id, "keep": true or false, "why_not": for a discard, one of "absurd", "impossible", "standard textbook", "no real physics", "beyond school physics", "promise": for a keep, "strong" or "rough", "firm_up": for a rough keep, one sentence on the simplification or missing detail that would make it work, "signature": for a keep, a few lowercase words naming the underlying physics rather than the look, such as "bead sliding in rotating guide, angular momentum exchange", "concepts": for a keep, 3 or more concept names from the list that it could really need, "drawable": for a keep, true if the figure kit below can draw it once firmed up, "missing_parts": for a keep, parts the kit lacks}}]}}
Discard only what can't be saved: don't discard an idea merely for being vague or over-complicated if a simpler version has something a strong student wouldn't see at once.

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


def read_items(text):
    """Mechanisms from whatever shape a free model returned: the object asked for, a bare list, or a list inside other words."""
    try:
        return qcreate.parse(text, 'mechanisms')['mechanisms']
    except ValueError:
        pass
    found, dec, i = [], json.JSONDecoder(strict=False), 0
    while (i := text.find('{', i)) != -1:
        try:
            value, end = dec.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(value, dict) and value.get('bodies'):
            found.append(value)
        i = end
    if not found:
        raise ValueError('no mechanisms')
    return found


def ask_free(model, seed, secret):
    """One batch from one free model. These fail often and that is fine: a failure loses a batch, not the run."""
    body = {'model': model, 'max_tokens': 8000, 'messages': [{'role': 'user', 'content': ASK.format(seed=seed, n=PER_CALL)}]}
    error = 'rate limited'
    for attempt in range(TRIES):
        t0 = time.time()
        try:
            r = httpx.post('https://openrouter.ai/api/v1/chat/completions', headers={'Authorization': f'Bearer {secret}'}, json=body, timeout=420)
            if r.status_code == 429:
                error = 'rate limited'
                time.sleep(45 * (attempt + 1))
                continue
            if r.status_code != 200:
                error = f'HTTP {r.status_code}'     # the code only: a message can carry the request's header
                if r.status_code in (400, 401, 402, 403, 404):
                    break
                time.sleep(20)
                continue
            choice = r.json()['choices'][0]['message']
            text = choice.get('content') or choice.get('reasoning') or ''
            items = read_items(text)
            return {'model': model, 'seed': seed, 'seconds': round(time.time() - t0, 1), 'items': [i for i in items if isinstance(i, dict) and i.get('bodies')]}
        except Exception as exc:
            error = type(exc).__name__
            time.sleep(10)
    return {'model': model, 'seed': seed, 'error': error, 'items': []}


def one_model(model, seeds, secret, run_dir):
    """A model's batches, one after another, with a pause: free tiers limit requests per minute. Each batch is saved as it arrives."""
    out = []
    for seed in seeds:
        b = ask_free(model, seed, secret)
        out.append(b)
        with (run_dir / 'batches.jsonl').open('a') as f:
            f.write(json.dumps(b, ensure_ascii=False) + '\n')
        print(model, b.get('error') or len(b['items']), flush=True)
        if b.get('error') in ('HTTP 404', 'HTTP 402', 'HTTP 401', 'HTTP 403'):
            break
        time.sleep(PAUSE)
    return out


def generate(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    secret, rng = key(), random.Random(2)
    with ThreadPoolExecutor(len(MODELS)) as pool:
        batches = [b for bs in pool.map(lambda m: one_model(m, rng.sample(SEEDS, CALLS_PER_MODEL), secret, run_dir), MODELS) for b in bs]
    bank, n = [], 0
    for b in batches:
        for item in b['items']:
            n += 1
            bank.append({'id': f'm{n:04d}', 'model': b['model'], 'seed': b['seed'], **{k: str(item.get(k, ''))[:600] for k in ('bodies', 'constraints', 'free', 'interesting')}})
    (run_dir / 'raw.json').write_text(json.dumps(bank, ensure_ascii=False, indent=1))
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
