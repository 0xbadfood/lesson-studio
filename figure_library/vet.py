"""Vision check of the library: what each Commons figure shows, and whether a school film can show it as it is.

A figure is usable when it is a clean teaching diagram (not a logo, icon, flag or photograph), its printed words are
English or absent, and it is drawn correctly enough for a Class 11-12 student. The verdict is stored on the record
("vet"); figure_library.pick then offers only usable figures, described in the vision check's words.

  .venv/bin/python -m figure_library.vet --url http://127.0.0.1:8001/v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from figure_library.pick import LIBRARY  # noqa: E402

KINDS = ('diagram', 'chart', 'photo', 'logo', 'icon', 'flag', 'other')
PROMPT = '''You are checking a picture from Wikimedia Commons for a chemistry film for Class 11-12 students in India.
Commons title: {name}
Commons description: {description}

Look at the picture itself. Return JSON:
{{"shows": "one or two plain sentences: what the picture shows, naming the apparatus, experiment or idea",
 "kind": one of {kinds},
 "labels": "english" | "none" | "other language",
 "clean": true if it is a clear, complete drawing with nothing cut off, false if cluttered, unfinished or broken,
 "correct": true unless it shows something scientifically wrong,
 "usable": true only if kind is diagram or chart, labels are english or none, clean and correct are true, and a
   student would learn from seeing it,
 "reason": "a short reason when not usable, else empty"}}'''


def verdict_errors(result):
    errors = []
    if result.get('kind') not in KINDS:
        errors.append(f'kind must be one of {list(KINDS)}')
    if result.get('labels') not in ('english', 'none', 'other language'):
        errors.append('labels must be english, none or other language')
    for field in ('clean', 'correct', 'usable'):
        if not isinstance(result.get(field), bool):
            errors.append(f'{field} must be true or false')
    if not str(result.get('shows', '')).strip():
        errors.append('say what it shows')
    return errors


def decide(result):
    """The model's usable flag, never looser than its own findings."""
    return bool(result['usable'] and result['kind'] in ('diagram', 'chart') and result['labels'] != 'other language'
                and result['clean'] and result['correct'])


def vet(chat, root=LIBRARY, log=print, again=False):
    index_path = root / 'index.json'
    index = json.loads(index_path.read_text())
    for n, record in enumerate(index, 1):
        if record.get('vet') and not again:
            continue
        prompt = PROMPT.format(name=record['name'], description=record.get('description', '')[:400],
                               kinds=' | '.join(KINDS))
        try:
            result = chat.call(f'vet-{record["id"]}', prompt, images=[root / f'{record["id"]}.png'], thinking=0,
                               max_tokens=600, validate=lambda r: _raise(verdict_errors(r)))
        except Exception as exc:                                       # noqa: BLE001 - one figure, not the run
            log(f'{n}/{len(index)} {record["name"][:50]}: failed ({type(exc).__name__}: {str(exc)[:100]})')
            continue
        record['vet'] = {**{k: result[k] for k in ('shows', 'kind', 'labels', 'clean', 'correct', 'reason')},
                         'usable': decide(result)}
        log(f'{n}/{len(index)} {record["name"][:50]}: {"usable" if record["vet"]["usable"] else "no"} '
            f'({record["vet"]["kind"]}, {record["vet"]["labels"]})')
        index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False))
    usable = sum(bool((r.get('vet') or {}).get('usable')) for r in index)
    log(f'{usable} of {len(index)} figures usable')
    return index


def _raise(errors):
    if errors:
        raise ValueError('; '.join(errors))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default='http://127.0.0.1:8001/v1', help='an OpenAI-compatible vision model')
    parser.add_argument('--model', default=None, help='model id (luce for the amdserver Lucebox pair)')
    parser.add_argument('--again', action='store_true', help='check figures that already have a verdict')
    args = parser.parse_args(argv)
    from scivid.llm import Chat
    luce = args.model == 'luce'
    chat = Chat(args.url, LIBRARY.parent / 'vet-cache', label='vet', model=args.model, temperature=0 if luce else .2,
                constrained=not luce, timeout=600)
    vet(chat, again=args.again)
    return 0


if __name__ == '__main__':
    sys.exit(main())
