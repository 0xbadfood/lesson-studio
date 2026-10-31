"""Question figures: a model names parts and how they connect, code places and draws them as a JEE line drawing.

A figure is {"width", "height", "parts": [...]} in units with y up. A place is [x, y] or "id.anchor", so a string really
ends on its block and a block really sits on its incline. A part the kit lacks is an error naming the kit, so a question
that needs one reports the gap instead of improvising (the list of gaps says what to add next, as missing verbs do).
"""
from __future__ import annotations

import math

SCALE = 8.0     # px per unit
FONT = 3.0      # label size, units

KIT = """Parts (every part has "type"; give "id" to any part others refer to). A place is [x, y] or "id.anchor". y is up.
- surface {from, to, hatch: "below"|"above"|"left"|"right"}: fixed floor, wall or ceiling, hatched on that side. Anchors: from, to, mid, at:0.3 (fraction along).
- incline {at: foot [x, y], angle: degrees, length, flip?: true (rises to the left), fixed?: true}: a wedge. Anchors: foot, top, corner, at:0.3 (along the slope). Its base is hatched when fixed.
- block {w, h, label?, at?: centre place, on?: "surface or incline id", s?: fraction along it (default 0.5)}: on places it resting on the top side and turned with the slope. Anchors: center, left, right, top, bottom.
- ball {r, label?, filled?: true, at?, on?, s?}: particle or sphere. disc {r, label?, at?, on?, s?}: disc or cylinder seen end on, with a centre dot. ring {r, label?, at?, on?, s?}: thin ring. Anchors: center, top, bottom, left, right, rim:30 (degrees from +x).
- pulley {r, at, label?}: a small wheel on a fixed centre. Anchors as disc.
- string {from, to, over?: [pulley ids in order], side?: ["top"|"bottom"|"left"|"right" per pulley]}: straight runs, tangent to each pulley.
- spring {from, to, coils?}: a zigzag. rod {from, to, label?}: a thin rigid bar. Anchors: from, to, mid, at:0.3.
- pivot {at, label?}: a fixed hinge.
- arc {center, r, start, end, hatch?: "out"}: a curved track or bowl, angles in degrees from +x, counter-clockwise from start to end. Anchors: from, to, center, at:45 (degrees).
- cut_block {at: lower-left place, w, h, r, label?}: a block with a quarter-circle cut from its upper-left corner, radius r. Anchors: center, cut_top, cut_bottom, cut_center, left, right, top, bottom.
- axes {origin, x_len, y_len, x_label?, y_label?}: dashed-free coordinate axes. Anchors: origin, x, y.
- line {from, to, dashed?: true, label?}: a plain or dashed line. arrow {from, to, label?}: a velocity or force arrow. dim {from, to, text, offset?}: a dimension line with end bars, set off by offset units.
- angle {vertex, from, to, text, r?}: an arc from one ray to the other with its text. point {at, label?}: a dot. label {at, text}: words."""

ANCHORED = {'surface', 'incline', 'block', 'ball', 'disc', 'ring', 'pulley', 'rod', 'arc', 'cut_block', 'axes', 'pivot', 'point'}
TYPES = ANCHORED | {'string', 'spring', 'line', 'arrow', 'dim', 'angle', 'label'}


class FigureError(ValueError):
    pass


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k)


