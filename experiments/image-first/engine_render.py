"""Compile word-anchored cues against measured layers and render with Manim.

Nothing here contains hand-entered coordinates for the engine: every position comes
from scene.json (vision grounding + SAM2 + Hough), every time from MFA words, every
action from the planner's cues. Constants below are presentation/controller choices.

Run with the Manim venv:
  .venv-manim-pilot/bin/python engine_render.py [--quality low|high]
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
import manim as m

ROOT = Path(__file__).resolve().parent
L = ROOT / 'layers'
NARR = Path('/home/nitin/remotion/artifacts/experiments/four-stroke-image-mggen-manim/narration-scenes.json')

SCENE = json.loads((L / 'scene.json').read_text())
W, H = SCENE['canvas_size']
S = 14.222222 / W  # px -> scene units (16:9 frame width)
GAS = {'fresh_mixture': ('#4FA3FF', .38), 'compressed': ('#2F5BFF', .55),
       'burning': ('#FF8A2A', .6), 'exhaust': ('#8A8F98', .5)}
INK, ACCENT = '#1F2A37', '#E8A317'
VALVE_LIFT_FRACTION = .30  # of the measured valve-head width (controller choice)


def scene_pt(x, y):
    return np.array([(x - W / 2) * S, (H / 2 - y) * S, 0.0])


# ---------------------------------------------------------------- timeline
def load_timeline(points, cue_file):
    narr = json.loads(NARR.read_text())
    scenes = [s for s in narr['scenes'] if s['id'] in points]
    t0, t1 = scenes[0]['start'], scenes[-1]['end']
    words = {w['id']: (w['start'] - t0, w['end'] - t0, w['word']) for w in narr['words'] if w['point_id'] in points}
    cues = json.loads(Path(cue_file).read_text())['cues']
    return t0, t1 - t0, words, cues


def cue_window(cue, words):
    if 'at' in cue:
        s = words[cue['at']][0]
        return s, s + .6
    return words[cue['from']][0], words[cue['to']][1]


# ---------------------------------------------------------------- mechanism
class Mechanism:
    """Ideal slider-crank fitted to the measured anchors; theta = crank-pin angle (image frame, y down)."""

    def __init__(self):
        a = SCENE['anchors']
        self.axle = np.array(a['axle'])
        self.pin0 = np.array(a['crank_pin'])
        self.wrist0 = np.array(a['wrist_pin'])
        self.r = float(np.linalg.norm(self.pin0 - self.axle))
        self.L = float(np.linalg.norm(self.wrist0 - self.pin0))
        self.axis_x = self.wrist0[0]
        self.theta0 = math.atan2(self.pin0[1] - self.axle[1], self.pin0[0] - self.axle[0])
        # Feasibility: the drawn throw may drive the crown into the head. Keep a clearance of
        # 10% of the stroke above the crown at TDC by shortening the throw if necessary.
        roof = min(SCENE['layers'][v]['bbox_px'][3] for v in ('valve_L', 'valve_R'))
        crown_offset = self.wrist0[1] - SCENE['layers']['piston']['bbox_px'][1]
        reach = self.axle[1] - math.sqrt(self.L ** 2 - (self.axis_x - self.axle[0]) ** 2) - crown_offset - roof
        self.r_drawn = self.r
        self.r = min(self.r, reach / 1.2)
        self.adapted = self.r < self.r_drawn

    def pin(self, th):
        return self.axle + self.r * np.array([math.cos(th), math.sin(th)])

    def wrist(self, th):
        p = self.pin(th)
        return np.array([self.axis_x, p[1] - math.sqrt(self.L ** 2 - (self.axis_x - p[0]) ** 2)])

    def check(self, samples=720):
        """Invariant: rod length is preserved and the wrist stays on the cylinder axis."""
        err = max(abs(np.linalg.norm(self.wrist(t) - self.pin(t)) - self.L)
                  for t in np.linspace(0, 4 * math.pi, samples))
        ys = [self.wrist(t)[1] for t in np.linspace(0, 2 * math.pi, samples)]
        return {'throw_drawn_px': round(float(self.r_drawn), 1), 'throw_used_px': round(float(self.r), 1),
                'throw_adapted_for_clearance': bool(self.adapted),
                'rod_length_error_px': float(err), 'stroke_px': float(max(ys) - min(ys)),
                'tdc_wrist_y': float(min(ys)), 'bdc_wrist_y': float(max(ys))}


def crank_schedule(cues, words, mech, duration):
    """Piecewise crank angle. 'down' ends with the pin at the bottom (BDC), 'up' at the top (TDC).
    Rotation is always clockwise on screen (angle increasing). Before the first stroke the
    mechanism settles from the canvas pose to that stroke's start position."""
    strokes = sorted((c for c in cues if c['verb'] == 'stroke'), key=lambda c: words[c['from']][0])
    keys = [(0.0, mech.theta0)]
    TDC, BDC = -math.pi / 2, math.pi / 2
    th, issues = mech.theta0, []
    for i, c in enumerate(strokes):
        s, e = cue_window(c, words)
        expected = TDC if c['direction'] == 'down' else BDC
        if i == 0:
            # Settle the canvas pose (shortest way) to the first stroke's start during the lead-in.
            delta = (expected - th + math.pi) % (2 * math.pi) - math.pi
            settle_end = max(.5, s - .2)
            keys.append((settle_end * .5, th))
            th += delta
            keys.append((settle_end, th))
        elif abs((th - expected + math.pi) % (2 * math.pi) - math.pi) > 1e-3:
            issues.append(f"stroke {c['direction']} at {c['from']} does not start from its dead centre")
        keys.append((s, th))
        th += math.pi  # one stroke = half a crank revolution, clockwise
        keys.append((e, th))
    crank_schedule.issues = issues
    keys.append((duration, th))
    keys.sort(key=lambda k: k[0])
    times = np.array([k[0] for k in keys])
    values = np.array([k[1] for k in keys])

    def angle(t):
        return float(np.interp(t, times, values))
    return angle, keys


