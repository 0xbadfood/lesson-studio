"""LLM-coded chapters: a coder writes one Manim scene per chapter, timed to the recorded narration.

The planner rates each chapter routine / involved / novel; that tier picks the coder step
(scene_code_routine / _involved / _novel). Every candidate is checked in code, rendered in the sandbox
(measured overlaps, bands, late cues), then reviewed for content (code + timeline) and from a contact sheet
of frames taken at the cue moments. Defects go back to the coder; after two failures at one tier the
chapter moves up a tier (never down). The last version that rendered is kept, with notes, if every attempt
fails review.
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import subprocess

from .diagram import limits, seccomp_profile
from . import review
from .scene_check import geometry_defects, validate_code

HERE = Path(__file__).resolve().parent
TIERS = ('routine', 'involved', 'novel')
ESCALATE_AFTER = 2   # failed attempts at one tier before the next tier takes over

KIT = '''Write one Manim Community 0.21 scene module for ONE chapter of a narrated lesson video.
Return JSON {"code": "<complete module>", "notes": ["<=3 short notes"]}.
The module starts exactly with:
import manim as m
import numpy as np
import math
from scene_kit import begin, at, finish, text, tex, arrow, polyline, BG, WHITE, CYAN, GREEN, RED, AMBER, VIOLET, GREY
and defines class ChapterScene(m.Scene) with construct(self):
- first line: begin(self, "<chapter title>")  (draws the heading; the chapter clock starts at 0)
- before the animations of each cue: at(self, <cue start seconds>)  (waits until that narration moment)
- last line: finish(self, <duration>)  (holds the picture to the end of the narration, then fades out)
TIMING: the TIMELINE gives each cue's start and end on the chapter clock, measured from the recorded voice. The
picture must change as the words are spoken: call at(self, start) for every cue in order, and make the run_times
of that cue's animations add up to no more than (end - start), and never past the next cue's start. Never call
self.wait(); at() does the waiting. Continuous motion (ValueTracker + updaters/always_redraw) is welcome.
SCREEN: frame x -7.1..7.1, y -4..4. The heading uses y > 2.95 and burned-in subtitles use y < -2.75: keep every
body object inside x -6.6..6.6, y -2.7..2.9. Decide regions first (for example a graph on the left, equations on
the right), derive every position from one consistent scale, and keep each label's whole box at least 0.15 units
clear of other labels, lines and shapes. Fade out or move old items before reusing their space. Keep on-screen
words short (the narrator explains); text size 22-34; maths with tex() (LaTeX MathTex); words with text().
Trajectories, curves and outlines are strokes only (fill_opacity=0); moving bodies stay inside the body area for
the whole motion (stop them or cut away before they reach the edge).
COLOURS: dark navy background; give each colour one meaning for the whole chapter (follow the plan's notes).
API RULES: qualify every Manim name (m.Axes, m.FadeIn, m.UP, m.ValueTracker). Positions are numpy arrays or
[x, y, 0]. Animate trackers with self.play(t.animate.set_value(v), run_time=..., rate_func=m.linear).
always_redraw callbacks take no arguments; add_updater callbacks take (mob) or (mob, dt). Use mob.become(new) to
rebuild geometry. Do not touch files, the network, the camera frame or other modules; no SVG or images.
CORRECTNESS: compute every number from the chapter's values in code; numbers on screen must match the narration
exactly; physics and geometry must be right (directions, proportions, units).'''


# ------------------------------------------------------------------ render
def render(settings, work, code, duration, background=None):
    """Render the scene in the sandbox. Returns (video, measured data); raises ValueError with defects."""
    work = Path(work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / 'scene.py').write_text(code)
    for name in ('scene_entry.py', 'scene_kit.py', 'scene_check.py', 'chem_kit.py'):
        shutil.copy2(HERE / name, work / name)
    if background:   # the lesson theme (validated #rrggbb) replaces the kit's default background
        with (work / 'scene_kit.py').open('a') as kit:
            kit.write(f"\nBG = {background!r}\n")
    seccomp_profile(work / 'render.seccomp')
    fd = os.open(work / 'render.seccomp', os.O_RDONLY)
    venv = Path(settings.manim_python).parent.parent
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--clearenv']
    for path in dict.fromkeys(['/usr', '/lib', '/lib64', settings.python_base, str(venv),
                               str(Path(settings.manim_python).resolve().parents[1]), '/etc/fonts', '/etc/ld.so.cache',
                               '/etc/localtime', '/etc/texmf', '/var/lib/texmf']):
        if Path(path).exists():
            cmd += ['--ro-bind', path, path]
    cmd += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--bind', str(work.resolve()), '/work',
            '--dir', '/work/home', '--setenv', 'HOME', '/work/home', '--setenv', 'PATH', '/usr/bin:/bin',
            '--setenv', 'PYTHONPATH', '/work', '--setenv', 'OMP_NUM_THREADS', '2', '--chdir', '/work',
            '--seccomp', str(fd), settings.manim_python, '/work/scene_entry.py', '/work/scene.py',
            str(settings.width), str(settings.height), str(settings.fps), f'{duration:.3f}']
    try:
        with (work / 'render.log').open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, pass_fds=(fd,), preexec_fn=limits,
                           timeout=settings.render_timeout)
    except subprocess.TimeoutExpired:
        raise ValueError(f'The scene took longer than {settings.render_timeout}s to render; simplify it '
                         '(fewer always_redraw objects, coarser sampling)')
    finally:
        os.close(fd)
    if not (work / 'result.json').exists():
        raise ValueError('The render crashed:\n' + (work / 'render.log').read_text()[-2500:])
    data = json.loads((work / 'result.json').read_text())
    if data.get('error'):
        raise ValueError('The scene raised an error while rendering:\n' + data['error'] + '\n' + data.get('traceback', ''))
    defects = geometry_defects(data)
    if defects:
        raise ValueError('\n'.join(defects))
    return work / Path(data['output']).relative_to('/work'), data


def contact_sheet(video, moments, out):
    """One labelled image of frames at the given (seconds, label) moments: one picture works for every model."""
    from PIL import Image, ImageDraw, ImageFont
    out = Path(out)
    tiles = []
    for i, (t, label) in enumerate(moments):
        frame = out.parent / f'{out.stem}-{i + 1}.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', str(video), '-frames:v', '1',
                        '-vf', 'scale=640:-1', '-q:v', '3', str(frame)], check=True, timeout=60)
        tiles.append((Image.open(frame).convert('RGB'), f'{i + 1}. t={t:.1f}s  {label}'))
    cols = 2 if len(tiles) <= 4 else 3
    rows = -(-len(tiles) // cols)
    w, h, band, gap = 640, 360, 46, 24
    sheet = Image.new('RGB', (cols * w + (cols - 1) * gap, rows * (h + band) + (rows - 1) * gap), '#d9d9d9')
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('DejaVuSans.ttf', 15)
    except OSError:
        font = ImageFont.load_default()

    def fitted(label):
        # At most two lines, each inside its own tile, so labels never touch each other.
        lines, words = [], label.split()
        while words and len(lines) < 2:
            line = ''
            while words and draw.textlength((line + ' ' + words[0]).strip(), font=font) <= w - 12:
                line = (line + ' ' + words.pop(0)).strip()
            if not line:
                line = words.pop(0)
            lines.append(line)
        if words:
            lines[-1] = lines[-1].rstrip('.,;') + '…'
        return lines
    for i, (img, label) in enumerate(tiles):
        x, y = (i % cols) * (w + gap), (i // cols) * (h + band + gap)
        draw.rectangle([x, y, x + w - 1, y + band - 1], fill='white')
        for j, line in enumerate(fitted(label)):
            draw.text((x + 6, y + 4 + j * 20), line, fill='black', font=font)
        sheet.paste(img.resize((w, h)), (x, y + band))
    sheet.save(out, quality=88)
    return out


# ------------------------------------------------------------------ prompts
def timeline(sc, timing, cues, duration):
    texts = {p['id']: p['narration'] for p in sc['points']}
    lines = [f'Chapter duration: {duration:.2f}s', 'NARRATION:']
    for p in timing['points']:
        lines.append(f"  {p['point_id']} [{p['start']:.1f}-{p['end']:.1f}s] {texts.get(p['point_id'], '')}")
    lines.append('CUES (call at(self, start) before each):')
    for i, c in enumerate(cues):
        lines.append(f"  k{i + 1} start={c['start']:.2f} end={c['end']:.2f} on \"{c['phrase']}\": {c.get('show', '')}")
    return '\n'.join(lines)


def chapter_brief(plan, chapter):
    keep = ('id', 'title', 'objective', 'complexity', 'visual', 'demonstrations')
    return json.dumps({'lesson': plan.get('title'), 'big_idea': plan.get('big_idea'),
                       'colour_notes': plan.get('colours'), 'chapter': {k: chapter.get(k) for k in keep}},
                       ensure_ascii=False)


def at_rest(cues, i, plays, duration):
    """When to photograph cue i for review: just after the animations that start in its window have finished
    (a frame taken mid-transform shows half-morphed glyphs), never past the next cue; without recorded plays
    (pure updater motion), late in the cue's own window."""
    c = cues[i]
    limit = min(cues[i + 1]['start'] if i + 1 < len(cues) else duration, duration - .5) - .1   # finish() fades out
    # Only this cue's own animations (starting inside its window): a fade-out or set-up between cues belongs to
    # no cue, and photographing after it showed an empty screen.
    window_end = min(max(c['end'], c['start'] + .3) + .3, limit)
    ends = [b for a, b in plays if c['start'] - .05 <= a < window_end]
    moment = max(ends) + .2 if ends else c['start'] + .85 * (c['end'] - c['start'])
    return max(c['start'], min(moment, limit))


