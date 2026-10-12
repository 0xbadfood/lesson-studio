"""Targeted repairs: a fixer returns operations on stable ids instead of rewriting a whole document.

Rewriting a full plan or script to fix one sentence is slow (most of the output is thinking plus an unchanged copy)
and re-opens everything else, so new errors creep into parts that were already right. A patch touches only what a
review finding names; code applies it, the normal code checks run on the result, and the reviewer then scores the
whole document again.

Addresses (ids, never list positions):
  plan:   title | big_idea | misconception | colours | theme.<key>
          chapters.<cN>.<title|objective|route|history|complexity|source_ids|seconds|visual|demonstrations>
          chapters.<cN>.demonstrations.<dN>.<watch|proves>
  script: points.<cNpM>.narration | slides.<cNpM> | cues.<cN>.<kN> (set or remove) | cues.<cN> (add)
Operations: {"op":"set","path":...,"value":...} | {"op":"add","path":"cues.<cN>","value":{cue}} |
            {"op":"remove","path":"cues.<cN>.<kN>"}
"""
import copy
import json

PLAN_TOP = ('title', 'big_idea', 'misconception', 'colours')
PLAN_CHAPTER = ('title', 'objective', 'route', 'history', 'complexity', 'source_ids', 'seconds', 'visual',
                'demonstrations')
THEME = ('background', 'accent', 'text', 'picture_style')

GUIDE = {
    'plan': ('Return {"ops":[...],"notes":[...]} where each op is {"op":"set","path":<address>,"value":<new value>}. '
             'Addresses: ' + ' | '.join(PLAN_TOP) + ' | theme.<' + '|'.join(THEME) + '> | chapters.<chapter id>.<' +
             '|'.join(PLAN_CHAPTER) + '> | chapters.<chapter id>.demonstrations.<demo id>.<watch|proves>. '),
    'script': ('Return {"ops":[...],"notes":[...]} with ops {"op":"set","path":"points.<point id>.narration",'
               '"value":str} | {"op":"set","path":"slides.<point id>","value":{card}} | {"op":"set","path":'
               '"cues.<chapter id>.<cue id>","value":{cue}} | {"op":"remove","path":"cues.<chapter id>.<cue id>"} | '
               '{"op":"add","path":"cues.<chapter id>","value":{cue}}. If you change narration words that a cue '
               'phrase or "until" is anchored to, update that cue in the same patch. '),
}
RULES = ('Change only what the findings require; everything you do not address stays exactly as it is. Give whole '
         'new values for the fields you change (not fragments). Use only the addresses listed.')


def number_cues(script):
    """Cue ids k1, k2, ... in order within each chapter (the ids the coder and reviewers see)."""
    for sc in script.get('chapters', []):
        for i, c in enumerate(sc.get('cues') or []):
            c['id'] = f'k{i + 1}'
    return script


def _chapter(doc, cid):
    for c in doc.get('chapters', []):
        if c.get('id') == cid:
            return c
    raise ValueError(f'no chapter "{cid}"')


def _point(script, pid):
    for sc in script.get('chapters', []):
        for p in sc.get('points', []):
            if p.get('id') == pid:
                return sc, p
    raise ValueError(f'no narration point "{pid}"')


def _apply_plan(plan, op):
    parts = str(op.get('path', '')).split('.')
    value = op.get('value')
    if op.get('op') != 'set':
        raise ValueError('plan patches only "set" values')
    if len(parts) == 1 and parts[0] in PLAN_TOP:
        plan[parts[0]] = value
    elif len(parts) == 2 and parts[0] == 'theme' and parts[1] in THEME:
        plan.setdefault('theme', {})[parts[1]] = value
    elif len(parts) == 3 and parts[0] == 'chapters' and parts[2] in PLAN_CHAPTER:
        _chapter(plan, parts[1])[parts[2]] = value
    elif len(parts) == 5 and parts[0] == 'chapters' and parts[2] == 'demonstrations' and parts[4] in ('watch', 'proves'):
        demos = _chapter(plan, parts[1]).get('demonstrations') or []
        demo = next((d for d in demos if d.get('id') == parts[3]), None)
        if demo is None:
            raise ValueError(f'no demonstration "{parts[3]}" in {parts[1]}')
        demo[parts[4]] = value
    else:
        raise ValueError(f'unknown plan address "{op.get("path")}"')


def _apply_script(script, op):
    parts = str(op.get('path', '')).split('.')
    kind, value = op.get('op'), op.get('value')
    if parts[0] == 'points' and len(parts) == 3 and parts[2] == 'narration' and kind == 'set':
        _point(script, parts[1])[1]['narration'] = value
    elif parts[0] == 'slides' and len(parts) == 2 and kind == 'set':
        sc, _ = _point(script, parts[1])
        slides = sc.get('slides') or []
        index = next((i for i, s in enumerate(slides) if s.get('point') == parts[1]), None)
        if index is None:
            raise ValueError(f'no slide for "{parts[1]}"')
        slides[index] = {**(value or {}), 'point': parts[1]}
    elif parts[0] == 'cues' and len(parts) in (2, 3):
        cues = _chapter(script, parts[1]).setdefault('cues', [])
        if kind == 'add' and len(parts) == 2:
            cues.append(dict(value or {}))
            return
        index = next((i for i, c in enumerate(cues) if c.get('id') == (parts[2] if len(parts) == 3 else None)), None)
        if index is None:
            raise ValueError(f'no cue "{op.get("path")}"')
        if kind == 'remove':
            cues.pop(index)
        elif kind == 'set':
            cues[index] = dict(value or {})
        else:
            raise ValueError(f'"{kind}" is not allowed on a cue address')
    else:
        raise ValueError(f'unknown script address or operation: {kind} {op.get("path")}')


def apply(kind, doc, ops):
    """A patched copy; raises ValueError naming the first bad operation."""
    if not isinstance(ops, list) or not ops:
        raise ValueError('Return a non-empty "ops" list')
    out = copy.deepcopy(doc)
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError('each op is an object')
        (_apply_plan if kind == 'plan' else _apply_script)(out, op)
    if kind == 'script':
        number_cues(out)
    return out


def repair(model, name, kind, doc, findings, context, check, *, thinking=3000, max_tokens=8000):
    """Ask for a patch that fixes `findings`; `check(patched)` raises ValueError on code-check failures (the
    model gets them back and tries again). Returns (patched document, notes)."""
    result = {}

    def validate(reply):
        patched = apply(kind, doc, reply.get('ops'))
        check(patched)
        result['doc'] = patched

    reply = model.call(name, (
        f'Repair this lesson {kind} so these review findings are fixed. ' + GUIDE[kind] + RULES +
        '\nFINDINGS (criteria scored below the required minimum):\n' + json.dumps(findings, ensure_ascii=False) +
        '\n' + context + f'\nCURRENT {kind.upper()} (JSON):\n' + json.dumps(doc, ensure_ascii=False)),
        thinking=thinking, max_tokens=max_tokens, attempts=3, validate=validate)
    if 'doc' not in result:   # served from the call cache: apply the saved reply again
        result['doc'] = apply(kind, doc, reply.get('ops'))
    return result['doc'], reply.get('notes') or []
