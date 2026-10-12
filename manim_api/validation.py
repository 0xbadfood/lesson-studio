import ast
import builtins
import math
import operator
import symtable


IMPORTS = {'manim', 'numpy', 'math', 'lesson_runtime'}
FORBIDDEN = {'open', 'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr', 'delattr',
             'globals', 'locals', 'vars', 'dir', 'input', 'breakpoint', 'exit', 'quit',
             'load', 'save', 'savez', 'loadtxt', 'savetxt', 'fromfile', 'tofile',
             'read', 'write', 'read_text', 'write_text', 'read_bytes', 'write_bytes',
             'system', 'popen', 'spawn', 'fork', 'socket', 'connect', 'send', 'recv',
             'Tex', 'MathTex', 'DecimalNumber', 'SVGMobject', 'ImageMobject',
             'tempfile', 'os', 'sys', 'subprocess', 'pathlib', 'builtins', 'ctypes',
             'importlib', 'pickle', 'requests', 'urllib', 'httpx', 'inspect',
             'set_start_and_end', 'set_start_and_end_points', 'clear_updater'}


def validate_code(code,manim_module=None):
    if not isinstance(code, str) or not 100 <= len(code) <= 35000:
        raise ValueError('Return a complete scene module of 100–35,000 characters')
    tree = ast.parse(code)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if len(classes) != 1 or classes[0].name != 'GeneratedScene':
        raise ValueError('Define exactly one class named GeneratedScene')
    if len(classes[0].bases)!=1 or not isinstance(classes[0].bases[0],ast.Attribute) or classes[0].bases[0].attr!='Scene':
        raise ValueError('GeneratedScene must inherit from m.Scene')
    construct = [n for n in classes[0].body if isinstance(n, ast.FunctionDef) and n.name == 'construct']
    if len(construct) != 1:
        raise ValueError('GeneratedScene must define construct(self)')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(n.name not in IMPORTS for n in node.names):
                raise ValueError('Import only manim, numpy, math and lesson_runtime')
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in IMPORTS:
                raise ValueError('Import only manim, numpy, math and lesson_runtime')
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ValueError('Do not modify global state')
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
        private = bool(name and (name.startswith('__') or isinstance(node,ast.Attribute) and name.startswith('_')))
        if name and (name in FORBIDDEN or private):
            raise ValueError('Unsupported access: '+name)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'Text' and node.args and isinstance(node.args[0], ast.Constant) and not node.args[0].value:
                raise ValueError('Empty Text objects are invalid; omit the object')
    symbols=symtable.symtable(code,'scene.py','exec')
    defined={s.get_name() for s in symbols.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    defined.update(dir(builtins))
    missing_names=set()
    scopes=[symbols]
    while scopes:
        scope=scopes.pop()
        scopes.extend(scope.get_children())
        missing_names.update(s.get_name() for s in scope.get_symbols()
                             if s.is_referenced() and s.is_global() and s.get_name() not in defined)
    defects=[]
    if missing_names:
        defects.append('Undefined names: '+', '.join(sorted(missing_names))+
                       '. With import manim as m, use m.FadeIn, m.Create, m.UP, etc.; qualify every Manim name.')
    if manim_module is not None:
        aliases={alias.asname or alias.name for node in ast.walk(tree) if isinstance(node,ast.Import)
                 for alias in node.names if alias.name=='manim'}
        unavailable={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)
                     and isinstance(node.value,ast.Name) and node.value.id in aliases
                     and not hasattr(manim_module,node.attr)}
        if unavailable:
            advice=' Use supported Community 0.21 APIs.'
            if 'X' in unavailable:advice+=' For a crossing-out mark use m.Cross or two Lines.'
            if 'PolyLine' in unavailable:
                advice+=' Import polyline from lesson_runtime and use polyline([point1,point2,...],color=CYAN); the helper returns a populated open path.'
            defects.append('Installed Manim has no module attributes: '+', '.join(sorted(unavailable))+
                           '.'+advice)
    functions={n.name:n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            if node.func.attr=='clear_updaters' and isinstance(node.func.value,ast.Name) and node.func.value.id=='self' and 'clear_updaters' not in functions:
                defects.append('Scene has no self.clear_updaters(). The supplied finish() helper clears object updaters; remove this Scene call.')
            if node.func.attr=='add_updater' and node.args:
                callback=node.args[0]
                definition=functions.get(callback.id) if isinstance(callback,ast.Name) else callback
                if isinstance(definition,(ast.FunctionDef,ast.Lambda)):
                    positional=definition.args.posonlyargs+definition.args.args
                    name=definition.name if isinstance(definition,ast.FunctionDef) else 'the lambda'
                    if not positional and definition.args.vararg is None:
                        defects.append('add_updater callbacks receive the mobject. Add a mob parameter to '+name+'.')
                    elif any(arg.arg=='dt' for arg in positional) and len(positional)<2 and definition.args.vararg is None:
                        defects.append('Time-based add_updater callbacks receive (mob,dt). Correct '+name+'.')
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='always_redraw' and node.args:
            callback=node.args[0]
            definition=functions.get(callback.id) if isinstance(callback,ast.Name) else callback
            if isinstance(definition,(ast.FunctionDef,ast.Lambda)):
                args=definition.args
                required=len(args.posonlyargs)+len(args.args)-len(args.defaults)
                required+=sum(value is None for value in args.kw_defaults)
                if required:
                    defects.append('always_redraw callbacks are called with zero arguments. Remove required parameters from '+
                                   (definition.name if isinstance(definition,ast.FunctionDef) else 'the lambda')+'.')
    if defects:
        raise ValueError('\n'.join(defects))
    trackers={n.targets[0].id for n in ast.walk(tree) if isinstance(n,ast.Assign)
              and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
              and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute)
              and n.value.func.attr=='ValueTracker'}
    updated={n.func.value.id for n in ast.walk(tree) if isinstance(n,ast.Call)
             and isinstance(n.func,ast.Attribute) and n.func.attr=='add_updater'
             and isinstance(n.func.value,ast.Name) and n.func.value.id in trackers}
    registered=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('add','play'):
            registered.update(n.id for arg in node.args for n in ast.walk(arg) if isinstance(n,ast.Name))
    missing=updated-registered
    if missing:
        raise ValueError('Time-updated ValueTracker(s) '+', '.join(sorted(missing))+
                         ' never enter the scene, so their updaters do not run. Use self.add(tracker), '
                         'or animate the tracker explicitly with self.play(tracker.animate.set_value(...)).')
    return tree


