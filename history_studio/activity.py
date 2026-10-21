"""Behind the scenes (user, 2026-10-21): what the pipeline is doing right now, in plain words, for the studio's film
page and as the groundwork for the next studio UI.

Everything is read from the film project's event log (jobs.sqlite3, written by infofilm as it works) and the
planning folders beside it; nothing here changes a film. Only the current attempt is shown: a film made again in the
same project starts at its latest "pipeline:research" event.

activity(project) -> {
  steps:   the pipeline's steps with state and duration,
  work:    sections for what each step is made of (planning rounds and review scores, narration points, the test
           learner, animated beats, pictures and their reviews, motion clips, the final render),
  log:     the latest events as sentences (newest first),
  models:  model calls, planner cost (USD, as billed) and reviewer tokens,
}
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

STEPS = [('research', 'Reading the book and sources'), ('evidence', 'Gathering the facts and planning the idea'),
         ('creative', 'Creative brief'), ('narration', 'Writing and recording the narration'),
         ('timing', 'Timing every word'), ('scenes', 'Planning the scenes and coding animations'),
         ('images', 'Painting the pictures'), ('clips', 'Bringing pictures to life'), ('music', 'Music'),
         ('video', 'Final cut')]
LOOPS = [(r'evidence', 'Gathering the facts from the book'),
         (r'idea-plan', 'Planning the idea: analogy, guide and beats'),
         (r'creative-brief', 'Creative brief'),
         (r'script-\d+', 'Writing the narration'),
         (r'script-\d+-land(\d+)', 'Rewriting so the idea lands, round {0}'),
         (r'visual-beats-\d+', 'Planning the scenes'),
         (r'visual-beats-\d+-b(\d+)', 'Planning the scenes, batch {0}'),
         (r'visual-library', 'Planning the picture library'),
         (r'film-cast', 'Choosing the people to show'),
         (r'scene-image-prompts-batch-0*(\d+)', 'Writing picture prompts, batch {0}'),
         (r'key-ideas', 'Finding the key ideas'),
         (r'person-reference-.*', 'Checking a reference portrait')]
LOOP_EVENT = re.compile(r'^(?P<loop>.+?)-(?P<kind>draft|review|blind-comparison)-[0-9a-f]{6,}(?:-(?P<n>\d+))?')
BEAT = re.compile(r'^Chapter (\w+): (.*)$')
ASSET = re.compile(r'^A\d{3}$')
TAKE = re.compile(r'^(A\d{3}) (\d+)/(\d+) take (\d+)/(\d+)$')
LOG_LINES = 60


def loop_label(name):
    for pattern, label in LOOPS:
        hit = re.fullmatch(pattern, name)
        if hit:
            return label.format(*hit.groups())
    return name.replace('-', ' ')


def clock(seconds):
    if seconds is None:
        return ''
    seconds = int(round(seconds))
    return f'{seconds // 60}m {seconds % 60:02d}s' if seconds >= 60 else f'{seconds}s'


def read_events(project):
    path = Path(project) / 'jobs.sqlite3'
    if not path.exists():
        return []
    try:
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=3) as db:
            rows = db.execute('SELECT id, time, stage, state, detail FROM events ORDER BY id').fetchall()
    except sqlite3.Error:
        return []
    start = max((r[0] for r in rows if r[2] == 'pipeline:research' and r[3] == 'running'), default=0)
    out = []
    for rid, at, stage, state, detail in rows:
        if rid < start:
            continue
        try:
            detail = json.loads(detail or '{}')
        except ValueError:
            detail = {}
        out.append((at, stage, state, detail if isinstance(detail, dict) else {}))
    return out


def _json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _latest_review(project, loop):
    """Score, pass and the major findings of the loop's latest review (planning/<loop>/<hash>/review-N.json)."""
    folder = Path(project) / 'planning' / loop
    if not folder.is_dir():
        return None
    runs = sorted((d for d in folder.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime)
    if not runs:
        return None
    reviews = sorted(runs[-1].glob('review-*.json'), key=lambda p: int(re.sub(r'\D', '', p.stem) or 0))
    if not reviews:
        return {'accepted': (runs[-1] / 'selected.json').exists()}
    review = _json(reviews[-1]) or {}
    majors = [str(i.get('problem', ''))[:220] for i in review.get('issues') or []
              if isinstance(i, dict) and i.get('severity') in ('blocker', 'major')]
    return {'score': review.get('score'), 'passed': review.get('pass'), 'majors': majors[:3],
            'accepted': (runs[-1] / 'selected.json').exists()}


def activity(project, now=None):
    project = Path(project)
    now = now or time.time()
    events = read_events(project)
    steps, loops, beats, pictures, log = {}, {}, {}, {}, []
    narration = {'points': 0, 'done': 0, 'retries': 0, 'problems': []}
    learner, clips, render, images, prompts = [], {'planned': 0, 'made': []}, {}, {}, {}
    models = {'calls': 0, 'planner_usd': 0.0, 'reviewer_tokens': 0}

    def say(at, text):
        log.append({'at': at, 'text': text})

    for at, stage, state, d in events:
        usage = d.get('usage') if isinstance(d.get('usage'), dict) else None
        if usage and state == 'succeeded':
            models['calls'] += 1
            models['planner_usd'] += float(usage.get('cost') or 0)
            if 'input_tokens' in usage:
                models['reviewer_tokens'] += int(usage.get('input_tokens') or 0) + int(usage.get('output_tokens') or 0)
        if stage.startswith('pipeline:'):
            key = stage.split(':', 1)[1]
            step = steps.setdefault(key, {'key': key, 'state': 'running', 'start': at, 'end': None, 'task': None})
            if state == 'running':
                step.update(state='running', end=None, task=d.get('task') or step.get('task'))
                say(at, d.get('task') or f'Started: {dict(STEPS).get(key, key)}')
            elif state in ('succeeded', 'failed', 'skipped'):
                step.update(state=state, end=at)
                if state == 'failed':
                    step['error'] = str(d.get('error', ''))[:400]
                    say(at, f'{dict(STEPS).get(key, key)} failed: {step["error"]}')
                elif state == 'skipped':
                    say(at, f'Skipped: {dict(STEPS).get(key, key)}')
                else:
                    say(at, f'Finished: {dict(STEPS).get(key, key)} in {clock(at - step["start"])}')
            continue
        hit = LOOP_EVENT.match(stage)
        if hit:
            name = hit['loop']
            loop = loops.setdefault(name, {'name': name, 'label': loop_label(name), 'start': at, 'end': None,
                                           'rounds': 0, 'reviews': 0, 'repairs': [], 'state': 'working'})
            loop['last'] = at
            if state not in ('running', 'failed'):
                continue
            if hit['kind'] == 'draft' and state == 'running':
                loop['rounds'] = max(loop['rounds'], int(hit['n'] or 0) + 1)
                say(at, f'{loop["label"]}: the planner is drafting (round {loop["rounds"]})')
            elif hit['kind'] == 'review' and state == 'running' and not stage.endswith('pointers'):
                loop['reviews'] += 1
                say(at, f'{loop["label"]}: the reviewer is checking round {int(hit["n"] or 0) + 1}')
            elif hit['kind'] == 'blind-comparison' and state == 'running':
                loop.update(state='done', end=at)
                say(at, f'{loop["label"]}: accepted; comparing the first and final drafts')
            elif state == 'failed' and d.get('reason') == 'output_token_limit':
                say(at, f'{loop["label"]}: the draft ran past its length limit; retrying with more room')
            continue
        if stage in loops:
            loop = loops[stage]
            loop['last'] = at
            if state == 'targeted_repair':
                loop['repairs'].append(d.get('units') or [])
                say(at, f'{loop["label"]}: fixing {", ".join(map(str, d.get("units") or []))} (round {d.get("attempt")})')
            elif state == 'full_repair':
                say(at, f'{loop["label"]}: redrafting after {d.get("stage_findings", 0)} findings')
            elif state == 'accepted_after_screening':
                loop.update(state='done', end=at)
                say(at, f'{loop["label"]}: accepted at score {d.get("score")} ({d.get("decision")})')
            continue
        if stage == 'animations' and state == 'progress':
            hit = BEAT.match(str(d.get('message', '')))
            if hit:
                beat = beats.setdefault(hit[1], {'id': hit[1], 'start': at, 'end': None, 'attempts': 0,
                                                 'state': 'coding', 'tier': None, 'line': ''})
                line = hit[2]
                beat['line'], beat['last'] = line, at
                attempt = re.search(r'attempt (\d+)', line)
                if attempt:
                    beat['attempts'] = max(beat['attempts'], int(attempt[1]))
                tier = re.search(r'\((\w+) coder', line)
                if tier:
                    beat['tier'] = tier[1]
                beat['state'] = ('done' if line.startswith('finished') else 'rendering' if line.startswith('rendering')
                                 else 'repairing' if 'repairing' in line else 'coding' if 'coding' in line
                                 else beat['state'])
                if line.startswith('finished'):
                    beat['end'] = at
            say(at, f'Animation {d.get("message", "")}'.replace('Animation Chapter ', 'Animated scene '))
            continue
        if stage.startswith('narration-') and re.fullmatch(r'narration-\d+-\d+', stage):
            if state == 'point_rendering':
                narration['points'] = max(narration['points'], len(d.get('points') or []))
                say(at, f'Recording the narration: {len(d.get("points") or [])} points')
            elif state == 'point_accepted':
                narration['done'] += 1
                say(at, f'Narration {d.get("point")}: recorded and checked against the script')
            elif state == 'point_audit_failed':
                problem = f'{d.get("point")}: {", ".join(d.get("reasons") or [])}'
                narration['problems'].append(problem)
                say(at, f'Narration {problem}; recording it again')
            elif state == 'point_retry':
                narration['retries'] += 1
            elif state == 'succeeded':
                say(at, f'All {d.get("point_clips")} narration points recorded: {clock(d.get("duration_seconds"))} of '
                        'narration; now checking the whole narration once more')
            continue
        if stage == 'audio-audit':                       # the whole-narration check and per-point cross-checks
            model = str(d.get('model', '')).split('/')[-1]
            reasons = ', '.join(d.get('reasons') or [])
            text = {'needs_crosscheck': f'Audio check: {model} scored {d.get("score")} ({reasons}); asking the next '
                                        'recogniser',
                    'crosscheck_passed': f'Audio check passed on {model} (score {d.get("score")})',
                    'failed': f'Audio check failed on {model} (score {d.get("score")}: {reasons})',
                    'semantic_accepted': 'Audio check: the reviewer finds the transcript differences harmless',
                    'semantic_needs_review': 'Audio check: the reviewer wants the recognisers to look again ('
                                             + str(d.get('reason', ''))[:140] + ')',
                    'repeated_failure_arbiter': 'Audio check: the same differences twice; asking an arbiter'}.get(state)
            if text and ('points/' not in str(d.get('audio', '')) or state in ('failed', 'crosscheck_passed')):
                say(at, text)
            continue
        if stage.startswith('alignment-') and state == 'running':
            say(at, 'Timing every word of the narration')
        if stage == 'learner-check':
            learner.append({'round': d.get('round'), 'score': d.get('score'), 'landed': state == 'landed'})
            say(at, f'Test learner, round {d.get("round")}: score {d.get("score")} '
                    f'({"the idea landed" if state == "landed" else "not landed yet"})')
            continue
        if stage == 'image-prompts':
            prompts = {'batch': d.get('batch'), 'of': d.get('total_batches'), 'state': state}
            if state == 'batch_running':
                say(at, f'Writing picture prompts, batch {d.get("batch")} of {d.get("total_batches")}')
            continue
        if stage == 'images':
            images.update({k: d[k] for k in ('planned_images', 'completed_images', 'accepted_images', 'blocked_images',
                                             'needs_review_images', 'remaining_images', 'provider') if k in d})
            if state == 'pool':
                images['workers'] = d.get('workers')
            continue
        take = TAKE.match(stage)
        if take and state == 'waiting':
            pic = pictures.setdefault(take[1], {'id': take[1], 'takes': 0, 'state': 'queued', 'message': '', 'issue': ''})
            pic['takes'] = max(pic['takes'], int(take[4]))
            pic['state'] = 'painting' if d.get('state') == 'running' else pic['state'] if pic['state'] != 'queued' else 'queued'
            continue
        if ASSET.match(stage):
            pic = pictures.setdefault(stage, {'id': stage, 'takes': 0, 'state': 'queued', 'message': '', 'issue': ''})
            pic['message'] = d.get('visual_message') or pic['message']
            if state == 'rendering':
                pic['state'] = 'painting'
            elif state == 'rejected':
                issues = d.get('issues') or []
                pic.update(state='retrying', issue=(issues[0] if issues else '') or d.get('correction', ''))
                say(at, f'Picture {stage} take {d.get("attempt")} rejected: {pic["issue"][:200]}')
            elif state == 'accepted':
                pic.update(state='accepted', issue='')
                say(at, f'Picture {stage} accepted on take {d.get("attempt")}')
            elif state == 'scene_replaced':
                why = "; ".join(d.get("simplifications") or [])[:180]
                say(at, f'Picture {stage}: prompt simplified' + (f' ({why})' if why else ''))
            elif state == 'best_available_selected':
                pic.update(state='needs review' if d.get('needs_review') else 'accepted', score=d.get('score'))
                say(at, f'Picture {stage}: kept the best take (score {d.get("score")})'
                        f'{", marked for expert review" if d.get("needs_review") else ""}')
            elif state == 'blocked':
                pic['state'] = 'blocked'
            continue
        if stage == 'action-clips':
            if state == 'running':
                clips['planned'] = d.get('clips', 0)
                say(at, f'Making {d.get("clips")} motion clips')
            elif state == 'rendered':
                clips['made'].append({'scene': d.get('scene'), 'worker': d.get('worker'), 'seconds': d.get('seconds')})
                say(at, f'Motion clip for {d.get("scene")} made on the {d.get("worker")} in {clock(d.get("seconds"))}')
            elif state in ('failed', 'switching', 'switched'):
                say(at, f'Motion clips: {state} {json.dumps(d)[:160]}')
            continue
        if stage == 'clips' and state not in ('waiting',):
            clips.setdefault('illustration', {}).update({k: v for k, v in d.items() if isinstance(v, (int, float, str))})
            continue
        if stage == 'render':
            render.update(state=state, start=render.get('start', at) if state != 'running' else at,
                          end=at if state != 'running' else None)
            say(at, 'Rendering the final video' if state == 'running' else f'Final video {state}')
            continue
        if stage == 'voice-calibration' and state == 'succeeded':
            say(at, 'Voice calibrated')
        if stage.startswith('alignment-') and state == 'succeeded':
            say(at, f'Every word timed ({d.get("words")} words)')
        if stage == 'depth' and state == 'succeeded':
            say(at, f'Depth maps made for {d.get("images")} pictures (for the gentle camera moves)')
        if stage == 'cast' and state == 'succeeded':
            say(at, f'People to show: {", ".join(d.get("people") or []) or "none"}')

    running = any(s['state'] == 'running' for s in steps.values())
    seconds = lambda a, b: (b or now) - a if a else None  # noqa: E731
    scenes_over = steps.get('scenes', {}).get('state') in ('succeeded', 'failed')
    for loop in loops.values():
        review = _latest_review(project, loop['name'])
        if review:
            loop.update(review)
            if review.get('accepted'):
                loop['state'] = 'done'
        if loop['end'] is None and (loop['state'] == 'done' or not running):
            loop['end'] = loop.get('last')
        loop['seconds'] = seconds(loop['start'], loop['end'])
        loop['repairs'] = loop['repairs'][-3:]
    for step in steps.values():
        step['seconds'] = seconds(step['start'], step['end'])
        step['title'] = dict(STEPS).get(step['key'], step['key'])
    for beat in beats.values():
        if beat['end'] is None and scenes_over:          # runs from before beats logged their finish
            beat.update(state='done', end=beat.get('last'))
        beat['seconds'] = seconds(beat['start'], beat['end'])
    titles = _beat_titles(project)
    for beat in beats.values():
        beat['title'] = titles.get(beat['id'], '')
    landing = None
    for path in sorted(project.glob('learner-check-*.json')):
        data = _json(path) or {}
        landing = [{'round': r.get('round'), 'understood': (r.get('verdict') or {}).get('understood'),
                    'simple': (r.get('verdict') or {}).get('simple'),
                    'confusing': len((r.get('learner') or {}).get('confusing') or []),
                    'landed': r.get('landed')} for r in data.get('rounds', [])]
    order = [k for k, _ in STEPS]
    if render.get('start'):
        render['seconds'] = seconds(render['start'], render.get('end'))
    log.sort(key=lambda e: e['at'], reverse=True)
    return {
        'steps': sorted(steps.values(), key=lambda s: order.index(s['key']) if s['key'] in order else 99),
        'work': {
            'planning': sorted(loops.values(), key=lambda x: x['start']),
            'narration': narration if narration['points'] else None,
            'learner': landing or learner or None,
            'animations': sorted(beats.values(), key=lambda b: b['id']),
            'pictures': {'summary': images, 'prompts': prompts,
                         'items': sorted(pictures.values(), key=lambda p: p['id'])} if images or pictures else None,
            'clips': clips if clips['planned'] or clips.get('illustration') else None,
            'render': render or None},
        'log': [{'at': time.strftime('%H:%M:%S', time.localtime(e['at'])), 'text': e['text']} for e in log[:LOG_LINES]],
        'models': {**models, 'planner_usd': round(models['planner_usd'], 3)},
        'started': time.strftime('%H:%M', time.localtime(events[0][0])) if events else None,
        'elapsed': clock((now if running else events[-1][0]) - events[0][0]) if events else None,
        'running': running,
    }


def _beat_titles(project):
    """Animated beat id ('s07') -> its title, from the storyboard written before the beats are coded."""
    out = {}
    for path in Path(project).glob('film-*/storyboard.json'):
        for scene in (_json(path) or {}).get('scenes', []):
            if scene.get('kind') == 'animation':
                out[str(scene.get('id', '')).lower()] = (scene.get('animation') or {}).get('title', '')
    return out
