"""Image-world scenes: the image model supplies layout and motion paths; code measures them.

Rules from the 2026-10-07 trials:
  * models never emit coordinates; object positions come from vision grounding + SAM2
  * edits are registered back to the source (they drift ~0.7% scale, ~5 px)
  * edited page areas are flattened (edits add grain/ghosts)
  * motion paths are drawn in pure magenta, extracted by colour, then erased
"""
import contextlib
import fcntl
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path

import cv2
import httpx
import numpy as np
from PIL import Image

W, H = 1664, 944          # generation size (nearest /16 to 16:9 the service accepts)
MAGENTA_RULE = ('Draw that path as one thin dashed line in pure bright magenta (#FF00FF). Magenta appears nowhere '
                'else in the picture. ')
NO_TEXT = 'No text, letters, numbers, labels or arrows anywhere in the picture. '


# ------------------------------------------------------------------ Qwen Image
@contextlib.contextmanager
def gpu_lease(lock):
    with open(lock, 'a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def generate(settings, out_dir, name, prompt, *, seed=1, references=(), steps=30, size=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = [Path(r) for r in references]
    gw, gh = size or (W, H)
    key = hashlib.sha256(json.dumps({'p': prompt, 's': seed, 'st': steps, 'w': gw, 'h': gh,
                                     'r': [hashlib.sha256(r.read_bytes()).hexdigest() for r in refs]},
                                    sort_keys=True).encode()).hexdigest()[:12]
    path = out_dir / f'{name}-{key}.png'
    if path.exists():
        return path
    url = settings.image_url
    with gpu_lease(settings.gpu_lock), httpx.Client(timeout=180) as client:
        status = client.get(url + '/api/status').json()
        if status['state'] != 'loaded':
            client.post(url + '/api/load')
            while client.get(url + '/api/status').json()['state'] != 'loaded':
                time.sleep(3)
        files = [('references', (r.name, r.read_bytes(), 'image/png')) for r in refs]
        job = client.post(url + '/api/generate', data={'prompt': prompt, 'width': gw, 'height': gh, 'steps': steps,
                                                       'seed': seed, 'output_format': 'png'},
                          files=files or None).raise_for_status().json()
        while True:
            job = client.get(url + f"/api/jobs/{job['id']}").json()
            if job['status'] == 'complete':
                break
            if job['status'] == 'error':
                raise RuntimeError('Image generation failed: ' + job['message'])
            time.sleep(2)
        path.write_bytes(client.get(url + job['url']).raise_for_status().content)
    path.with_suffix('.json').write_text(json.dumps({'prompt': prompt, 'seed': seed, 'references': [str(r) for r in refs]},
                                                    indent=1))
    return path


def release_image_model(settings):
    with contextlib.suppress(httpx.HTTPError), httpx.Client(timeout=30) as client:
        status = client.get(settings.image_url + '/api/status').json()
        if status.get('state') == 'loaded' and not status.get('busy'):
            client.post(settings.image_url + '/api/unload')


# ------------------------------------------------------------------ measurement helpers
def page_colour(rgb):
    border = np.concatenate([rgb[:10].reshape(-1, 3), rgb[-10:].reshape(-1, 3),
                             rgb[:, :10].reshape(-1, 3), rgb[:, -10:].reshape(-1, 3)])
    return np.median(border, axis=0)


def flatten_page(rgb, tol=26):
    page = page_colour(rgb)
    near = np.abs(rgb.astype(int) - page).max(2) < tol
    out = rgb.copy()
    out[near] = page.astype(np.uint8)
    return out


def register(moving, fixed, exclude=None):
    """Similarity transform mapping `moving` onto `fixed` using SIFT on regions outside `exclude`."""
    gf, gm = cv2.cvtColor(fixed, cv2.COLOR_RGB2GRAY), cv2.cvtColor(moving, cv2.COLOR_RGB2GRAY)
    mask = None if exclude is None else (~exclude).astype(np.uint8) * 255
    sift = cv2.SIFT_create(5000)
    kf, df = sift.detectAndCompute(gf, mask)
    km, dm = sift.detectAndCompute(gm, None)
    if df is None or dm is None or len(kf) < 8 or len(km) < 8:
        return moving, {'registered': False, 'reason': 'too few features'}
    good = [m for m, n in cv2.BFMatcher().knnMatch(dm, df, k=2) if m.distance < .7 * n.distance]
    if len(good) < 12:
        return moving, {'registered': False, 'reason': f'{len(good)} matches'}
    M, inl = cv2.estimateAffinePartial2D(np.float32([km[m.queryIdx].pt for m in good]),
                                         np.float32([kf[m.trainIdx].pt for m in good]),
                                         method=cv2.RANSAC, ransacReprojThreshold=3)
    if M is None:
        return moving, {'registered': False, 'reason': 'no transform'}
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    if abs(scale - 1) > .05:
        return moving, {'registered': False, 'reason': f'implausible scale {scale:.3f}'}
    warped = cv2.warpAffine(moving, M, (fixed.shape[1], fixed.shape[0]), borderMode=cv2.BORDER_REPLICATE)
    return warped, {'registered': True, 'scale': round(scale, 4), 'shift': [round(float(M[0, 2]), 1),
                                                                             round(float(M[1, 2]), 1)],
                    'inliers': int(inl.sum())}


def magenta_mask(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    return (hsv[..., 0] > 135) & (hsv[..., 0] < 165) & (hsv[..., 1] > 110) & (hsv[..., 2] > 120)


def extract_path(rgb):
    """Ordered, smoothed polyline from magenta dashes; closed when the ends meet."""
    mask = magenta_mask(rgb).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    pts = {i: cents[i] for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 4}
    if len(pts) < 4:
        return None
    # Start from the dash farthest from the centroid of all dashes (an end of an open path).
    centre = np.mean(list(pts.values()), axis=0)
    current = max(pts, key=lambda i: np.linalg.norm(pts[i] - centre))
    order, pos = [current], pts.pop(current)
    while pts:
        nxt = min(pts, key=lambda i: np.linalg.norm(pts[i] - pos))
        if np.linalg.norm(pts[nxt] - pos) > 140:
            break
        order.append(nxt)
        pos = pts.pop(nxt)
    poly = np.array([cents[i] for i in order], float)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))]
    dense = np.c_[np.interp(np.linspace(0, seg[-1], 600), seg, poly[:, 0]),
                  np.interp(np.linspace(0, seg[-1], 600), seg, poly[:, 1])]
    k = 12
    dense = np.array([dense[max(0, i - k):i + k + 1].mean(0) for i in range(len(dense))])
    closed = bool(np.linalg.norm(poly[0] - poly[-1]) < 0.12 * seg[-1])
    return {'points': dense.round(1).tolist(), 'closed': closed, 'dashes': len(order),
            'unchained': len(pts), 'length': round(float(seg[-1]), 1), 'mask_pixels': int(mask.sum())}