def validate_geometry(data):
    """Check persistent text collisions and claimed equal-force diagrams."""
    violations=[]
    overlap_runs={}
    confirmed_overlaps={}
    hidden_runs={}
    confirmed_hidden={}
    for sample in data.get('samples',[]):
        labels=[label for label in sample.get('text_labels',[]) if 'min' in label and 'max' in label]
        for label in labels:
            for fill in sample.get('filled_rectangles',[]):
                if not label.get('color') or label['color'].lower()!=fill['color'].lower():continue
                area=(label['max'][0]-label['min'][0])*(label['max'][1]-label['min'][1])
                overlap=max(0,min(label['max'][0],fill['max'][0])-max(label['min'][0],fill['min'][0]))
                overlap*=max(0,min(label['max'][1],fill['max'][1])-max(label['min'][1],fill['min'][1]))
                if area<=0 or overlap/area<.45:continue
                key=(label['text'],label['color'].lower())
                now=sample['time'];run=hidden_runs.get(key)
                if run is None or now-run['last']>.8:
                    run={'start':now,'last':now,'text':label['text'],'color':label['color'],
                         'label_box':{'min':label['min'],'max':label['max']},'fill_box':fill}
                run['last']=now;hidden_runs[key]=run
                if now-run['start']>=1:confirmed_hidden[key]=run.copy()
        for index,first in enumerate(labels):
            for second in labels[index+1:]:
                sizes=[max(0,label['max'][0]-label['min'][0])*max(0,label['max'][1]-label['min'][1])
                       for label in (first,second)]
                area=max(0,min(first['max'][0],second['max'][0])-max(first['min'][0],second['min'][0]))
                area*=max(0,min(first['max'][1],second['max'][1])-max(first['min'][1],second['min'][1]))
                if min(sizes)<=0 or area/min(sizes)<=.1:
                    continue
                key=tuple(sorted((first['text'],second['text'])))
                now=sample['time']
                run=overlap_runs.get(key)
                if run is None or now-run['last']>.8:
                    run={'start':now,'last':now,'labels':list(key),'overlap_fraction':area/min(sizes),
                         'boxes':[{'text':label['text'],'min':label['min'],'max':label['max']} for label in (first,second)]}
                run['last']=now
                overlap_runs[key]=run
                if now-run['start']>=1:
                    confirmed_overlaps[key]=run.copy()
        claims=('equalmagnitude','samemagnitude','equallength','balancedforces','forcesbalance')
        if not any(any(claim in ''.join(label['text'].lower().split()) for claim in claims)
                   for label in sample.get('text_labels',[])):
            continue
        red=[arrow for arrow in sample.get('arrows',[]) if arrow['color'].lower()=='#ff727c']
        amber=[arrow for arrow in sample.get('arrows',[]) if arrow['color'].lower()=='#ffc768']
        for first in red:
            for second in amber:
                distance=math.sqrt(sum((a-b)**2 for a,b in zip(first['start'],second['start'])))
                a=[end-start for start,end in zip(first['start'],first['end'])]
                b=[end-start for start,end in zip(second['start'],second['end'])]
                la=math.sqrt(sum(value**2 for value in a));lb=math.sqrt(sum(value**2 for value in b))
                if distance>.08 or min(la,lb)<.1:
                    continue
                cosine=sum(x*y for x,y in zip(a,b))/(la*lb)
                if cosine<-.98 and abs(la-lb)>max(.08,.15*max(la,lb)):
                    violations.append({'time':sample['time'],'inward_length':la,'outward_length':lb})
    defects=[]
    if confirmed_hidden:
        defects.append('Text is hidden against a filled rectangle of the same color for a sustained interval. '
                       'Use contrasting ink and keep arrows clear of the text, or move the labels outside the filled bars: '+
                       str(list(confirmed_hidden.values())[:3]))
    if confirmed_overlaps:
        defects.append('Body text labels overlap persistently. Position their complete bounding boxes '
                       'in separate areas with at least 0.12 scene units of clear gap: '+str(list(confirmed_overlaps.values())[:3]))
    if len(violations)>=3 and violations[-1]['time']-violations[0]['time']>=1:
        defects.append('The diagram claims equal magnitude, but opposing force arrows at the same '
                       'object have different measured lengths. Use a common visual force scale and '
                       'equal final lengths for balanced forces: '+str(violations[:3]))
    if defects:raise ValueError('\n'.join(defects))


