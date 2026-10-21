"""Test yourself (user, 2026-10-22): creative questions on what a finished film taught.

Two planner/reviewer stages, cached like every film stage, in <film project>/questions/:
  1. blueprint: eight different ideas the film taught, spread across the film, each given a kind of question and
     the weak spot it should expose. The first experiment (Hydrocarbons 9.3.5) let the writer choose freely and
     seven of eight questions tested the peroxide effect; a blueprint checked by code keeps the set broad.
  2. questions: one per blueprint idea, in order. Code checks the shape, multiple-choice answers and, for chemistry,
     every structure (SMILES against its formula) and the main reaction (atoms balance), as the film figures are.
Chemistry structures are drawn by code (figure_library) for the page. questions.json holds the result.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REMOTION = Path('/home/nitin/remotion')
ROOT = Path(__file__).resolve().parents[1]
for path in (REMOTION, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

COUNT = 8
KINDS = {'predict': 'predict an outcome in a new case the book does not show',
         'explain': 'explain why, in the student\'s own reasoning',
         'spot_error': 'spot and correct the error in a student\'s answer',
         'backwards': 'work backwards from a result to what produced it',
         'compare': 'compare two cases or conditions',
         'data': 'read data or a figure the film gave',
         'sequence': 'order or complete the steps of a process',
         'scenario': 'an everyday or lab scenario that needs the idea'}

BLUEPRINT_TASK = (
    'A student has just watched a short curriculum film (its narration points and the facts it rests on are below) '
    'and will now test their understanding. Plan a set of {count} questions: choose {count} DIFFERENT ideas the film '
    'taught, spread across the whole film (beginning, middle and end), the ideas a student most needs to have '
    'understood. Give each idea one kind of question, using each kind once: {kinds}. Return {{ideas:[{{id:"B1", '
    'idea:"one sentence: what the student must understand", points:["the narration point ids that teach it"], '
    'kind:"one of {kind_ids}", targets:"the misconception or weak spot this question should expose"}}]}}.')

QUESTION_TASK = (
    'Write test questions for {audience} on "{concept}" (NCERT {book}, Chapter {chapter_no} "{chapter}"), one for '
    'each idea of the BLUEPRINT, in its order, of the kind it names, testing that idea and exposing the weak spot it '
    'names. Test understanding, not recall: a student who memorised the sentences should not be able to answer, one '
    'who understood can. Be creative (new cases and situations the film did not show) but stay inside the chapter: '
    'every fact and answer must follow the film\'s facts. Multiple choice where it suits (four options, one clearly '
    'correct, the others the mistakes students really make), open questions where reasoning is the point. {extra}'
    'Return {{questions:[{{id:"Q1", blueprint:"B1", kind:"the blueprint\'s kind", stem:"the question as the student '
    'reads it", options:["A ...","B ...","C ...","D ..."] or [] for an open question, answer:"the option letter, or '
    'a model answer", explanation:"why, in two or three sentences, as a teacher would explain it", targets:"the weak '
    'spot it exposes", difficulty:"easy|medium|hard"{schema_extra}}}]}}.')
CHEMISTRY_EXTRA = ('Give every molecule named in a stem, option or answer in "structures" (SMILES with its '
                   'molecular formula) and the main reaction the answer rests on in "reaction" (balanced, with every '
                   'product), so code can check them; use IUPAC names with the lowest locants. ')
CHEMISTRY_SCHEMA = (', structures:[{role:"what it is in the question", name:"IUPAC name", smiles, formula}], '
                    'reaction:{reactants:["SMILES"], products:["SMILES"]} or null')


def blueprint_errors(value, point_ids):
    ideas = value.get('ideas')
    if not isinstance(ideas, list) or len(ideas) != COUNT:
        return [f'give exactly {COUNT} ideas']
    out, used = [], {}
    for n, idea in enumerate(ideas, 1):
        tag = f'B{n}'
        if not isinstance(idea, dict) or idea.get('id') != tag:
            out.append(f'{tag}: needs id "{tag}"')
            continue
        if idea.get('kind') not in KINDS:
            out.append(f'{tag}: kind must be one of {list(KINDS)}')
        points = idea.get('points')
        if not isinstance(points, list) or not points or any(p not in point_ids for p in points):
            out.append(f'{tag}: points must be narration point ids from the film')
        else:
            for p in points:
                used[p] = used.get(p, 0) + 1
        for key in ('idea', 'targets'):
            if not isinstance(idea.get(key), str) or len(idea[key].split()) < 4:
                out.append(f'{tag}: say the {key}')
    kinds = [i.get('kind') for i in ideas if isinstance(i, dict)]
    if len(set(kinds)) != len(kinds):
        out.append('use each kind of question once')
    crowded = [p for p, n in used.items() if n > 2]
    if crowded:
        out.append(f'points {crowded} carry more than two ideas: choose different ideas, spread across the film')
    order = sorted(point_ids, key=point_ids.index)
    quarters = {min(3, 4 * order.index(p) // max(1, len(order))) for p in used}
    if len(order) >= 8 and len(quarters) < 3:
        out.append('the ideas come from too narrow a part of the film; spread them over its beginning, middle and end')
    return out


def question_errors(value, blueprint, chemistry):
    from figure_library import chem
    qs = value.get('questions')
    ideas = blueprint['ideas']
    if not isinstance(qs, list) or len(qs) != len(ideas):
        return [f'give exactly {len(ideas)} questions, one per blueprint idea']
    out = []
    for n, (q, idea) in enumerate(zip(qs, ideas), 1):
        tag = f'Q{n}'
        if not isinstance(q, dict):
            out.append(f'{tag}: must be an object')
            continue
        if q.get('id') != tag or q.get('blueprint') != idea['id'] or q.get('kind') != idea['kind']:
            out.append(f'{tag}: id "{tag}", blueprint "{idea["id"]}" and kind "{idea["kind"]}", in the blueprint order')
        for key in ('stem', 'answer', 'explanation'):
            if not isinstance(q.get(key), str) or len(q[key].split()) < (1 if key == 'answer' else 6):
                out.append(f'{tag}: say the {key}')
        options = q.get('options') or []
        if options:
            letters = [str(o).strip()[:1] for o in options]
            if not 3 <= len(options) <= 5 or letters != list('ABCDE'[:len(options)]):
                out.append(f'{tag}: options are 3-5 strings starting "A ", "B "...')
            elif str(q.get('answer', '')).strip()[:1] not in letters:
                out.append(f'{tag}: a multiple-choice answer is one option letter')
        if chemistry:
            for s in q.get('structures') or []:
                if not isinstance(s, dict):
                    out.append(f'{tag}: structures are objects')
                    continue
                out += [f'{tag} {s.get("name")}: {e}' for e in chem.figure_errors(
                    {'type': 'molecule', 'smiles': s.get('smiles', ''), 'formula': s.get('formula')})]
            reaction = q.get('reaction')
            if isinstance(reaction, dict):
                out += [f'{tag} reaction: {e}' for e in chem.figure_errors(
                    {'type': 'reaction', 'reactants': [{'smiles': x} for x in reaction.get('reactants') or []],
                     'products': [{'smiles': x} for x in reaction.get('products') or []], 'balanced': True})]
    return out


def shuffle(question):
    """Options in an order fixed by the question but not by the writer (the first set put the right answer at A in
    six of seven questions); the answer letter follows its option."""
    import random
    import re
    options = question.get('options') or []
    if not options:
        return question
    letter = str(question.get('answer', '')).strip()[:1]
    texts = [re.sub(r'^[A-E][.)]?\s+', '', str(o).strip()) for o in options]
    right = texts['ABCDE'.index(letter)] if letter in 'ABCDE'[:len(texts)] else None
    random.Random(hashlib.sha256(question.get('stem', '').encode()).hexdigest()).shuffle(texts)
    letters = 'ABCDE'[:len(texts)]
    out = {**question, 'options': [f'{l}. {t}' for l, t in zip(letters, texts)]}
    if right is not None:
        out['answer'] = letters[texts.index(right)]
    return out


def folder(project):
    return Path(project) / 'questions'


def saved(project):
    try:
        return json.loads((folder(project) / 'questions.json').read_text())
    except (OSError, ValueError):
        return None


def figure_key(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:20]


def draw(project, questions):
    """Code-drawn structures for each chemistry question: its main reaction, else its molecules (at most three)."""
    from figure_library import chem
    out = folder(project) / 'figures'
    out.mkdir(parents=True, exist_ok=True)
    for q in questions:
        specs = []
        reaction = q.get('reaction')
        if isinstance(reaction, dict) and reaction.get('reactants') and reaction.get('products'):
            specs.append({'type': 'reaction', 'reactants': [{'smiles': x} for x in reaction['reactants']],
                          'products': [{'smiles': x} for x in reaction['products']]})
        else:
            specs += [{'type': 'molecule', 'smiles': s['smiles']} for s in (q.get('structures') or [])[:3]]
        q['figures'] = []
        for spec in specs:
            key = figure_key(spec)
            path = out / f'{key}.png'
            try:
                if not path.exists():
                    chem.png(spec, path, width=1200)
                q['figures'].append(key)
            except Exception:                                            # noqa: BLE001 - a figure is a nicety
                continue
    return questions


def make(project, curriculum, chemistry=False, models=None):
    """Plan and write the questions (cached model calls) and save them; returns the questions."""
    from infofilm.core import Store, configuration
    from infofilm.llm import Models
    project = Path(project)
    film_dir = project / f'film-{curriculum.get("seconds")}'
    script = json.loads((film_dir / 'script.json').read_text())
    evidence = json.loads((project / 'evidence-final.json').read_text())
    if models is None:
        models = Models(configuration(project / 'config-snapshot.json'), Store(folder(project)))
    points = [{'id': p['id'], 'heading': p.get('heading'), 'narration': p.get('narration')} for p in script['points']]
    point_ids = [p['id'] for p in points]
    film = {'concept': curriculum.get('concept'), 'audience': curriculum.get('audience'),
            'narration': points, 'facts': [f.get('claim') for f in evidence.get('facts', [])]}
    blueprint = models.loop('test-blueprint', BLUEPRINT_TASK.format(
        count=COUNT, kinds='; '.join(f'{k} ({v})' for k, v in KINDS.items()), kind_ids=', '.join(KINDS)),
        film, lambda v: blueprint_errors(v, point_ids))
    task = QUESTION_TASK.format(
        audience=curriculum.get('audience') or 'school students', concept=curriculum.get('concept', ''),
        book=curriculum.get('book', ''), chapter_no=curriculum.get('chapter_no', ''),
        chapter=curriculum.get('chapter', ''), extra=CHEMISTRY_EXTRA if chemistry else '',
        schema_extra=CHEMISTRY_SCHEMA if chemistry else '')
    value = models.loop('test-questions', task, {**film, 'blueprint': blueprint},
                        lambda v: question_errors(v, blueprint, chemistry), max_tokens=12000)
    questions = [shuffle(q) for q in value['questions']]
    if chemistry:
        draw(project, questions)
    path = folder(project) / 'questions.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'blueprint': blueprint['ideas'], 'questions': questions}, indent=1,
                               ensure_ascii=False))
    return questions
