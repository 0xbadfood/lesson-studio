"""Slide chapters: cards drawn by the frozen infofilm (remotion) renderer, used as a library and never modified.

The script gives one card per narration point (image, flow, compare or cycle). Each card starts on its point's first
word (MFA times) and stays until the next card. Image cards get a generated picture (Qwen Image under the shared
GPU lease) that a vision model checks for text, accuracy and artefacts; a picture that keeps failing is dropped and
the card keeps its heading and summary on the lesson background. The lesson theme colours the cards.
"""
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess

from . import imageworld, review
from .audio import locate, phrase_in_text

HERE = Path(__file__).resolve().parent

KINDS = ('image', 'flow', 'compare', 'cycle')
MOTIONS = ('drift', 'push', 'pull', 'hold')
PICTURE_SIZE = (1536, 864)
PICTURE_STYLE = ('Polished editorial illustration for an educational documentary: realistic atmospheric rendering, '
                 'soft gradients, cinematic lighting, uncluttered composition with a calm darker left third.')
CARD_WIDTH, CARD_HEIGHT = 1920, 1080     # the renderer's layout is designed for 1080p; scaled to the lesson size

SLIDE_GUIDE = (
    'Slide chapters (route "slide") have no cues. Give "slides" instead: one card per narration point, in point '
    'order: {"point","kind":"image|flow|compare|cycle","heading":"<=7 words","summary":"<=18 words",'
    '"banner":"<=4 words (image cards, optional)","picture":"image cards: 15-60 words describing a realistic '
    'illustration: setting, objects, lighting","labels":[...],"details":[...]}. "image" = a picture with the heading '
    'and summary; "flow" = 2-4 steps in order; "cycle" = 2-4 stages that repeat; "compare" = exactly 2 sides. Flow, '
    'cycle and compare cards give "labels" (<=5 words each), the same number of "details" (<=9 words each), and '
    '"reveal": one exact phrase per label, copied from that point\'s narration in speaking order; each box appears '
    'when its phrase is spoken. Card '
    'text is read on screen, so digits, symbols and short formulas are fine there. Pictures never contain text, '
    'labels, numbers, diagrams or charts, and show people only as generic unnamed figures (never a portrait of a '
    'real person): show the setting, the instruments or the problem instead. A picture is a real-world scene '
    '(a place, an object in use, an experiment, a historical setting); never icons, pictograms, line art, '
    'outlines, symbols or abstract shapes. When no real scene helps (abstract maths, a method, a recap), use a '
    'flow, cycle or compare card instead of a picture card.\n')

# Image generation draws scenes; it cannot be trusted with icons, diagrams or exact counts of abstract shapes.
NOT_A_SCENE = re.compile(r'\b(icons?|pictograms?|outlines?|line[- ]?art|strokes?|diagrams?|charts?|graphs?|axis|axes|'
                         r'arrows?|labels?|equations?|formulas?|symbols?|geometric|abstract)\b', re.I)
NEGATED = re.compile(r'\b(?:no|not|never|without|avoid(?:ing)?|free of|nor)\b[^.;:]*', re.I)


def non_scene_words(text):
    """Words asking for icons or diagrams; what the text says NOT to draw ("no icons or diagrams") is ignored."""
    return sorted({w.lower() for w in NOT_A_SCENE.findall(NEGATED.sub(' ', str(text or '')))})


