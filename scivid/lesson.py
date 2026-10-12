"""Evidence, lesson plan and narration script, each validated in code and reviewed by a second call."""
import json
import re
import subprocess
from pathlib import Path

from . import curriculum
from .audio import closest_span, phrase_in_text, speakable
from .spoken import leftovers
from . import diagram_spec
from . import patch, review as rubric
from .slides import SLIDE_GUIDE, slide_errors

IMAGE_VERBS = {
    'label': 'name an object on screen: {"verb":"label","object":id,"text":"<=4 words"}',
    'highlight': 'draw attention to an object: {"verb":"highlight","object":id}',
    'arrow': 'arrow from an object: {"verb":"arrow","object":id,"direction":"up|down|left|right|toward:<id>|along_motion","text":"optional <=3 words"}',
    'move_along': 'a moving object travels its drawn path: {"verb":"move_along","object":id,"path":id,"laps":1,"direction":"forward|reverse"}',
    'rotate': 'a moving object turns in the screen plane about its pivot (wheels, discs, fans; NOT a planet spinning on a tilted axis): {"verb":"rotate","object":id,"turns":0.25}',
    'swing': 'a hanging moving object (pendulum, swing) swings to and fro about its top pivot: {"verb":"swing","object":id,"angle":20}',
    'shake': 'a moving object vibrates: {"verb":"shake","object":id}',
    'release': 'a moving object leaves its path in a straight line along the direction it was moving (a string snaps, a car skids off): {"verb":"release","object":id}',
    'show': 'a moving object appears: {"verb":"show","object":id}',
    'hide': 'a moving object disappears: {"verb":"hide","object":id}',
    'zoom': 'camera moves in on an object then back: {"verb":"zoom","object":id}',
    'trace': 'draw the path line progressively: {"verb":"trace","path":id}',
    'title': 'a short on-screen heading: {"verb":"title","text":"<=5 words"}',
}
MOTION_VERBS = {'move_along', 'rotate', 'swing', 'shake', 'show', 'hide', 'release'}

TONE = {6: 'playful and curious: short sentences, everyday Indian examples, a question to the viewer, light humour',
        7: 'playful and curious: short sentences, everyday Indian examples, a question to the viewer, light humour',
        8: 'lively and relatable: a puzzle or surprise, everyday examples, a myth to bust, a touch of humour',
        9: 'lively and sharp: a surprising hook, clear reasoning, real-world examples, occasional wit',
        10: 'energetic and precise: a strong hook, exact definitions and units, applications, exam-ready clarity',
        11: 'rigorous and engaging: a strong hook, derivations step by step, vectors and calculus where they help, '
            'exact notation and units, real applications',
        12: 'rigorous and engaging: a strong hook, derivations step by step, vectors and calculus where they help, '
            'exact notation and units, real applications',
        'open': 'expert and exciting: as deep as the topic needs (undergraduate level is fine), full derivations, '
                'calculus, vectors and precise notation, no simplification for a school audience, still a vivid hook '
                'and clear spoken explanations'}


NO_SOURCES = ('NONE. No sources were gathered for this lesson by design: use well-established, standard knowledge '
              'of the subject; do not invent specific figures, dates, names or quotations; keep every number '
              'derivable from stated values.')


def evidence_text(evidence, limit=None):
    text = json.dumps(evidence, ensure_ascii=False) if evidence else NO_SOURCES
    return text[:limit] if limit else text


def from_evidence(evidence, grounded, ungrounded):
    """Prompt wording for a grounded lesson, or for one planned from the model's own knowledge."""
    return grounded if evidence else ungrounded


def audience(level):
    """How prompts name the audience: a class, or no level limit."""
    return 'an advanced audience with no class-level limit (up to undergraduate depth)' if level == 'open' else f'Class {level}'


# ------------------------------------------------------------------ evidence
def chapter_evidence(root, chapter_ref, query, limit=10):
    """Textbook evidence: knowledge-bank facts (when banked) plus the best page passages."""
    chapter = curriculum.find(root, chapter_ref)
    cite = lambda page: (f"NCERT Class {chapter['class']} · {chapter['book_title']} · Ch {chapter['chapter']} "
                         f"{chapter['title']} · p.{page}")
    items = []
    bank = curriculum.knowledge_bank(chapter)
    if bank:
        for fact in curriculum.bank_facts(bank, query, limit=8):
            pages = fact.get('pages') or ['?']
            items.append({'id': f'F{len(items) + 1:02d}', 'source': 'ncert', 'ref': f"{chapter['id']}/bank",
                          'cite': cite(', '.join(map(str, pages))), 'text': fact['statement'],
                          'score': 3.0 if fact.get('confidence') == 'high' else 2.0})
    hits = curriculum.search(chapter, query, limit=limit - (4 if bank else 0))
    items += [{'id': f'N{i + 1:02d}', 'source': 'ncert', 'ref': h['id'], 'cite': cite(h['page']),
               'text': h['text'], 'score': h.get('score', 0)} for i, h in enumerate(hits)]
    return chapter, items, bank