def erase_magenta(rgb):
    erase = cv2.dilate(magenta_mask(rgb).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
    return cv2.cvtColor(cv2.inpaint(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), erase, 5, cv2.INPAINT_TELEA),
                        cv2.COLOR_BGR2RGB)


# ------------------------------------------------------------------ the scene builder
class PictureRejected(RuntimeError):
    """Every attempt still had problems a teacher would object to; the chapter should be drawn as a diagram."""


SETTING = re.compile(r'\b(floor|ground|rink|road|surface|sky|background|field|pitch|arena|table ?top|water|grass|'
                     r'space|landscape|street|track|playground|room)\b', re.I)


def is_setting(o):
    """A still object that is the backdrop itself (a rink floor, the sky): it fills the picture, so it is not located."""
    return not o.get('moves') and bool(SETTING.search(o['id'].replace('_', ' ') + ' ' + o.get('description', '')))


STORY = re.compile(r'\b(animat\w*|later|afterwards|then|replay\w*|added|adds|viewpoint|side view|sequence|'
                   r'panels?|frames?)\b', re.I)


def frozen(description):
    """Only what is visible now: talk of what happens next makes the image model draw comic panels or several
    copies along the way. Each sentence is cut at the first clause about later events."""
    kept = []
    for sentence in re.split(r'(?<=[.!?])\s+', description.strip()):
        clauses = []
        for clause in re.split(r'(?<=[,;])\s+', sentence):
            if STORY.search(clause):
                break
            clauses.append(clause)
        if clauses:
            kept.append(' '.join(clauses).rstrip(',;') + ('' if clauses[-1].rstrip()[-1:] in '.!?' else '.'))
    return ' '.join(kept) or 'One frozen moment.'


