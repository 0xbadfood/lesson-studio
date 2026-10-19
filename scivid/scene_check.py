"""Checks for LLM-coded chapter scenes: static code rules (host and sandbox) and measured-geometry rules.

Copied into the render sandbox as scene_check.py; it must import nothing outside the standard library.
"""
import ast
import builtins
import symtable

IMPORTS = {'manim', 'numpy', 'math', 'scene_kit', 'chem_kit'}
FORBIDDEN = {'open', 'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr', 'delattr', 'globals', 'locals',
             'vars', 'dir', 'input', 'breakpoint', 'exit', 'quit', 'load', 'save', 'savez', 'loadtxt', 'savetxt',
             'fromfile', 'tofile', 'read_text', 'write_text', 'read_bytes', 'write_bytes', 'system', 'popen', 'spawn',
             'fork', 'socket', 'connect', 'tempfile', 'os', 'sys', 'subprocess', 'pathlib', 'builtins', 'ctypes',
             'importlib', 'pickle', 'requests', 'urllib', 'httpx', 'inspect', 'SVGMobject', 'ImageMobject',
             'set_start_and_end_points', 'set_camera_orientation', 'begin_ambient_camera_rotation'}
CLASS = 'ChapterScene'


def validate_code(code, manim_module=None):
    """Raise ValueError listing every defect found without running the code."""
    if not isinstance(code, str) or not 100 <= len(code) <= 40000:
        raise ValueError('Return a complete scene module of 100-40,000 characters')
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:   # a broken edit is a defect for the coder, never a crash
        line = (exc.text or '').rstrip()
        raise ValueError(f'The module does not parse: {type(exc).__name__}: {exc.msg} at line {exc.lineno}: {line!r}') from exc
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if len(classes) != 1 or classes[0].name != CLASS:
        raise ValueError(f'Define exactly one class named {CLASS}')
    base = classes[0].bases[0] if len(classes[0].bases) == 1 else None
    if not (isinstance(base, ast.Attribute) and base.attr == 'Scene'):
        raise ValueError(f'{CLASS} must inherit from m.Scene')
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'construct' for n in classes[0].body):
        raise ValueError(f'{CLASS} must define construct(self)')
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    defects = [f'Call {name}() from scene_kit' for name in ('begin', 'finish') if name not in calls]
    if 'at' not in calls:
        defects.append('Call at(self, t) before each cue so the animation follows the narration')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(n.name not in IMPORTS for n in node.names) or \
                isinstance(node, ast.ImportFrom) and (node.level or node.module not in IMPORTS):
            defects.append('Import only manim, numpy, math, scene_kit and chem_kit')
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            defects.append('Do not modify global state')
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
        if name and (name in FORBIDDEN or name.startswith('__') or isinstance(node, ast.Attribute) and name.startswith('_')):
            defects.append('Unsupported access: ' + name)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'wait' and \
                isinstance(node.func.value, ast.Name) and node.func.value.id == 'self':
            defects.append('Use at(self, t) instead of self.wait() so timing follows the narration clock')
    symbols = symtable.symtable(code, 'scene.py', 'exec')
    defined = {s.get_name() for s in symbols.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    defined.update(dir(builtins))
    missing, scopes = set(), [symbols]
    while scopes:
        scope = scopes.pop()
        scopes.extend(scope.get_children())
        missing.update(s.get_name() for s in scope.get_symbols()
                       if s.is_referenced() and s.is_global() and s.get_name() not in defined)
    if missing:
        defects.append('Undefined names: ' + ', '.join(sorted(missing)) + '. With import manim as m, qualify every '
                       'Manim name (m.FadeIn, m.UP, ...).')
    if manim_module is not None:
        aliases = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
                   if a.name == 'manim'}
        unknown = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                   and n.value.id in aliases and not hasattr(manim_module, n.attr)}
        if unknown:
            defects.append('Installed Manim (Community 0.21) has no: ' + ', '.join(sorted(unknown)))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args):
            continue
        callback = node.args[0]
        definition = functions.get(callback.id) if isinstance(callback, ast.Name) else callback
        if not isinstance(definition, (ast.FunctionDef, ast.Lambda)):
            continue
        label = definition.name if isinstance(definition, ast.FunctionDef) else 'the lambda'
        args = definition.args
        if node.func.attr == 'add_updater':
            positional = args.posonlyargs + args.args
            if not positional and args.vararg is None:
                defects.append(f'add_updater callbacks receive the mobject; add a mob parameter to {label}')
        if node.func.attr == 'always_redraw':
            required = len(args.posonlyargs) + len(args.args) - len(args.defaults)
            if required:
                defects.append(f'always_redraw callbacks take no arguments; fix {label}')
    if defects:
        raise ValueError('\n'.join(dict.fromkeys(defects)))
    return tree


def geometry_defects(data):
    """Defects measured in the render: overlapping labels, text in reserved bands or off frame, late cues."""
    defects = []
    runs, confirmed = {}, {}
    for sample in data.get('samples', []):
        labels, present = sample.get('labels', []), set()
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                sizes = [max(0, x['max'][0] - x['min'][0]) * max(0, x['max'][1] - x['min'][1]) for x in (a, b)]
                area = max(0, min(a['max'][0], b['max'][0]) - max(a['min'][0], b['min'][0])) * \
                    max(0, min(a['max'][1], b['max'][1]) - max(a['min'][1], b['min'][1]))
                if min(sizes) <= 0 or area / min(sizes) <= .08:
                    continue
                key = tuple(sorted((a['text'], b['text'])))
                present.add(key)
                # Samples are taken while animations play; a static wait has none, so an overlap seen in
                # consecutive samples lasted for the whole time between them.
                start = runs.setdefault(key, sample['time'])
                if sample['time'] - start >= .9:
                    confirmed[key] = {'labels': list(key), 'from': round(start, 1), 'to': round(sample['time'], 1)}
        runs = {k: v for k, v in runs.items() if k in present}
    if confirmed:
        defects.append('On-screen labels overlap each other for over a second; give each its own clear space '
                       '(at least 0.15 units apart): ' + str(list(confirmed.values())[:4]))
    if data.get('band_text'):
        defects.append('Body text enters the heading band (y > 2.95) or the subtitle band (y < -2.75); keep every '
                       'label between those lines: ' + str(data['band_text'][:3]))
    if data.get('off_frame'):
        defects.append('Objects leave the visible frame (x beyond ±7.1 or y beyond ±4): ' + str(data['off_frame'][:3]))
    late = [x for x in data.get('late', []) if x['reached_at'] - x['cue_time'] > .6]
    if late:
        defects.append('Animations ran past the start of later cues, so the picture lags the narration; shorten the '
                       'run_time of the animations before these cues: ' + str(late[:5]))
    if data.get('elapsed', 0) > data.get('duration', 0) + .6:
        defects.append(f"The scene runs {data['elapsed']:.1f}s but the narration lasts {data['duration']:.1f}s; "
                       'trim animations so finish() is reached in time')
    return defects