def web_evidence(settings, folder, topic, guidance, model_url=None):
    """The infofilm research worker (Tavily search + fetched pages + source digests)."""
    import os
    import shlex
    env = dict(os.environ)
    if not env.get('TAVILY_API_KEY'):
        service = Path(settings.remotion_root) / '.service.env'
        if service.exists():
            for line in service.read_text().splitlines():
                if line.startswith('TAVILY_API_KEY='):
                    env['TAVILY_API_KEY'] = shlex.split(line.partition('=')[2])[0]
    if not env.get('TAVILY_API_KEY'):
        raise RuntimeError('Web research needs a Tavily key (TAVILY_API_KEY)')
    # The infofilm worker keeps its own model-call store two levels above this folder, so nest it in the
    # lesson (lesson/research/web); lessons researched before this keep their original lesson/web results.
    legacy = Path(folder) / 'web'
    directory = legacy if (legacy / 'extracted.json').exists() else Path(folder) / 'research' / 'web'
    extracted = directory / 'extracted.json'
    if not extracted.exists():
        request = directory / 'request.json'
        directory.mkdir(parents=True, exist_ok=True)
        request.write_text(json.dumps({'subject': topic, 'directory': str(directory),
                                       'kbagent_root': settings.kbagent_root,
                                       'model_url': model_url or settings.planner_url,
                                       'subject_guidance': guidance}, ensure_ascii=False))
        result = subprocess.run([settings.research_python, '-u', '-m', 'infofilm.research_worker', str(request)],
                                cwd=settings.remotion_root, env=env, capture_output=True, text=True, timeout=1800)
        if result.returncode or not extracted.exists():
            failure = directory / 'failure.json'
            reason = json.loads(failure.read_text()).get('error') if failure.exists() else result.stdout[-800:]
            raise RuntimeError('Web research failed: ' + str(reason))
    items = []
    for item in json.loads(extracted.read_text())['results']:
        digest = item.get('source_digest') or {}
        passages = {p.get('id'): p.get('text', '') for p in digest.get('passages', [])}
        for claim in digest.get('claims', [])[:4]:
            text = claim.get('claim', '') if isinstance(claim, dict) else str(claim)
            support = ' '.join(passages.get(pid, '') for pid in (claim.get('passage_ids', []) if isinstance(claim, dict) else []))
            items.append({'id': f'W{len(items) + 1:02d}', 'source': 'web', 'ref': item['url'], 'cite': item['url'],
                          'text': (text + (' — ' + support if support else ''))[:900]})
    if not items:
        raise RuntimeError('Web research returned no usable sources')
    return items[:14]


# ------------------------------------------------------------------ plan
PLAN_SCHEMA = '''{"title":str,"subject":"physics|chemistry|maths|biology|other","big_idea":str,
"misconception":str|null,
"chapters":[{"id":"c1","title":str,"objective":str,"route":"diagram","source_ids":[str],
  "seconds":int,
  "demonstrations":[{"id":"d1","watch":"what the viewer SEES happen on screen (motion or change)","proves":"the one idea it shows"}],
  "diagram":{"layout":"single|split","elements":[...diagram elements...]}}]}'''

CODED_SCHEMA = '''{"title":str,"subject":"physics|chemistry|maths|biology|other","big_idea":str,
"misconception":str|null,"colours":"what each colour means across the lesson",
"theme":{"background":"#rrggbb, dark","accent":"#rrggbb","text":"#rrggbb, light","picture_style":"one sentence: the shared art style of every slide picture"},
"chapters":[{"id":"c1","title":str,"objective":str,"route":"coded|slide","history":bool,
  "complexity":"routine|involved|novel (coded chapters only)","source_ids":[str],"seconds":int,
  "demonstrations":[{"id":"d1","watch":"what the viewer SEES happen on screen (motion or change)","proves":"the one idea it shows"}],
  "visual":"coded: storyboard for the scene coder (what is on screen, where, what moves or transforms, in what order); slide: what the cards show"}]}'''

TIER_GUIDE = ('"complexity" rates how hard the chapter is to animate and picks its scene coder: "routine" = standard '
              'patterns (a plot, bars, a worked equation, a number line, one labelled motion); "involved" = several '
              'synced moving parts, custom geometry, live vectors, transforms between representations; "novel" = '
              'original constructions, perspective drawn by hand, physical simulation. Rate honestly; do not '
              'under-rate: a weak coder on a hard chapter wastes more than a strong one.')


# Chapters are Manim-native: "coded" (an LLM writes each scene, timed to the narration) or "diagram" (the declarative
# vocabulary drawn by a trusted renderer). The image route (imageworld.py) is dormant: picture extraction kept
# producing duplicates, mismatched cut-outs and ghost patches.
ROUTES = ('coded', 'diagram')
TIERS = ('routine', 'involved', 'novel')
FORMS = ('coded', 'slide')      # chapter routes inside a coded lesson
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def luminance(colour):
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return .2126 * r + .7152 * g + .0722 * b


def theme_errors(theme):
    if not isinstance(theme, dict) or not all(HEX.match(str(theme.get(k, ''))) for k in ('background', 'accent', 'text')):
        return ['theme needs "background", "accent" and "text" as #rrggbb colours']
    errors = []
    if luminance(theme['background']) > .2:
        errors.append('theme background must be dark (the animation colours are bright)')
    if luminance(theme['text']) < .6:
        errors.append('theme text colour must be light')
    return errors