def scene_prompt(style, scene):
    objects = '; '.join(o['description'] + (' (as the backdrop filling the picture)' if is_setting(o) else '')
                        for o in scene['objects'])
    text = (f"{style.strip()} {frozen(scene['description'])} The picture clearly shows: {objects}. "
            'Each listed thing is fully visible, separate from the others where possible, and not cut off by the '
            'frame. Keep the composition uncluttered with calm empty space around the main subject. '
            'Show one frozen moment: every object appears exactly once, at rest in its starting position, with no '
            'motion blur, trails, repeated or ghost copies, and no motion lines. ' + NO_TEXT)
    if scene.get('paths'):
        # A route in the first picture invites the model to draw the mover again along it; it is added by an edit.
        text += 'Do not draw any path, route, orbit or trail line; the route is added later. '
    return text


def path_prompt(scene, path):
    who = next((o['description'] for o in scene['objects'] if o['id'] == path.get('object')), path.get('object'))
    return ('Keep this picture exactly as it is: same objects, same positions, same colours; add nothing else. '
            f"Add only {path['description']}, starting right at {who} where it stands now. " + MAGENTA_RULE +
            'Do not add any new copy of anything.')


GROUND = '''This picture was generated for an educational animation. Check it and locate the requested things.
Requested things (id: description):
{objects}
For each id, count how many separate copies of it are visible, give a tight bounding box around ONE copy
(only that thing, never including other listed things) and its centre; for things that rotate or swing, also the pivot point
(for a hanging pendulum or swing: the fixed point at the top where it hangs from).
Coordinates: integers on a 0-1000 scale relative to image width (x) and height (y).
Also report any visible text, letters or numbers (true/false), and problems with a severity:
major = a teacher would object: wrong science or physics, wrong number of objects, a requested object missing,
duplicated or merged with another, extra copies of an object; minor = pose, expression, style, colour, framing.
Return JSON {{"objects":{{"<id>":{{"found":bool,"count":int,"bbox":[x1,y1,x2,y2],"centre":[x,y],"pivot":[x,y]|null,"note":str}}}},
"text_present":bool,"problems":[{{"severity":"major"|"minor","problem":str}}],"looks_like":str}}'''


