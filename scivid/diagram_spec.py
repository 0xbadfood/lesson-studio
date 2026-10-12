"""Diagram vocabulary: the planner declares WHAT to show; code decides WHERE and computes every number.

A diagram chapter's spec:
  {"layout": "single" | "split", "elements": [ {id, type, panel?: "left"|"right", ...type fields} ]}
Script cues for diagram chapters: {"verb", "target": "<element id>[.<part id>]", point, phrase, until?, ...}
"""
import ast
import math
import re

ELEMENTS = {
    'equation_steps': ('Worked maths, one line per step, each a short LaTeX expression; shown one step at a time.',
                       '{"id":"work","type":"equation_steps","steps":["v = u + at","v = 0 + 2 \\\\times 5","v = 10\\\\,\\\\text{m/s}"]}'),
    'graph': ('Axes with plotted series. A series is a function of x (Python arithmetic) or a list of points. Code '
              'computes every point.',
              '{"id":"vt","type":"graph","x":{"label":"t (s)","min":0,"max":10,"step":2},"y":{"label":"v (m/s)",'
              '"min":0,"max":20,"step":5},"series":[{"id":"car","function":"2*x","colour":"blue"},'
              '{"id":"bus","points":[[0,5],[10,5]],"colour":"orange"}],"marks":[{"id":"p","x":5,"y":10,"label":"(5, 10)"}]}'),
    'number_line': ('A number line with marked values.',
                    '{"id":"nl","type":"number_line","min":-5,"max":5,"step":1,"marks":[{"id":"a","value":-3,"label":"-3"}]}'),
    'shape': ('An exact geometric figure computed by code from NAMED side lengths: right_triangle (the two sides '
              'at the right angle), triangle (all three sides), rectangle (w,h), square (side), circle (r), '
              'regular_polygon (n, side). Side labels with numbers must match the lengths. Parts: vertices by '
              'name, sides by two names (e.g. "AB").',
              '{"id":"tri","type":"shape","kind":"right_triangle","vertices":["A","B","C"],"right_angle_at":"B",'
              '"sides":{"AB":3,"BC":4},"side_labels":{"AB":"3 cm","BC":"4 cm","CA":"?"}}'),
    'path_motion': ('A route (circle of radius r, straight line of length, or semicircle) with a mover that can '
                    'travel it, a start marker and an optional displacement arrow from start to mover.',
                    '{"id":"track","type":"path_motion","shape":"circle","size":50,"unit":"m","mover":"runner",'
                    '"start_label":"Start"}'),
    'counter': ('A live readout that counts from one value to another (a timer, an oscillation count).',
                '{"id":"timer","type":"counter","label":"Time","from":0,"to":20,"unit":"s","decimals":0}'),
    'table': ('A small table; rows and cells can be highlighted.',
              '{"id":"t","type":"table","columns":["Trial","Time for 10 swings","Time period"],'
              '"rows":[["1","20 s","2 s"],["2","20.2 s","2.02 s"]]}'),
    'bars': ('A bar chart comparing a few values.',
             '{"id":"b","type":"bars","unit":"s","bars":[{"id":"short","label":"Short string","value":1.2},'
             '{"id":"long","label":"Long string","value":2.0}]}'),
    'cards': ('Two to four side-by-side cards with a title and a short value (comparisons, recaps).',
              '{"id":"c","type":"cards","items":[{"id":"d","title":"Distance","value":"314 m"},'
              '{"id":"s","title":"Displacement","value":"0 m"}]}'),
    'note': ('One short sentence or rule shown as a callout.',
             '{"id":"rule","type":"note","text":"Displacement = shortest distance from start to finish"}'),
}