def plan_errors(plan, evidence_ids, subject_hint, route='diagram', history=False):
    errors = []
    if route == 'coded':
        errors += theme_errors(plan.get('theme'))
        from .slides import non_scene_words
        if non_scene_words((plan.get('theme') or {}).get('picture_style')):
            errors.append('theme picture_style must be a realistic illustration style for real-world scenes, not '
                          'icons, pictograms, line art or diagrams')
    chapters = plan.get('chapters') or []
    if not 2 <= len(chapters) <= 8:
        errors.append('Use 2 to 8 chapters')
    for i, c in enumerate(chapters):
        if c.get('id') != f'c{i + 1}':
            errors.append(f'Chapter ids must be c1, c2, ... in order (got {c.get("id")})')
        bad = [s for s in c.get('source_ids', []) if s not in evidence_ids]
        if evidence_ids and (bad or not c.get('source_ids')):
            errors.append(f"{c.get('id')}: cite at least one source id from the evidence; unknown: {bad}")
        if route == 'coded' and c.get('route') not in FORMS:
            errors.append(f"{c.get('id')}: route must be \"coded\" (animation) or \"slide\"")
        elif route != 'coded' and c.get('route') != route:
            errors.append(f"{c.get('id')}: route must be \"{route}\"")
        if c.get('history') and (not history or c.get('route') != 'slide'):
            errors.append(f"{c.get('id')}: " + ('history chapters are always slides' if history else
                                                 'the teacher did not ask for historical context; set "history": false'))
        if route == 'coded' and c.get('route') == 'slide':
            if len(str(c.get('visual', '')).split()) < 8:
                errors.append(f"{c.get('id')}: say in at least 8 words what the slide cards show")
            if len(c.get('demonstrations') or []) > 3:
                errors.append(f"{c.get('id')}: give at most 3 demonstrations")
            continue
        if route == 'coded':
            if c.get('complexity') not in TIERS:
                errors.append(f"{c.get('id')}: complexity must be routine, involved or novel")
            if len(str(c.get('visual', '')).split()) < 15:
                errors.append(f"{c.get('id')}: describe the visual storyboard (what is on screen and what moves) in at least 15 words")
        if route == 'diagram':
            errors += [f"{c.get('id')} diagram: {e}" for e in diagram_spec.spec_errors(c.get('diagram'))]
            kinds = [e.get('type') for e in (c.get('diagram') or {}).get('elements', [])]
            if not any(k in ('shape', 'graph', 'number_line', 'path_motion', 'bars') for k in kinds):
                errors.append(f"{c.get('id')}: a diagram needs a visual element (shape, graph, number_line, path_motion or bars), not just text")
            if sum(k in ('note', 'cards', 'table') for k in kinds) > 1:
                errors.append(f"{c.get('id')}: use at most one text element (note, cards or table); show the rest visually")
        demos = c.get('demonstrations') or []
        if not 1 <= len(demos) <= 3 or any(len(str(d.get('watch', '')).split()) < 5 or not d.get('proves') for d in demos):
            errors.append(f"{c.get('id')}: give 1-3 demonstrations, each saying what the viewer watches happen and what it proves")
    return errors


def _diagram_visuals():
    return ('Every chapter is an animated DIAGRAM drawn natively in Manim (exact geometry, LaTeX maths, moving '
            'bodies, live force and velocity arrows, graphs). Physical situations are shown with the diagram elements '
            '(a stone on a string is a path_motion circle with a mover; forces are vectors).\n'
            'Declare the diagram as 1-5 ELEMENTS from the list below; give only '
            'measurements and values, never positions (code lays out the screen and computes all geometry). Use '
            'enough elements to keep the screen meaningful for the whole chapter. Every diagram needs at least one '
            'visual element (shape, graph, number_line, path_motion, bars) and at most one text element (note, cards, '
            'table).\n' + diagram_spec.prompt_reference() + '\n')


FORM_GUIDE = (
    'CHAPTER FORM: give each chapter a "route". "coded" = an animation a coder writes in Manim; use it only when '
    'the learner must WATCH something change over time (motion, a process, a quantity changing, a construction '
    'where order matters). "slide" = cards revealed as the narrator speaks: a picture card with a heading and one '
    'line, or 2-4 numbered steps, stages or points, or a two-sided comparison; use it for definitions, context, '
    'real-world examples, classifications, recaps and "why it matters". Animation is the expensive part of a lesson: '
    'a chapter a slide teaches equally well must be a slide, and a slide chapter needs no demonstrations ([]). '
    'Slide cards are fixed layouts: a picture card (a generated real-world scene behind a heading, one line and an '
    'optional banner) or a steps, cycle or comparison card (numbered boxes with a title and one line each); plan '
    'slides with these, not custom layouts. Pictures suit context, applications, real examples and history; an '
    'abstract method or recap uses steps or comparison cards, not pictures. '
    'Give the lesson one "theme" for every chapter: a dark background, an accent and a light text colour, and '
    'one picture style for the slide pictures: a realistic illustration style (never icons, pictograms, line art '
    'or diagrams).\n')


