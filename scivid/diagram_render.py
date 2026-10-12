"""Render a diagram chapter from its spec as a Manim animation (trusted code; sandboxed, LaTeX available).

Input JSON: {spec, cues: [{verb, target, start, end, ...}], duration, title, resolution}
Discrete moments are real Manim animations played on the narration's cue words (Create, Write,
TransformMatchingTex, squares growing on sides, TransformFromCopy, Indicate, camera focus). Continuous
processes (counters, movers, plots, traces) are updaters on the scene clock, so they run alongside.
The model supplied no code and no coordinates.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import manim as m

from diagram_spec import graph_points, shape_points

BG, INK, MUTED = '#F7F5EF', '#1B2733', '#6B7280'
COLOURS = {'blue': '#2563EB', 'orange': '#D97706', 'green': '#15803D', 'red': '#C2410C', 'purple': '#7C3AED',
           'grey': '#6B7280', 'teal': '#0B7A83'}
ACCENT, HIGHLIGHT = '#D97706', '#E0911B'
FONT = 'DejaVu Sans'
BODY = (-6.6, -2.45, 6.6, 2.75)       # x0, y0, x1, y1 (captions live below, the heading above)
BIG = {'graph', 'shape', 'path_motion', 'bars', 'table', 'number_line'}


def ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def text(value, size=28, colour=INK, weight=m.NORMAL):
    return m.Text(str(value), font=FONT, font_size=size, color=colour, weight=weight)


def colour(name, default='blue'):
    return COLOURS.get(str(name or default).lower(), COLOURS[default])


def remember(mob):
    for f in mob.get_family():
        if isinstance(f, m.VMobject) and not hasattr(f, '_alpha'):
            f._alpha = (f.get_stroke_opacity(), f.get_fill_opacity())
    return mob


def fade(mob, a):
    """Scale every part's ORIGINAL stroke/fill opacity (set_opacity would fill hollow shapes)."""
    for f in mob.get_family():
        if hasattr(f, '_alpha'):
            f.set_stroke(opacity=f._alpha[0] * a, family=False)
            f.set_fill(opacity=f._alpha[1] * a, family=False)
    return mob


def fit(mob, slot, max_scale=1.6):
    x0, y0, x1, y1 = slot
    w, h = (x1 - x0) * .92, (y1 - y0) * .9
    if mob.width > 0 and mob.height > 0:
        mob.scale(min(w / mob.width, h / mob.height, max_scale))
    mob.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])
    return mob


# ---------------------------------------------------------------- layout
def slots(spec):
    x0, y0, x1, y1 = BODY
    elements = spec['elements']

    def stack(items, box):
        bx0, by0, bx1, by1 = box
        def weight(e):
            if e['type'] in BIG:
                return 3.0
            if e['type'] == 'equation_steps':
                return max(1.0, .7 * len(e.get('steps', [])))
            if e['type'] == 'cards':
                n = len(e.get('items', []))
                return 1.3 * (math.ceil(n / 2) if n > 2 else 1)    # wrapped cards need a row's height each
            if e['type'] == 'note':
                return 1.2
            return .9
        weights = [weight(e) for e in items]
        total, top, out = sum(weights), by1, {}
        for e, wt in zip(items, weights):
            h = (by1 - by0) * wt / total
            out[e['id']] = (bx0, top - h, bx1, top)
            top -= h
        return out
    if spec['layout'] == 'split':
        mid = (x0 + x1) / 2
        left = [e for e in elements if e.get('panel') == 'left']
        right = [e for e in elements if e.get('panel') != 'left']
        return {**stack(left, (x0, y0, mid - .15, y1)), **stack(right, (mid + .15, y0, x1, y1))}
    big = [e for e in elements if e['type'] in BIG]
    small = [e for e in elements if e['type'] not in BIG]
    if big and small:
        cut = x0 + (x1 - x0) * .6
        return {**stack(big, (x0, y0, cut - .15, y1)), **stack(small, (cut + .15, y0, x1, y1))}
    if len(big) == 2:
        mid = (x0 + x1) / 2
        return {big[0]['id']: (x0, y0, mid - .15, y1), big[1]['id']: (mid + .15, y0, x1, y1)}
    if len(big) >= 3:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        cells = [(x0, my + .1, mx - .15, y1), (mx + .15, my + .1, x1, y1),
                 (x0, y0, mx - .15, my - .1), (mx + .15, y0, x1, my - .1)]
        return {e['id']: cells[i] for i, e in enumerate(big[:4])}
    return stack(elements, BODY)