# ---------------------------------------------------------------- layers
def layer_image(name):
    info = SCENE['layers'][name]
    return np.array(Image.open(L / info['file']).convert('RGBA')), info['bbox_px']


def outline_png(name, pad=10, width=5):
    import cv2
    rgba, (x0, y0, x1, y1) = layer_image(name)
    alpha = np.pad(rgba[..., 3], pad) > 127
    ring = cv2.dilate(alpha.astype(np.uint8), np.ones((width * 2 + 1,) * 2, np.uint8)) & ~alpha
    out = np.zeros(ring.shape + (4,), np.uint8)
    out[ring > 0] = [232, 163, 23, 255]
    return out, [x0 - pad, y0 - pad, x1 + pad, y1 + pad]


class Layer:
    """An image layer whose pose is a rigid transform of its image-pixel bbox."""

    def __init__(self, array, bbox):
        self.mob = m.ImageMobject(array)
        x0, y0, x1, y1 = bbox
        self.corners = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]], float)
        self.place(0.0, np.zeros(2), np.zeros(2))

    def place(self, rot, pivot, shift):
        """Rotate by rot (radians, image frame: positive = clockwise on screen) about pivot, then shift."""
        c, s = math.cos(rot), math.sin(rot)
        rel = self.corners - pivot
        moved = np.c_[c * rel[:, 0] - s * rel[:, 1], s * rel[:, 0] + c * rel[:, 1]] + pivot + shift
        self.mob.points = np.array([scene_pt(x, y) for x, y in moved])


