"""Key ideas: the second level of films (user, 2026-10-20).

After a concept film is made, its key ideas can each become a short simplified film (3-5 minutes, from how complex
the idea is). The ideas come from the finished film: its narration, its evidence and the concept's objectives, read
by the planner model, which picks the ideas a student most needs simplified. They are kept in
<film project>/key-ideas/ideas.json; the model calls (cached, like every film stage) sit beside it.

A key-idea film request (catalog.film_request + key_idea_record) keeps the concept's book text and figure options,
and adds the idea, the questions the learner check asks, and a research question on how others explain it simply.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

REMOTION = Path('/home/nitin/remotion')
if str(REMOTION) not in sys.path:
    sys.path.insert(0, str(REMOTION))

FEWEST, MOST = 3, 6
SHORTEST, LONGEST = 3, 5          # minutes; the idea's complexity decides within this range

TASK = (
    "A short film has just taught one textbook concept, faithfully and completely (its narration and evidence are "
    "below). Students who found it hard now need its key ideas simplified: each key idea becomes its own short film "
    "of {shortest}-{longest} minutes that drills down one idea with analogies and everyday pictures. Choose {fewest}-"
    "{most} key ideas from this concept: the ideas everything else rests on and the ones students most often find "
    "hard or get wrong, in the order a student should watch them. Do not list mere facts or definitions; a key idea "
    "is something to understand. For each give id ('I1'...), title (a short question or statement a student would "
    "click on, at most 9 words), why (one sentence: why students find it hard), understanding (one or two sentences: "
    "what the learner should be able to say after the film, in the everyday words of a 15-year-old who finds science "
    "hard: no symbols, formulas or numbers), questions (2-3 short questions a learner "
    "who understood it could answer from the film), minutes ({shortest}-{longest}, from how much the idea needs), "
    "research (one web search question for simple explanations, analogies and common misconceptions of this idea). "
    "Return {{ideas:[...]}}.")


def errors(value):
    out = []
    ideas = value.get('ideas')
    if not isinstance(ideas, list) or not FEWEST <= len(ideas) <= MOST:
        return [f'Give {FEWEST}-{MOST} key ideas']
    for n, idea in enumerate(ideas, 1):
        tag = f'I{n}'
        if not isinstance(idea, dict):
            out.append(f'{tag}: must be an object')
            continue
        if idea.get('id') != tag:
            out.append(f'{tag}: id must be "{tag}" (number the ideas in order)')
        for key in ('title', 'why', 'understanding', 'research'):
            if not isinstance(idea.get(key), str) or len(idea[key].split()) < 3:
                out.append(f'{tag}: say the {key}')
        if isinstance(idea.get('title'), str) and len(idea['title'].split()) > 9:
            out.append(f'{tag}: title has {len(idea["title"].split())} words; at most 9')
        questions = idea.get('questions')
        if not isinstance(questions, list) or not 2 <= len(questions) <= 3 or not all(isinstance(q, str) for q in questions):
            out.append(f'{tag}: give 2-3 questions')
        if not isinstance(idea.get('minutes'), (int, float)) or not SHORTEST <= idea['minutes'] <= LONGEST:
            out.append(f'{tag}: minutes must be {SHORTEST}-{LONGEST}')
    return out


def folder(project):
    return Path(project) / 'key-ideas'


def saved(project):
    path = folder(project) / 'ideas.json'
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def find(project, curriculum, models=None):
    """Ask the planner for the film's key ideas (cached) and save them; returns the ideas."""
    from infofilm.core import Store, configuration
    from infofilm.llm import Models
    project = Path(project)
    film_dir = project / f'film-{curriculum.get("seconds")}'
    script = json.loads((film_dir / 'script.json').read_text())
    evidence = json.loads((project / 'evidence-final.json').read_text())
    if models is None:
        models = Models(configuration(project / 'config-snapshot.json'), Store(folder(project)))
    context = {'concept': curriculum.get('concept'), 'audience': curriculum.get('audience'),
               'book': curriculum.get('book'), 'chapter': curriculum.get('chapter'),
               'objectives': [c['point'] for c in curriculum.get('coverage', []) if c['point'].startswith('Objective')],
               'narration': [{'heading': p.get('heading'), 'narration': p.get('narration')} for p in script['points']],
               'facts': [f.get('claim') for f in evidence.get('facts', [])]}
    task = TASK.format(fewest=FEWEST, most=MOST, shortest=SHORTEST, longest=LONGEST)
    value = models.loop('key-ideas', task, context, errors)
    ideas = [{k: idea[k] for k in ('id', 'title', 'why', 'understanding', 'questions', 'minutes', 'research')}
             for idea in value['ideas']]
    path = folder(project) / 'ideas.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ideas, indent=1, ensure_ascii=False))
    return ideas


class Finder:
    """Finds key ideas in the background (a minute or so of model time); one search per film at a time."""

    def __init__(self, find_fn=find, saved_fn=None):
        self.find, self.running, self.failed, self.lock = find_fn, set(), {}, threading.Lock()
        self.saved = saved_fn or saved             # where the work lands (key ideas, or a question set)

    def start(self, project, curriculum):
        key = str(project)
        with self.lock:
            if key in self.running:
                return
            self.running.add(key)
            self.failed.pop(key, None)

        def work():
            try:
                self.find(project, curriculum)
            except Exception as exc:                                   # noqa: BLE001 - shown as "could not"
                self.failed[key] = f'{type(exc).__name__}: {exc}'[:300]
            finally:
                with self.lock:
                    self.running.discard(key)
        threading.Thread(target=work, daemon=True).start()

    def state(self, project):
        key = str(project)
        if key in self.running:
            return 'finding'
        if self.saved(project) is not None:
            return 'ready'
        return 'failed' if key in self.failed else 'none'


def key_idea_record(built, idea, parent_film):
    """A key-idea film request from the concept's request (catalog.film_request): same book text, sources and figure
    options; the idea, its learner questions and its research question; length from the idea."""
    record = {**built['record'], 'kind': 'key_idea', 'coverage': [], 'seconds': int(round(idea['minutes'] * 60)),
              'idea': {k: idea[k] for k in ('id', 'title', 'why', 'understanding', 'questions')},
              'research': idea['research'], 'parent_film': parent_film}
    subject = f'{idea["title"]} (key idea of {built["record"]["concept"]}, {built["record"]["book"]})'
    return {'subject': subject[:300], 'record': record, 'sources': built['sources']}
