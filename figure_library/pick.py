"""Which library figures a concept film may use: Commons figures whose words match the concept, among those the vision
check (figure_library.vet) found to be clean teaching diagrams with English (or no) labels."""
from __future__ import annotations

import json
import re
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1] / 'figure-library' / 'commons'
STOP = set('this that with from their there which these those have been were also into about than then them they '
           'what when where while shows diagram figure image illustration drawing file svg made used using version '
           'english simple basic model'.split())


def tokens(text):
    out = set()
    for word in re.findall(r'[a-z]{4,}', str(text).lower()):
        word = re.sub(r'(ies)$', 'y', word)
        word = re.sub(r'(?<!s)s$', '', word)
        if word not in STOP:
            out.add(word)
    return out


def usable(record):
    """Vetted records must have passed; unvetted ones are offered only when their printed words are English."""
    vet = record.get('vet')
    if vet is not None:
        return bool(vet.get('usable'))
    return not any(re.search(r'[^\x00-\x7f°±×·→←θβαγλνμ]', label) for label in record.get('labels') or [])


def describe(record):
    """What the planner reads: the vision check's account when there is one, else Commons' own description."""
    vet = record.get('vet') or {}
    return (vet.get('shows') or record.get('description') or record.get('name', ''))[:300]


def candidates(about, limit=8, index=None, minimum=2):
    """The library figures that best match a concept's words (name, summary, the book's figure captions)."""
    index = index if index is not None else load()
    want = tokens(about)
    scored = []
    for record in index:
        if not usable(record):
            continue
        name = tokens(record.get('name', '')) | tokens((record.get('vet') or {}).get('shows', ''))
        body = tokens(record.get('description', '')) | tokens(' '.join(record.get('categories') or []))
        score = 2 * len(want & name) + len(want & (body - name))
        if score >= minimum and want & name:
            scored.append((score, record))
    scored.sort(key=lambda pair: (-pair[0], pair[1]['id']))
    return [{'id': r['id'], 'name': r['name'], 'description': describe(r), 'labels': (r.get('labels') or [])[:12],
             'credit': r['credit']} for _, r in scored[:limit]]


def load(root=LIBRARY):
    path = Path(root) / 'index.json'
    return json.loads(path.read_text()) if path.exists() else []