# ---------------------------------------------------------------- element builders
class Element:
    """A built element: its group, addressable parts, and per-type state hooks."""

    def __init__(self, data, slot):
        self.data, self.slot, self.parts, self.extra = data, slot, {}, {}
        self.group = remember(getattr(self, 'build_' + data['type'])(data))

    def build_equation_steps(self, d):
        lines = [m.MathTex(s, color=INK, font_size=46) for s in d['steps']]
        group = m.VGroup(*lines).arrange(m.DOWN, buff=.38)
        fit(group, self.slot, max_scale=1.25)
        self.extra['lines'] = lines
        return group

    def build_graph(self, d):
        x0, y0, x1, y1 = self.slot
        xa, ya = d['x'], d['y']
        ax = m.Axes(x_range=[xa['min'], xa['max'], xa['step']], y_range=[ya['min'], ya['max'], ya['step']],
                    x_length=(x1 - x0) * .78, y_length=(y1 - y0) * .72, tips=False,
                    axis_config={'color': INK, 'stroke_width': 2.5, 'include_ticks': True})
        ticks = m.VGroup()
        for v in np.arange(xa['min'], xa['max'] + 1e-9, xa['step']):
            ticks.add(text(f'{v:g}', 20, MUTED).next_to(ax.c2p(v, ya['min']), m.DOWN, buff=.12))
        for v in np.arange(ya['min'], ya['max'] + 1e-9, ya['step']):
            ticks.add(text(f'{v:g}', 20, MUTED).next_to(ax.c2p(xa['min'], v), m.LEFT, buff=.12))
        labels = m.VGroup(text(xa.get('label', ''), 22).next_to(ax.x_axis, m.DOWN, buff=.5),
                          text(ya.get('label', ''), 22).rotate(math.pi / 2).next_to(ax.y_axis, m.LEFT, buff=.55))
        group = m.VGroup(ax, ticks, labels)
        for s in d.get('series', []):
            pts = [ax.c2p(px, min(max(py, ya['min']), ya['max'])) for px, py in graph_points(d, s)]
            curve = m.VMobject(stroke_color=colour(s.get('colour')), stroke_width=5).set_points_as_corners(pts)
            self.parts[s['id']] = curve
            group.add(curve)
        for mk in d.get('marks', []):
            dot = m.Dot(ax.c2p(mk['x'], mk['y']), radius=.07, color=ACCENT)
            lab = text(mk.get('label', ''), 20).next_to(dot, m.UR, buff=.08)
            self.parts[mk['id']] = m.VGroup(dot, lab)
            group.add(self.parts[mk['id']])
        self.extra['axes'] = ax
        group.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])
        if group.width > (x1 - x0) or group.height > (y1 - y0):
            group.scale(min((x1 - x0) / group.width, (y1 - y0) / group.height) * .95)
        return group

    def build_number_line(self, d):
        x0, y0, x1, y1 = self.slot
        line = m.NumberLine(x_range=[d['min'], d['max'], d['step']], length=(x1 - x0) * .9, color=INK,
                            include_tip=False, stroke_width=3)
        values = list(np.arange(d['min'], d['max'] + 1e-9, d['step']))
        gap = line.length / max(1, len(values) - 1)
        every = max(1, math.ceil(.55 / gap))     # keep tick numbers at least ~0.55 units apart
        nums = m.VGroup(*[text(f'{v:g}', 24, MUTED).next_to(line.n2p(v), m.DOWN, buff=.2)
                          for i, v in enumerate(values) if i % every == 0 or v == 0])
        group = m.VGroup(line, nums)
        for mk in d.get('marks', []):
            dot = m.Dot(line.n2p(mk['value']), radius=.1, color=ACCENT)
            lab = text(mk.get('label', ''), 26, ACCENT, m.BOLD).next_to(dot, m.UP, buff=.35)
            self.parts[mk['id']] = m.VGroup(dot, lab)
            group.add(self.parts[mk['id']])
        self.extra['line'] = line
        group.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])
        return group

    def build_shape(self, d):
        if d['kind'] == 'circle':
            r = float(d['r'])
            circle = m.Circle(radius=1, color=INK, stroke_width=4)
            radius = m.Line(circle.get_center(), circle.point_at_angle(0), color=COLOURS['blue'], stroke_width=4)
            lab = text(d.get('label', f"r = {r:g}"), 26).next_to(radius, m.UP, buff=.1)
            group = m.VGroup(circle, radius, lab)
            self.parts['r'] = radius
            return fit(group, self.slot)
        pts = shape_points(d)
        span = max(max(p[0] for p in pts) - min(p[0] for p in pts), max(p[1] for p in pts) - min(p[1] for p in pts))
        x0, y0, x1, y1 = self.slot
        k = min(x1 - x0, y1 - y0) * .62 / span       # drawn at final size, so labels keep their real size
        poly = m.Polygon(*[[p[0] * k, p[1] * k, 0] for p in pts], color=INK, stroke_width=4,
                         fill_color=COLOURS['blue'], fill_opacity=.06)
        vertices = poly.get_vertices()
        centroid = np.mean(vertices, axis=0)
        group = m.VGroup(poly)
        names = d.get('vertices') or []
        for name, v in zip(names, vertices):
            out = (v - centroid) / (np.linalg.norm(v - centroid) or 1)
            lab = text(name, 30, INK, m.BOLD).move_to(v + out * .32)
            dot = m.Dot(v, radius=.04, color=INK)
            self.parts[name] = m.VGroup(dot, lab)
            group.add(self.parts[name])
        for (a, va), (b, vb) in zip(zip(names, vertices), list(zip(names, vertices))[1:] + list(zip(names, vertices))[:1]):
            side = m.Line(va, vb, color=INK, stroke_width=4)
            self.parts[a + b] = self.parts[b + a] = side
            group.add(side)
            label = (d.get('side_labels') or {}).get(a + b) or (d.get('side_labels') or {}).get(b + a)
            if label:
                mid = (va + vb) / 2
                out = (mid - centroid) / (np.linalg.norm(mid - centroid) or 1)
                lab = text(label, 26, COLOURS['blue'])
                group.add(lab.move_to(mid + out * (.25 + .5 * max(lab.width, lab.height))))
                self.extra.setdefault('side_labels', {})[a + b] = lab
                self.extra['side_labels'][b + a] = lab
        corner = d.get('right_angle_at')
        if corner in names:
            i = names.index(corner)
            v, p, n = vertices[i], vertices[i - 1], vertices[(i + 1) % len(vertices)]
            s = .22
            u1, u2 = (p - v) / np.linalg.norm(p - v), (n - v) / np.linalg.norm(n - v)
            group.add(m.VMobject(color=INK, stroke_width=3).set_points_as_corners(
                [v + u1 * s, v + u1 * s + u2 * s, v + u2 * s]))
        if d.get('_squares'):
            squares = m.VGroup()
            unit = ''
            for lab in (d.get('side_labels') or {}).values():
                found = __import__('re').match(r'\s*[0-9.]+\s*([A-Za-z]+)', str(lab))
                if found:
                    unit = found.group(1)
                    break
            palette = [COLOURS['blue'], COLOURS['orange'], COLOURS['green'], COLOURS['purple']]
            for i, ((a, va), (b, vb)) in enumerate(zip(zip(names, vertices), list(zip(names, vertices))[1:] + list(zip(names, vertices))[:1])):
                if d['_squares'] != 'all' and a + b not in d['_squares'] and b + a not in d['_squares']:
                    continue
                side = vb - va
                normal = np.array([-side[1], side[0], 0.0])
                normal /= np.linalg.norm(normal) or 1
                if np.dot(normal, ((va + vb) / 2) - centroid) < 0:
                    normal = -normal
                length = np.linalg.norm(side)
                corners = [va, vb, vb + normal * length, va + normal * length]
                sq = m.Polygon(*corners, color=palette[i % 4], stroke_width=3, fill_color=palette[i % 4], fill_opacity=.18)
                true_len = math.dist(pts[names.index(a)], pts[names.index(b)])
                grid = m.VGroup()
                if abs(true_len - round(true_len)) < 1e-6 and 2 <= round(true_len) <= 8:
                    n = int(round(true_len))
                    for j in range(1, n):
                        f = j / n
                        grid.add(m.Line(va + side * f, va + side * f + normal * length, stroke_width=1.2, color=palette[i % 4]))
                        grid.add(m.Line(va + normal * length * f, vb + normal * length * f, stroke_width=1.2, color=palette[i % 4]))
                area = true_len ** 2
                label = text(f"{area:g} {unit}²".strip() if unit else f"{area:g}", 26, palette[i % 4], m.BOLD)
                label.move_to(sum(corners) / 4)
                piece = m.VGroup(sq, grid, label)
                piece.side = a + b
                self.parts['sq_' + a + b] = self.parts['sq_' + b + a] = piece
                squares.add(piece)
            whole = m.VGroup(group, squares)
            fit(whole, self.slot, max_scale=1.0)
            self.extra['squares'] = squares
            return group
        return fit(group, self.slot, max_scale=1.0)

    def build_path_motion(self, d):
        x0, y0, x1, y1 = self.slot
        size = min(x1 - x0, y1 - y0) * .78
        if d['shape'] == 'circle':
            route = m.Circle(radius=size / 2, color=INK, stroke_width=6)
            start = route.point_at_angle(-math.pi / 2)
            route = route.copy().rotate(0)
            info = text(f"r = {d['size']:g} {d.get('unit', '')}".strip(), 24, MUTED).next_to(route, m.RIGHT, buff=.2)
            centre = m.Dot(route.get_center(), radius=.04, color=MUTED)
            radius_line = m.DashedLine(route.get_center(), route.point_at_angle(0), color=MUTED)
            extras = m.VGroup(info, centre, radius_line)

            def at(u):
                return route.point_at_angle(-math.pi / 2 + 2 * math.pi * u)
        elif d['shape'] == 'semicircle':
            route = m.Arc(radius=size / 2, start_angle=math.pi, angle=-math.pi, color=INK, stroke_width=6)
            start = route.get_start()
            extras = m.VGroup(text(f"r = {d['size']:g} {d.get('unit', '')}".strip(), 24, MUTED).next_to(route, m.DOWN))

            def at(u):
                return route.point_from_proportion(min(1.0, u))
        else:
            route = m.Line([-size * .8, 0, 0], [size * .8, 0, 0], color=INK, stroke_width=6)
            start = route.get_start()
            extras = m.VGroup(text(f"{d['size']:g} {d.get('unit', '')}".strip(), 24, MUTED).next_to(route, m.DOWN))

            def at(u):
                return route.point_from_proportion(min(1.0, u))
        flag = m.VGroup(m.Dot(start, radius=.08, color=COLOURS['green']),
                        text(d.get('start_label', 'Start'), 22, COLOURS['green']).next_to(start, m.DOWN, buff=.15))
        mover = m.VGroup(m.Dot(radius=.13, color=ACCENT), text(d.get('mover', ''), 20, ACCENT, m.BOLD))
        mover[1].next_to(mover[0], m.UP, buff=.08)
        group = m.VGroup(route, extras, flag)
        group.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])
        offset = group.get_center() - m.VGroup(route, extras, flag).get_center()
        self.extra.update(route=route, at=at, start=flag[0].get_center(), mover=mover,
                          closed=d['shape'] == 'circle')
        mover.move_to(self.extra['start'] + (mover.get_center() - mover[0].get_center()))
        group.add(mover)
        return group

    def build_counter(self, d):
        label = text(d.get('label', ''), 26, MUTED)
        self.extra['value_text'] = None
        group = m.VGroup(label)
        fit(group, (self.slot[0], self.slot[1] + (self.slot[3] - self.slot[1]) * .55, self.slot[2], self.slot[3]),
            max_scale=1)
        self.extra['value_pos'] = [(self.slot[0] + self.slot[2]) / 2, self.slot[1] + (self.slot[3] - self.slot[1]) * .32, 0]
        return group

    def build_table(self, d):
        table = m.Table([[str(c) for c in r] for r in d['rows']],
                        col_labels=[text(c, 24, INK, m.BOLD) for c in d['columns']],
                        element_to_mobject=lambda s: text(s, 24), include_outer_lines=True,
                        line_config={'color': MUTED, 'stroke_width': 1.5})
        fit(table, self.slot, max_scale=1.1)
        rows = table.get_rows()
        for i in range(len(d['rows'])):
            self.parts[f'row{i + 1}'] = rows[i + 1]
        return table

    def build_bars(self, d):
        bars = d['bars']
        top = max(float(b['value']) for b in bars) or 1
        group = m.VGroup()
        for i, b in enumerate(bars):
            h = 2.6 * float(b['value']) / top
            rect = m.Rectangle(width=.9, height=max(h, .02), fill_color=list(COLOURS.values())[i % 5], fill_opacity=.85,
                               stroke_width=0).move_to([i * 1.5, h / 2, 0])
            value = text(f"{float(b['value']):g} {d.get('unit', '')}".strip(), 22).next_to(rect, m.UP, buff=.1)
            label = text(b.get('label', ''), 20, MUTED).next_to([i * 1.5, 0, 0], m.DOWN, buff=.2)
            self.parts[b['id']] = m.VGroup(rect, value, label)
            group.add(self.parts[b['id']])
        group.add(m.Line([-.7, 0, 0], [(len(bars) - 1) * 1.5 + .7, 0, 0], color=INK, stroke_width=2))
        return fit(group, self.slot, max_scale=1.4)

    def build_cards(self, d):
        cards = m.VGroup()
        for item in d['items']:
            title = text(item.get('title', ''), 26, MUTED)
            value = text(item.get('value', ''), 40, INK, m.BOLD)
            inner = m.VGroup(title, value).arrange(m.DOWN, buff=.25)
            box = m.RoundedRectangle(width=max(2.6, inner.width + .6), height=inner.height + .7, corner_radius=.15,
                                     stroke_color=COLOURS['blue'], stroke_width=2.5, fill_color='#FFFFFF', fill_opacity=1)
            card = m.VGroup(box, inner.move_to(box))
            self.parts[item['id']] = card
            cards.add(card)
        x0, y0, x1, y1 = self.slot
        cards.arrange(m.RIGHT, buff=.4)
        if len(cards) > 2 and (x1 - x0) * .92 / cards.width < .8:
            cards.arrange_in_grid(cols=2, buff=.3)     # wrap rather than shrink below a readable size
        return fit(cards, self.slot, max_scale=1.2)

    def build_note(self, d):
        x0, y0, x1, y1 = self.slot
        words = str(d['text']).split()
        best = None
        for width in (40, 32, 26, 20, 16):          # pick the line length that keeps the text largest
            lines, line = [], ''
            for w in words:
                if line and len(line) + len(w) + 1 > width:
                    lines.append(line)
                    line = ''
                line = (line + ' ' + w).strip()
            lines.append(line)
            body = text('\n'.join(lines), 30, INK)
            scale = min((x1 - x0) * .92 / (body.width + .7), (y1 - y0) * .9 / (body.height + .5), 1.1)
            if best is None or scale > best[0]:
                best = (scale, body)
        body = best[1]
        box = m.RoundedRectangle(width=body.width + .7, height=body.height + .5, corner_radius=.15,
                                 stroke_color=ACCENT, stroke_width=3, fill_color='#FFF7E8', fill_opacity=1)
        return fit(m.VGroup(box, body.move_to(box)), self.slot, max_scale=1.1)


