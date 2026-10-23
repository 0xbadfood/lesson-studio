"""From a settled solution to clips (user, 2026-10-23): what each clip explains, the book concepts it rests on, and
the drawing aid it needs. This is where solutions meet the digest, and where missing drawing aids are discovered.

Who plans follows how the solution was settled (record['planner'], solve.py):
  team   both students were right: the chosen solution's author drafts, the other student reviews, Opus settles;
  <one>  one model alone: the only student who was right, or Opus when it had to solve the question itself. It drafts,
         and repairs once if code finds faults; no other model is involved.
Code checks every plan: each concept must exist in the subject's digest, each verb must be a Linkwork card, each
chemistry figure must be a figure type chem.py draws, and each solution step must belong to one clip.

The drawing aid is chosen from a closed list per subject (the selection tree's level 2), with "none" and "missing"
as exits:
  none             the worked equations on screen are enough;
  question_figure  the question's own figure, redrawn and labelled;
  verb             a Linkwork verb from its card (name it, and say what its spec would set);
  chem_figure      chemistry only: a code-drawn figure_library/chem.py figure (molecule, reaction, mechanism...);
  missing          a picture that would help but nothing draws it: name its family and describe it.
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from .models import ask

ROOT = Path(__file__).resolve().parents[1]
DIGESTS = ROOT / 'textbook-digest'
LINKWORK = Path.home() / 'linkwork'
NODE = Path.home() / '.local' / 'node-v24.4.0' / 'bin'
BOOKS = {'physics': ('keph1', 'keph2', 'leph1', 'leph2'), 'chemistry': ('kech1', 'kech2', 'lech1', 'lech2'),
         'mathematics': ('kemh1', 'lemh1', 'lemh2')}
CARD_SUBJECT = {'physics': 'physics', 'chemistry': 'chemistry', 'mathematics': 'maths'}
# figure_library/chem.py and organic.py figure types.
CHEM_FIGURES = ('equation', 'molecule', 'reaction', 'resonance', 'bohr', 'orbital_boxes', 'energy_levels', 'orbital',
                'spectrum', 'mechanism', 'newman', 'sawhorse', 'chair')
# Families with no drawing aid yet. Physics: from the coverage dry run (2026-10-23); the others to start the tally.
FAMILIES = {
    'physics': {
        'ray_optics': 'mirrors, lenses, prisms, refraction, total internal reflection, instruments',
        'circuit': 'a schematic with current flow, meters, switches',
        'level_diagram': 'energy levels, bands, orbital boxes, enthalpy cycles (beyond hydrogen)',
        'wave': 'travelling, superposition, standing waves, beats, an EM wave',
        'oscillator': 'spring-mass, the reference circle drawing SHM graphs',
        'field_lines': 'field lines of charges, a dipole, plates, magnets, wires, coils',
        'phasor': 'a rotating phasor drawing its sine; AC, a generator',
        'kinematics': 'a body on a track drawing its x-t and v-t graphs live',
        'torque_and_balance': 'levers, couples, a dipole in a field, rolling',
        'charge_in_field': 'a charge on a parabola in E, a circle or helix in B',
        'projectile': 'a projectile with its velocity components and path',
        'induction': 'a magnet into a coil, a sliding rod, a loop through a field',
        'incline_and_forces': 'free-body diagrams, friction, a banked road',
        'pv_cycle': 'a piston and its P-V path drawn together',
        'centre_of_mass': 'a system and its centre of mass moving',
        'orbit': 'an ellipse, equal areas, a satellite',
        'particles': 'gas molecules in a box, drift, diffusion, collisions',
        'rigid_body': 'a rotating or rolling body, moment of inertia, angular momentum',
        'fluid': 'pressure, buoyancy, flow from an orifice',
    },
    'chemistry': {
        'lattice': 'unit cells, packing, voids, crystal structures',
        'cell': 'an electrochemical or electrolytic cell with electrodes, salt bridge and electron flow',
        'apparatus': 'a lab set-up: titration, distillation, a gas collected',
        'particles': 'molecules in motion: gas behaviour, diffusion, collisions, equilibrium as two-way traffic',
        'phase_diagram': 'phase or vapour-pressure diagrams, colligative shifts',
        'complex_geometry': '3-D shapes of complexes and molecules (VSEPR), isomers in space',
        'level_diagram': 'crystal-field splitting, MO diagrams, enthalpy cycles',
        'periodic_table': 'positions and trends on the periodic table',
    },
    'mathematics': {
        'conic': 'a parabola, ellipse or hyperbola with focus, directrix, tangents and normals',
        'region': 'a region bounded by curves, shaded, its area or a point inside',
        'vector_3d': 'lines and planes in space, angles and distances between them',
        'probability': 'sample spaces, trees, Venn diagrams, counting arrangements',
        'trig_circle': 'the unit circle, angles and trigonometric values and graphs',
        'transformation': 'shifts, stretches and reflections of a graph; inverse functions',
        'complex_plane': 'complex numbers as points and rotations; loci in the Argand plane',
        'sequence': 'terms of a sequence or series building up; limits',
        'matrix': 'a matrix acting on the plane; determinants as area',
    },
}


def aids(subject):
    base = ('none', 'question_figure', 'verb', 'missing')
    return base[:3] + ('chem_figure',) + base[3:] if subject == 'chemistry' else base


@lru_cache(maxsize=4)
def cards(subject='physics'):
    env = {**os.environ, 'PATH': f'{NODE}:{os.environ.get("PATH", "")}'}
    out = subprocess.run(['node', 'src/cli.ts', 'verbs', '--json', '--all'], cwd=LINKWORK, env=env,
                         capture_output=True, text=True, check=True).stdout
    wanted = {CARD_SUBJECT[subject], 'maths'}         # every subject may use the maths verbs (graphs, areas...)
    return {name: {k: c[k] for k in ('about', 'use_when', 'not_when', 'status') if k in c}
            for name, c in json.loads(out).items() if wanted & set(c.get('subjects', []))}


@lru_cache(maxsize=4)
def concepts(subject='physics'):
    """Every chapter's concepts for the subject, as 'keph1-02:C3' -> name, from the digest."""
    out = {}
    for folder in sorted(DIGESTS.iterdir()):
        if folder.name.split('-')[0] not in BOOKS[subject] or not (folder / 'digest.json').exists():
            continue
        digest = json.loads((folder / 'digest.json').read_text())
        title = digest['source'].get('title', folder.name)
        for c in digest.get('concepts', []):
            out[f'{folder.name}:{c["id"]}'] = f'{title} / {c["name"]}'
    return out