def history_guide(history, evidence):
    if not history:
        return 'Do not add historical context: every chapter has "history": false.\n'
    return ('HISTORICAL CONTEXT: the teacher asked for it. Where it fits naturally and makes the idea more '
            'interesting, tell the story behind it: who found it, when, the problem they were trying to solve, how '
            'the idea changed. Decide where and how much; history always goes in slide chapters marked "history": '
            'true. ' + from_evidence(evidence, 'Names, dates and claims must come from the evidence. ',
                                     'Use only well-established history: no invented quotations, no uncertain dates. ') + '\n')


CODED_VISUALS = (
    'Every animated chapter is a Manim scene that a coder writes from your storyboard and times to the recorded '
    'narration: anything Manim can draw in 2D is available (LaTeX maths and transforms between equations, axes and '
    'live plots, vectors that update as things move, geometry constructions, bars and number lines, moving bodies, '
    'counters, zoom-in insets, side-by-side comparisons). For each chapter write "visual": a concrete storyboard '
    'of what is on screen, where (left/right/top), what moves or transforms and in what order, with the actual '
    'values to draw. Name one colour meaning for the whole lesson in "colours" (dark navy background; cyan, green, '
    'red, amber, violet available). Keep on-screen text short: the narrator explains.\n' + TIER_GUIDE + '\n' +
    FORM_GUIDE)


DIAGRAM_INTRO = (
    'THIS IS A VISUAL LESSON. Plan it as things the viewer WATCHES HAPPEN, then the words that go with them. '
    'For each chapter first write 1-3 DEMONSTRATIONS: "watch" = what visibly moves or changes on screen '
    '(Earth travels round the Sun; the stone flies off along the tangent when the string breaks; squares grow '
    'on the triangle\'s sides), and "proves" = the one idea that motion shows. A chapter that would work as a '
    'static slide is a failed chapter. Facts and numbers support the demonstrations; they are never the '
    'demonstration.\n'
    'Structure: chapter c1 is a hook that SHOWS something surprising moving within its first sentence; middle '
    'chapters each demonstrate one idea; the last chapter replays the key motion as a recap. Include a common '
    'misconception if one fits, and show it being proved wrong.\n')

CODED_INTRO = (
    'Plan what the viewer SEES and the words that go with it. For each animated ("coded") chapter first write 1-3 '
    'DEMONSTRATIONS: "watch" = what visibly moves or changes on screen (Earth travels round the Sun; the stone '
    'flies off along the tangent when the string breaks; squares grow on the triangle\'s sides), and "proves" = '
    'the one idea that motion shows. Facts and numbers support the demonstrations; they are never the '
    'demonstration.\n'
    'Structure: c1 is a hook that grabs attention in its first sentence (usually something surprising moving); '
    'middle chapters each teach one idea; the last chapter recaps. Include a common misconception if one fits, '
    'and show it being proved wrong.\n')


def make_plan(planner, reviewer, request, scope, evidence, log=print, route='diagram'):
    level = scope['class']
    evidence_ids = {e['id'] for e in evidence}
    subject_hint = scope.get('subject')
    prompt = (
        'Plan a narrated animated lesson for Indian students. It must teach the request accurately, ' +
        from_evidence(evidence, 'using only the evidence, ', 'from well-established knowledge (no sources were gathered), ') +
        'at the level of ' + audience(level) + '. Tone: ' + TONE[level] + '.\n'
        + (CODED_INTRO + CODED_VISUALS + history_guide(request.get('include_history'), evidence)
           if route == 'coded' else DIAGRAM_INTRO + _diagram_visuals())
        + ('SOLVER MODE: the topic is a question to solve. Chapters: (1) pose the question and why it is interesting; '
           '(2) what is given and what is asked, with units; (3+) the method and each working step as animated '
           'chapters, every number computed exactly; then the answer with units and a quick sense check; '
           'finish with a common trap students fall into. Use the evidence for the laws and definitions.\n'
           if request['mode'] == 'solver' else '')
        + 'Chapter seconds should add up to about ' + str(request['duration_seconds']) + ' (advisory).\n'
        'REQUEST:\n' + json.dumps({k: request[k] for k in ('topic', 'mode', 'notes')}, ensure_ascii=False) +
        '\nSCOPE:\n' + json.dumps(scope, ensure_ascii=False) + '\nEVIDENCE:\n' + evidence_text(evidence) +
        '\nReturn JSON: ' + (CODED_SCHEMA if route == 'coded' else PLAN_SCHEMA))
    check = lambda p: _raise(plan_errors(p, evidence_ids, subject_hint, route, bool(request.get('include_history'))))
    feedback, last_valid, plan, rounds, patches = '', None, None, [], 0
    for attempt in range(4):
        if plan is None:   # a full (re)write: the first draft, a structural problem, or patches that did not pass
            try:
                plan = planner.call(f'plan-{attempt}', prompt + feedback, thinking=8000, max_tokens=16000, attempts=3,
                                    validate=check)
            except RuntimeError as exc:   # validation kept failing: try again with the errors as feedback
                log('Re-planning to fix format problems')
                feedback = '\nThe previous plan was rejected by automatic checks; fix exactly these problems:\n' + str(exc)[-1500:]
                continue
        review = rubric.review(reviewer, f'plan-review-{attempt}', 'plan', (
            'Review this lesson plan for ' + audience(level) + '. ' +
            from_evidence(evidence, 'Facts must agree with the evidence. ', 'No sources were used: judge every fact '
                          'against standard knowledge. ') +
            ('Judge the depth against the topic (no class-level limit). ' if level == 'open' else
             'Nothing may be beyond the class level without explanation. ') +
            'Style preferences lower no score.' + earlier_rounds(rounds) + '\nREQUEST:\n' +
            json.dumps(request, ensure_ascii=False) + '\nEVIDENCE:\n' + evidence_text(evidence) + '\nPLAN:\n' +
            json.dumps(plan, ensure_ascii=False)),
            route=route, thinking=2048, max_tokens=5000)
        if review['decision']['pass']:
            return plan, review
        majors = rubric.findings(review)
        rounds.append(majors)
        if last_valid is None or review['decision']['score'] >= last_valid[1]['decision']['score']:
            last_valid = (plan, review)
        failed = {f['criterion'] for f in review['decision']['failed']}
        if not failed & STRUCTURAL and patches < 2:
            log(f'Repairing the plan in place ({len(majors)} criteri{"a" if len(majors) > 1 else "on"} below the minimum)')
            try:
                plan, _ = patch.repair(planner, f'plan-patch-{attempt}', 'plan', plan, majors,
                                       'EVIDENCE:\n' + evidence_text(evidence), check)
                patches += 1
                continue
            except RuntimeError:
                log('The repair did not apply cleanly; rewriting the plan')
        else:
            log(f'Rewriting the plan after review ({len(majors)} criteri{"a" if len(majors) > 1 else "on"} below the minimum)')
        feedback = ('\nRevise this plan; these review scores are below the required minimum:\n' +
                    json.dumps(plan, ensure_ascii=False) + '\n' + json.dumps(majors, ensure_ascii=False))
        plan, patches = None, 0
    if last_valid is not None:   # passes every code check; the best-scored plan is kept, its open points noted
        plan, review = last_valid
        review = {**review, 'accepted_with_notes': True}
        log('Using the best-scored plan; the reviewer\'s remaining notes are recorded for the teacher')
        return plan, review
    raise RuntimeError('The lesson plan did not pass its checks after four rounds: ' + feedback[-600:])


