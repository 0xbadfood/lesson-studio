"""Biology diagrams in films: the ~/biology SVG library (authored geometry, NCERT-referenced, reviewed) drawn to a
figure PNG for one scene.

A figure is {type:'biology', id, stage?, highlight?, labels?}: the library id, a stage of a staged diagram (mitosis,
meiosis, transport, osmosis), one part to light up (the others dim), and at most five part ids to label. Code adds
the class level (L1 Classes 6-8, L2 9-10, L3 11-12) from the film: parts and labels above it are hidden and a
simpler label is used where the sidecar gives one. The SVGs carry no text; labels come from the sidecar and are
placed here in its label gutters, with leader lines to the parts' anchors (docs/renderer-contract.md).
"""
from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

LIBRARY = Path('/home/nitin/biology')
SVG_NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG_NS)
MAX_LABELS = 5
FONT = 21
CROP = (560, 30, 1040, 650)             # the label region and the artwork above the quiet bottom quarter, with a
                                        # margin so a long word in the narrow left gutter is not cut (2026-10-22)
DIM = '0.28'


@lru_cache(maxsize=1)
def entries(root=LIBRARY):
    """id -> {sidecar, svg}: every diagram in the registry."""
    registry = json.loads((Path(root) / 'registry.json').read_text())
    out = {}
    for obj in registry['objects'].values():
        svg = Path(root) / obj['file']
        sidecar = json.loads((Path(root) / obj['sidecar']).read_text())
        out[sidecar['id']] = {'sidecar': sidecar, 'svg': svg}
    return out


def level_for(class_no):
    class_no = int(class_no or 11)
    return 1 if class_no <= 8 else 2 if class_no <= 10 else 3


def _book_chapter(chapter_id):
    book, _, number = str(chapter_id).replace(':', '-').partition('-')
    return book, int(number) if number.isdigit() else None


def label(part, level):
    return part.get('label_by_level', {}).get(str(level)) or part.get('label', '')


def visible(part, level):
    return int(part.get('level', 1)) <= level


def labelable(part, level):
    return visible(part, level) and (int(part.get('label_level', part.get('level', 1))) <= level
                                     or str(level) in part.get('label_by_level', {}))


def candidates(chapter_id, class_no=None):
    """The diagrams the book's chapter cites, as the planner sees them: id, title, parts it may label or highlight
    (at the film's level), and stages."""
    book, number = _book_chapter(chapter_id)
    level = level_for(class_no)
    out = []
    for fid, entry in sorted(entries().items()):
        side = entry['sidecar']
        refs = [r for r in side.get('ncert') or [] if r.get('book') == book and int(r.get('chapter', 0)) == number]
        if not refs:
            continue
        out.append({'id': fid, 'name': side.get('title', fid),
                    'description': '; '.join(f'NCERT Fig. {r["figure"]}' for r in refs if r.get('figure'))
                                   + (f'. {side["notes"][0]}' if side.get('notes') else ''),
                    'parts': {p['id']: label(p, level) for p in side['parts'] if labelable(p, level)
                              and not p.get('stage')},
                    'stages': [{'id': s['id'], 'title': s.get('title', '')} for s in side.get('stages') or []]})
    return out


def _stage(side, spec):
    stages = side.get('stages') or []
    if not stages:
        return None
    want = spec.get('stage')
    return next((s for s in stages if s['id'] == want), None) or next(
        (s for s in stages if s.get('default_visible')), stages[0])


def _parts(side, stage):
    """The parts that can be shown: whole-asset parts and those of the chosen stage, by semantic id too."""
    by_id = {p['id']: p for p in side['parts']}
    out = {k: v for k, v in by_id.items() if not v.get('stage') or (stage and v.get('stage') == stage['id'])}
    if stage:
        for semantic, concrete in (stage.get('part_map') or {}).items():
            if concrete in by_id:
                out.setdefault(semantic, by_id[concrete])
    return out


def figure_errors(spec, level=3):
    entry = entries().get(spec.get('id'))
    if not entry:
        return [f'biology id "{spec.get("id")}" is not in the library (use one from figure_options.library)']
    side = entry['sidecar']
    errors = []
    stages = {s['id'] for s in side.get('stages') or []}
    if spec.get('stage') and spec['stage'] not in stages:
        errors.append(f'stage must be one of {sorted(stages)}' if stages else f'{spec["id"]} has no stages')
    stage = _stage(side, spec)
    parts = _parts(side, stage)
    if spec.get('highlight') and (spec['highlight'] not in parts or not visible(parts[spec['highlight']], level)):
        errors.append(f'highlight "{spec["highlight"]}" is not a part of {spec["id"]} at this class level')
    labels = spec.get('labels') or []
    if not isinstance(labels, list) or len(labels) > MAX_LABELS:
        errors.append(f'labels: a list of at most {MAX_LABELS} part ids')
    else:
        bad = [x for x in labels if x not in parts or not labelable(parts[x], level)]
        if bad:
            errors.append(f'labels {bad} are not labelled parts of {spec["id"]} at this class level')
    return errors


def _resolve_colours(text, theme):
    """cairosvg has no CSS custom properties: put the theme's colour where each var(--x, var(--bio-y)) stands."""
    def value(match):
        names = re.findall(r'--([\w-]+)', match.group(0))
        for name in reversed(names):
            if name in theme:
                return theme[name]
        return '#888888'
    return re.sub(r'var\(--[\w-]+(?:\s*,\s*var\(--[\w-]+\))?\)', value, text)