ARBITRATE = (
    'A reviewer failed the criteria below for one animated chapter of a lesson, after the coder had disputed findings '
    'with the reasons given. You are the arbiter. For EVERY failed criterion rule "stands" if the problem is really in '
    'the current code or frames and would mislead or block a learner or breaks a stated rule, or "wrong" if it is a '
    'false positive: the coder\'s dispute holds, the problem is not there, it is only a difference of wording, '
    'coordinates, stage, detail or style, it comes from a frame caught mid-animation or before its cue, or it would not '
    'mislead a learner. The contact sheet shows frames at the cue moments (the white label strips belong to the '
    'checker, not the video). Return {"rulings":[{"review":"code"|"frames","criterion":str,"verdict":"stands"|"wrong",'
    '"reason":str}]}.')


def arbitrate(job, tag, content, frames, disputes, code, sheet, brief, clock):
    """Disputed findings that a reviewer repeated are ruled on by the review auditor; code applies the rulings."""
    failed = ([{'review': 'code', **{k: f[k] for k in ('criterion', 'label', 'score', 'reason')}}
               for f in content['decision']['failed']] +
              [{'review': 'frames', **{k: f[k] for k in ('criterion', 'label', 'score', 'reason')}}
               for f in frames['decision']['failed']])
    wanted = {(f['review'], f['criterion']) for f in failed}

    def check(reply):
        got = {(r.get('review'), r.get('criterion')) for r in reply.get('rulings') or []
               if r.get('verdict') in ('stands', 'wrong')}
        if not wanted <= got:
            raise ValueError(f'rule on every failed criterion: {sorted(wanted - got)}')
    reply = job.llm('review_audit').call(f'arbitrate-{tag}', (
        ARBITRATE + '\nFAILED CRITERIA:\n' + json.dumps(failed, ensure_ascii=False) + '\nCODER\'S DISPUTES (last round):\n' +
        json.dumps(disputes, ensure_ascii=False) + '\nCHAPTER PLAN:\n' + brief + '\nTIMELINE:\n' + clock +
        '\nCODE:\n' + code), images=[sheet], thinking=3000, max_tokens=5000, validate=check)
    return [r for r in reply['rulings'] if (r.get('review'), r.get('criterion')) in wanted]