STRUCTURAL = {'order', 'coverage'}   # failures that may need chapters added, removed or reordered: rewrite


def earlier_rounds(rounds):
    """The review log for plan and script reviewers: do not contradict a finding the writer already acted on."""
    if not rounds:
        return ''
    return ('\nEARLIER REVIEW ROUNDS (oldest first); the document was revised after each. Never lower a score for '
            'the opposite of an earlier finding that was acted on; keep a low score for an earlier finding only if '
            'the problem is still there:\n' + json.dumps(rounds, ensure_ascii=False)[-5000:])


def _raise(errors):
    if errors:
        raise ValueError('; '.join(errors))


# ------------------------------------------------------------------ script
def script_errors(script, plan):
    errors = []
    by_id = {c['id']: c for c in plan['chapters']}
    got = [c.get('id') for c in script.get('chapters', [])]
    if got != list(by_id):
        errors.append(f'Write chapters {list(by_id)} in order (got {got})')
        return errors
    for sc in script['chapters']:
        plan_c = by_id[sc['id']]
        points = sc.get('points') or []
        if not 1 <= len(points) <= 8:
            errors.append(f"{sc['id']}: use 1-8 narration points")
        texts = {}
        for j, p in enumerate(points):
            if p.get('id') != f"{sc['id']}p{j + 1}":
                errors.append(f"{sc['id']}: point ids must be {sc['id']}p1, {sc['id']}p2, ...")
            words = len(str(p.get('narration', '')).split())
            if not 4 <= words <= 120:
                errors.append(f"{p.get('id')}: each point has 4-120 words (has {words})")
            texts[p.get('id')] = p.get('narration', '')
            unheard = leftovers(str(p.get('narration', '')))
            if unheard:
                errors.append(f"{p.get('id')}: narration is read aloud; write {' '.join(unheard)} as spoken words")
        if plan_c['route'] == 'slide':
            errors += slide_errors(sc, points)
            continue
        cues = sc.get('cues') or []
        if not cues:
            errors.append(f"{sc['id']}: add cues that show what the narration says")
        objects = {o['id']: o for o in (plan_c.get('scene') or {}).get('objects', [])}
        paths = {p['id'] for p in (plan_c.get('scene') or {}).get('paths', [])}
        order = list(texts)
        for c in cues:
            where = f"{sc['id']} cue {c.get('verb') or c.get('id')}"
            if c.get('point') not in texts:
                errors.append(f'{where}: point must be one of {order}')
                continue
            if not phrase_in_text(texts[c['point']], str(c.get('phrase', ''))):
                errors.append(f"{where}: phrase \"{c.get('phrase')}\" must be copied exactly from {c['point']}")
            if c.get('until'):
                up = c.get('until_point', c['point'])
                if up not in texts or order.index(up) < order.index(c['point']) or not phrase_in_text(texts[up], c['until']):
                    errors.append(f"{where}: until \"{c.get('until')}\" must be copied exactly from {up} (same or later point)")
            if plan_c['route'] == 'coded':
                if not 3 <= len(str(c.get('show', '')).split()) <= 45:
                    errors.append(f'{where}: "show" must say in 3-45 words what appears or changes on screen')
                continue
            if plan_c['route'] == 'image':
                verb = c.get('verb')
                if verb not in IMAGE_VERBS:
                    errors.append(f'{where}: unknown verb')
                    continue
                if verb not in ('title', 'trace') and c.get('object') not in objects:
                    errors.append(f"{where}: object must be one of {list(objects)}")
                if verb in MOTION_VERBS and not objects.get(c.get('object'), {}).get('moves'):
                    errors.append(f"{where}: only moving objects ({[k for k, o in objects.items() if o.get('moves')]}) can {verb}")
                if verb in ('move_along', 'trace') and c.get('path') not in paths:
                    errors.append(f"{where}: path must be one of {sorted(paths)}")
                if verb == 'arrow' and str(c.get('direction', '')).startswith('toward:') and c['direction'][7:] not in objects:
                    errors.append(f'{where}: arrow target must be an object')
                if verb in ('label', 'title', 'arrow') and len(str(c.get('text', '')).split()) > 7:
                    errors.append(f'{where}: on-screen text must be short')
            else:
                errors += [f'{where}: {e}' for e in diagram_spec.cue_errors(c, plan_c.get('diagram') or {})]
        if plan_c['route'] == 'coded':
            silent = [p for p in order if not any(c.get('point') == p for c in cues)]
            if silent:
                errors.append(f"{sc['id']}: give every narration point at least one cue (none for {silent})")
            first = lambda t: re.sub(r'\W+', '', (str(t).split() or [''])[0].lower())
            if sc['id'] == 'c1' and points and not any(c.get('point') == points[0].get('id') and first(c.get('phrase', ''))
                                                       == first(points[0].get('narration', '')) for c in cues):
                errors.append('c1: the lesson\'s first words must start a cue (something moving at once)')
            continue
        # A visual lesson: every chapter shows something happen; highlights alone are a slide.
        verbs = [str(c.get('verb')) for c in cues]
        motion = {'move_along', 'rotate', 'swing', 'shake', 'show', 'trace', 'zoom', 'move', 'plot', 'count', 'release',
                  'squares', 'next_step', 'transform', 'jump', 'vectors', 'release', 'mark', 'focus'}
        if cues and not any(v in motion for v in verbs):
            errors.append(f"{sc['id']}: add cues where something moves, grows or changes (not only highlights and labels)")
        if len(verbs) >= 4 and verbs.count('highlight') > len(verbs) / 2:
            errors.append(f"{sc['id']}: too many highlights; show the idea with motion instead")
        if sc['id'] == 'c1' and points and not any(c.get('point') == points[0].get('id') and str(c.get('verb')) in motion
                                                   - {'show', 'mark', 'focus'} for c in cues):
            errors.append('c1: the first sentence must be paired with something moving (a motion cue on c1p1)')
    return errors