VERBS = {
    'show': 'make an element (or part) appear',
    'hide': 'remove an element',
    'next_step': 'reveal the next line of equation_steps',
    'plot': 'draw one graph series ("vt.car")',
    'mark': 'show a mark on a graph or number line ("nl.a")',
    'jump': 'number-line hop from one mark to another: {"verb":"jump","target":"nl.a","to":"nl.b","text":"+5"}',
    'count': 'run a counter from its "from" to its "to" value over the cue',
    'move': 'path_motion mover travels: {"verb":"move","target":"track","laps":1} (laps may be 0.5, 1, 2)',
    'trace': 'highlight the full route of a path_motion',
    'connect': 'arrow between two targets, or for path_motion the displacement arrow from start to mover: '
               '{"verb":"connect","target":"track","text":"displacement"}',
    'highlight': 'emphasise an element or part ("tri.AB", "t.row2", "c.d", "b.long", "work")',
    'focus': 'the camera moves in on the target for the cue, then back out',
    'squares': 'squares grow outward on a triangle\'s sides with unit grids and area labels (the visual proof of '
               'Baudhayana-Pythagoras): {"verb":"squares","target":"tri","sides":["AB","BC","CA"]}',
    'vectors': 'live arrows on a path_motion mover, kept for the rest of the chapter: velocity (along the tangent), '
               'centripetal_force or centripetal_acceleration (toward the centre), string (line to the centre): '
               '{"verb":"vectors","target":"track","kinds":["velocity","centripetal_force","string"]}',
    'release': 'the mover leaves its circle along the tangent from this moment (no more inward pull): '
               '{"verb":"release","target":"track"}',
    'transform': 'a copy of one target flies into and becomes another (a value moving into an equation): '
                 '{"verb":"transform","target":"cards.sq3","to":"work"}',
}

LATEX_ALLOWED = set('''frac dfrac tfrac sqrt times div cdot pm mp approx neq ne le ge leq geq lt gt pi theta alpha beta
gamma delta Delta lambda mu omega Omega phi sigma rho tau infty circ degree text mathrm mathbf left right quad qquad
sin cos tan log ln exp sum int lim to rightarrow Rightarrow leftarrow implies therefore because angle triangle perp
parallel overline underline hat vec dot ddot prime cdots ldots dots percent'''.split())


class SpecError(ValueError):
    pass


def latex_errors(expr):
    """Only maths-typesetting commands are allowed (no file or shell access through LaTeX)."""
    problems = []
    if len(expr) > 160:
        problems.append('keep each equation step under 160 characters')
    for cmd in re.findall(r'\\([A-Za-z]+)', expr):
        if cmd not in LATEX_ALLOWED:
            problems.append(f'LaTeX command \\{cmd} is not allowed')
    if re.search(r'[\$#%&~^]{2,}|\\\\', expr.replace('\\\\,', '')):
        pass
    if expr.count('{') != expr.count('}'):
        problems.append('unbalanced braces')
    return problems