def _unit(a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def _on_track(sup, s):
    """A surface's point at fraction s, and the outward direction a thing rests along."""
    if sup['type'] == 'incline':
        a, b = sup['_foot'], sup['_top']
        u = _unit(a, b)
        n = (-u[1], u[0]) if not sup.get('flip') else (u[1], -u[0])
        return _add(a, u, s * math.dist(a, b)), u, n
    if sup['type'] == 'surface':
        a, b = sup['_a'], sup['_b']
        u = _unit(a, b)
        away = {'below': (0, 1), 'above': (0, -1), 'left': (1, 0), 'right': (-1, 0)}[sup.get('hatch', 'below')]
        return _add(a, u, s * math.dist(a, b)), u, away
    raise FigureError(f"on: {sup.get('id')} is a {sup['type']}; things rest on a surface or an incline")


class Figure:
    def __init__(self, spec):
        self.W, self.H = float(spec.get('width', 100)), float(spec.get('height', 60))
        self.parts = spec.get('parts') or []
        self.by = {}
        self.out, self.labels, self.errors, self.extent = [], [], [], []
        for i, p in enumerate(self.parts):
            if not isinstance(p, dict) or p.get('type') not in TYPES:
                self.errors.append(f"part {i}: no part called {p.get('type') if isinstance(p, dict) else p!r}; the kit has {', '.join(sorted(TYPES))}. "
                                   'If none can draw it, report it in missing_parts')
            elif p.get('id'):
                self.by[p['id']] = p

    # places
    def place(self, v):
        if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(q, (int, float)) for q in v):
            return (float(v[0]), float(v[1]))
        if isinstance(v, str) and '.' in v:
            pid, name = v.split('.', 1)
            part = self.by.get(pid)
            if part is None:
                raise FigureError(f'{v}: no part with id {pid}')
            if '_at' not in part:
                self.resolve(part)
            return self.anchor(part, name, v)
        raise FigureError(f'{v!r}: a place is [x, y] or "id.anchor"')

    def anchor(self, p, name, whole):
        t = p['type']
        param = None
        if ':' in name:
            name, param = name.split(':', 1)
            param = float(param)
        if t in ('block', 'cut_block'):
            c, u, n, w, h = p['_at'], p['_u'], p['_n'], p['w'], p['h']
            table = {'center': c, 'left': _add(c, u, -w / 2), 'right': _add(c, u, w / 2), 'top': _add(c, n, h / 2), 'bottom': _add(c, n, -h / 2)}
            if t == 'cut_block':
                x, y, r = p['_ll'][0], p['_ll'][1], p['r']
                table.update(cut_center=(x, y + h), cut_top=(x + r, y + h), cut_bottom=(x, y + h - r))
        elif t in ('ball', 'disc', 'ring', 'pulley'):
            c, r = p['_at'], p['r']
            if name == 'rim' and param is not None:
                return (c[0] + r * math.cos(math.radians(param)), c[1] + r * math.sin(math.radians(param)))
            table = {'center': c, 'top': (c[0], c[1] + r), 'bottom': (c[0], c[1] - r), 'left': (c[0] - r, c[1]), 'right': (c[0] + r, c[1])}
        elif t in ('surface', 'rod'):
            a, b = p['_a'], p['_b']
            if name == 'at' and param is not None:
                return _add(a, _unit(a, b), param * math.dist(a, b))
            table = {'from': a, 'to': b, 'mid': ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)}
        elif t == 'incline':
            if name == 'at' and param is not None:
                return _add(p['_foot'], _unit(p['_foot'], p['_top']), param * math.dist(p['_foot'], p['_top']))
            table = {'foot': p['_foot'], 'top': p['_top'], 'corner': p['_corner']}
        elif t == 'arc':
            c, r = p['_at'], p['r']
            pt = lambda d: (c[0] + r * math.cos(math.radians(d)), c[1] + r * math.sin(math.radians(d)))
            if name == 'at' and param is not None:
                return pt(param)
            table = {'center': c, 'from': pt(p['start']), 'to': pt(p['end'])}
        elif t == 'axes':
            o = p['_at']
            table = {'origin': o, 'x': (o[0] + p.get('x_len', 20), o[1]), 'y': (o[0], o[1] + p.get('y_len', 20))}
        else:
            table = {'center': p['_at'], 'at': p['_at']}
        if name not in table:
            raise FigureError(f'{whole}: a {t} has anchors {", ".join(table)}')
        return table[name]

    def resolve(self, p):
        """Where a part stands, working from what it rests on."""
        t = p['type']
        if '_at' in p:
            return
        p['_at'] = None     # a loop of references ends here rather than recursing
        if t == 'surface' or t == 'rod':
            p['_a'], p['_b'] = self.place(p['from']), self.place(p['to'])
            p['_at'] = p['_a']
        elif t == 'incline':
            foot, L, A = self.place(p['at']), float(p['length']), math.radians(float(p['angle']))
            sign = -1 if p.get('flip') else 1
            p['_foot'], p['_corner'], p['_top'] = foot, (foot[0] + sign * L * math.cos(A), foot[1]), (foot[0] + sign * L * math.cos(A), foot[1] + L * math.sin(A))
            p['_at'] = foot
        elif t in ('block', 'ball', 'disc', 'ring'):
            half = float(p['h']) / 2 if t == 'block' else float(p['r'])
            if p.get('on'):
                sup = self.by.get(p['on'])
                if sup is None:
                    raise FigureError(f"on: no part with id {p['on']}")
                self.resolve(sup)
                q, u, n = _on_track(sup, float(p.get('s', 0.5)))
                p['_at'], p['_u'], p['_n'] = _add(q, n, half), u, n
            else:
                p['_at'], p['_u'], p['_n'] = self.place(p['at']), (1, 0), (0, 1)
        elif t == 'cut_block':
            ll = self.place(p['at'])
            p['_ll'], p['_u'], p['_n'] = ll, (1, 0), (0, 1)
            p['_at'] = (ll[0] + p['w'] / 2, ll[1] + p['h'] / 2)
            if p['r'] > min(p['w'], p['h']):
                raise FigureError('cut_block: r is at most the smaller of w and h')
        elif t == 'arc':
            p['_at'] = self.place(p['center'])
        elif t == 'axes':
            p['_at'] = self.place(p['origin'])
        else:
            p['_at'] = self.place(p['at'])

    # drawing
    def x(self, q):
        return q[0] * SCALE

    def y(self, q):
        return (self.H - q[1]) * SCALE

    def seen(self, *pts):
        self.extent.extend(pts)

    def seg(self, a, b, width=1.6, dash=False):
        self.seen(a, b)
        d = ' stroke-dasharray="7 5"' if dash else ''
        self.out.append(f'<line x1="{self.x(a):.1f}" y1="{self.y(a):.1f}" x2="{self.x(b):.1f}" y2="{self.y(b):.1f}" stroke="#000" stroke-width="{width}"{d}/>')

    def poly(self, pts, fill='#fff', closed=True, width=1.6):
        self.seen(*pts)
        s = ' '.join(f'{self.x(q):.1f},{self.y(q):.1f}' for q in pts)
        tag = 'polygon' if closed else 'polyline'
        self.out.append(f'<{tag} points="{s}" fill="{fill}" stroke="#000" stroke-width="{width}"/>')

    def circle(self, c, r, fill='#fff', width=1.6):
        self.seen((c[0] - r, c[1] - r), (c[0] + r, c[1] + r))
        self.out.append(f'<circle cx="{self.x(c):.1f}" cy="{self.y(c):.1f}" r="{r * SCALE:.1f}" fill="{fill}" stroke="#000" stroke-width="{width}"/>')

    def text(self, at, s, anchor='middle'):
        s = str(s)
        w = len(s) * FONT * 0.55
        x0 = at[0] - w / 2 if anchor == 'middle' else at[0] if anchor == 'start' else at[0] - w
        box = (x0, at[1] - FONT * 0.35, x0 + w, at[1] + FONT * 0.65)
        for other, name in self.labels:
            if box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3]:
                self.errors.append(f'labels overlap: {s!r} and {name!r}: move one')
        self.labels.append((box, s))
        self.seen((box[0], box[1]), (box[2], box[3]))
        safe = s.replace('&', '&amp;').replace('<', '&lt;')
        self.out.append(f'<text x="{self.x(at):.1f}" y="{self.y(at):.1f}" font-family="DejaVu Serif" font-style="italic" font-size="{FONT * SCALE:.1f}" text-anchor="{anchor}" fill="#000">{safe}</text>')

    def hatch(self, a, b, side):
        u = _unit(a, b)
        L = math.dist(a, b)
        d = {'below': (-0.7, -1), 'above': (-0.7, 1), 'left': (-1, -0.7), 'right': (1, -0.7)}[side]
        for i in range(int(L / 2.5) + 1):
            q = _add(a, u, i * 2.5)
            self.seg(q, _add(q, d, 1.8), width=1)

    def arrowhead(self, tip, u, size=1.8):
        n = (-u[1], u[0])
        back = _add(tip, u, -size)
        self.poly([tip, _add(back, n, size * 0.4), _add(back, n, -size * 0.4)], fill='#000', width=0.5)

    def tangent(self, p, side, other):
        """The point a straight run from `other` leaves a pulley on `side`."""
        c, r = p['_at'], p['r']
        d = math.dist(c, other)
        if d <= r:
            raise FigureError(f"string: a run starts inside pulley {p.get('id')}")
        base = math.atan2(other[1] - c[1], other[0] - c[0])
        off = math.acos(r / d)
        cand = [(c[0] + r * math.cos(base + s * off), c[1] + r * math.sin(base + s * off)) for s in (1, -1)]
        want = {'top': (0, 1), 'bottom': (0, -1), 'left': (-1, 0), 'right': (1, 0)}[side]
        return max(cand, key=lambda q: (q[0] - c[0]) * want[0] + (q[1] - c[1]) * want[1])

    def draw(self, p):
        t = p['type']
        if t in ANCHORED:
            self.resolve(p)
        if t == 'surface':
            self.seg(p['_a'], p['_b'], 2)
            self.hatch(p['_a'], p['_b'], p.get('hatch', 'below'))
        elif t == 'incline':
            self.poly([p['_foot'], p['_corner'], p['_top']])
            if p.get('fixed'):
                a, b = sorted([p['_foot'], p['_corner']])
                self.hatch(a, b, 'below')
        elif t == 'block':
            c, u, n, w, h = p['_at'], p['_u'], p['_n'], float(p['w']) / 2, float(p['h']) / 2
            self.poly([_add(_add(c, u, sx * w), n, sy * h) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            if p.get('label'):
                self.text((c[0], c[1] - FONT * 0.3), p['label'])
        elif t in ('ball', 'disc', 'ring', 'pulley'):
            c, r = p['_at'], float(p['r'])
            self.circle(c, r, fill='#000' if p.get('filled') else '#fff', width=2.4 if t == 'ring' else 1.6)
            if t in ('disc', 'pulley'):
                self.circle(c, 0.35, fill='#000', width=0.5)
            if p.get('label'):
                self.text((c[0] + r + 1, c[1] + r * 0.6), p['label'], 'start')
        elif t == 'rod':
            self.seg(p['_a'], p['_b'], 3.2)
            if p.get('label'):
                m = ((p['_a'][0] + p['_b'][0]) / 2, (p['_a'][1] + p['_b'][1]) / 2)
                self.text((m[0] + 1.5, m[1] + 1.5), p['label'], 'start')
        elif t == 'pivot':
            c = p['_at']
            self.poly([c, (c[0] - 1.6, c[1] - 2.4), (c[0] + 1.6, c[1] - 2.4)])
            self.hatch((c[0] - 2, c[1] - 2.4), (c[0] + 2, c[1] - 2.4), 'below')
            self.circle(c, 0.45, width=1.2)
            if p.get('label'):
                self.text((c[0] - 2.4, c[1]), p['label'], 'end')
        elif t == 'arc':
            c, r, a0, a1 = p['_at'], float(p['r']), float(p['start']), float(p['end'])
            if a1 <= a0:
                a1 += 360
            pts = [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / 60)), c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / 60))) for i in range(61)]
            self.poly(pts, fill='none', closed=False, width=2)
            if p.get('hatch'):
                for q in pts[::4]:
                    self.seg(q, _add(q, _unit(c, q), 1.6), width=1)
        elif t == 'cut_block':
            x, y, w, h, r = *p['_ll'], float(p['w']), float(p['h']), float(p['r'])
            arc = [(x + r * math.sin(math.radians(90 * i / 24)), y + h - r * math.cos(math.radians(90 * i / 24))) for i in range(25)]
            self.poly([(x, y), (x + w, y), (x + w, y + h)] + list(reversed(arc)))
            if p.get('label'):
                self.text((x + w * 0.68, y + h * 0.3), p['label'])
        elif t == 'axes':
            o = p['_at']
            for key, u, name, off in (('x_len', (1, 0), p.get('x_label', 'x'), (1.2, -0.8)), ('y_len', (0, 1), p.get('y_label', 'y'), (0.8, 1.0))):
                tip = _add(o, u, float(p.get(key, 20)))
                self.seg(o, tip)
                self.arrowhead(tip, u)
                self.text(_add(tip, off), name, 'start')
        elif t == 'point':
            self.circle(p['_at'], 0.5, fill='#000', width=0.5)
            if p.get('label'):
                self.text((p['_at'][0] + 1, p['_at'][1] + 1), p['label'], 'start')
        elif t == 'label':
            self.text(self.place(p['at']), p['text'], p.get('anchor', 'middle'))
        elif t == 'string':
            self.string(p)
        elif t == 'spring':
            a, b = self.place(p['from']), self.place(p['to'])
            u, n, L, c = _unit(a, b), (-_unit(a, b)[1], _unit(a, b)[0]), math.dist(a, b), int(p.get('coils', 8))
            pts = [a, _add(a, u, L * 0.1)]
            for i in range(c * 2):
                pts.append(_add(_add(a, u, L * (0.1 + 0.8 * (i + 0.5) / (c * 2))), n, 1.1 if i % 2 == 0 else -1.1))
            pts += [_add(a, u, L * 0.9), b]
            self.poly(pts, fill='none', closed=False)
        elif t == 'line':
            a, b = self.place(p['from']), self.place(p['to'])
            self.seg(a, b, 1.2, dash=bool(p.get('dashed')))
            if p.get('label'):
                self.text(((a[0] + b[0]) / 2 + 1, (a[1] + b[1]) / 2 + 1), p['label'], 'start')
        elif t == 'arrow':
            a, b = self.place(p['from']), self.place(p['to'])
            self.seg(a, b)
            self.arrowhead(b, _unit(a, b))
            if p.get('label'):
                self.text((b[0] + 1, b[1] + 1), p['label'], 'start')
        elif t == 'dim':
            a, b = self.place(p['from']), self.place(p['to'])
            u = _unit(a, b)
            n = (-u[1], u[0])
            off = float(p.get('offset', -4))
            a2, b2 = _add(a, n, off), _add(b, n, off)
            self.seg(a2, b2, 1)
            self.arrowhead(a2, (-u[0], -u[1]), 1.4)
            self.arrowhead(b2, u, 1.4)
            self.seg(a, _add(a2, n, 0.6 if off > 0 else -0.6), 0.7)
            self.seg(b, _add(b2, n, 0.6 if off > 0 else -0.6), 0.7)
            m = ((a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2)
            side = 1 if off > 0 else -1
            self.text(_add(_add(m, n, side * 1.6), (0, -FONT * 0.3)), p['text'])
        elif t == 'angle':
            v, a, b = self.place(p['vertex']), self.place(p['from']), self.place(p['to'])
            r = float(p.get('r', 5))
            a0, a1 = math.atan2(a[1] - v[1], a[0] - v[0]), math.atan2(b[1] - v[1], b[0] - v[0])
            while a1 - a0 > math.pi:
                a1 -= 2 * math.pi
            while a1 - a0 < -math.pi:
                a1 += 2 * math.pi
            pts = [(v[0] + r * math.cos(a0 + (a1 - a0) * i / 20), v[1] + r * math.sin(a0 + (a1 - a0) * i / 20)) for i in range(21)]
            self.poly(pts, fill='none', closed=False, width=1)
            mid = (a0 + a1) / 2
            self.text((v[0] + (r + 2.2) * math.cos(mid), v[1] + (r + 2.2) * math.sin(mid) - FONT * 0.3), p['text'])

    def string(self, p):
        a, b, over = self.place(p['from']), self.place(p['to']), p.get('over') or []
        sides = p.get('side') or ['top'] * len(over)
        here = a
        for i, pid in enumerate(over):
            pul = self.by.get(pid)
            if pul is None or pul['type'] != 'pulley':
                raise FigureError(f'string over {pid}: no pulley with that id')
            self.resolve(pul)
            side = sides[i] if i < len(sides) else 'top'
            enter = self.tangent(pul, side, here)
            self.seg(here, enter, 1.3)
            if i + 1 < len(over):
                nxt = self.by[over[i + 1]]
                self.resolve(nxt)
                target = nxt['_at']
            else:
                target = b
            leave = self.tangent(pul, side, target)
            c, r = pul['_at'], pul['r']
            a0, a1 = math.atan2(enter[1] - c[1], enter[0] - c[0]), math.atan2(leave[1] - c[1], leave[0] - c[0])
            want = math.atan2(*{'top': (1, 0), 'bottom': (-1, 0), 'left': (0, -1), 'right': (0, 1)}[side])
            # the wrap runs the way that passes the named side
            for turn in (0, 2 * math.pi, -2 * math.pi):
                end = a1 + turn
                if abs(end - a0) <= 2 * math.pi and min(a0, end) <= want + 1e-6 <= max(a0, end):
                    a1 = end
                    break
                for k in (2 * math.pi, -2 * math.pi):
                    if min(a0, end) <= want + k + 1e-6 <= max(a0, end):
                        a1 = end
                        break
            pts = [(c[0] + r * math.cos(a0 + (a1 - a0) * j / 16), c[1] + r * math.sin(a0 + (a1 - a0) * j / 16)) for j in range(17)]
            self.poly(pts, fill='none', closed=False, width=1.3)
            here = leave
        self.seg(here, b, 1.3)

    def svg(self):
        # solids first, connectors after, words last, so a string or a label is never hidden under a block
        order = {'surface': 0, 'incline': 0, 'arc': 0, 'cut_block': 0, 'axes': 0, 'pulley': 1, 'block': 2, 'ball': 2, 'disc': 2, 'ring': 2, 'pivot': 2,
                 'rod': 2, 'string': 3, 'spring': 3, 'line': 3, 'arrow': 4, 'dim': 4, 'angle': 4, 'point': 4, 'label': 5}
        if not self.errors:
            for p in sorted(self.parts, key=lambda q: order[q['type']]):
                try:
                    self.draw(p)
                except FigureError as e:
                    self.errors.append(f"{p['type']} {p.get('id', '')}: {e}".strip())
                except (KeyError, TypeError, ValueError) as e:
                    self.errors.append(f"{p['type']} {p.get('id', '')}: bad or missing field {e}")
        for q in self.extent:
            if q[0] < -0.5 or q[0] > self.W + 0.5 or q[1] < -0.5 or q[1] > self.H + 0.5:
                self.errors.append(f'something reaches ({q[0]:.0f}, {q[1]:.0f}), outside the {self.W:.0f} by {self.H:.0f} frame: move it or widen the frame')
                break
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.W * SCALE:.0f}" height="{self.H * SCALE:.0f}" viewBox="0 0 {self.W * SCALE:.0f} {self.H * SCALE:.0f}">'
                f'<rect width="100%" height="100%" fill="#fff"/>{"".join(self.out)}</svg>')


def render(spec):
    """(svg, errors) of a figure spec."""
    fig = Figure(spec)
    svg = fig.svg()
    return svg, fig.errors