def check_numbers(planner, script, attempt):
    """Every calculation stated in the narration is re-evaluated by code; returns wrong ones as issues."""
    from .diagram_spec import evaluate as arithmetic
    narration = {sc['id']: [p['narration'] for p in sc['points']] for sc in script['chapters']}
    for sc in script['chapters']:
        for card in sc.get('slides') or []:
            shown = [card.get('heading'), card.get('summary'), card.get('banner')] + list(card.get('labels') or []) + \
                list(card.get('details') or [])
            narration[sc['id']].append('On screen: ' + ' ; '.join(str(x) for x in shown if x))
        for e in (sc.get('_diagram') or {}).get('elements', []):
            shown = e.get('steps') or [f"{i.get('title', '')}: {i.get('value', '')}" for i in e.get('items', [])]
            if shown:
                narration[sc['id']].append('On screen: ' + ' ; '.join(map(str, shown)))
    found = planner.call(f'numbers-{attempt}', (
        'List every calculation the narration states or implies with a numerical result (for example "twenty '
        'seconds divided by ten is two seconds", "2 × 3.14 × 50 is about 314 metres"). For each give the arithmetic '
        'using only numbers, + - * / ** ( ) and pi, sqrt, sin, cos, tan, radians; the result the narration states; '
        'and the relative tolerance the wording allows (0.001 for exact, 0.02 for "about"). Ignore numbers that '
        'are not calculated. Return {"calculations":[{"chapter":str,"words":str,"expression":str,"stated":number,'
        '"tolerance":number}]}.\nNARRATION:\n' + json.dumps(narration, ensure_ascii=False)), thinking=1024, max_tokens=4500)
    wrong = []
    for c in found.get('calculations', []):
        try:
            value = arithmetic(str(c['expression']))
            stated = float(c['stated'])
        except (ValueError, KeyError, TypeError):
            continue
        tolerance = min(.05, max(.001, float(c.get('tolerance') or .001)))
        if abs(value - stated) > tolerance * max(1.0, abs(value)):
            wrong.append({'severity': 'major', 'where': c.get('chapter', ''), 'problem':
                          f'"{c.get("words", "")}" states {stated}, but {c["expression"]} = {value:.6g}',
                          'fix': f'Use the correct value {value:.4g} or correct the numbers in the sentence.'})
    return wrong