def _theme(svg_text, light=False):
    block = re.search(r'<style>(.*?)</style>', svg_text, re.S).group(1)
    rules = re.findall(r'([^{}]+)\{([^}]*)\}', block)
    chosen = {}
    for selector, body in rules:
        is_light = 'light' in selector
        if is_light == light or (not chosen and not is_light):
            chosen.update(dict(re.findall(r'--([\w-]+)\s*:\s*([^;]+)', body)))
    return chosen


def _wrap(words, width):
    per_line = max(6, int(width / (FONT * .56)))
    lines, line = [], ''
    pieces = []
    for word in words.split():                          # "Atrio-ventricular" breaks after its hyphen
        while len(word) > per_line and '-' in word[:-1]:
            cut = word.index('-') + 1
            pieces.append(word[:cut])
            word = word[cut:]
        pieces.append(word)
    for word in pieces:
        if line and len(line) + 1 + len(word) > per_line:
            lines.append(line)
            line = word
        else:
            line = f'{line} {word}'.strip()
    return lines + [line] if line else lines


def _place(items, top, bottom, gap=10):
    """Boxes in anchor order, pushed apart downwards, then back up if they run past the bottom."""
    items.sort(key=lambda i: i['anchor'][1])
    y = top
    for item in items:
        item['y'] = max(y, item['anchor'][1] - item['h'] / 2)
        y = item['y'] + item['h'] + gap
    over = y - gap - bottom
    if over > 0:                                            # too low: lift the column, never above the top
        for item in items:
            item['y'] = max(top, item['y'] - over)
    return items


def draw(spec, level=3, light=False):
    entry = entries()[spec['id']]
    side = entry['sidecar']
    raw = entry['svg'].read_text()
    theme = _theme(raw, light)
    root = ET.fromstring(raw)
    stage = _stage(side, spec)
    parts = _parts(side, stage)
    by_svg_id = {el.get('id'): el for el in root.iter() if el.get('id')}
    parent = {child: el for el in root.iter() for child in el}
    for s in side.get('stages') or []:                          # one stage shows
        if s.get('group') in by_svg_id:
            by_svg_id[s['group']].set('display', 'inline' if stage and s['id'] == stage['id'] else 'none')
    for p in side['parts']:                                     # the film's class level
        if not visible(p, level) and p['id'] in by_svg_id:
            by_svg_id[p['id']].set('display', 'none')
    lit = parts.get(spec.get('highlight') or '')
    if lit and lit['id'] in by_svg_id:
        target = by_svg_id[lit['id']]
        chain = [target]
        while chain[-1] in parent:
            chain.append(parent[chain[-1]])
        for node in chain[1:]:                                  # dim what is beside the lit part's line
            for child in node:
                if child not in chain and str(child.get('id', '')).startswith('part-'):
                    child.set('opacity', DIM)
        for el in target.iter():
            if el.get('stroke') not in (None, 'none'):
                el.set('stroke', theme.get('bio-highlight', '#f3b85e'))
    body = _resolve_colours(ET.tostring(root, encoding='unicode'), theme)
    body = re.sub(r'<style>.*?</style>', '', body, flags=re.S)
    body = re.sub(r'^<svg[^>]*>|</svg>\s*$', '', body.strip())
    ink, muted = theme.get('bio-label', '#f7f3e9'), theme.get('bio-muted', '#82a5a7')
    overlay = []
    gutters = side['layout']['label_gutters']
    art = side['layout']['artwork_region']
    sides = {'left': [], 'right': []}
    for pid in (spec.get('labels') or [])[:MAX_LABELS]:
        p = parts[pid]
        where = p.get('label_side', 'auto')
        if where not in sides:
            where = 'left' if p['anchor'][0] < art[0] + art[2] / 2 else 'right'
        gx, gy, gw, gh = gutters[where]
        lines = _wrap(label(p, level), gw - 6)
        sides[where].append({'anchor': p['anchor'], 'lines': lines, 'h': len(lines) * FONT * 1.2,
                             'lit': lit is p})
    for where, items in sides.items():
        gx, gy, gw, gh = gutters[where]
        for item in _place(items, gy, gy + gh):
            ax, ay = item['anchor']
            mid = item['y'] + item['h'] / 2
            edge = gx + gw if where == 'left' else gx
            colour = theme.get('bio-highlight', '#f3b85e') if item['lit'] else ink
            overlay.append(f"<path d='M {edge + (4 if where == 'left' else -4):.1f} {mid:.1f} L {ax:.1f} {ay:.1f}' "
                           f"stroke='{muted}' stroke-width='2' fill='none'/>"
                           f"<circle cx='{ax:.1f}' cy='{ay:.1f}' r='5' fill='{colour}'/>")
            anchor, x = ('end', gx + gw) if where == 'left' else ('start', gx)
            for n, line in enumerate(item['lines']):
                overlay.append(f"<text x='{x:.1f}' y='{item['y'] + FONT * (1 + 1.2 * n) - 4:.1f}' "
                               f"font-family='DejaVu Sans' font-size='{FONT}' fill='{colour}' "
                               f"text-anchor='{anchor}'>{_escape(line)}</text>")
    x, y, w, h = CROP
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{x} {y} {w} {h}' width='{w}' height='{h}'>"
            + body + ''.join(overlay) + '</svg>')


def _escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def png(spec, path, level=3, width=1824):
    import cairosvg
    cairosvg.svg2png(bytestring=draw(spec, level).encode(), write_to=str(path), output_width=width)