def all_concepts():
    return {ref: name for subject in BOOKS for ref, name in concepts(subject).items()}


def catalogue(subject):
    return '\n'.join(f'{ref} {name}' for ref, name in concepts(subject).items())


def shape(subject):
    kinds = '|'.join(aids(subject))
    chem = ('"figure": {"type": "one of ' + ', '.join(CHEM_FIGURES) + '", "what": "the species or reaction"} '
            '(only for kind chem_figure), ' if subject == 'chemistry' else '')
    return (
        'Return {"clips": [{"n": 1, "explains": "what this clip makes the student understand, one sentence", '
        '"steps": [solution step numbers it covers], "concepts": ["book concept refs from the catalogue, e.g. '
        f'{BOOKS[subject][0]}-02:C3; one to three"], "aid": {{"kind": "{kinds}", "verb": "a verb name, only for '
        f'kind verb", {chem}"family": "a family name, only for kind missing (or other:<name>)", "shows": "what the '
        'picture shows and how it moves, one or two sentences", "why": "why this aid and not the others"}}]}. '
        'Three to six clips; every solution step belongs to exactly one clip, in order. Choose a verb only when its '
        'card\'s use_when fits and its not_when does not; a near fit is "missing", not "verb". "none" is right when '
        'the equations alone carry the idea: do not decorate.')


