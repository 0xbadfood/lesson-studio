"""One review method for every review in the pipeline: the model scores fixed criteria, code decides.

Each review kind has a rubric: criteria with a question and the minimum score code accepts. The reviewer model scores
every criterion 0-3 (0 wrong or missing, 1 a serious problem, 2 a small flaw, 3 right) and gives a reason and a fix
below 3. It never decides pass or fail: decide() does, from the scores and the minimums. A criterion below its
minimum fails the review and its reason goes back to the writer; a score below 3 that meets its minimum is a note.
Correctness criteria accept 2 because the scale reserves 1 or less for any actual error: a 2 is correct but
simplified, so it is a note, never a retry.
The criteria differ per review; the method does not. Minimums can be overridden per lesson (frozen in models.json).
"""
import json

SCALE = ('Score each criterion 0-3: 0 = wrong or missing; 1 = a serious problem; 2 = a small flaw that does not '
         'mislead or block understanding; 3 = right. Any actual error of fact, number, science, maths or history, '
         'however small, scores at most 1. Use 2 for what is correct but simplified, approximate, illustrative or '
         'imprecise in a way that does not mislead (an illustrative constant, a schematic perspective). Score only '
         'these criteria; anything else is out of scope. For '
         'every score below 3 give "reason" (exactly what is wrong and where) and "fix". You do not decide whether '
         'the work passes: the scores do.')

# kind -> [(id, label, question, minimum, routes or None)]
RUBRICS = {
    'plan': [
        ('accuracy', 'Accuracy', 'Every fact, number and storyboard is correct and agrees with the evidence (or with '
         'standard knowledge when there is none), including any history.', 2, None),
        ('order', 'Teaching order', 'The chapters build the idea in a sensible order, each with one clear job.', 2, None),
        ('coverage', 'Coverage and level', 'The plan teaches what was requested at the right depth for the audience, '
         'and nothing needed is missing.', 2, None),
        ('form', 'Chapter forms', 'Each animated (coded) chapter shows something that changes over time; anything a '
         'slide teaches equally well is a slide; no slide chapter needs motion to be understood.', 2, ('coded',)),
        ('visual', 'Visual teaching', 'Every chapter shows something happening (no chapter is a static slide) and its '
         'demonstrations really show the idea.', 2, ('diagram',)),
        ('complexity', 'Complexity ratings', 'Each animated chapter\'s routine/involved/novel rating is honest (a hard '
         'scene is not rated routine).', 2, ('coded',)),
    ],
    'script': [
        ('accuracy', 'Accuracy', 'Every fact and number agrees with the evidence (or standard knowledge when there '
         'is none), on cards as well as in the narration.', 2, None),
        ('explanation', 'Explanation', 'Explanations are correct, clear and in a sensible order.', 2, None),
        ('level', 'Language and level', 'The language suits the audience and is written for the ear.', 2, None),
        ('engagement', 'Engagement', 'The hook really hooks and the narration holds attention.', 2, None),
        ('visual_match', 'Cues and cards', 'Each cue or slide card matches what the narration says at that moment and '
         'is physically sensible.', 2, None),
    ],
    'scene_content': [
        ('science', 'Science and maths', 'Facts, units, physics and maths in the code are correct.', 2, None),
        ('numbers', 'Numbers', 'Every number on screen is computed correctly and matches the narration.', 2, None),
        ('sync', 'Sync with narration', 'At each cue the screen shows what the narration is saying then (follow the '
         'at() calls).', 2, None),
        ('demonstrations', 'Demonstrations', 'The chapter\'s planned demonstrations are actually shown.', 2, None),
    ],
    'scene_frames': [
        ('legibility', 'Legibility', 'No text overlaps other text, lines or shapes; nothing is cut off or outside '
         'the picture.', 2, None),
        ('clarity', 'Clarity', 'Frames are uncluttered and the eye knows where to look.', 2, None),
        ('visual_correctness', 'Visual correctness', 'What is drawn fits the values and labels shown (directions, '
         'proportions, counts).', 2, None),
        ('teaches', 'Teaches the idea', 'The pictures make the narrated idea clear.', 2, None),
    ],
    'diagram_frames': [
        ('legibility', 'Legibility', 'Text is readable; nothing overlaps or is cut off.', 2, None),
        ('correctness', 'Correctness', 'What is drawn is physically and mathematically right for the spec.', 2, None),
        ('cue_visible', 'Cues visible', 'What each cue describes is visible in its frame.', 2, None),
    ],
    'picture': [
        ('no_text', 'No text', 'The picture contains no text, letters, numbers, labels, logos, charts or diagrams.', 3, None),
        ('matches', 'Matches the description', 'It shows what the description asks.', 2, None),
        ('not_misleading', 'Not misleading', 'Nothing in it is scientifically or historically misleading.', 2, None),
        ('artefacts', 'No artefacts', 'No malformed bodies, hands or objects.', 2, None),
    ],
}