def evaluate(expr, x=None):
    """Bounded arithmetic in x (no eval): numbers, x, pi, e, + - * / **, and math functions."""
    funcs = {k: getattr(math, k) for k in ('sin', 'cos', 'tan', 'sqrt', 'exp', 'log', 'log10', 'radians', 'fabs')}
    ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b}

    def visit(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return float(n.value)
        if isinstance(n, ast.Name) and n.id in ('pi', 'e'):
            return getattr(math, n.id)
        if isinstance(n, ast.Name) and n.id == 'x' and x is not None:
            return float(x)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -visit(n.operand) if isinstance(n.op, ast.USub) else visit(n.operand)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            a, b = visit(n.left), visit(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 12:
                raise SpecError('exponent too large')
            return ops[type(n.op)](a, b)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs and len(n.args) == 1:
            return funcs[n.func.id](visit(n.args[0]))
        raise SpecError(f'unsupported expression part in "{expr}"')
    tree = ast.parse(str(expr), mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 80:
        raise SpecError('expression too long')
    value = visit(tree.body)
    if not math.isfinite(value):
        raise SpecError('expression is not finite')
    return value


def parts(element):
    """Addressable part ids of an element."""
    t = element.get('type')
    if t == 'graph':
        return {s['id'] for s in element.get('series', [])} | {m['id'] for m in element.get('marks', [])}
    if t == 'number_line':
        return {m['id'] for m in element.get('marks', [])}
    if t == 'shape':
        names = element.get('vertices') or []
        sides = {a + b for a, b in zip(names, names[1:] + names[:1])} | {b + a for a, b in zip(names, names[1:] + names[:1])}
        return set(names) | sides | {'sq_' + x for x in sides}
    if t == 'table':
        return {f'row{i + 1}' for i in range(len(element.get('rows', [])))}
    if t in ('bars', 'cards'):
        return {b['id'] for b in element.get('bars', element.get('items', []))}
    return set()


def spec_errors(spec):
    errors = []
    if not isinstance(spec, dict):
        return ['diagram must be an object with layout and elements']
    if spec.get('layout') not in ('single', 'split'):
        errors.append('layout must be "single" or "split"')
    elements = spec.get('elements') or []
    if not 1 <= len(elements) <= 5:
        errors.append('use 1-5 elements per diagram chapter')
    ids = [e.get('id') for e in elements]
    if len(set(ids)) != len(ids) or not all(re.fullmatch(r'[a-z][a-z0-9_]{0,20}', str(i)) for i in ids):
        errors.append('element ids must be unique short snake_case')
    for e in elements:
        where = f"element {e.get('id')}"
        t = e.get('type')
        if t not in ELEMENTS:
            errors.append(f'{where}: type must be one of {sorted(ELEMENTS)}')
            continue
        if spec.get('layout') == 'split' and e.get('panel') not in ('left', 'right'):
            errors.append(f'{where}: in a split layout give panel "left" or "right"')
        try:
            if t == 'equation_steps':
                steps = e.get('steps') or []
                if not 1 <= len(steps) <= 8:
                    errors.append(f'{where}: 1-8 steps')
                for s in steps:
                    errors += [f'{where}: {p}' for p in latex_errors(str(s))]
            elif t == 'graph':
                for axis in ('x', 'y'):
                    a = e.get(axis) or {}
                    if not (isinstance(a.get('min'), (int, float)) and isinstance(a.get('max'), (int, float))
                            and a['max'] > a['min'] and a.get('step', 0) > 0 and (a['max'] - a['min']) / a['step'] <= 16):
                        errors.append(f'{where}: axis {axis} needs min < max and a step giving at most 16 ticks')
                if errors:
                    continue
                for srs in e.get('series', []):
                    pts = graph_points(e, srs)
                    out = [p for p in pts if not (e['y']['min'] - 1e-9 <= p[1] <= e['y']['max'] + 1e-9)]
                    if len(out) > len(pts) * .1:
                        errors.append(f"{where}: series {srs.get('id')} goes outside the y range; widen the axis")
                for m in e.get('marks', []):
                    if not (e['x']['min'] <= m['x'] <= e['x']['max'] and e['y']['min'] <= m['y'] <= e['y']['max']):
                        errors.append(f"{where}: mark {m.get('id')} is outside the axes")
            elif t == 'number_line':
                if not (e['max'] > e['min'] and e['step'] > 0 and (e['max'] - e['min']) / e['step'] <= 24):
                    errors.append(f'{where}: min < max and at most 24 steps')
                for m in e.get('marks', []):
                    if not e['min'] <= m['value'] <= e['max']:
                        errors.append(f"{where}: mark {m.get('id')} is off the line")
            elif t == 'shape':
                errors += [f'{where}: {x}' for x in label_errors(e)]
            elif t == 'path_motion':
                if e.get('shape') not in ('circle', 'line', 'semicircle') or not e.get('size', 0) > 0:
                    errors.append(f'{where}: shape circle|line|semicircle with a positive size')
            elif t == 'counter':
                float(e['from']), float(e['to'])
            elif t == 'table':
                cols = e.get('columns') or []
                if not 1 <= len(cols) <= 6 or not 1 <= len(e.get('rows') or []) <= 8 or \
                        any(len(r) != len(cols) for r in e['rows']):
                    errors.append(f'{where}: 1-6 columns, 1-8 rows, every row as long as the columns')
            elif t == 'bars':
                if not 2 <= len(e.get('bars') or []) <= 8 or any(float(b['value']) < 0 for b in e['bars']):
                    errors.append(f'{where}: 2-8 bars with non-negative values')
            elif t == 'cards':
                if len(e.get('items') or []) < 2:
                    errors.append(f'{where}: 2-4 cards')
                e['items'] = e['items'][:4]            # formatting limit: extra cards are dropped, not fatal
            elif t == 'note':
                if not 2 <= len(str(e.get('text', '')).split()) <= 30:
                    errors.append(f'{where}: a note is one or two short sentences (up to 30 words)')
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f'{where}: {exc}')
    return errors


def cue_errors(cue, spec):
    elements = {e['id']: e for e in spec.get('elements', [])}
    verb, target = cue.get('verb'), str(cue.get('target', ''))
    if verb not in VERBS:
        return [f'unknown diagram verb {verb}; use {sorted(VERBS)}']
    eid, _, part = target.partition('.')
    if eid not in elements:
        return [f'target {target} must name an element: {sorted(elements)}']
    e = elements[eid]
    if part and part not in parts(e):
        return [f'{target}: part must be one of {sorted(parts(e))}']
    if verb == 'vectors':
        kinds = cue.get('kinds') or []
        allowed = {'velocity', 'centripetal_force', 'centripetal_acceleration', 'string'}
        if not kinds or not set(kinds) <= allowed:
            return [f'vectors needs "kinds" from {sorted(allowed)}']
    need = {'next_step': 'equation_steps', 'count': 'counter', 'move': 'path_motion', 'trace': 'path_motion',
            'vectors': 'path_motion', 'release': 'path_motion',
            'plot': 'graph', 'jump': 'number_line'}
    if verb in need and e['type'] != need[verb]:
        return [f'{verb} works on {need[verb]} elements']
    if verb == 'plot' and not part:
        return ['plot needs a series: "graph.series"']
    if verb == 'jump' and str(cue.get('to', '')).partition('.')[2] not in parts(e):
        return ['jump needs "to": another mark on the same number line']
    if verb == 'squares' and not (e['type'] == 'shape' and e.get('kind') in ('right_triangle', 'triangle', 'rectangle',
                                                                             'square', 'regular_polygon')):
        return ['squares works on a shape with straight sides']
    if verb == 'squares' and cue.get('sides') and any(str(sd) not in parts(e) for sd in cue['sides']):
        return [f'squares sides must be side names of {eid}: {sorted(p for p in parts(e) if len(p) == 2)}']
    if verb == 'transform':
        to_eid, _, to_part = str(cue.get('to', '')).partition('.')
        if to_eid not in elements or (to_part and to_part not in parts(elements[to_eid])):
            return ['transform needs "to": another element or element.part']
    if verb == 'connect' and e['type'] != 'path_motion' and str(cue.get('to', '')).partition('.')[0] not in elements:
        return ['connect needs "to": another target (or use it on a path_motion element)']
    return []


# ---------------------------------------------------------------- exact geometry
def graph_points(e, series, samples=120):
    if 'function' in series:
        lo, hi = e['x']['min'], e['x']['max']
        return [(lo + (hi - lo) * i / samples, evaluate(series['function'], lo + (hi - lo) * i / samples))
                for i in range(samples + 1)]
    pts = [(float(a), float(b)) for a, b in series.get('points', [])]
    if len(pts) < 2:
        raise SpecError(f"series {series.get('id')} needs a function or at least two points")
    return pts


def _length(e, a, b):
    """A side's length from "sides" (by name, either direction) or from a numeric side label."""
    for key in (a + b, b + a):
        if key in (e.get('sides') or {}):
            return float(e['sides'][key])
    for key in (a + b, b + a):
        label = str((e.get('side_labels') or {}).get(key, ''))
        found = re.match(r'\s*([0-9]+(?:\.[0-9]+)?)', label)
        if found:
            return float(found.group(1))
    return None


def shape_points(e):
    """Vertex coordinates in shape units, computed exactly from named side lengths."""
    kind = e.get('kind')
    names = e.get('vertices') or []
    if kind == 'right_triangle':
        if len(names) != 3:
            names = ['A', 'B', 'C']
        corner = e.get('right_angle_at') if e.get('right_angle_at') in names else names[1]
        i = names.index(corner)
        prev, nxt = names[i - 1], names[(i + 1) % 3]
        up = _length(e, prev, corner) or (float(e['b']) if 'b' in e else None)
        across = _length(e, corner, nxt) or (float(e['a']) if 'a' in e else None)
        if not (up and across and up > 0 and across > 0):
            raise SpecError('right_triangle needs the two sides at the right angle, e.g. "sides":{"AB":3,"BC":4}')
        coords = {corner: (0.0, 0.0), prev: (0.0, up), nxt: (across, 0.0)}
        pts = [coords[n] for n in names]
    elif kind == 'triangle':
        if len(names) != 3:
            names = ['A', 'B', 'C']
        A, B, C = names
        c, a, b = _length(e, A, B), _length(e, B, C), _length(e, C, A)
        if c is None:
            a, b, c = float(e['a']), float(e['b']), float(e['c'])
        if not (a + b > c and b + c > a and a + c > b):
            raise SpecError('those three sides cannot make a triangle')
        # B at the origin, C along the base (BC = a); A from AB = c and CA = b.
        ax = (c * c - b * b + a * a) / (2 * a)
        pts = [(ax, math.sqrt(max(0.0, c * c - ax * ax))), (0.0, 0.0), (a, 0.0)]
    elif kind == 'rectangle':
        w, h = float(e['w']), float(e['h'])
        pts = [(0, h), (0, 0), (w, 0), (w, h)]
    elif kind == 'square':
        side = float(e['side'])
        pts = [(0, side), (0, 0), (side, 0), (side, side)]
    elif kind == 'regular_polygon':
        n, side = int(e['n']), float(e.get('side', 1))
        if not 3 <= n <= 12:
            raise SpecError('regular_polygon needs 3-12 sides')
        r = side / (2 * math.sin(math.pi / n))
        pts = [(r * math.cos(math.pi / 2 + 2 * math.pi * i / n), r * math.sin(math.pi / 2 + 2 * math.pi * i / n))
               for i in range(n)]
    elif kind == 'circle':
        if not float(e['r']) > 0:
            raise SpecError('circle needs r > 0')
        return []
    else:
        raise SpecError('shape kind must be right_triangle, triangle, rectangle, square, regular_polygon or circle')
    if names and len(names) != len(pts):
        raise SpecError(f'{kind} has {len(pts)} vertices; give exactly that many names')
    return pts


def label_errors(e):
    """Every numeric side label must match the computed side length."""
    if e.get('type') != 'shape' or e.get('kind') == 'circle':
        return []
    pts, names = shape_points(e), e.get('vertices') or []
    errors = []
    for key, label in (e.get('side_labels') or {}).items():
        found = re.match(r'\s*([0-9]+(?:\.[0-9]+)?)', str(label))
        if not found or len(key) != 2 or key[0] not in names or key[1] not in names:
            continue
        p, q = pts[names.index(key[0])], pts[names.index(key[1])]
        length = math.dist(p, q)
        if abs(length - float(found.group(1))) > max(.02, .01 * length):
            errors.append(f'side {key} is labelled {label} but measures {length:.3g} from the given sides')
    return errors


def prompt_reference():
    lines = ['DIAGRAM ELEMENTS (declare 1-5; code lays them out and computes all geometry):']
    for name, (what, example) in ELEMENTS.items():
        lines.append(f'- {name}: {what}\n  e.g. {example}')
    lines.append('Layout "single" stacks elements; "split" puts each element in panel "left" or "right".')
    lines.append('This is animated in Manim style: things are drawn, written, transformed and moved while the '
                 'narrator speaks. Prefer VISUAL elements (shape, graph, number_line, path_motion, bars) and build '
                 'ideas up with verbs (squares, next_step, transform, plot, move, jump, focus). Use at most ONE '
                 'text element (note or cards) per chapter; never make a chapter of text alone.')
    return '\n'.join(lines)


def verb_reference():
    return '\n'.join(f'- {v}: {d}' for v, d in VERBS.items())