def build(settings, chat, out_dir, chapter, style, log=print):
    """Return scene.json (cached) for one image-route chapter."""
    out_dir = Path(out_dir)
    final = out_dir / 'scene.json'
    if final.exists():
        return json.loads(final.read_text())
    scene = chapter['scene']
    prompt = scene_prompt(style, scene)
    redo_file = out_dir.parent / 'redo.json'
    variation = json.loads(redo_file.read_text())['count'] if redo_file.exists() else 0
    feedback, image, ground = '', None, None
    warnings, best = [], None
    for attempt in range(settings.image_attempts):
        log(f"Drawing the picture for chapter {chapter['id'][1:]}" + (f' (try {attempt + 1})' if attempt else ''))
        image = generate(settings, out_dir / 'gen', 'scene', prompt + feedback, seed=11 + attempt * 97 + variation * 1009)
        ground = chat.call(f"ground-{chapter['id']}-{variation}-{attempt}", GROUND.format(
            objects='\n'.join(f"{o['id']}: {o['description']}" + (
                ' (the setting: it may fill the whole picture with no visible edges; found=true when the picture '
                'shows this kind of place, bbox = the area it covers)' if is_setting(o) else '')
                for o in scene['objects'])),
            images=[image], thinking=1024, max_tokens=5000)
        got = ground.get('objects', {})
        for o in scene['objects']:   # a backdrop is never "missing"; it is the picture
            if is_setting(o) and not (got.get(o['id'], {}).get('found') and len(got[o['id']].get('bbox') or []) == 4):
                got[o['id']] = {'found': True, 'count': 1, 'bbox': [0, 0, 1000, 1000], 'centre': [500, 500],
                                'note': 'setting (whole picture)'}
        ground['problems'] = [p for p in ground.get('problems', []) if not (
            isinstance(p, dict) and any(is_setting(o) and o['id'] in str(p.get('problem', '')) and
                                        re.search(r'missing|absent|no (visible )?(floor|edge)', str(p.get('problem', '')), re.I)
                                        for o in scene['objects']))]
        missing = [o['id'] for o in scene['objects'] if not (got.get(o['id'], {}).get('found')
                   and len(got.get(o['id'], {}).get('bbox') or []) == 4 and len(got[o['id']].get('centre') or []) == 2)]
        path_ok = True
        for o in scene['objects']:
            g = got.get(o['id'], {})
            if o.get('moves') and g.get('found') and int(g.get('count') or 1) != 1:
                ground.setdefault('problems', []).append(
                    {'severity': 'major', 'problem': f"{o['id']} appears {g.get('count')} times; it must appear exactly once"})
        for o in scene['objects']:
            g = got.get(o['id'], {})
            if not (o.get('moves') and len(g.get('bbox') or []) == 4):
                continue
            x0, y0, x1, y1 = g['bbox']
            settings_ids = {x['id'] for x in scene['objects'] if is_setting(x)}
            inside = [k for k, other in got.items() if k != o['id'] and k not in settings_ids
                      and len(other.get('centre') or []) == 2
                      and x0 < other['centre'][0] < x1 and y0 < other['centre'][1] < y1]
            if inside:
                ground.setdefault('problems', []).append(
                    {'severity': 'major', 'problem': f"{o['id']} overlaps {', '.join(inside)}; it must stand clear of them"})
        problems = [p.get('problem', '') if isinstance(p, dict) else str(p) for p in ground.get('problems', [])
                    if p and (not isinstance(p, dict) or p.get('severity') == 'major')]
        ground['major_problems'] = problems
        if not missing and not ground.get('text_present') and path_ok and not problems:
            break
        found = len(scene['objects']) - len(missing)
        rank = (found, -len(problems), attempt)  # later attempts carry the reviewer's corrections
        if not ground.get('text_present') and (best is None or rank > best[0]):
            best = (rank, image, ground, missing, path_ok)
        issues = ([f'missing: {", ".join(missing)}'] if missing else []) + \
                 (['the picture contains text or labels; there must be none'] if ground.get('text_present') else []) + \
                 ([] if path_ok else ['the magenta path line is missing']) + problems
        log(f"Redrawing chapter {chapter['id'][1:]}: {'; '.join(issues)[:160]}")
        feedback = ' Important corrections from the previous attempt: ' + '; '.join(issues)[:600] + '.'
    else:
        # Keep the best attempt when at least half the objects are present; drop the missing ones.
        if best is None or best[0][0] * 2 < len(scene['objects']):
            raise RuntimeError(f"Could not get a usable picture for {chapter['id']}: {'; '.join(issues)[:400]}")
        _, image, ground, missing, path_ok = best
        if ground.get('major_problems'):
            raise PictureRejected('; '.join(ground['major_problems'])[:400])
        scene = {**scene, 'objects': [o for o in scene['objects'] if o['id'] not in missing],
                 'paths': [p for p in scene.get('paths', []) if path_ok and p.get('object') not in missing]}
        notes = [f"Picture is missing {', '.join(missing)}; related cues were dropped"] if missing else []
        notes += [] if path_ok else ['The motion path could not be drawn; path motion was dropped']
        notes += ['Kept after review notes: ' + '; '.join(ground.get('major_problems', []))[:300]] if ground.get('major_problems') else []
        warnings.extend(notes)
        log(f"Chapter {chapter['id'][1:]} continues without {', '.join(missing)}")
    rgb = np.array(Image.open(image).convert('RGB'))
    h, w = rgb.shape[:2]
    to_px = lambda p: [p[0] * w / 1000, p[1] * h / 1000]
    objects = {}
    for o in scene['objects']:
        g = ground['objects'][o['id']]
        x0, y0 = to_px(g['bbox'][:2])
        x1, y1 = to_px(g['bbox'][2:])
        objects[o['id']] = {'description': o['description'], 'moves': bool(o.get('moves')),
                            'bbox': [round(x0), round(y0), round(x1), round(y1)],
                            'centre': [round(v, 1) for v in to_px(g['centre'])],
                            'pivot': [round(v, 1) for v in to_px(g['pivot'])] if g.get('pivot') else None}
    # Drawn (magenta) paths are extracted and erased; orbits around an object are computed later.
    paths = {}
    drawn = [p for p in scene.get('paths', []) if not p.get('around')]
    rgb_clean, erased = rgb, False
    if drawn:
        found = extract_path(rgb)
        if found:                  # the model drew the route anyway: use it and paint it out
            rgb_clean, erased = erase_magenta(rgb), True
        else:
            found = draw_path(settings, out_dir, image, rgb, scene, drawn[0], objects.get(drawn[0].get('object')), log)
        if found:
            paths[drawn[0]['id']] = {**found, 'object': drawn[0].get('object')}
        else:
            warnings.append('The motion path could not be drawn; path motion was dropped')
            log(f"Chapter {chapter['id'][1:]}: no usable route for {drawn[0]['id']}; it stays still")
    movers = {k: v for k, v in objects.items() if v['moves']}
    background = None
    if movers:
        masks = mover_masks(settings, out_dir, rgb_clean, movers, objects)
        background = clean_background(settings, out_dir, image, rgb_clean, movers, masks, log)
        for k, mover in movers.items():
            sprite = make_sprite(settings, chat, out_dir, chapter, k, mover, image, style, log)
            if sprite is None and masks[k].get('layer') and verify_cutout(chat, out_dir, chapter, k, mover, masks[k]['layer']):
                sprite = masks[k]['layer']
            if sprite is None:
                log(f"Chapter {chapter['id'][1:]}: {k} stays still (no clean cut-out)")
                warnings.append(f'{k} could not be isolated cleanly; it stays still in this chapter')
                mover['moves'] = False
                continue
            place_sprite(mover, sprite, masks[k].get('bbox') or mover['bbox'])
    for p in scene.get('paths', []):
        if p.get('around') in objects and p.get('object') in objects:
            tied = bool(p.get('facing_centre')) or bool(__import__('re').search(
                r'string|rope|thread|cord|chain|rod|arm|seat|swing', objects[p['object']]['description'] + ' ' + p['object']))
            paths[p['id']] = {**orbit(objects[p['around']], objects[p['object']], rgb.shape[1], rgb.shape[0]),
                              'object': p['object'], 'facing_centre': tied}
            centre = paths[p['id']]['points'][0]
            place_sprite(objects[p['object']], objects[p['object']].get('layer'), None, centre=centre)
    if background is None:
        background = flatten_page(rgb_clean) if erased else rgb_clean
    Image.fromarray(background).save(out_dir / 'background.png')
    return finish_scene(out_dir, image, objects, paths, ground, prompt, warnings, (w, h))