def context(q, record):
    subject = q['subject']
    return {
        'question': {'id': q['id'], 'type': q['type'], 'text': q['text'], 'stem': q.get('stem'),
                     'official_answer': (q.get('answer') or {}).get('raw')},
        'solution': {k: record['solution'].get(k) for k in ('answer', 'steps', 'ideas', 'check', 'options')},
        'verbs': cards(subject),
        'missing_families': FAMILIES[subject],
    }


def errors(plan, steps, subject='physics'):
    found = []
    clips = plan.get('clips') if isinstance(plan, dict) else None
    if not isinstance(clips, list) or not 1 <= len(clips) <= 8:
        return ['clips must be a list of 1-8 clips']
    known, verbs, kinds = concepts(subject), cards(subject), aids(subject)
    covered = []
    for c in clips:
        n = c.get('n')
        covered += c.get('steps') or []
        for ref in c.get('concepts') or []:
            if ref not in known:
                found.append(f'clip {n}: concept {ref} is not in the catalogue')
        if not c.get('concepts'):
            found.append(f'clip {n}: name at least one book concept')
        aid = c.get('aid') or {}
        if aid.get('kind') not in kinds:
            found.append(f'clip {n}: aid kind must be one of {kinds}')
        if aid.get('kind') == 'verb' and aid.get('verb') not in verbs:
            found.append(f'clip {n}: {aid.get("verb")} is not a Linkwork verb; use kind missing')
        if aid.get('kind') == 'chem_figure' and (aid.get('figure') or {}).get('type') not in CHEM_FIGURES:
            found.append(f'clip {n}: chem_figure type must be one of {CHEM_FIGURES}; otherwise use kind missing')
        if aid.get('kind') == 'missing':
            family = str(aid.get('family') or '')
            if family not in FAMILIES[subject] and not family.startswith('other:'):
                found.append(f'clip {n}: family {family!r} is not listed; use other:<name>')
    if sorted(covered) != sorted(steps):
        found.append(f'the clips cover steps {sorted(covered)} but the solution has steps {sorted(steps)}: each '
                     'step in exactly one clip')
    return found