def slide_errors(sc, points):
    """Code checks for one slide chapter's cards."""
    errors, slides = [], sc.get('slides') or []
    ids = [p.get('id') for p in points]
    texts = {p.get('id'): str(p.get('narration', '')) for p in points}
    if [s.get('point') for s in slides] != ids:
        return [f"{sc['id']}: give exactly one slide per narration point, in order {ids}"]
    words = lambda v: len(str(v or '').split())
    for s in slides:
        where = f"{sc['id']} slide {s.get('point')}"
        kind = s.get('kind')
        if kind not in KINDS:
            errors.append(f'{where}: kind must be one of {list(KINDS)}')
            continue
        if not 1 <= words(s.get('heading')) <= 7:
            errors.append(f'{where}: heading needs 1-7 words')
        if words(s.get('summary')) > 18 or (kind == 'image' and not s.get('summary')):
            errors.append(f'{where}: summary is at most 18 words (and required on image cards)')
        if kind == 'image':
            if not 15 <= words(s.get('picture')) <= 60:
                errors.append(f'{where}: describe the picture in 15-60 words')
            bad = non_scene_words(s.get('picture'))
            if bad:
                errors.append(f'{where}: a picture is a real-world scene, not {", ".join(bad)}; '
                              'for an abstract idea use a flow, cycle or compare card')
            if words(s.get('banner')) > 4:
                errors.append(f'{where}: banner is at most 4 words')
            continue
        labels, details = s.get('labels') or [], s.get('details') or []
        wanted = (2, 2) if kind == 'compare' else (2, 4)
        if not wanted[0] <= len(labels) <= wanted[1] or len(details) != len(labels):
            errors.append(f'{where}: {kind} needs {"exactly 2" if kind == "compare" else "2-4"} labels and as many details')
        if any(words(x) > 5 for x in labels) or any(words(x) > 9 for x in details):
            errors.append(f'{where}: labels are at most 5 words, details at most 9')
        reveal, text = s.get('reveal') or [], texts.get(s.get('point'), '')
        if len(reveal) != len(labels):
            errors.append(f'{where}: give "reveal" with one exact narration phrase per label')
        bad = [r for r in reveal if not phrase_in_text(text, str(r))]
        if bad:
            errors.append(f'{where}: reveal phrases must be copied exactly from {s.get("point")}: {bad}')
    return errors


def scene_times(points, duration, fps):
    """Frame ranges: each card from its point's first word (the first card from 0) to the next card."""
    starts = [0] + [round(p['start'] * fps) for p in points[1:]]
    ends = starts[1:] + [round(duration * fps)]
    return list(zip(starts, ends))


def check_picture(job, cid, name, path, card):
    result = review.review(job.llm('diagram_review'), f'picture-{cid}-{name}', 'picture', (
        'This picture will sit behind a slide of an educational video (heading and summary are overlaid by the '
        'renderer).\nSLIDE: ' + json.dumps({k: card.get(k) for k in ('heading', 'summary', 'picture')},
                                           ensure_ascii=False)), images=[path], thinking=1024, max_tokens=1500)
    failed = result['decision']['failed']
    return result['decision']['pass'], '; '.join(f"{f['label']}: {f['reason']}" for f in failed)


def picture(job, folder, cid, index, card, style):
    """Generate and check one picture; returns (path or None, note)."""
    attempts, avoid, problem = max(1, job.settings.image_attempts), '', ''
    for attempt in range(attempts):
        prompt = (style + '\nScene: ' + card['picture'] + '\n' + imageworld.NO_TEXT +
                  (f'Avoid: {avoid}' if avoid else ''))
        path = imageworld.generate(job.settings, folder, f'card{index + 1}', prompt, seed=101 + attempt,
                                   size=PICTURE_SIZE)
        ok, problem = check_picture(job, cid, f'{index + 1}-{attempt}', path, card)
        if ok:
            return path, ''
        job.log(f'Chapter {cid[1:]}: picture {index + 1} rejected ({problem[:120]}); drawing it again')
        avoid = (avoid + ' ' + problem)[-400:]
    return None, f'Picture for card {index + 1} kept failing its check ({problem[:200]}); card shown without it'


def reveal_frames(card, start, timing, fps):
    """Frames (from the card's start) at which each box appears: when its phrase is spoken, never earlier than the
    box before it. Phrases that cannot be found fall back to the even reveal."""
    out, last = [], 0
    for phrase in card.get('reveal') or []:
        try:
            at = max(last, round(locate(timing['words'], card['point'], phrase)[0] * fps) - start)
        except ValueError:
            return None
        out.append(at)
        last = at
    return out or None


def timeline(plan, chapter, cards, pictures, times, fps, timing=None):
    theme = plan.get('theme') or {}
    scenes = []
    for i, (card, (start, end), src) in enumerate(zip(cards, times, pictures)):
        scenes.append({'id': f'scene-{i + 1:02d}', 'point_id': card['point'], 'index': i, 'from': start,
                       'duration': max(1, end - start), 'kind': card['kind'], 'heading': card['heading'],
                       'summary': card.get('summary') or '', 'labels': card.get('labels') or [],
                       'details': card.get('details') or [], 'banner': card.get('banner') or '',
                       'motion': MOTIONS[i % len(MOTIONS)], 'copy_density': 'standard',
                       'source_ids': chapter.get('source_ids') or [], **({'src': src} if src else {}),
                       **({'reveal': r} if timing and card['kind'] != 'image' and
                          (r := reveal_frames(card, start, timing, fps)) else {})})
    return {'data': {'title': plan.get('title', ''), 'subject': plan.get('title', ''), 'width': CARD_WIDTH,
                     'height': CARD_HEIGHT, 'fps': fps, 'durationInFrames': times[-1][1], 'scenes': scenes,
                     'captions': [], 'sources': [],
                     'creativeBrief': {'resolved_mood': 'neutral', 'intensity': 'restrained',
                                       'theme': {k: theme[k] for k in ('background', 'accent', 'text') if theme.get(k)}}}}


