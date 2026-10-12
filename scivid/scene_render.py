"""Render one image-world chapter from a resolved spec (runs in the Manim venv).

spec = {size:[w,h], background, objects:{id:{bbox,centre,pivot,layer?}}, paths:{id:{points,closed,nearest_index}},
        duration, cues:[{verb, start, end, ...}], quality, out, name}
All positions are image pixels measured upstream; this file never invents geometry.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import manim as m

INK, CARD, ACCENT, ACCENT2 = '#14202B', '#FFFFFF', '#E0911B', '#2563EB'
FONT = 'DejaVu Sans'
CAPTION_BAND = .16   # bottom fraction kept clear for burned-in captions
TITLE_ZONE = (0, 0, .42, .14)


def ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


class Spec:
    def __init__(self, data):
        self.d = data
        self.w, self.h = data['size']
        self.s = m.config.frame_width / self.w

    def pt(self, x, y):
        return np.array([(x - self.w / 2) * self.s, (self.h / 2 - y) * self.s, 0.0])


class ChapterScene(m.MovingCameraScene):
    def construct(self):
        spec = Spec(SPEC)
        d = spec.d
        clock = m.ValueTracker(0)
        self.add(clock)
        now = clock.get_value
        cues = d['cues']
        objects = d['objects']
        paths = {k: np.array(v['points']) for k, v in d['paths'].items()}

        bg = m.ImageMobject(np.array(Image.open(d['background']).convert('RGB')))
        bg.points = np.array([spec.pt(0, 0), spec.pt(spec.w, 0), spec.pt(0, spec.h), spec.pt(spec.w, spec.h)])
        self.add(bg)

        # ------------------------------------------------ object state over time (rigid transforms in px)
        def path_function(path_id, s_start, cue):
            """at(u) for u in [0,1] along a path, starting from arc length s_start; returns (at, s_end)."""
            pts = paths[path_id]
            seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
            total = seg[-1]
            closed = d['paths'][path_id].get('closed')
            reverse = cue.get('direction') == 'reverse'
            if closed:
                travel = float(cue.get('laps') or 1) * total * (-1 if reverse else 1)
                s_end = (s_start + travel) % total
                wrap = lambda s: s % total
            else:
                s_end = 0.0 if (reverse or (total - s_start) < s_start) else total
                if cue.get('direction') == 'forward':
                    s_end = total
                travel = s_end - s_start
                wrap = lambda s: min(max(s, 0.0), total)

            def at(u):
                s = wrap(s_start + travel * u)
                return np.array([np.interp(s, seg, pts[:, 0]), np.interp(s, seg, pts[:, 1])])
            return at, s_end

        # Per-object motion segments; each move continues from the previous end on the same path.
        segments = {oid: [] for oid in objects}
        arc = {}
        for c in sorted(cues, key=lambda c: c['start']):
            oid = c.get('object')
            if oid not in objects:
                continue
            if c['verb'] == 'move_along' and c.get('path') in paths:
                pts = paths[c['path']]
                seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
                s0 = arc.get((oid, c['path']), seg[d['paths'][c['path']].get('nearest_index', 0)])
                at, s_end = path_function(c['path'], s0, c)
                arc[(oid, c['path'])] = s_end
                base = at(0)
                closed = d['paths'][c['path']].get('closed')
                segments[oid].append(('move', c, lambda u, at=at, base=base: at(u) - base, closed))
                centre = (d['paths'][c['path']].get('computed') or {}).get('centre')
                if centre is not None and d['paths'][c['path']].get('facing_centre'):
                    # Tied to the centre (string, arm, seat): turn with the angle travelled, so it keeps facing it.
                    laps = float(c.get('laps') or 1) * (-1 if c.get('direction') == 'reverse' else 1)

                    def turn(u, at=at, base=base, centre=np.array(centre, float), laps=laps):
                        # Unwrapped angle travelled: the path's own direction of travel, scaled by laps.
                        a0 = math.atan2(*(base - centre)[::-1])
                        mid = math.atan2(*(at(.25 / max(abs(laps), .25)) - centre)[::-1])
                        sign = 1 if ((mid - a0 + math.pi) % (2 * math.pi) - math.pi) >= 0 else -1
                        return sign * 2 * math.pi * abs(laps) * u
                    segments[oid].append(('face', c, turn, closed))
            elif c['verb'] == 'rotate':
                segments[oid].append(('rotate', c, lambda u, k=float(c.get('turns', .25)): 2 * math.pi * k * u, False))
            elif c['verb'] == 'release':
                segments[oid].append(('release', c, None, False))
            elif c['verb'] == 'shake':
                segments[oid].append(('shake', c, None, False))
            elif c['verb'] == 'swing':
                segments[oid].append(('swing', c, None, False))

        def progress(c, t, steady):
            """0..1 through a cue; steady motion (orbits) keeps a constant speed except at the very ends."""
            if t >= c['end']:
                return 1.0
            k = (t - c['start']) / max(.05, c['end'] - c['start'])
            return k if steady and .06 < k < .94 else ease(k)

        def pose(oid, t, limit=float('inf')):
            """(rotation radians, pivot px, shift px) of an object's layer at time t."""
            o = objects[oid]
            shift, rot = np.zeros(2), 0.0
            top_centre = [(o['bbox'][0] + o['bbox'][2]) / 2, o['bbox'][1]]
            swings = any(seg[0] == 'swing' for seg in segments[oid])
            pivot = np.array(o.get('pivot') or (top_centre if swings else o['centre']), float)
            for kind, c, f, steady in segments[oid]:
                if t < c['start'] or c['start'] >= limit:
                    break
                if kind == 'release':
                    # From here it keeps the velocity it had at the release moment, in a straight line.
                    tr = c['start']
                    r1, p1, s1 = pose(oid, tr, limit=tr)
                    r0, p0, s0 = pose(oid, tr - .05, limit=tr)
                    v = (s1 - s0) / .05
                    return r1, p1 + v * (t - tr), s1 + v * (t - tr)
                u = progress(c, t, steady)
                if kind == 'move':
                    shift = shift + f(u)
                    pivot = pivot + f(u)
                elif kind == 'face':
                    rot += f(u)
                elif kind == 'rotate':
                    rot += f(u)
                elif kind == 'swing' and t < c['end']:
                    # Steady period (a pendulum keeps time); amplitude eases in and out.
                    env = min(1.0, (t - c['start']) / .5, (c['end'] - t) / .5)
                    amp = math.radians(float(c.get('angle', 18)))
                    period = float(c.get('period', 1.6))
                    # Phase runs on the chapter clock: equal pendulums swing in step whenever they start.
                    rot += amp * env * math.sin(2 * math.pi * t / period)
                elif kind == 'shake' and t < c['end']:
                    size = max(o['bbox'][2] - o['bbox'][0], o['bbox'][3] - o['bbox'][1])
                    shift = shift + np.array([math.sin(t * 38) * .02 * size, 0])
            return rot, pivot, shift

        def transformed(oid, t, point):
            rot, pivot, shift = pose(oid, t)
            # Rotate about the (moved) pivot after translating the point with the object.
            cs, sn = math.cos(rot), math.sin(rot)
            r = np.array(point, float) + shift - pivot
            return np.array([cs * r[0] - sn * r[1], sn * r[0] + cs * r[1]]) + pivot

        def current_box(oid, t):
            x0, y0, x1, y1 = objects[oid]['bbox']
            corners = np.array([transformed(oid, t, p) for p in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))])
            return [*corners.min(0), *corners.max(0)]

        # Visibility (show/hide) per object.
        vis_events = {}
        for c in cues:
            if c['verb'] in ('show', 'hide'):
                vis_events.setdefault(c['object'], []).append(c)

        def visibility(oid, t):
            events = sorted(vis_events.get(oid, []), key=lambda c: c['start'])
            level = 0.0 if events and events[0]['verb'] == 'show' else 1.0
            for c in events:
                if t >= c['start']:
                    u = min(1.0, (t - c['start']) / .5)
                    level = u if c['verb'] == 'show' else 1 - u
            return level

        for oid, o in objects.items():
            if not o.get('layer'):
                continue
            mob = m.ImageMobject(np.array(Image.open(o['layer']).convert('RGBA')))
            x0, y0, x1, y1 = o['bbox']

            def place(mob, oid=oid, x0=x0, y0=y0, x1=x1, y1=y1):
                t = now()
                mob.points = np.array([spec.pt(*transformed(oid, t, p)) for p in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))])
                mob.set_opacity(visibility(oid, t))
            place(mob)
            mob.add_updater(place)
            self.add(mob)

        # ------------------------------------------------ overlays
        def window(c, t, linger=.5):
            fade_in = min(1.0, (t - c['start']) / .3)
            fade_out = min(1.0, (c['end'] + linger - t) / .3)
            return max(0.0, min(fade_in, fade_out)) if c['start'] <= t <= c['end'] + linger else 0.0

        for c in [c for c in cues if c['verb'] == 'trace' and c.get('path') in paths]:
            pts = paths[c['path']]

            def trace(c=c, pts=pts):
                t = now()
                if t < c['start']:
                    return m.VGroup()
                u = ease((t - c['start']) / max(.05, c['end'] - c['start']))
                k = max(2, int(len(pts) * u))
                line = m.VMobject(stroke_color=ACCENT2, stroke_width=4).set_points_as_corners([spec.pt(*p) for p in pts[:k]])
                return m.DashedVMobject(line, num_dashes=max(4, k // 6))
            self.add(m.always_redraw(trace))

        for c in [c for c in cues if c['verb'] == 'highlight' and c.get('object') in objects]:
            def ring(c=c):
                t = now()
                a = window(c, t)
                if a <= 0:
                    return m.VGroup()
                x0, y0, x1, y1 = current_box(c['object'], t)
                pad = 10
                rect = m.RoundedRectangle(width=(x1 - x0 + 2 * pad) * spec.s, height=(y1 - y0 + 2 * pad) * spec.s,
                                          corner_radius=.12, stroke_color=ACCENT, stroke_width=5)
                rect.move_to(spec.pt((x0 + x1) / 2, (y0 + y1) / 2))
                return rect.set_stroke(opacity=a * (.65 + .35 * math.sin(7 * (t - c['start']))))
            self.add(m.always_redraw(ring))

        for c in [c for c in cues if c['verb'] == 'arrow' and c.get('object') in objects]:
            def arrow(c=c):
                t = now()
                a = window(c, t)
                if a <= 0:
                    return m.VGroup()
                x0, y0, x1, y1 = current_box(c['object'], t)
                centre = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
                size = max(60.0, min(260.0, .9 * max(x1 - x0, y1 - y0)))
                direction = str(c.get('direction', 'right'))
                vec = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}.get(direction)
                if direction.startswith('toward:') and direction[7:] in objects:
                    bx = current_box(direction[7:], t)
                    vec = np.array([(bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2]) - centre
                elif direction == 'along_motion':
                    vec = transformed(c['object'], t + .05, centre) - transformed(c['object'], t - .05, centre)
                vec = np.array(vec if vec is not None else (1, 0), float)
                vec = vec / (np.linalg.norm(vec) or 1)
                # Start at the box edge in that direction.
                half = np.array([(x1 - x0) / 2, (y1 - y0) / 2])
                edge = centre + vec * min(half[0] / max(abs(vec[0]), 1e-6), half[1] / max(abs(vec[1]), 1e-6))
                tip = edge + vec * size
                group = m.VGroup(m.Arrow(spec.pt(*edge), spec.pt(*tip), buff=0, color=c.get('colour', ACCENT2),
                                         stroke_width=7, max_tip_length_to_length_ratio=.22))
                if c.get('text'):
                    label = m.Text(c['text'], font=FONT, font_size=24, color=INK, weight=m.BOLD)
                    label.next_to(spec.pt(*tip), m.RIGHT if vec[0] >= 0 else m.LEFT, buff=.1)
                    group.add(m.BackgroundRectangle(label, color=CARD, fill_opacity=.85, buff=.06), label)
                return group.set_opacity(a)
            self.add(m.always_redraw(arrow))

        label_cues = [c for c in cues if c['verb'] == 'label' and c.get('object') in objects]

        def free_spot(c, t, card_w, card_h):
            """First candidate beside the object whose card avoids other objects, labels, title and caption band."""
            x0, y0, x1, y1 = current_box(c['object'], t)
            gap = 28
            cands = [(x1 + gap, (y0 + y1) / 2 - card_h / 2), (x0 - gap - card_w, (y0 + y1) / 2 - card_h / 2),
                     ((x0 + x1) / 2 - card_w / 2, y0 - gap - card_h), ((x0 + x1) / 2 - card_w / 2, y1 + gap),
                     (x1 + gap, y0 - card_h), (x0 - gap - card_w, y0 - card_h)]
            blocked = [current_box(k, t) for k in objects if k != c['object']]
            blocked += [b for b in placed.values() if b is not None]
            tz = TITLE_ZONE
            blocked.append([tz[0] * spec.w, tz[1] * spec.h, tz[2] * spec.w, tz[3] * spec.h])

            def ok(x, y):
                if x < 12 or y < 12 or x + card_w > spec.w - 12 or y + card_h > spec.h * (1 - CAPTION_BAND):
                    return False
                return all(x + card_w < b[0] or x > b[2] or y + card_h < b[1] or y > b[3] for b in blocked)
            for x, y in cands:
                if ok(x, y):
                    return x, y
            # Fall back to the nearest free slot on a coarse grid.
            best = None
            for gx in np.linspace(12, spec.w - card_w - 12, 14):
                for gy in np.linspace(12, spec.h * (1 - CAPTION_BAND) - card_h, 9):
                    if ok(gx, gy):
                        dist = math.hypot(gx - x1, gy - y0)
                        if best is None or dist < best[0]:
                            best = (dist, gx, gy)
            return (best[1], best[2]) if best else cands[0]

        placed = {}
        for i, c in enumerate(label_cues):
            def label(c=c, i=i):
                t = now()
                a = window(c, t, linger=.8)
                if a <= 0:
                    placed[i] = None
                    return m.VGroup()
                text = m.Text(c['text'], font=FONT, font_size=26, color=INK)
                card_w, card_h = (text.width + .36) / spec.s, (text.height + .28) / spec.s
                if placed.get(i) is None or c.get('_spot') is None:
                    c['_spot'] = free_spot(c, t, card_w, card_h)
                x, y = c['_spot']
                placed[i] = [x, y, x + card_w, y + card_h]
                box = m.RoundedRectangle(width=card_w * spec.s, height=card_h * spec.s, corner_radius=.08,
                                         stroke_color=ACCENT, stroke_width=3, fill_color=CARD, fill_opacity=.95)
                box.move_to(spec.pt(x + card_w / 2, y + card_h / 2))
                text.move_to(box)
                # Point at the object itself (its measured centre as it moves), not at an empty box corner.
                target = transformed(c['object'], t, objects[c['object']]['centre'])
                anchor = np.array([min(max(target[0], x), x + card_w), min(max(target[1], y), y + card_h)])
                line = m.Line(spec.pt(*anchor), spec.pt(*target), color=ACCENT, stroke_width=3)
                dot = m.Dot(spec.pt(*target), radius=.05, color=ACCENT)
                return m.VGroup(line, dot, box, text).set_opacity(a)
            self.add(m.always_redraw(label))

        for c in [c for c in cues if c['verb'] == 'title']:
            def title(c=c):
                a = window(c, now(), linger=.3)
                if a <= 0:
                    return m.VGroup()
                text = m.Text(c['text'], font=FONT, font_size=34, weight=m.BOLD, color=INK)
                bgr = m.BackgroundRectangle(text, color=CARD, fill_opacity=.88, buff=.16, corner_radius=.1)
                group = m.VGroup(bgr, text)
                group.move_to(spec.pt(spec.w * .03, spec.h * .04), aligned_edge=m.UL)
                return group.set_opacity(a)
            self.add(m.always_redraw(title))

        # ------------------------------------------------ camera: gentle drift, zoom cues
        zooms = sorted([c for c in cues if c['verb'] == 'zoom' and c.get('object') in objects], key=lambda c: c['start'])
        full_w = m.config.frame_width
        drift = d.get('drift', True) and not any(o.get('layer') for o in objects.values())

        def camera(frame):
            t = now()
            width, centre = full_w, np.zeros(3)
            if drift:
                width = full_w * (1 - .035 * min(1.0, t / max(1.0, d['duration'])))
            for c in zooms:
                if c['start'] <= t <= c['end'] + .8:
                    x0, y0, x1, y1 = current_box(c['object'], t)
                    target_w = max(full_w * .45, min(full_w, (x1 - x0) * spec.s * 2.6, (y1 - y0) * spec.s * 2.6 * 16 / 9))
                    k = ease((t - c['start']) / .8) * ease((c['end'] + .8 - t) / .8)
                    width = width + (target_w - width) * k
                    centre = centre + (spec.pt((x0 + x1) / 2, (y0 + y1) / 2) - centre) * k
            frame.set(width=width)
            frame.move_to(centre)
        self.camera.frame.add_updater(camera)
        self.add(self.camera.frame)
        self.play(clock.animate.set_value(d['duration']), run_time=d['duration'], rate_func=m.linear)


if __name__ == '__main__':
    SPEC = json.loads(Path(sys.argv[1]).read_text())
    h, w, fps = SPEC.get('resolution', [720, 1280, 30])
    with m.tempconfig({'pixel_height': h, 'pixel_width': w, 'frame_rate': fps, 'media_dir': SPEC['media_dir'],
                       'output_file': SPEC['name'], 'disable_caching': True, 'verbosity': 'WARNING',
                       'progress_bar': 'none', 'background_color': '#000000'}):
        scene = ChapterScene()
        scene.render()
        print(json.dumps({'video': str(scene.renderer.file_writer.movie_file_path)}))