def draw_path(settings, out_dir, image, rgb, scene, path, mover, log=print, attempts=3):
    """Add the route by editing the accepted picture; only the magenta line is taken from the edit, so extra
    copies the edit may draw never reach the lesson. The route is oriented to start at the mover."""
    h, w = rgb.shape[:2]
    for attempt in range(attempts):
        log(f"Drawing the route {path['id']}" + (f' (try {attempt + 1})' if attempt else ''))
        edited = generate(settings, out_dir / 'gen', 'route', path_prompt(scene, path), seed=23 + attempt * 131,
                          references=[image])
        edited = np.array(Image.open(edited).convert('RGB').resize((w, h), Image.LANCZOS))
        warped, info = register(edited, rgb)
        found = extract_path(warped if info.get('registered') else edited)
        if not found or found['length'] < .15 * w:
            continue
        pts = np.array(found['points'])
        if mover:
            x0, y0, x1, y1 = mover['bbox']
            anchor = np.array([(x0 + x1) / 2, y1])                       # where it stands
            reach = .6 * np.hypot(x1 - x0, y1 - y0) + .05 * w
            near = np.linalg.norm(pts - anchor, axis=1)
            if near.min() > reach:
                log(f"Route {path['id']} does not start at {path.get('object')}; redrawing")
                continue
            if not found['closed']:
                if near[-1] < near[0]:
                    pts = pts[::-1]
                    near = near[::-1]
                if near[0] > reach:                    # the line passes the mover: start where it is closest
                    pts = pts[int(near.argmin()):]
            if len(pts) < 20:
                continue
            # The route stays where it was drawn (on the floor); a short glide joins the mover's feet to it.
            gap = float(np.linalg.norm(pts[0] - anchor))
            if gap > 4:
                step = float(np.median(np.linalg.norm(np.diff(pts, axis=0), axis=1))) or 3.0
                lead = np.linspace(anchor, pts[0], max(2, int(gap / step)), endpoint=False)
                pts = np.r_[lead, pts]
            found = {**found, 'points': pts.round(1).tolist(), 'starts_at_object': True}
        return {**found, 'drawn_by': 'edit', 'registration': info}
    return None


