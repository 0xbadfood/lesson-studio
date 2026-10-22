"""Visual needs: a second pass over a chapter's digest that finds the exact diagrams its films (and later its solved
problems) need, with what each must be able to do on screen (user, 2026-10-22: "for science and geography we will
need an SVG library with defined animation scope ... make another pass on the digest to discover them and create a
database easily searchable by the pipeline").

The digest already describes every figure, map and table of the book (caption and what it shows), so the pass reads
no PDF. For each chapter the model sorts every such block into a teaching diagram, an illustration (people, scenes:
the image model's job) or a data table, describes each teaching diagram as a need (name, kind, parts, stages, the
animations it should support, the concepts that use it, the book's figure number), and adds the few diagrams a
teacher would draw for a concept that the book does not. Code checks that every block is accounted for once and
that every field uses the fixed vocabulary. Output: textbook-digest/<chapter>/visual-needs.json. The registry
(figure_library/visuals.py) merges the chapters' needs into one searchable database.

  .venv/bin/python kb_research/visual_needs.py kebo1-15 kech1-02 ...   [--endpoint URL]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import digest  # noqa: E402
import textbook_kb as kb  # noqa: E402

VISUAL_BLOCKS = ('figure', 'map', 'table')
ROLES = ('teaching', 'illustration', 'data_table')
KINDS = {'structure': 'an object, organ, cell or organism drawn to show its parts (often a section)',
         'process': 'steps or stages in order (cell division, a cycle, a mechanism over time)',
         'flow': 'something moving along a path (blood, current, energy, a nerve impulse, matter in a cycle)',
         'apparatus': 'an experiment or instrument set-up',
         'circuit': 'an electric circuit',
         'ray_diagram': 'light rays through mirrors, lenses or prisms',
         'graph': 'a plotted relationship, curve, waveform or spectrum',
         'map': 'a geographic map',
         'molecule': 'a molecular structure or model',
         'reaction': 'a chemical reaction or mechanism drawn with structures',
         'model': 'an abstract scientific model (atom model, orbital, energy levels, a field)',
         'comparison': 'two or more things side by side to compare',
         'schematic': 'any other labelled schematic'}
MOTIONS = {'highlight': 'light up one part while the narration is about it',
           'labels': 'reveal part labels as they are named',
           'stages': 'change from one stage or state to the next',
           'flow': 'move dots or arrows along a path (blood, current, rays, electrons, energy)',
           'rotate': 'turn a part or the whole about a point',
           'translate': 'move a part from one place to another',
           'draw_on': 'draw a line, curve or arrow progressively',
           'value_change': 'change a quantity and redraw (a graph point, a slider, a level)',
           'zoom': 'zoom from the whole into a detail'}
MAX_EXTRA = 2

SYSTEM = ('You are an experienced NCERT teacher and science illustrator. You decide which diagrams a lesson needs '
          'and what each must be able to show. Reply with JSON only.')

TASK = '''Below are the figures, maps and tables of NCERT Class {cls} {book}, Chapter {no} "{title}", as the book's
digest describes them, and the chapter's concepts. Sort every block, and describe the diagrams a teaching film of each
concept needs.

1. figures: every block below, once: role "teaching" (a diagram that teaches: a structure, process, apparatus, circuit,
   ray diagram, graph, map, molecule, model, schematic), "illustration" (people, a scene, a photograph, a cartoon, a
   decorative picture: an image model can paint it) or "data_table" (a table of data or facts). A teaching block names
   the need it becomes; several blocks can be one need (the same diagram drawn twice, or (a)/(b) parts of one figure).
2. needs: one per diagram the films need, each with
   id "N1"..., name (a short, general name that another chapter or book would use for the same diagram, e.g. "Human
   heart, section", "Cathode ray tube", "Mitosis stages"), kind (one of: {kinds}), shows (one sentence: what it
   shows), parts (the parts the book names on it, at most 16, short names), stages (the stages or states in order if
   it changes, else []), motions (what it must be able to do on screen, from: {motions}), concepts (the concept ids
   that use it), blocks (its block ids, [] if the book does not draw it), figure_ref (the book's figure number, e.g.
   "Fig. 15.2", else ""), beyond_book (true if the book does not draw it).
3. Add, for a concept, at most {extra} beyond_book needs: diagrams a good teacher would draw on the board for it that
   the book does not have (a flow chart of double circulation, a labelled cell cycle, a graph the text describes in
   words). Only when it clearly helps the concept; none is fine.

Return {{"figures":[{{"block":"B12","role":"teaching","need":"N1"}}, {{"block":"B13","role":"illustration","need":null}}],
"needs":[{{"id":"N1","name":"...","kind":"structure","shows":"...","parts":["..."],"stages":[],"motions":["highlight","labels"],
"concepts":["C3"],"blocks":["B12"],"figure_ref":"Fig. 15.2","beyond_book":false}}]}}

CONCEPTS:
{concepts}

BLOCKS:
{blocks}'''


def visual_blocks(d):
    owner = {x: c['id'] for c in d['concepts'] for x in c['blocks']}
    return [{'block': b['id'], 'type': b['type'], 'concept': owner.get(b['id']), 'section': b.get('section'),
             'caption': b.get('caption') or b.get('title') or '', 'shows': (b.get('shows') or b.get('text') or '')[:400]}
            for b in d['blocks'] if b['type'] in VISUAL_BLOCKS]


def need_errors(value, blocks, concept_ids):
    errors = []
    figures, needs = value.get('figures'), value.get('needs')
    if not isinstance(figures, list) or not isinstance(needs, list):
        return ['return "figures" and "needs" lists']
    wanted = [b['block'] for b in blocks]
    got = [f.get('block') for f in figures]
    missing, extra = [b for b in wanted if b not in got], [b for b in got if b not in wanted]
    twice = sorted({b for b in got if got.count(b) > 1})
    if missing or extra or twice:
        errors.append(f'figures must list every block once: missing {missing}, unknown {extra}, twice {twice}')
    ids = [n.get('id') for n in needs]
    if len(set(ids)) != len(ids) or any(not str(i).startswith('N') for i in ids):
        errors.append('needs need unique ids N1, N2, ...')
    for f in figures:
        if f.get('role') not in ROLES:
            errors.append(f'{f.get("block")}: role must be one of {list(ROLES)}')
        elif f['role'] == 'teaching' and f.get('need') not in ids:
            errors.append(f'{f["block"]}: a teaching block names its need id')
        elif f['role'] != 'teaching' and f.get('need'):
            errors.append(f'{f["block"]}: only a teaching block has a need')
    teaching = {f['block']: f.get('need') for f in figures if f.get('role') == 'teaching'}
    extra_per_concept = {}
    for n in needs:
        tag = n.get('id')
        if n.get('kind') not in KINDS:
            errors.append(f'{tag}: kind must be one of {list(KINDS)}')
        if not n.get('motions') or any(m not in MOTIONS for m in n.get('motions') or []):
            errors.append(f'{tag}: motions from {list(MOTIONS)}')
        if len(str(n.get('name', '')).split()) < 1 or len(str(n.get('shows', '')).split()) < 4:
            errors.append(f'{tag}: give its name and what it shows')
        if not n.get('concepts') or any(c not in concept_ids for c in n.get('concepts') or []):
            errors.append(f'{tag}: concepts must be concept ids')
        if not isinstance(n.get('parts'), list) or len(n['parts']) > 16 or not isinstance(n.get('stages'), list):
            errors.append(f'{tag}: parts (at most 16) and stages are lists')
        mine = sorted(b for b, need in teaching.items() if need == tag)
        if sorted(n.get('blocks') or []) != mine:
            errors.append(f'{tag}: blocks must be exactly the teaching blocks that name it: {mine}')
        if bool(n.get('beyond_book')) != (not mine):
            errors.append(f'{tag}: beyond_book is true exactly when no block of the book draws it')
        if n.get('beyond_book'):
            for c in n.get('concepts') or []:
                extra_per_concept[c] = extra_per_concept.get(c, 0) + 1
    over = sorted(c for c, k in extra_per_concept.items() if k > MAX_EXTRA)
    if over:
        errors.append(f'at most {MAX_EXTRA} beyond_book needs per concept: {over}')
    return errors


def chapter_needs(model, d):
    s = d['source']
    blocks = visual_blocks(d)
    concepts = [{'id': c['id'], 'name': c['name'], 'objectives': c.get('objectives', [])[:4]} for c in d['concepts']]
    prompt = TASK.format(cls=s['class'], book=s.get('book_title', ''), no=s['chapter'], title=s['title'],
                         kinds='; '.join(f'{k} ({v})' for k, v in KINDS.items()),
                         motions='; '.join(f'{k} ({v})' for k, v in MOTIONS.items()), extra=MAX_EXTRA,
                         concepts=json.dumps(concepts, ensure_ascii=False),
                         blocks=json.dumps(blocks, ensure_ascii=False))
    ids = {c['id'] for c in d['concepts']}
    value = model.call('visual-needs', prompt, thinking=2000, max_tokens=16000, attempts=3, system=SYSTEM,
                       validate=lambda r: kb.raise_if(need_errors(r, blocks, ids)))
    return {'chapter': s['id'], 'class': s['class'], 'subject': s['subject'], 'book': s.get('book'),
            'chapter_no': s['chapter'], 'title': s['title'], 'figures': value['figures'], 'needs': value['needs']}


def run(refs, endpoint, out_root=digest.OUT, log=print):
    done = []
    for ref in refs:
        folder = out_root / ref.replace(':', '-')
        source = folder / 'digest.json'
        if not source.exists():                       # a chapter being rebuilt keeps its last digest aside
            olds = sorted(out_root.glob(f'{folder.name}.bak-*/digest.json'))
            if not olds:
                log(f'{ref}: no digest')
                continue
            source = olds[-1]
        d = json.loads(source.read_text())
        model = digest.chat(endpoint, folder, 'visual', 3600)
        try:
            result = chapter_needs(model, d)
        except RuntimeError as exc:
            log(f'{ref}: FAILED {exc}')
            continue
        (folder / 'visual-needs.json').write_text(json.dumps(result, indent=1, ensure_ascii=False))
        roles = [f['role'] for f in result['figures']]
        log(f'{ref}: {len(result["needs"])} needs ({sum(n["beyond_book"] for n in result["needs"])} beyond the book) '
            f'from {roles.count("teaching")} teaching, {roles.count("illustration")} illustration, '
            f'{roles.count("data_table")} table blocks')
        done.append(ref)
    return done


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('chapters', nargs='+')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8001/v1')
    args = parser.parse_args()
    run(args.chapters, args.endpoint)