KIND_LABELS = {'plan': 'Plan review', 'script': 'Script review', 'scene_content': 'Scene content review (code)',
               'scene_frames': 'Scene frame review', 'diagram_frames': 'Diagram frame review (diagram route)',
               'picture': 'Slide picture check'}

_overrides = {}


def defaults():
    return {kind: {cid: minimum for cid, _, _, minimum, _ in items} for kind, items in RUBRICS.items()}


def clean_rules(rules):
    """Validated minimums, keeping only the ones that differ from the defaults."""
    base, out = defaults(), {}
    for kind, values in (rules or {}).items():
        if kind not in base or not isinstance(values, dict):
            raise ValueError(f'Unknown review: {kind}')
        for cid, value in values.items():
            if cid not in base[kind] or not isinstance(value, int) or not 0 <= value <= 3:
                raise ValueError(f'{kind}.{cid}: the minimum must be a whole number 0-3')
            if value != base[kind][cid]:
                out.setdefault(kind, {})[cid] = value
    return out


def public(rules):
    return [{'kind': kind, 'label': KIND_LABELS[kind],
             'criteria': [{'id': cid, 'label': label, 'question': question, 'default': minimum,
                           'minimum': (rules or {}).get(kind, {}).get(cid, minimum),
                           'routes': list(routes) if routes else None}
                          for cid, label, question, minimum, routes in items]}
            for kind, items in RUBRICS.items()]


def configure(rules):
    """Per-lesson minimums {kind: {criterion: minimum}} (from the lesson's frozen settings)."""
    _overrides.clear()
    for kind, values in (rules or {}).items():
        _overrides[kind] = {k: int(v) for k, v in values.items()}


def criteria(kind, route=None):
    return [{'id': cid, 'label': label, 'question': question,
             'minimum': _overrides.get(kind, {}).get(cid, minimum)}
            for cid, label, question, minimum, routes in RUBRICS[kind] if routes is None or route in routes]


def prompt(kind, route=None):
    """The rubric part of a review prompt."""
    items = criteria(kind, route)
    lines = '\n'.join(f'- {c["id"]}: {c["question"]}' for c in items)
    shape = ', '.join(f'"{c["id"]}":{{"score":0-3,"reason":str,"fix":str}}' for c in items)
    return f'{SCALE}\nCRITERIA:\n{lines}\nReturn {{"scores":{{{shape}}}}}.'


def check(kind, route=None):
    """A validate() hook for the model call: every criterion scored 0-3, with a reason below 3."""
    def validate(result):
        scores = result.get('scores') if isinstance(result, dict) else None
        if not isinstance(scores, dict):
            raise ValueError('Return {"scores": {...}} with one entry per criterion')
        problems = []
        for c in criteria(kind, route):
            s = scores.get(c['id'])
            if not isinstance(s, dict) or not isinstance(s.get('score'), int) or not 0 <= s['score'] <= 3:
                problems.append(f'{c["id"]}: give an integer "score" 0-3')
            elif s['score'] < 3 and not str(s.get('reason', '')).strip():
                problems.append(f'{c["id"]}: a score below 3 needs a "reason"')
        if problems:
            raise ValueError('; '.join(problems))
    return validate


def decide(kind, result, route=None):
    """Code-owned decision: pass only when every criterion meets its minimum."""
    scores = (result or {}).get('scores') or {}
    failed, notes, total = [], [], 0
    items = criteria(kind, route)
    for c in items:
        s = scores.get(c['id']) or {}
        score = s.get('score') if isinstance(s.get('score'), int) else 0
        total += score
        entry = {'criterion': c['id'], 'label': c['label'], 'score': score, 'minimum': c['minimum'],
                 'reason': str(s.get('reason', '')), 'fix': str(s.get('fix', ''))}
        if score < c['minimum']:
            failed.append(entry)
        elif score < 3:
            notes.append(entry)
    return {'pass': not failed, 'score': round(total / (3 * len(items)), 3) if items else 1.0,
            'failed': failed, 'notes': notes}


def review(model, name, kind, body, *, route=None, images=(), thinking=2048, max_tokens=5000):
    """Ask for scores, then decide in code. Returns {"scores":..., "decision":...}."""
    result = model.call(name, body + '\n' + prompt(kind, route), images=images, thinking=thinking,
                        max_tokens=max_tokens, validate=check(kind, route))
    return {'scores': result['scores'], 'decision': decide(kind, result, route)}


def overrule(result, criterion, why):
    """Code-owned: an arbiter ruled a failed criterion a false positive; it becomes a note and pass is recomputed."""
    decision = result['decision']
    for f in list(decision['failed']):
        if f['criterion'] == criterion:
            decision['failed'].remove(f)
            decision['notes'].append({**f, 'overruled': why})
    decision['pass'] = not decision['failed']
    return result


def findings(*reviews):
    """The failed criteria of one or more reviews, as feedback for the writer."""
    return [{k: f[k] for k in ('label', 'score', 'minimum', 'reason', 'fix')}
            for r in reviews for f in r['decision']['failed']]


def as_text(*reviews):
    return json.dumps(findings(*reviews), ensure_ascii=False)