def mover_masks(settings, out_dir, rgb_clean, movers, objects):
    """SAM2 masks for the movers (to clean the background); a box-shaped mask when SAM fails."""
    out = {}
    try:
        seg_dir = out_dir / 'layers'
        job = {'image': str(out_dir / 'working.png'), 'weights': settings.sam_weights, 'out': str(seg_dir),
               'boxes': {k: [v['bbox'][0] - 6, v['bbox'][1] - 6, v['bbox'][2] + 6, v['bbox'][3] + 6]
                         for k, v in movers.items()}}
        Image.fromarray(rgb_clean).save(out_dir / 'working.png')
        (out_dir / 'segment-job.json').write_text(json.dumps(job))
        subprocess.run([settings.segment_python, str(Path(__file__).with_name('segment_worker.py')),
                        str(out_dir / 'segment-job.json')], check=True, capture_output=True, timeout=600)
        found = json.loads((seg_dir / 'segments.json').read_text())
    except (subprocess.SubprocessError, OSError, ValueError):
        found = {}
    for k, v in movers.items():
        seg = found.get(k) or {}
        x0, y0, x1, y1 = v['bbox']
        ok = seg and 'error' not in seg and seg['fill_of_box'] >= .04
        if ok:   # the cut must sit around the grounded centre, not on a neighbour inside the box
            mx0, my0, mx1, my1 = seg['bbox']
            ok = mx0 <= v['centre'][0] <= mx1 and my0 <= v['centre'][1] <= my1
        if ok:
            out[k] = {'mask': seg['mask'], 'layer': seg['layer'], 'bbox': seg['bbox']}
        else:
            mask = np.zeros(rgb_clean.shape[:2], np.uint8)
            cv2.ellipse(mask, (int((x0 + x1) / 2), int((y0 + y1) / 2)), (int((x1 - x0) / 2), int((y1 - y0) / 2)),
                        0, 0, 360, 255, -1)
            path = out_dir / f'{k}-boxmask.png'
            Image.fromarray(mask).save(path)
            out[k] = {'mask': str(path), 'layer': None, 'bbox': v['bbox']}
    return out


SPRITE_CHECK = ('This cut-out (on a grey background) is meant to be: {description}. Is it that thing, complete, '
                'shown once, with nothing else from the scene? Return {{"match":bool,"copies":int,"what":str}}')
SPRITE_SAME = ('Image 1 is a crop of a scene; image 2 is a cut-out (on grey) meant to replace {description} from that '
               'crop in an animation. Is image 2 the SAME object as in image 1 - same colours, clothing or markings, '
               'same kind of parts (for example the same type of wheels, skates or helmet) - so a viewer would not '
               'notice a swap? Size and small pose differences are fine. Return {{"same":bool,"differences":str}}')


def sprite_ok(chat, out_dir, chapter, oid, description, path, tag, reference=None):
    rgba = Image.open(path)
    if rgba.mode != 'RGBA':
        return False
    alpha = np.array(rgba)[..., 3] > 127
    share = alpha.mean()
    if share < .004 or (tag == 'cutout' and share > .6):
        return False
    n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha.astype(np.uint8))
    if n < 2 or stats[1:, cv2.CC_STAT_AREA].max() < .75 * alpha.sum():
        return False      # scattered pieces: not one clean object
    grey = Image.new('RGBA', rgba.size, (128, 128, 128, 255))
    grey.alpha_composite(rgba)
    preview = out_dir / f'{oid}-{tag}-check.jpg'
    grey.convert('RGB').save(preview, quality=88)
    verdict = chat.call(f"sprite-{chapter['id']}-{oid}-{tag}", SPRITE_CHECK.format(description=description),
                        images=[preview], thinking=0, max_tokens=1500)
    if not (verdict.get('match') is True and int(verdict.get('copies') or 1) == 1):
        return False
    if reference is None:
        return True
    same = chat.call(f"sprite-same-{chapter['id']}-{oid}-{tag}", SPRITE_SAME.format(description=description),
                     images=[reference, preview], thinking=0, max_tokens=1500)
    if same.get('same') is not True:
        print(f"  {oid} cut-out differs from the scene: {str(same.get('differences'))[:160]}")
    return same.get('same') is True


def chroma_key(path, out):
    """Cut an object drawn on pure magenta: keep non-magenta pixels, largest piece, soft edge, cropped."""
    rgb = np.array(Image.open(path).convert('RGB')).astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    key = (r > 150) & (b > 150) & (g < 110) & (np.abs(r - b) < 90)
    mask = (~key).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    keep = labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if keep.mean() < .01 or keep[:8].any() or keep[-8:].any() or keep[:, :8].any() or keep[:, -8:].any():
        return None      # nothing drawn, or the object runs off the canvas (not complete)
    alpha = cv2.GaussianBlur(keep.astype(np.uint8) * 255, (0, 0), 1.0)
    alpha[~cv2.dilate(keep.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)] = 0
    rgba = np.dstack([rgb.astype(np.uint8), alpha])
    ys, xs = np.nonzero(keep)
    Image.fromarray(rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]).save(out)
    return str(out)