# ---------------------------------------------------------------- the scene
DISCRETE = {'show', 'hide', 'next_step', 'mark', 'jump', 'highlight', 'squares', 'transform', 'focus'}
RUN = {'enter': 1.3, 'show': 1.0, 'hide': .6, 'next_step': 1.1, 'mark': .7, 'jump': 1.0, 'highlight': 1.1,
       'squares': 2.2, 'transform': 1.3, 'focus': .9, 'unfocus': .9}


def draw_in(mob):
    """Manim-style entrance: strokes are drawn, text is written (groups are entered child by child)."""
    if isinstance(mob, (m.Text, m.MathTex, m.Tex)):
        return m.Write(mob)
    if isinstance(mob, m.Dot):
        return m.GrowFromCenter(mob)
    children = list(mob.submobjects) if isinstance(mob, (m.VGroup, m.Group)) and type(mob) in (m.VGroup, m.Group) else []
    if not children:
        return m.Create(mob) if len(mob.points) else m.FadeIn(mob)
    if len(children) == 1:
        return draw_in(children[0])
    return m.LaggedStart(*[draw_in(c) for c in children], lag_ratio=.25)


class DiagramScene(m.MovingCameraScene):
    def construct(self):
        data = DATA
        spec, cues, duration = data['spec'], sorted(data['cues'], key=lambda c: c['start']), data['duration']
        self.camera.background_color = BG
        frame = self.camera.frame
        full_width = frame.width
        # Squares need room in the layout: tell the shape builder before it fits itself.
        for c in cues:
            if c['verb'] == 'squares':
                e = next((x for x in spec['elements'] if x['id'] == c['target'].partition('.')[0]), None)
                if e is not None:
                    e['_squares'] = c.get('sides') or 'all'
        layout = slots(spec)
        el = {e['id']: Element(e, layout[e['id']]) for e in spec['elements']}
        # A time-based updater keeps every frame live: without one, Manim renders waits as frozen frames and
        # movers, counters and plots would stop between cue words.
        ticker = m.ValueTracker(0)
        ticker.add_updater(lambda mob, dt: mob.increment_value(dt))
        self.add(ticker)
        heading = text(data.get('title', ''), 34, INK, m.BOLD).to_corner(m.UL, buff=.35)
        self.play(m.Write(heading), run_time=.6)
        visible = set()

        def part_of(target):
            eid, _, pid = target.partition('.')
            return el[eid], (el[eid].parts.get(pid) if pid else None)

        # ---- continuous processes on the scene clock
        for c in [c for c in cues if c['verb'] == 'count']:
            e = el[c['target']]
            d = e.data
            cache = {}

            def readout(c=c, e=e, d=d, cache=cache):
                if c['target'] not in visible:
                    return m.VGroup()
                u = min(1.0, max(0.0, (self.time - c['start']) / max(.3, c['end'] - c['start'])))
                v = float(d['from']) + (float(d['to']) - float(d['from'])) * u
                s = f"{v:.{int(d.get('decimals', 0))}f} {d.get('unit', '')}".strip()
                if s not in cache:
                    cache[s] = text(s, 56, COLOURS['blue'], m.BOLD).move_to(e.extra['value_pos'])
                return cache[s].copy()
            self.add(m.always_redraw(readout))
        for e in [x for x in el.values() if x.data['type'] == 'counter']:
            if not any(c['verb'] == 'count' and c['target'] == e.data['id'] for c in cues):
                start = text(f"{float(e.data['from']):g} {e.data.get('unit', '')}".strip(), 56, COLOURS['blue'], m.BOLD)
                e.group.add(start.move_to(e.extra['value_pos']))
        moves = {}
        for c in [c for c in cues if c['verb'] == 'move']:
            moves.setdefault(c['target'], []).append(c)
        for e in [x for x in el.values() if x.data['type'] == 'path_motion']:
            eid = e.data['id']
            mv = moves.get(eid, [])
            rel = next((c for c in cues if c['verb'] == 'release' and c['target'] == eid), None)

            def progress(t, mv=mv):
                u = 0.0
                for c in mv:
                    laps = float(c.get('laps', 1))
                    if t >= c['end']:
                        u += laps
                    elif t >= c['start']:
                        # steady speed while moving (uniform circular motion), easing only at the very ends
                        span = max(.3, c['end'] - c['start'])
                        k = (t - c['start']) / span
                        u += laps * (k if .08 < k < .92 else ease(k))
                return u

            def on_path(u, e=e):
                return e.extra['at'](u % 1.0 if e.extra['closed'] else min(u, 1.0))

            def tangent(t, e=e, progress=progress, on_path=on_path):
                u = progress(t)
                d = on_path(u + .002) - on_path(u - .002)
                n = np.linalg.norm(d)
                if n < 1e-9:   # not moving: use the direction it would move
                    d = on_path(.002 + (u % 1.0)) - on_path(u % 1.0)
                    n = np.linalg.norm(d) or 1
                return d / n

            def position(t, e=e, rel=rel, progress=progress, on_path=on_path, tangent=tangent):
                if rel is not None and t >= rel['start']:
                    speed = 2 * math.pi * (e.extra['route'].width / 2) / max(2.0, max((c['end'] - c['start']) / max(
                        float(c.get('laps', 1)), .1) for c in mv) if mv else 6.0)
                    return on_path(progress(rel['start'])) + tangent(rel['start']) * speed * (t - rel['start'])
                return on_path(progress(t))
            e.extra.update(position=position, tangent=tangent, release=rel)

            def follow(mob, position=position):
                pos = position(self.time)
                mob.shift(pos - mob[0].get_center())
            e.extra['mover'].add_updater(follow)
        for c in [c for c in cues if c['verb'] == 'plot']:
            e, curve = part_of(c['target'])
            full = curve.copy()
            e.group.remove(curve)

            def plotted(c=c, full=full):
                if self.time < c['start']:
                    return m.VGroup()
                u = ease((self.time - c['start']) / max(1.0, min(3.5, c['end'] - c['start'])))
                return full.copy().pointwise_become_partial(full, 0, max(.002, u))
            self.add(m.always_redraw(plotted))
        for c in [c for c in cues if c['verb'] == 'vectors']:
            e = el[c['target']]

            def vectors(c=c, e=e):
                t = self.time
                if t < c['start'] or c['target'] not in visible:
                    return m.VGroup()
                a = ease((t - c['start']) / .5)
                pos = e.extra['position'](t)
                released = e.extra['release'] is not None and t >= e.extra['release']['start']
                centre = e.extra['route'].get_center()
                g = m.VGroup()
                length = max(.7, e.extra['route'].width * .28)
                for kind in c.get('kinds', []):
                    if kind == 'velocity':
                        tip = pos + e.extra['tangent'](t if not released else e.extra['release']['start']) * length
                        g.add(m.Arrow(pos, tip, buff=0, color=COLOURS['green'], stroke_width=6, max_tip_length_to_length_ratio=.2),
                              m.MathTex('v', color=COLOURS['green'], font_size=34).next_to(tip, m.UR, buff=.05))
                    elif kind in ('centripetal_force', 'centripetal_acceleration') and not released and e.extra['closed']:
                        inward = (centre - pos) / (np.linalg.norm(centre - pos) or 1)
                        tip = pos + inward * length * .85
                        sym = 'F_c' if kind == 'centripetal_force' else 'a_c'
                        g.add(m.Arrow(pos, tip, buff=0, color=COLOURS['red'], stroke_width=6, max_tip_length_to_length_ratio=.2),
                              m.MathTex(sym, color=COLOURS['red'], font_size=34).next_to(tip, m.DL, buff=.05))
                    elif kind == 'string' and not released and e.extra['closed']:
                        g.add(m.Line(centre, pos, color=MUTED, stroke_width=3))
                return g.set_opacity(a)
            self.add(m.always_redraw(vectors))
        for c in [c for c in cues if c['verb'] == 'trace']:
            e = el[c['target']]

            def traced(c=c, e=e):
                if self.time < c['start']:
                    return m.VGroup()
                u = ease((self.time - c['start']) / max(1.0, min(3.0, c['end'] - c['start'])))
                route = e.extra['route']
                return route.copy().set_stroke(COLOURS['blue'], 10, .55).pointwise_become_partial(route, 0, max(.002, u))
            self.add(m.always_redraw(traced))
        for c in [c for c in cues if c['verb'] == 'connect']:
            e = el[c['target'].partition('.')[0]]

            def arrow(c=c, e=e):
                if self.time < c['start']:
                    return m.VGroup()
                if e.data['type'] == 'path_motion' and not c.get('to'):
                    a, b = e.extra['start'], e.extra['mover'][0].get_center()
                else:
                    a, b = part_of(c['target'])[1 if '.' in c['target'] else 0], part_of(c['to'])[1 if '.' in c['to'] else 0]
                    a, b = (a.group if isinstance(a, Element) else a).get_center(), (b.group if isinstance(b, Element) else b).get_center()
                g = m.VGroup()
                if np.linalg.norm(b - a) > .15:
                    g.add(m.Arrow(a, b, buff=0, color=COLOURS['red'], stroke_width=6, max_tip_length_to_length_ratio=.15))
                else:
                    g.add(m.Circle(radius=.18, color=COLOURS['red'], stroke_width=5).move_to(a))
                if c.get('text'):
                    g.add(text(c['text'], 24, COLOURS['red'], m.BOLD).next_to(g[0], m.RIGHT, buff=.15))
                return g
            self.add(m.always_redraw(arrow))
        # Parts revealed later start hidden: plotted series, marks and shown parts wait for their cue.
        later = {c['target'] for c in cues if c['verb'] in ('mark',) or (c['verb'] == 'show' and '.' in c['target'])}

        # ---- discrete moments, played on their words
        def entrance(eid):
            e = el[eid]
            d = e.data
            visible.add(eid)
            if d['type'] == 'equation_steps':
                stepped = any(c['verb'] == 'next_step' and c['target'] == eid for c in cues)
                e.extra['shown'] = 1 if stepped else len(e.extra['lines'])
                lines = e.extra['lines'][:e.extra['shown']]
                return m.LaggedStart(*[m.Write(x) for x in lines], lag_ratio=.4)
            if d['type'] == 'bars':
                anims = []
                for pid, piece in e.parts.items():
                    anims.append(m.AnimationGroup(m.GrowFromEdge(piece[0], m.DOWN), m.Write(piece[1]), m.Write(piece[2])))
                rest = [x for x in e.group.submobjects if x not in e.parts.values()]
                return m.LaggedStart(*[m.Create(x) for x in rest], *anims, lag_ratio=.3)
            if d['type'] in ('cards',):
                return m.LaggedStart(*[m.FadeIn(x, shift=m.UP * .3) for x in e.group], lag_ratio=.3)
            if d['type'] == 'table':
                return m.FadeIn(e.group, shift=m.UP * .2)
            waiting = {id(part) for pid, part in e.parts.items() if f'{eid}.{pid}' in later}
            if d['type'] == 'path_motion':
                # The mover enters as one group so its motion updater runs.
                mover = e.extra['mover']
                rest = [x for x in e.group.submobjects if x is not mover]
                return m.LaggedStart(draw_in(m.VGroup(*rest)), m.FadeIn(mover, scale=.5), lag_ratio=.6)
            return draw_in(m.VGroup(*[x for x in e.group.submobjects if id(x) not in waiting]))

        def moment(c):
            verb, target = c['verb'], c['target']
            eid = target.partition('.')[0]
            e, part = part_of(target)
            if verb == 'show':
                if '.' in target and part is not None:
                    return draw_in(part) if eid in visible else None
                return entrance(eid) if eid not in visible else None
            if eid not in visible and verb not in ('hide',):
                # Acting on something not on screen yet: bring it in first.
                return m.Succession(entrance(eid), moment(c) or m.Wait(.1))
            if verb == 'hide':
                visible.discard(eid)
                return m.FadeOut(part if part is not None else e.group)
            if verb == 'next_step':
                n = e.extra.get('shown', 1)
                if n >= len(e.extra['lines']):
                    return None
                e.extra['shown'] = n + 1
                return m.TransformMatchingTex(e.extra['lines'][n - 1].copy(), e.extra['lines'][n])
            if verb == 'mark':
                return draw_in(part)
            if verb == 'jump':
                a_pt = part[0].get_center()
                b_pt = e.parts[str(c['to']).partition('.')[2]][0].get_center()
                hop = m.CurvedArrow(a_pt + m.UP * .15, b_pt + m.UP * .15, color=COLOURS['blue'],
                                    angle=-math.pi / 2 if b_pt[0] > a_pt[0] else math.pi / 2)
                anims = [m.Create(hop)]
                if c.get('text'):
                    anims.append(m.Write(text(c['text'], 26, COLOURS['blue'], m.BOLD).next_to(hop, m.UP, buff=.08)))
                return m.LaggedStart(*anims, lag_ratio=.5)
            if verb == 'highlight':
                mob = part if part is not None else e.group
                if isinstance(mob, m.Line):
                    glow = mob.copy().set_stroke(HIGHLIGHT, 14)
                    return m.Succession(m.ShowPassingFlash(glow, time_width=1.0), m.Indicate(mob, color=HIGHLIGHT, scale_factor=1.04))
                if part is not None and isinstance(mob, (m.Text, m.MathTex, m.Dot)):
                    return m.Indicate(mob, color=HIGHLIGHT)
                # Cards, bars, rows, whole elements: an outline sweeps round (recolouring would fill their boxes).
                return m.Circumscribe(mob, color=HIGHLIGHT, time_width=.5, buff=.1)
            if verb == 'squares':
                pieces = e.extra.get('squares', m.VGroup())
                labels = e.extra.get('side_labels', {})
                # The side's length label makes way: the square's area label carries the number now.
                return m.LaggedStart(*[m.Succession(
                    m.AnimationGroup(m.DrawBorderThenFill(p[0]),
                                     *([m.FadeOut(labels[p.side])] if p.side in labels else [])),
                    m.AnimationGroup(m.Create(p[1]), m.Write(p[2]))) for p in pieces], lag_ratio=.6)
            if verb == 'transform':
                dst_e, dst_part = part_of(str(c['to']))
                if dst_part is None and dst_e.data['type'] == 'equation_steps':
                    # Land on the line currently showing, never on lines still waiting for their cue.
                    if dst_e.data['id'] not in visible:
                        entrance(dst_e.data['id'])
                    dst_part = dst_e.extra['lines'][max(0, dst_e.extra.get('shown', 1) - 1)]
                    return m.TransformFromCopy(part if part is not None else e.group, dst_part.copy(),
                                               remover=True)
                if dst_e.data['id'] not in visible:
                    return m.Succession(entrance(dst_e.data['id']),
                                        m.TransformFromCopy(part if part is not None else e.group,
                                                            dst_part if dst_part is not None else dst_e.group))
                return m.TransformFromCopy(part if part is not None else e.group, dst_part if dst_part is not None else dst_e.group)
            if verb == 'focus':
                mob = part if part is not None else e.group
                return frame.animate.set(width=max(mob.width * 1.9, mob.height * 1.9 * 16 / 9, full_width * .5)).move_to(mob)
            if verb == 'unfocus':
                return frame.animate.set(width=full_width).move_to(m.ORIGIN)
            return None

        events = []
        for i, eid in enumerate(el):
            explicit = any(c['verb'] == 'show' and c['target'] == eid for c in cues)
            if not explicit:
                events.append((.7 + .45 * i, {'verb': 'enter', 'target': eid}))
        for c in cues:
            if c['verb'] in DISCRETE:
                events.append((c['start'], c))
            if c['verb'] == 'focus':
                events.append((c['end'], {'verb': 'unfocus', 'target': c['target']}))
        events.sort(key=lambda x: x[0])
        i = 0
        while i < len(events):
            t0 = events[i][0]
            batch = [ev for ev in events[i:] if ev[0] - t0 <= .25]
            i += len(batch)
            nxt = events[i][0] if i < len(events) else duration
            if t0 > self.time:
                self.wait(t0 - self.time)
            # Entrances first; anything acting on an element entering at this same moment plays right after it,
            # never in the same step (two animations on one mobject at once leave it in a broken state).
            first, after = [], []
            entering = {c['target'] for _, c in batch if c['verb'] in ('enter', 'show') and '.' not in c['target']
                        and c['target'] not in visible}
            for _, c in batch:
                if c['verb'] in ('enter', 'show') and c['target'] in entering:
                    anim = entrance(c['target']) if c['target'] not in visible else None
                    (first.append(anim) if anim is not None else None)
                elif c['verb'] == 'enter':
                    continue
                elif c['target'].partition('.')[0] in entering:
                    after.append(c)
                else:
                    anim = moment(c)
                    (first.append(anim) if anim is not None else None)
            for group in (first, [a for a in (moment(c) for c in after) if a is not None]):
                if not group:
                    continue
                want = max(RUN.get(c['verb'], 1.0) for _, c in batch)
                room = max(.4, min(duration - self.time - .1, nxt - self.time - .05))
                self.play(*group, run_time=max(.35, min(want, room) / (2 if after else 1)))
        if duration > self.time:
            self.wait(duration - self.time)


if __name__ == '__main__':
    DATA = json.loads(Path(sys.argv[1]).read_text())
    h, w, fps = DATA['resolution']
    with m.tempconfig({'pixel_height': h, 'pixel_width': w, 'frame_rate': fps, 'media_dir': 'media',
                       'output_file': 'chapter', 'disable_caching': True, 'verbosity': 'WARNING',
                       'progress_bar': 'none', 'background_color': BG}):
        scene = DiagramScene()
        scene.render()
        Path('result.json').write_text(json.dumps({'output': str(scene.renderer.file_writer.movie_file_path),
                                                   'duration': float(scene.time)}))