def repair_phrases(script, judge=None, log=print):
    """Patch cue phrases a model paraphrased to the exact narration words (strong match in code; borderline
    matches confirmed by a small 'same meaning?' call to the local model). Returns the number patched."""
    patched = 0
    for sc in script.get('chapters', []):
        for p in sc.get('points', []):
            p['narration'] = speakable(p.get('narration', ''))
        for c in sc.get('cues', []):
            for key in ('phrase', 'until'):
                if c.get(key):
                    c[key] = speakable(c[key])
        for card in sc.get('slides') or []:   # reveal phrases anchor to the spoken narration too
            if isinstance(card.get('reveal'), list):
                card['reveal'] = [speakable(str(r)) for r in card['reveal']]
        texts = {p.get('id'): p.get('narration', '') for p in sc.get('points', [])}
        for c in sc.get('cues', []):
            for key, point_key in (('phrase', 'point'), ('until', 'until_point')):
                phrase = c.get(key)
                point = c.get(point_key) or c.get('point')
                if not phrase or point not in texts or phrase_in_text(texts[point], phrase):
                    continue
                span, score = closest_span(texts[point], phrase)
                ok = span and score >= .8
                if span and not ok and score >= .5 and judge is not None:
                    try:
                        verdict = judge.call('same-meaning', (
                            'Do these two phrases refer to the same moment of the narration (same meaning, small wording '
                            'differences allowed)? Return {"same":bool}.\nA: ' + phrase + '\nB: ' + span),
                            thinking=0, max_tokens=300, attempts=1)
                        ok = verdict.get('same') is True
                    except RuntimeError:
                        ok = False
                if ok:
                    c[key] = span
                    patched += 1
    if patched:
        log(f'Matched {patched} reworded cue phrase(s) to the exact narration')
    return patched


CODED_CUES = (
    'Each animated ("coded") chapter is animated by a coder who follows your cues exactly in time. A cue says what appears or changes '
    'on screen at that moment: {"point","phrase","until"?,"until_point"?,"show":"3-45 words: what is drawn, moves, '
    'transforms or is highlighted, with the values"}. Follow the chapter\'s storyboard ("visual") and '
    'demonstrations. Give every narration point at least one cue, about one cue per sentence, and start a cue on '
    'the lesson\'s very first words. Use "until" for motions that last while a stretch of narration is spoken.\n')