def arithmetic(expression):
    """Evaluate bounded numerical arithmetic without eval or generated test code."""
    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                 ast.Div: operator.truediv, ast.Pow: operator.pow}
    functions = {k: getattr(math, k) for k in ('sin','cos','tan','sqrt','exp','log','log10','radians')}
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = float(node.value)
        elif isinstance(node, ast.Name) and node.id in ('pi','e'):
            value = getattr(math, node.id)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub,ast.UAdd)):
            value = (-1 if isinstance(node.op,ast.USub) else 1)*visit(node.operand)
        elif isinstance(node, ast.BinOp) and type(node.op) in operators:
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op,ast.Pow) and abs(b)>100:
                raise ValueError('Exponent exceeds numerical bound')
            value = operators[type(node.op)](a,b)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and len(node.args)==1 and not node.keywords:
            value = functions[node.func.id](visit(node.args[0]))
        else:
            raise ValueError('Calculation supports only numbers, pi/e and approved arithmetic/math functions')
        if not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>1e100:
            raise ValueError('Calculation is not finite or exceeds the numerical bound')
        return value
    try:
        tree = ast.parse(expression, mode='eval')
        if sum(1 for _ in ast.walk(tree)) > 100:
            raise ValueError('Calculation is too complex')
        return visit(tree.body)
    except (SyntaxError,ArithmeticError) as exc:
        raise ValueError('Invalid numerical calculation: '+str(exc)) from exc


def validate_plan(plan, request, source_ids):
    ids = [s.id for s in plan.scenes]
    if ids != [f's{i+1:02d}' for i in range(len(ids))]:
        raise ValueError('Use ordered scene IDs s01, s02, ...')
    total = sum(s.duration_seconds for s in plan.scenes)
    if abs(total-request.duration_seconds)>max(3,request.duration_seconds*.12):
        raise ValueError('Scene durations must approximately total the requested video duration')
    for scene in plan.scenes:
        if not set(scene.source_ids)<=source_ids or any(not set(c.source_ids)<=source_ids for c in scene.calculations):
            raise ValueError('Every source ID must refer to a fetched research source')
        if len(scene.caption.split())>20:
            raise ValueError('Captions must contain at most 20 words')
    checks=[]
    for scene in plan.scenes:
        for calculation in scene.calculations:
            actual=arithmetic(calculation.expression)
            if abs(actual-calculation.expected)>calculation.tolerance:
                raise ValueError(f'Incorrect calculation in {scene.id}: {calculation.label}; computed {actual}, declared {calculation.expected}')
            checks.append({'scene':scene.id,**calculation.model_dump(),'actual':actual,'passed':True})
    return checks