def plan(q, record, progress=None):
    """Plan the clips as record['planner'] says (team, or one model alone). Returns the plan and the trail."""
    subject = q['subject']
    say = progress or (lambda text: None)
    steps = [s.get('n') for s in record['solution'].get('steps') or []]
    pages = q.get('pages', [])
    lead = ('A JEE question has a settled, checked solution (below). It becomes a worked-solution video made of '
            'short clips. Plan the clips. Ground each clip in the textbook: the catalogue lists every '
            f'{subject} concept our digest of the NCERT books holds, and each clip names the ones it rests on. For '
            'each clip choose the drawing aid.\n\nCONCEPT CATALOGUE:\n' + catalogue(subject) + '\n\nINPUT:\n' +
            json.dumps(context(q, record), ensure_ascii=False) + '\n\n' + shape(subject))
    trail, usage = {}, {}
    planner = record.get('planner') or 'team'
    if planner != 'team':
        say(f'Planning the clips: {planner} alone')
        final, usage[planner] = ask(planner, lead, pages, max_tokens=12000, name=f'{q["id"]}-clips-{planner}')
        left = errors(final, steps, subject)
        if left:
            say(f'Code found {len(left)} faults; {planner} repairs the plan once')
            final, usage[f'{planner}-repair'] = ask(planner, lead + '\n\nYour plan:\n' + json.dumps(
                final, ensure_ascii=False) + '\n\nIt failed these checks; fix them: ' + '; '.join(left), pages,
                max_tokens=12000, name=f'{q["id"]}-clips-{planner}-repair')
            left = errors(final, steps, subject)
        trail['final'] = final
        say(f'Plan settled: {len(final.get("clips") or [])} clips' + (f'; checks still failing: {"; ".join(left)}' if left else ''))
        return final, {'trail': trail, 'usage': usage, 'errors': left, 'planner': planner}
    author = record.get('author') or 'haiku'
    other = next(w for w in ('haiku', 'luna') if w != author)
    say(f'Planning the clips: {author} drafts')
    draft, usage[author] = ask(author, lead, pages, name=f'{q["id"]}-clips-draft')
    trail['draft'] = {**draft, 'by': author}
    issues = errors(draft, steps, subject)
    say(f'Draft: {len(draft.get("clips") or [])} clips; {other} reviews it')
    review_task = (lead + '\n\nA colleague drafted this plan:\n' + json.dumps(draft, ensure_ascii=False) +
                   ('\nCode found: ' + '; '.join(issues) if issues else '') +
                   '\n\nReview it as a teacher would: wrong or missing concepts, a clip that teaches two things, an '
                   'aid that does not fit its card (or a verb forced where "missing" or "none" is honest). Return '
                   '{"findings": [{"clip": n, "problem": "...", "fix": "..."}], "verdict": "accept|revise"}.')
    review, usage[other] = ask(other, review_task, pages, name=f'{q["id"]}-clips-review')
    trail['review'] = {**review, 'by': other}
    say(f'{other}: {review.get("verdict", "?")}, {len(review.get("findings") or [])} findings; Opus settles the plan')
    settle = (lead + '\n\nThe planner drafted:\n' + json.dumps(draft, ensure_ascii=False) + '\n\nThe reviewer found:\n' +
              json.dumps(review, ensure_ascii=False) + ('\nCode found: ' + '; '.join(issues) if issues else '') +
              '\n\nYou are the teacher and have the final say. Return the final plan in the same shape. Take a '
              'finding only if it is right.')
    final, usage['opus'] = ask('opus', settle, pages, max_tokens=12000, name=f'{q["id"]}-clips-final')
    left = errors(final, steps, subject)
    if left:
        final, usage['opus-repair'] = ask('opus', settle + '\n\nYour plan failed these checks; fix them: ' +
                                          '; '.join(left), pages, max_tokens=12000, name=f'{q["id"]}-clips-repair')
        left = errors(final, steps, subject)
    trail['final'] = final
    say(f'Plan settled: {len(final.get("clips") or [])} clips' + (f'; checks still failing: {"; ".join(left)}' if left else ''))
    return final, {'trail': trail, 'usage': usage, 'errors': left, 'planner': 'team'}


def retry(q, record, clip):
    """Retry Linkwork search for one clip that hit a snag: the teacher looks again at today's verb cards (new verbs
    may exist since the plan). Returns the aid; a verb only when code finds it on the cards."""
    verbs = cards(q['subject'])
    task = ('One clip of a worked-solution video has no Linkwork drawing aid yet. Look again at the verb cards (some '
            'may be new) and decide: is there a verb whose use_when fits this clip and whose not_when does not? A '
            'near fit is still "missing".\n\nQUESTION:\n' + q['text'] + '\n\nSOLUTION STEPS:\n' +
            json.dumps(record['solution'].get('steps'), ensure_ascii=False) + '\n\nCLIP:\n' +
            json.dumps(clip, ensure_ascii=False) + '\n\nVERBS:\n' + json.dumps(verbs, ensure_ascii=False) +
            '\n\nReturn {"kind": "verb|missing", "verb": "only for kind verb", "family": "only for kind missing", '
            '"shows": "what the picture shows and how it moves", "why": "one sentence"}.')
    aid, usage = ask('opus', task, q.get('pages', []), max_tokens=3000,
                     name=f'{q["id"]}-clip{clip.get("n")}-retry-{"-".join(sorted(verbs))[:60]}')
    if aid.get('kind') != 'verb' or aid.get('verb') not in verbs:
        aid = {**(clip.get('aid') or {}), 'kind': 'missing', 'retry_why': aid.get('why')}
    return aid, usage