def apply_edits(source, edits):
    if not isinstance(edits, list) or not 1 <= len(edits) <= 16:
        raise ValueError('Return 1-16 exact source edits, or the complete module as "code" with a "rewrite_reason"')
    for e in edits:
        old, new = (e or {}).get('old'), (e or {}).get('new')
        if not isinstance(old, str) or not old.strip() or not isinstance(new, str) or old == new:
            raise ValueError('Each edit needs non-empty "old" text and a different "new" text')
        if source.count(old) != 1:
            raise ValueError('Edit "old" text must match the current source exactly once: ' + old[:160])
        source = source.replace(old, new, 1)
    return source


# ------------------------------------------------------------------ one chapter
def code_chapter(job, plan, chapter, sc, timing, cues, duration, evidence_text, folder, extra='', kit=KIT):
    """Code, render and review one chapter. Returns (video, record). `kit` is the coder's instructions (KIT, or KIT
    plus a subject kit such as kit_docs.CHEM)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    accepted = folder / 'accepted.json'
    if accepted.exists():
        saved = json.loads(accepted.read_text())
        if Path(saved['video']).exists():
            return Path(saved['video']), saved
    n = chapter['id'][1:]
    tier = chapter.get('complexity') if chapter.get('complexity') in TIERS else 'involved'
    brief, clock = chapter_brief(plan, chapter), timeline(sc, timing, cues, duration)
    prompt = (kit + '\nCHAPTER PLAN:\n' + brief + '\nTIMELINE:\n' + clock + '\nEVIDENCE:\n' + evidence_text +
              (f'\nTEACHER REQUEST FOR THIS VERSION: {extra}' if extra else ''))
    attempts = job.settings.code_attempts + ESCALATE_AFTER   # room for one escalation, more if tiers allow
    code, feedback, failures, history, best = None, '', 0, [], None
    log = []          # every review round: findings, then the coder's reply to them
    top = None        # the best reviewed attempt: fewest failed criteria, then the highest scores

    def review_log():
        if not log:
            return ''
        return ('\nEARLIER REVIEW ROUNDS (oldest first). The coder changed the code after each round. Never lower a '
                'score for the opposite of an earlier finding the coder acted on; keep a low score for an earlier '
                'finding only if the problem is still in the current code; accept a coder dispute unless it is '
                'factually wrong:\n' +
                json.dumps(log, ensure_ascii=False)[-6000:])
    def repair_check(reply):
        """Checked inside the model call, so a bad edit is corrected by a cheap retry, not a whole attempt."""
        if reply.get('code'):
            if not str(reply.get('rewrite_reason') or '').strip():
                raise ValueError('A complete module needs a "rewrite_reason"; otherwise repair in place with "edits"')
            validate_code(reply['code'])
            return
        if reply.get('edits') or not (reply.get('disputes') or reply.get('notes')):
            validate_code(apply_edits(code, reply.get('edits')))   # the edited module must still parse and pass

    for attempt in range(attempts):
        step = f'scene_code_{tier}'
        coder = job.llm(step)
        tag = f"{chapter['id']}-{attempt}"
        job.log(f'Chapter {n}: {"coding" if code is None else "repairing"} the scene ({tier} coder, attempt {attempt + 1})')
        job.chapter_status(chapter['id'], 'coding', f'{tier} coder · attempt {attempt + 1}')
        entry = {'attempt': attempt + 1, 'tier': tier, 'connection': job.models['steps'].get(step)}
        try:
            try:
                if code is None:
                    reply = coder.call(f'code-{tag}', prompt, thinking=8000, max_tokens=16000)
                    candidate = reply.get('code', '')
                else:
                    reply = coder.call(f'repair-{tag}', prompt + '\nCURRENT MODULE:\n' + code + '\nDEFECTS TO FIX:\n' +
                                       feedback + '\nFix every defect and keep what works. If a review finding is '
                                       'wrong (the code is already correct, or following it would make the science or '
                                       'the picture worse), do not obey it: list it in "disputes" with a short reason. '
                                       'Repair in place: return {"edits":[{"old":"exact unique source text","new":'
                                       '"replacement"}],"notes":[...],"disputes":[{"finding":str,"reason":str}]}, '
                                       'changing only what the defects need (1-16 edits; each "old" must occur exactly '
                                       'once in the current module). Only if the scene\'s whole construction must change '
                                       'return {"code":"<complete module>","rewrite_reason":str,"notes":[...],'
                                       '"disputes":[...]}.',
                                       thinking=5000, max_tokens=16000, validate=repair_check)
                    if log:
                        log[-1]['coder_reply'] = {'notes': reply.get('notes') or [], 'disputes': reply.get('disputes') or []}
                    entry['repair'] = 'rewrite' if reply.get('code') else 'edits' if reply.get('edits') else 'disputes'
                    if reply.get('code'):
                        candidate = reply['code']
                    elif not reply.get('edits') and (reply.get('disputes') or reply.get('notes')) and best and best[1] == code:
                        candidate = code          # every finding disputed: same code goes back to review
                    else:
                        candidate = apply_edits(code, reply.get('edits'))
            except RuntimeError as exc:   # the model call itself failed (budget, format): resend the real defect
                raise ValueError(f'The coder reply could not be used ({str(exc)[-300:]}).' +
                                 ('\n' + feedback if feedback else '')) from exc
            validate_code(candidate)
            if best and candidate == best[1]:
                video = best[0]
                job.log(f'Chapter {n}: coder disputes the findings; reviewing the same render again')
            else:
                code = candidate
                (folder / f'scene-{attempt + 1}.py').write_text(code)
                job.log(f'Chapter {n}: rendering attempt {attempt + 1}')
                job.chapter_status(chapter['id'], 'rendering', f'attempt {attempt + 1}')
                video, data = render(job.settings, folder / f'render-{attempt + 1}', code, duration,
                                     (plan.get('theme') or {}).get('background'))
                best = (video, code, attempt + 1, data)
            job.chapter_status(chapter['id'], 'reviewing', f'attempt {attempt + 1}')
            moments = [(at_rest(cues, i, best[3].get('plays') or [], duration), f"k{i + 1}: {c.get('show', '')}")
                       for i, c in enumerate(cues)]
            if len(moments) > 6:   # spread six frames over the chapter
                moments = [moments[round(i * (len(moments) - 1) / 5)] for i in range(6)]
            sheet = contact_sheet(video, moments, folder / f'render-{best[2]}' / f'review-sheet-{attempt + 1}.jpg')

            def content_review():
                return review.review(job.llm('content_review'), f'content-review-{tag}', 'scene_content', (
                    'Review the code of one animated chapter of a narrated lesson against its plan, narration timeline and '
                    'evidence. Follow loops and group membership rather than variable names. Judge the teaching, not the '
                    'wording: the plan and cue texts are intentions written before the code, and a different but correct, '
                    'clear way of showing the idea is fine. A mismatch with the wording of a cue or the plan, exact '
                    'coordinates, the stage or level of a drawing, or the animation technique (transform, fade, redraw) '
                    'lowers no score unless it makes the science wrong or leaves the narration describing something that '
                    'is not on screen. Layout is checked separately from frames.\nCHAPTER PLAN:\n' + brief +
                    '\nTIMELINE:\n' + clock + '\nEVIDENCE:\n' + evidence_text[:4000] + review_log() + '\nCODE:\n' + code),
                    thinking=3000, max_tokens=5000)

            def frame_review():
                return review.review(job.llm('diagram_review'), f'frame-review-{tag}', 'scene_frames', (
                    'These numbered frames come from one animated chapter of a lesson video, each taken near the end of a '
                    'narration cue. The white label strip above each frame was added by the checker (frame number, '
                    'time and what the cue should show): it is not part of the video, so never judge it. Judge what is '
                    'VISIBLE inside the frames, and name the frame number in every reason. The label text is the intended '
                    'idea, not a specification: differences in wording, stage, detail or style lower no score when the '
                    'picture teaches the idea correctly. Each frame shows the screen when ITS OWN cue has played: what a '
                    'later cue adds is not expected yet, and what earlier cues drew may still be there. Ignore subtitles '
                    '(none are drawn yet) and states that may be mid-animation (a counter partway through a run or reset '
                    'for a new run is not wrong; a trace that has only just levelled off is not still rising).\n'
                    'CHAPTER PLAN:\n' + brief + review_log()), images=[sheet], thinking=2000, max_tokens=4000)

            if getattr(job, 'parallel_reviews', False):   # independent reviews of the same attempt
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending = pool.submit(content_review), pool.submit(frame_review)
                    content, frames = pending[0].result(), pending[1].result()
            else:
                content, frames = content_review(), frame_review()
            disputes = (log[-1].get('coder_reply') or {}).get('disputes') if log else None
            if disputes and review.findings(content, frames) and 'review_audit' in job.models['steps']:
                rulings = arbitrate(job, tag, content, frames, disputes, code, sheet, brief, clock)
                dropped = [r for r in rulings if r['verdict'] == 'wrong']
                for r in dropped:
                    review.overrule(content if r['review'] == 'code' else frames, r['criterion'],
                                    'arbiter: ' + r['reason'])
                entry['arbitration'] = rulings
                if dropped:
                    job.log(f'Chapter {n}: the arbiter upheld the coder on {len(dropped)} disputed finding(s)')
            entry.update(content_review=content, frame_review=frames, render=str(video))
            history.append(entry)
            rank = (-len(review.findings(content, frames)), content['decision']['score'] + frames['decision']['score'])
            if top is None or rank >= top[0]:
                top = (rank, video, code, attempt + 1, [n['label'] + ': ' + n['reason'] for r in (content, frames)
                                                        for n in r['decision']['failed'] + r['decision']['notes']])
            if content['decision']['pass'] and frames['decision']['pass']:
                notes = [f"Reviewer note ({n['label']}, {n['score']}/3): {n['reason']}"
                         for r in (content, frames) for n in r['decision']['notes']]
                record = {'video': str(video), 'code': code, 'tier': tier, 'attempts': attempt + 1, 'history': history,
                          'source_sha256': hashlib.sha256(code.encode()).hexdigest(), 'notes': notes}
                accepted.write_text(json.dumps(record, indent=1))
                return video, record
            log.append({'round': attempt + 1, 'failed': review.findings(content, frames)})
            feedback = ('Review scores below the required minimum (frames are numbered as in the contact sheet):\n' +
                        review.as_text(content, frames))
        except ValueError as exc:
            feedback = str(exc)[:5000]
            history.append({**entry, 'defect': feedback})
        failures += 1
        (folder / 'feedback.txt').write_text(feedback)
        if failures >= ESCALATE_AFTER:
            current = job.models['steps'].get(f'scene_code_{tier}')
            higher = [t for t in TIERS[TIERS.index(tier) + 1:] if job.models['steps'].get(f'scene_code_{t}') != current]
            failures = 0
            if higher:   # a higher tier on the same model is no escalation: keep repairing instead
                tier = higher[0]
                job.log(f'Chapter {n}: moving up to the {tier} coder')
    if best is None:
        raise RuntimeError(f"Chapter {n}: no coded scene rendered after {attempts} attempts; last problem: {feedback[:600]}")
    if top is not None:     # keep the highest-scoring attempt, not merely the last one that rendered
        _, video, code, number, open_points = top
        notes = [f'Kept attempt {number} (best review scores); open points: ' + ' | '.join(open_points)[:600]]
    else:
        video, code, number = best[:3]
        notes = [f'Kept attempt {number} with review notes: {feedback[:400]}']
    record = {'video': str(video), 'code': code, 'tier': tier, 'attempts': attempts, 'history': history,
              'kept_attempt': number, 'source_sha256': hashlib.sha256(code.encode()).hexdigest(), 'notes': notes}
    accepted.write_text(json.dumps(record, indent=1))
    return Path(video), record