def make_script(planner, reviewer, request, scope, plan, evidence, log=print, numbers=None, judge=None):
    level = scope['class']
    words = int(request['duration_seconds'] * 2.4)
    coded = any(c.get('route') == 'coded' for c in plan['chapters'])
    slides = any(c.get('route') == 'slide' for c in plan['chapters'])
    prompt = (
        'Write the narration for this lesson plan, chapter by chapter, for ' + audience(level) + '. Tone: ' +
        TONE[level] + '. It is spoken by one narrator over animation, so write for the ear: natural Indian English, '
        'vivid, concrete, one idea at a time, with the hook really hooking. ' + from_evidence(evidence, 'Use only facts from the evidence. ',
        'Use only well-established facts; no invented figures, dates or quotations. ') +
        'About ' + str(words) + ' words in total (advisory). Write numbers and units the way they should be '
        'spoken when that avoids ambiguity.\n'
        'Write the narration TO THE DEMONSTRATIONS in the plan: each demonstration is narrated while it happens '
        '("watch the stone... now the string breaks... it flies straight off"), so the words describe what the '
        'viewer is watching. The very first sentence of the lesson must be paired with something moving.\n'
        'While writing, decide what the viewer SEES at each moment and add CUES. A cue is anchored to an exact '
        'phrase copied from one point ("point" and "phrase"); optionally it lasts "until" another exact phrase '
        '(in the same point, or in a later point given as "until_point"). Never give coordinates or times.\n'
        + (SLIDE_GUIDE if slides else '')
        + (CODED_CUES if coded else
           'Show motion while the narration describes it. Cues use these verbs on the chapter\'s declared diagram '
           'elements ("target" is an element id, or '
           'element.part such as "vt.car", "tri.AB", "cards.d"):\n' + diagram_spec.verb_reference() + '\n'
           'Elements without a "show" cue are visible from the start of the chapter; reveal equation lines with '
           'next_step while they are spoken; run counters and movers while the narration describes them.\n') +
        'Narration is read aloud by a voice: write every symbol and unit as spoken words ("v squared over r", '
        '"metres per second squared"), never m/s², =, or bare letters for units. Equations go on screen as cues.\n'
        'Return JSON {"chapters":[{"id":"c1","points":[{"id":"c1p1","narration":str}],"cues":[...]}]}' +
        (' (slide chapters give "slides":[...] instead of "cues")' if slides else '') + '\n'
        'PLAN:\n' + json.dumps(plan, ensure_ascii=False) + '\nEVIDENCE:\n' + evidence_text(evidence) +
        '\nTEACHER NOTES:\n' + (request.get('notes') or 'none'))
    def check(s):
        repair_phrases(s, judge, log)
        _raise(script_errors(s, plan))
        patch.number_cues(s)

    feedback, last_valid, script, rounds, patches = '', None, None, [], 0
    for attempt in range(4):
        if script is None:   # a full (re)write: the first draft, or patches that did not pass
            try:
                script = planner.call(f'script-{attempt}', prompt + feedback, thinking=8000, max_tokens=16000,
                                      attempts=3, validate=check)
                patch.number_cues(script)
            except RuntimeError as exc:
                log('Rewriting the narration to fix format problems')
                feedback = '\nThe previous script was rejected by automatic checks; fix exactly these problems:\n' + str(exc)[-1500:]
                continue
        review = rubric.review(reviewer, f'script-review-{attempt}', 'script', (
            'Review this narration of a science/maths video for ' + audience(level) + '. ' +
            from_evidence(evidence, 'Facts and numbers must agree with the evidence. ', 'No sources were used: '
                          'judge every fact and number against standard knowledge. ') +
            'Slide cards (if any) must be accurate, readable and match their narration point. Style preferences '
            'lower no score.' + earlier_rounds(rounds) + '\nEVIDENCE:\n' + evidence_text(evidence) + '\nPLAN:\n' +
            json.dumps(plan, ensure_ascii=False) + '\nSCRIPT:\n' + json.dumps(script, ensure_ascii=False)),
            thinking=2048, max_tokens=5000)
        majors = rubric.findings(review)
        if review['decision']['pass']:
            for sc in script['chapters']:
                plan_c = next(c for c in plan['chapters'] if c['id'] == sc['id'])
                sc['_diagram'] = plan_c.get('diagram') if plan_c['route'] == 'diagram' else None
            try:
                wrong = check_numbers(numbers or planner, script, attempt)
            except RuntimeError as exc:
                log('Calculation check could not run; continuing and recording it')
                review = {**review, 'numbers_check': f'not run: {str(exc)[:200]}'}
                wrong = []
            for sc in script['chapters']:
                sc.pop('_diagram', None)
            if not wrong:
                return script, review
            majors = wrong            # never kept as a fallback: wrong arithmetic is not a note
            log(f'Correcting {len(wrong)} calculation(s) in the narration')
        else:
            rounds.append(majors)
            if last_valid is None or review['decision']['score'] >= last_valid[1]['decision']['score']:
                last_valid = (script, review)
        if patches < 2:   # wrong calculations and review findings are fixed in place
            if not review['decision']['pass']:
                log(f'Repairing the narration in place ({len(majors)} criteri{"a" if len(majors) > 1 else "on"} below the minimum)')
            try:
                script, _ = patch.repair(planner, f'script-patch-{attempt}', 'script', script, majors,
                                         'PLAN:\n' + json.dumps(plan, ensure_ascii=False) + '\nEVIDENCE:\n' +
                                         evidence_text(evidence), check)
                patches += 1
                continue
            except RuntimeError:
                log('The repair did not apply cleanly; rewriting the narration')
        else:
            log('Rewriting the narration after review')
        feedback = ('\nRevise this script; these problems must be fixed:\n' +
                    json.dumps(script, ensure_ascii=False) + '\n' + json.dumps(majors, ensure_ascii=False))
        script, patches = None, 0
    if last_valid is not None:
        script, review = last_valid
        review = {**review, 'accepted_with_notes': True}
        log('Using the best-scored narration; the reviewer\'s remaining notes are recorded for the teacher')
        return script, review
    raise RuntimeError('The narration did not pass its checks after four rounds: ' + feedback[-600:])


def diagram_chapter(planner, chapter, script_chapter, evidence, feedback, name):
    """Design (or revise) one diagram chapter: returns {"diagram": spec, "cues": [...]} validated in code."""
    texts = {p['id']: p['narration'] for p in script_chapter['points']}

    def check(result):
        repair_phrases({'chapters': [{'points': script_chapter['points'], 'cues': result.get('cues') or []}]})
        errors = [f'diagram: {e}' for e in diagram_spec.spec_errors(result.get('diagram'))]
        for c in result.get('cues') or []:
            if c.get('point') not in texts or not phrase_in_text(texts[c['point']], str(c.get('phrase', ''))):
                errors.append(f"cue phrase \"{c.get('phrase')}\" must be copied exactly from point {c.get('point')}")
            elif not errors:
                errors += diagram_spec.cue_errors(c, result['diagram'])
        if not result.get('cues'):
            errors.append('add cues')
        _raise(errors)
    return planner.call(name, (
        'Design the animated diagram for this chapter of a narrated school lesson. The narration is final; '
        'choose 1-5 elements and cues anchored to exact phrases of the narration so the screen shows what is '
        'being said. Give only measurements and values, never positions.\n' + diagram_spec.prompt_reference() +
        '\nVERBS:\n' + diagram_spec.verb_reference() + '\nReturn {"diagram":{"layout":...,"elements":[...]},'
        '"cues":[{"verb","target","point","phrase","until"?,"until_point"?,...}]}.\nCHAPTER:\n' +
        json.dumps({k: chapter.get(k) for k in ('title', 'objective')}, ensure_ascii=False) + '\nNARRATION POINTS:\n' + json.dumps(texts, ensure_ascii=False) +
        '\nEVIDENCE:\n' + evidence_text(evidence, 5000) +
        ('\nFIX THESE PROBLEMS FROM THE PREVIOUS VERSION:\n' + feedback if feedback else '')),
        thinking=2048, max_tokens=12000, attempts=3, validate=check)