def remotion(settings, work, props):
    """Render the cards with a private copy of the renderer (the remotion tree is only read)."""
    renderer = Path(settings.remotion_root) / 'renderer'
    config = json.loads((Path(settings.remotion_root) / 'config.json').read_text())
    snapshot = work / 'renderer'
    for name in ('package.json', 'package-lock.json', 'tsconfig.json'):
        snapshot.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(renderer / name, snapshot / name)
    for name in ('src', 'public/fonts'):
        shutil.copytree(renderer / name, snapshot / name, dirs_exist_ok=True)
    shutil.copyfile(HERE / 'cards' / 'Video.tsx', snapshot / 'src' / 'Video.tsx')   # adds phrase-timed reveals
    modules = snapshot / 'node_modules'
    if not modules.exists():
        modules.symlink_to((renderer / 'node_modules').resolve(), target_is_directory=True)
    for scene in props['data']['scenes']:
        if scene.get('src'):
            source = Path(scene['src'])
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
            target = snapshot / 'public' / 'cards' / f'{digest}.png'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            scene['src'] = f'cards/{digest}.png'
    props_path = work / 'timeline.json'
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=1))
    layout = work / 'layout'
    with (work / 'layout.log').open('w') as log:
        subprocess.run(['node', str(renderer / 'measure.cjs'), str(snapshot), str(props_path), config['browser'],
                        str(layout)], cwd=snapshot, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    results = layout / 'layout-results.json'
    measured = json.loads(results.read_text()) if results.exists() else {'passed': False, 'note': 'not measured'}
    picture = work / 'cards.mp4'
    with (work / 'render.log').open('w') as log:
        subprocess.run([str(modules / '.bin' / 'remotion'), 'render', 'src/index.ts', 'InfoFilm', str(picture),
                        '--props=' + str(props_path), '--browser-executable=' + config['browser'], '--codec=h264',
                        '--crf=19', '--muted', '--pixel-format=yuv420p', '--concurrency=3'],
                       cwd=snapshot, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=settings.render_timeout)
    out = work / 'slides.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(picture), '-vf', f'scale={settings.width}:{settings.height}',
                    '-r', str(settings.fps), '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(out)],
                   check=True, timeout=600)
    return out, measured


def render_chapter(job, plan, chapter, sc, timing, duration, folder):
    """Pictures, then the card render. Returns (video, notes)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cid, cards = chapter['id'], sc['slides']
    style = (plan.get('theme') or {}).get('picture_style') or PICTURE_STYLE
    pictures, notes = [], []
    for i, card in enumerate(cards):
        if card['kind'] != 'image':
            pictures.append(None)
            continue
        job.chapter_status(cid, 'drawing', f'picture {i + 1}')
        path, note = picture(job, folder / 'pictures', cid, i, card, style)
        pictures.append(str(path) if path else None)
        if note:
            notes.append(note)
    if not getattr(job, 'keep_image_model', False):   # local voice needs the GPU back; remote voice keeps it hot
        imageworld.release_image_model(job.settings)
    points = sorted(timing['points'], key=lambda p: p['start'])
    times = scene_times(points, duration, job.settings.fps)
    job.chapter_status(cid, 'rendering', 'cards')
    props = timeline(plan, chapter, cards, pictures, times, job.settings.fps, timing)
    video, measured = remotion(job.settings, folder / 'render', props)
    if not measured.get('passed'):
        notes.append('Card layout check reported problems; see the slide layout results')
    (folder / 'slides.json').write_text(json.dumps({'cards': cards, 'pictures': pictures, 'notes': notes,
                                                    'layout_passed': bool(measured.get('passed'))}, indent=1))
    return video, notes