class EngineScene(m.Scene):
    def construct(self):
        cfg = self.renderer.camera
        t0, duration, words, cues = load_timeline(POINTS, CUE_FILE)
        mech = Mechanism()
        angle, keys = crank_schedule(cues, words, mech, duration)
        clock = m.ValueTracker(0)
        self.add(clock)
        now = lambda: clock.get_value()

        bg = m.ImageMobject(np.array(Image.open(SCENE['background']).convert('RGB')))
        bg.points = np.array([scene_pt(0, 0), scene_pt(W, 0), scene_pt(0, H), scene_pt(W, H)])
        self.add(bg)

        # --- gas fill above the crown (state persists until the next gas cue)
        fixed = SCENE['fixed']
        bore = fixed['cylinder_bore']
        # Chamber roof = measured bottoms of the closed valve heads (more precise than the VLM box).
        chamber_top = min(SCENE['layers'][v]['bbox_px'][3] for v in ('valve_L', 'valve_R')) - 6
        crown0 = SCENE['layers']['piston']['bbox_px'][1]
        gas_cues = sorted((c for c in cues if c['verb'] == 'gas'), key=lambda c: words[c['from']][0])

        def gas_state(t):
            active = [c for c in gas_cues if words[c['from']][0] <= t]
            if not active:
                return None, 0.0
            c = active[-1]
            fade = min(1.0, (t - words[c['from']][0]) / .5)
            return c['kind'], fade

        def gas_mob():
            t = now()
            kind, fade = gas_state(t)
            crown = max(chamber_top + 10, crown0 + (mech.wrist(angle(t))[1] - mech.wrist0[1]))
            poly = [scene_pt(bore[0] + 6, chamber_top + 4), scene_pt(bore[2] - 6, chamber_top + 4),
                    scene_pt(bore[2] - 6, crown + 8), scene_pt(bore[0] + 6, crown + 8)]
            color, alpha = GAS.get(kind, ('#FFFFFF', 0))
            return m.Polygon(*poly, stroke_width=0, fill_color=color, fill_opacity=alpha * fade)
        self.add(m.always_redraw(gas_mob))

        # --- mechanism layers (crank < rod < piston), driven by the crank angle
        crank = Layer(*layer_image('crankshaft'))
        rod = Layer(*layer_image('conrod'))
        piston = Layer(*layer_image('piston'))
        rod_dir0 = math.atan2(*(mech.wrist0 - mech.pin0)[::-1])

        def pose_crank(t):
            return angle(t) - mech.theta0, mech.axle, np.zeros(2)

        def pose_rod(t):
            th = angle(t)
            p, w = mech.pin(th), mech.wrist(th)
            return math.atan2(*(w - p)[::-1]) - rod_dir0, mech.pin0, p - mech.pin0

        def pose_piston(t):
            return 0.0, mech.wrist0, np.array([0.0, mech.wrist(angle(t))[1] - mech.wrist0[1]])

        poses = {'crankshaft': pose_crank, 'conrod': pose_rod, 'piston': pose_piston}
        for layer, pose in ((crank, pose_crank), (rod, pose_rod), (piston, pose_piston)):
            layer.mob.add_updater(lambda mob, layer=layer, pose=pose: layer.place(*pose(now())))
            self.add(layer.mob)

        # --- valves: open/closed state changes, lift from measured head width
        valve_events = {}
        for c in cues:
            if c['verb'] == 'valve':
                valve_events.setdefault(c['part'], []).append((words[c['at']][0], c['state']))
        valves = {}
        for name in ('valve_L', 'valve_R'):
            arr, bbox = layer_image(name)
            head_width = int((arr[-12:, :, 3] > 127).any(0).sum())
            lift = VALVE_LIFT_FRACTION * head_width
            events = sorted(valve_events.get(name, []))

            def opening(t, events=events):
                level = 0.0
                for at, state in events:
                    k = min(1.0, max(0.0, (t - at) / .5))
                    level = level + (k * ((1.0 if state == 'open' else 0.0) - level))
                return level
            layer = Layer(arr, bbox)
            layer.mob.add_updater(lambda mob, layer=layer, lift=lift, opening=opening:
                                  layer.place(0.0, np.zeros(2), np.array([0.0, lift * opening(now())])))
            valves[name] = (layer, lift, opening)
            poses[name] = (lambda t, lift=lift, opening=opening: (0.0, np.zeros(2), np.array([0.0, lift * opening(t)])))
            self.add(layer.mob)

        # --- flow arrows along the measured passage, into the chamber
        passage = {'valve_L': fixed['intake_passage'], 'valve_R': fixed['exhaust_passage']}
        chamber = fixed['combustion_chamber']
        for c in [c for c in cues if c['verb'] == 'flow']:
            s, e = cue_window(c, words)
            route = [np.array(p) for p in passage[c['through']]]
            centre = np.array([(chamber[0] + chamber[2]) / 2, (chamber[1] + chamber[3]) / 2 + 20])
            route = route + [centre] if c['through'] == 'valve_L' else [centre] + route
            if c.get('direction') == 'out':
                route = route
            seg = np.cumsum([0] + [np.linalg.norm(b - a) for a, b in zip(route, route[1:])])

            def along(u, route=route, seg=seg):
                d = (u % 1.0) * seg[-1]
                i = min(int(np.searchsorted(seg, d, side='right')) - 1, len(route) - 2)
                f = (d - seg[i]) / max(1e-6, seg[i + 1] - seg[i])
                return route[i] + f * (route[i + 1] - route[i])

            def dots(s=s, e=e, along=along):
                t = now()
                group = m.VGroup()
                if s <= t <= e + .4:
                    vis = min(1.0, (t - s) / .4, max(0.0, (e + .4 - t) / .4))
                    for k in range(6):
                        p = along((t * .35 + k / 6))
                        group.add(m.Dot(scene_pt(*p), radius=.06, color='#2F7BFF', fill_opacity=.9 * vis))
                return group
            self.add(m.always_redraw(dots))

        # --- highlights follow their part
        for c in [c for c in cues if c['verb'] == 'highlight']:
            s, e = cue_window(c, words)
            ring = Layer(*outline_png(c['part']))
            pose = poses[c['part']]

            def upd(mob, ring=ring, pose=pose, s=s, e=e):
                t = now()
                ring.place(*pose(t))
                pulse = .6 + .4 * math.sin(6 * (t - s))
                mob.set_opacity(pulse * min(1.0, max(0.0, (t - s) / .3), max(0.0, (e - t) / .3)))
            ring.mob.add_updater(upd)
            self.add(ring.mob)

        # --- spark at the plug tip
        tip = fixed['spark_plug_tip']
        for c in [c for c in cues if c['verb'] == 'spark']:
            s = words[c['at']][0]

            def spark(s=s):
                t = now()
                k = (t - s) / .7
                if not 0 <= k <= 1:
                    return m.VGroup()
                star = m.Star(n=8, outer_radius=.18 + .25 * k, inner_radius=.07 + .08 * k,
                              color='#FFD84A', fill_opacity=1 - k, stroke_width=0)
                return star.move_to(scene_pt(tip[0], tip[1] + 8))
            self.add(m.always_redraw(spark))

        # --- right-hand panel: titles and part labels with leader lines
        panel_x = 1180
        part_centre = {name: (lambda name=name: np.array([(SCENE['layers'][name]['bbox_px'][0] + SCENE['layers'][name]['bbox_px'][2]) / 2,
                                                         (SCENE['layers'][name]['bbox_px'][1] + SCENE['layers'][name]['bbox_px'][3]) / 2]))
                       for name in SCENE['layers']}
        label_cues = sorted([c for c in cues if c['verb'] == 'label'], key=lambda c: words[c['from']][0])
        slots = {}
        for c in label_cues:
            s, e = cue_window(c, words)
            busy = {k for k, (ss, ee) in slots.items() if not (e < ss or s > ee)}
            slot = next(i for i in range(6) if i not in busy)
            slots[slot] = (s, e)
            c['_slot'] = slot
        for c in label_cues:
            s, e = cue_window(c, words)
            y = 330 + 90 * c['_slot']

            def label(c=c, s=s, e=e, y=y):
                t = now()
                vis = min(1.0, max(0.0, (t - s) / .3), max(0.0, (e + .6 - t) / .3))
                if vis <= 0:
                    return m.VGroup()
                text = m.Text(c['text'], font='DejaVu Sans', font_size=26, color=INK).move_to(scene_pt(panel_x, y))
                box = m.SurroundingRectangle(text, buff=.12, corner_radius=.08, color=ACCENT, stroke_width=3,
                                             fill_color='#FFFFFF', fill_opacity=.92)
                pose = poses[c['part']](t)
                rot, piv, sh = pose
                cx, cy = part_centre[c['part']]()
                cc, ss_ = math.cos(rot), math.sin(rot)
                rel = np.array([cx, cy]) - piv
                target = np.array([cc * rel[0] - ss_ * rel[1], ss_ * rel[0] + cc * rel[1]]) + piv + sh
                line = m.Line(box.get_left(), scene_pt(*target), color=ACCENT, stroke_width=3)
                dot = m.Dot(scene_pt(*target), radius=.05, color=ACCENT)
                return m.VGroup(line, dot, box, text).set_opacity(vis)
            self.add(m.always_redraw(label))

        title_cues = [c for c in cues if c['verb'] == 'title']
        for c in title_cues:
            s, e = cue_window(c, words)

            def title(c=c, s=s, e=e):
                t = now()
                vis = min(1.0, max(0.0, (t - s) / .3), max(0.0, (e + .3 - t) / .3))
                if vis <= 0:
                    return m.VGroup()
                return m.Text(c['text'], font='DejaVu Sans', font_size=46, weight=m.BOLD,
                              color=INK).move_to(scene_pt(panel_x + 60, 170)).set_opacity(vis)
            self.add(m.always_redraw(title))

        # --- captions from MFA words (chunks end at punctuation or 9 words)
        chunks, cur = [], []
        for wid in sorted(words):
            cur.append(words[wid])
            if words[wid][2][-1:] in '.,;:' or len(cur) >= 9:
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)

        def caption():
            t = now()
            for ch in chunks:
                if ch[0][0] - .1 <= t <= ch[-1][1] + .25:
                    txt = m.Text(' '.join(w[2] for w in ch), font='DejaVu Sans', font_size=30, color='#FFFFFF')
                    bgbox = m.BackgroundRectangle(txt, color='#111827', fill_opacity=.72, buff=.14)
                    return m.VGroup(bgbox, txt).move_to(m.DOWN * 3.45)
            return m.VGroup()
        self.add(m.always_redraw(caption))

        tdc_crown = crown0 + (mech.wrist(-math.pi / 2)[1] - mech.wrist0[1])
        clearance = {'chamber_roof_y': chamber_top + 6, 'tdc_crown_y': round(float(tdc_crown), 1),
                     'clearance_px': round(float(tdc_crown - chamber_top - 6), 1),
                     'geometric_compression_ratio': round((mech.check()['stroke_px'] + max(1, tdc_crown - chamber_top - 6)) / max(1, tdc_crown - chamber_top - 6), 1)}
        report = {'mechanism_check': mech.check(), 'clearance': clearance, 'schedule_issues': crank_schedule.issues, 'crank_keys': [[round(a, 3), round(math.degrees(b), 1)] for a, b in keys],
                  'duration': duration, 'audio_offset': t0, 'cues': len(cues)}
        (ROOT / 'renders').mkdir(exist_ok=True)
        (ROOT / 'renders' / f'{OUT_NAME}-compile.json').write_text(json.dumps(report, indent=2))
        self.play(clock.animate.set_value(duration), run_time=duration, rate_func=m.linear)


POINTS, CUE_FILE, OUT_NAME = ('N02', 'N03'), ROOT / 'cues/qwen-cues.json', 'engine-n02-n03'

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--quality', default='low', choices=['low', 'high'])
    ap.add_argument('--cues', default=str(CUE_FILE))
    ap.add_argument('--name', default=OUT_NAME)
    args = ap.parse_args()
    CUE_FILE, OUT_NAME = Path(args.cues), args.name
    h, w, fps = (480, 854, 15) if args.quality == 'low' else (720, 1280, 30)
    with m.tempconfig({'pixel_height': h, 'pixel_width': w, 'frame_rate': fps, 'media_dir': str(ROOT / 'media'),
                       'output_file': OUT_NAME, 'disable_caching': True, 'verbosity': 'WARNING',
                       'background_color': '#FDFAF2'}):
        scene = EngineScene()
        scene.render()
        print(scene.renderer.file_writer.movie_file_path)