def make_sprite(settings, chat, out_dir, chapter, oid, mover, scene_image, style, log):
    """The moving object as its own image: drawn alone on magenta and keyed out (extraction as a second try)."""
    sprite = out_dir / f'{oid}-sprite.png'
    crop = object_crop(scene_image, mover['bbox'], out_dir / f'{oid}-crop.png')
    for attempt in range(2):
        log(f"Chapter {chapter['id'][1:]}: preparing {oid} as a separate moving piece" + (' (again)' if attempt else ''))
        # Redrawn FROM the scene's own object, so the moving piece is the one the viewer already saw.
        path = generate(settings, out_dir / 'gen', f'{oid}-keyed', (
            f"Redraw the {mover['description'].rstrip('.')} from the reference picture exactly as it looks there: the "
            'same colours, clothing, markings, parts and pose, in the same drawing style. Show it alone and complete, '
            'centred, once, on a plain flat pure magenta (#FF00FF) background filling the whole picture. Nothing else: '
            'no backdrop, no floor, no halo, no shadow, no text. Magenta appears nowhere on the object itself.'),
            seed=23 + attempt * 101, size=(1024, 1024), references=[crop])
        keyed = chroma_key(path, sprite)
        if keyed and sprite_ok(chat, out_dir, chapter, oid, mover['description'], keyed, f'keyed{attempt}',
                               reference=crop):
            return keyed
    return None


def object_crop(scene_image, bbox, out, pad=.08):
    img = Image.open(scene_image).convert('RGB')
    x0, y0, x1, y1 = bbox
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    img.crop((max(0, int(x0 - px)), max(0, int(y0 - py)), min(img.width, int(x1 + px)),
              min(img.height, int(y1 + py)))).save(out)
    return out


def verify_cutout(chat, out_dir, chapter, oid, mover, layer):
    return sprite_ok(chat, out_dir, chapter, oid, mover['description'], layer, 'cutout')


def place_sprite(mover, sprite, bbox, centre=None):
    """Size the sprite to the object's measured size in the scene and put it at its measured place."""
    if sprite:
        mover['layer'] = sprite
    if not mover.get('layer'):
        return
    sw, sh = Image.open(mover['layer']).size
    x0, y0, x1, y1 = bbox or mover['bbox']
    scale = max(x1 - x0, y1 - y0) / max(sw, sh)
    cx, cy = centre if centre is not None else ((x0 + x1) / 2, (y0 + y1) / 2)
    w, h = sw * scale, sh * scale
    mover['bbox'] = [round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2)]
    mover['centre'] = [round(cx, 1), round(cy, 1)]
    mover['pivot'] = None


def orbit(centre_obj, mover, width, height, samples=600):
    """A closed orbit computed around the centre object, through the mover's place, kept inside the frame."""
    cx, cy = centre_obj['centre']
    mx, my = mover['centre']
    size_c = max(centre_obj['bbox'][2] - centre_obj['bbox'][0], centre_obj['bbox'][3] - centre_obj['bbox'][1])
    size_m = max(mover['bbox'][2] - mover['bbox'][0], mover['bbox'][3] - mover['bbox'][1])
    r = max(math.hypot(mx - cx, my - cy), .6 * (size_c + size_m))
    margin = size_m * .6 + 12
    rx = min(r, cx - margin, width - margin - cx)
    ry = min(r, cy - margin, height * .84 - margin - cy)   # keep clear of the caption band
    rx, ry = max(rx, size_c * .7), max(ry, size_c * .5)
    a0 = math.atan2((my - cy) / ry, (mx - cx) / rx)
    pts = [[round(cx + rx * math.cos(a0 - 2 * math.pi * i / samples), 1),
            round(cy + ry * math.sin(a0 - 2 * math.pi * i / samples), 1)] for i in range(samples + 1)]
    return {'points': pts, 'closed': True, 'object': None, 'computed': {'centre': [cx, cy], 'rx': round(rx, 1),
                                                                         'ry': round(ry, 1)}}


def finish_scene(out_dir, image, objects, paths, ground, prompt, warnings, size):
    w, h = size
    # Paths are drawn through their object's position; measure the gap so motion starts at the object.
    for pid, p in paths.items():
        oid = p.get('object')
        if oid in objects:
            pts = np.array(p['points'])
            c = np.array(objects[oid]['centre'])
            d = np.linalg.norm(pts - c, axis=1)
            p['nearest_index'] = 0 if p.get('starts_at_object') else int(d.argmin())
            p['object_gap_px'] = round(float(d.min()), 1)
    result = {'size': [w, h], 'source_image': str(image), 'background': str(out_dir / 'background.png'),
              'objects': objects, 'paths': paths, 'grounding': ground, 'prompt': prompt, 'warnings': warnings}
    (Path(out_dir) / 'scene.json').write_text(json.dumps(result, indent=1))
    return result


def still_visible(background, original, mask, search=70, threshold=.8):
    """True when a solid piece of the removed object reappears near its old place.

    Edits sometimes redraw the object slightly shifted. Thin parts (strings, chains) are eroded away first,
    then each solid piece (a bob, a seat, a ball) is template-matched in the neighbourhood.
    """
    depth = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    solid = (depth > max(3.5, .35 * depth.max())).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid)
    H, W = mask.shape
    for i in range(1, n):
        x0, y0, w, h, area = stats[i]
        if area < 40:
            continue
        grow = int(2 * .35 * depth.max()) + 3
        piece = cv2.dilate((labels == i).astype(np.uint8), np.ones((grow, grow), np.uint8)) & mask.astype(np.uint8)
        ys, xs = np.nonzero(piece)
        py0, py1, px0, px1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        template = cv2.cvtColor(original[py0:py1, px0:px1].astype(np.uint8), cv2.COLOR_RGB2GRAY)
        tmask = (piece[py0:py1, px0:px1] * 255).astype(np.uint8)
        sy0, sy1 = max(0, py0 - search), min(H, py1 + search)
        sx0, sx1 = max(0, px0 - search), min(W, px1 + search)
        region = cv2.cvtColor(background[sy0:sy1, sx0:sx1].astype(np.uint8), cv2.COLOR_RGB2GRAY)
        if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
            continue
        score = np.nan_to_num(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED, mask=tmask),
                              nan=0.0, posinf=0.0, neginf=0.0)
        if float(score.max()) > threshold:
            return True
    return False


def clean_background(settings, out_dir, image, rgb_clean, movers, layers, log):
    """layers: {id: {'mask': path}} - SAM masks, or box masks when SAM could not cut the object."""
    """Remove moving objects: one edit of the native image, registered and page-flattened.
    Falls back to inpainting the movers' masks when the edit leaves them behind or drifts."""
    names = ', '.join(m['description'] for m in movers.values())
    log('Preparing the background behind the moving objects')
    edited = generate(settings, out_dir / 'gen', 'background', (
        f'Edit the reference picture: remove {names} completely, and remove any magenta line. Show what is '
        'behind them. Keep everything else exactly identical, in the same position and framing.'),
        seed=5, references=[image])
    edited = np.array(Image.open(edited).convert('RGB').resize((rgb_clean.shape[1], rgb_clean.shape[0]),
                                                                Image.LANCZOS))
    union = np.zeros(rgb_clean.shape[:2], bool)
    for v in layers.values():
        union |= np.array(Image.open(v['mask'])) > 127
    union = cv2.dilate(union.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    warped, info = register(edited, rgb_clean, exclude=union)
    # Only take edited pixels inside the movers' neighbourhood; keep the original everywhere else.
    feather = cv2.GaussianBlur(cv2.dilate(union.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(float),
                               (0, 0), 6)[..., None]
    composite = (rgb_clean * (1 - feather) + warped * feather).astype(np.uint8)
    # Verify removal: inside each mover's mask the composite must differ from the original.
    leftovers = []
    for k, v in layers.items():
        m = np.array(Image.open(v['mask'])) > 127
        # Every part of the object must be gone: most of its pixels must change, not just on average.
        changed = (np.abs(composite.astype(int) - rgb_clean.astype(int)).mean(2) > 25)[m].mean()
        if changed < .6 or still_visible(composite, rgb_clean, m):
            leftovers.append(k)
    if leftovers or not info.get('registered'):
        log('Cleaning the background by filling in behind the moving objects')
        erase = (cv2.dilate(union.astype(np.uint8), np.ones((9, 9), np.uint8)) * 255)
        composite = cv2.cvtColor(cv2.inpaint(cv2.cvtColor(rgb_clean, cv2.COLOR_RGB2BGR), erase, 9,
                                             cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB)
    # Edits leave grain only where their pixels were used, and only plain light pages need flattening;
    # on dark or glowing scenes (space, night) snapping to one colour would leave a visible patch.
    if page_colour(rgb_clean).mean() > 170:
        flat = flatten_page(composite)
        edited = feather[..., 0] > .02
        composite[edited] = flat[edited]
    return composite
