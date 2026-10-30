"""What a chapter's PDF holds besides its teaching text, extracted once so the pipeline never reads the PDF again.

1. answers: NCERT prints the answers to end-of-chapter questions in one PDF per book (<book>an.pdf, downloaded to
   ncert-banks/answers). A vision model reads each page into items (chapter, exercise set, question number, answer);
   code matches each item to the digest's exercise block by its printed label. Sub-parts stay in one answer string.
2. figures: every figure block of a digest is cut out of its page as a PNG. The vision model gives a box (0-1000 on
   both axes); code widens it to the PDF's own drawing objects and labels it cuts through, so a box that clips a label
   still yields the whole drawing. A figure the model cannot find is recorded as missing, not guessed.
3. svgs: the same box cut from the page's own vector drawing (pdftocairo), so a figure is the book's exact SVG, with
   everything outside it pruned. Photographs and scans come out as 'raster' (left for vtracer).

Results sit beside each digest (answers.json, figures.json, figures/<ref>.png) and in one index,
textbook-digest/extras.sqlite3, for lookups by chapter and the book's own label (Exercise 5.23, Fig. 5.10).
digest.json is not modified: a rebuilt digest keeps them, and a chapter re-run repeats only what changed (every
model call is cached).

  .venv/bin/python kb_research/book_extras.py answers [books...]
  .venv/bin/python kb_research/book_extras.py figures [chapters...] [--min-class 9]
  .venv/bin/python kb_research/book_extras.py svgs [chapters...]      (SVGs for figures already cut)
  .venv/bin/python kb_research/book_extras.py index
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import digest  # noqa: E402

OUT = digest.OUT
ANSWERS = HERE.parent / 'ncert-banks' / 'answers'
INDEX = OUT / 'extras.sqlite3'
SPARK = 'http://127.0.0.1:8001/v1'
FIG_DPI = 200


# ------------------------------------------------------------------ shared
def chapters(min_class=9, books=None):
    out = []
    for path in sorted(OUT.glob('*/digest.json')):
        d = json.loads(path.read_text())
        s = d['source']
        if s['class'] >= min_class and (not books or s['id'].split('-')[0] in books):
            out.append((path.parent, d))
    return out


def page_text(pdf, page):
    return subprocess.run(['pdftotext', '-layout', '-f', str(page), '-l', str(page), str(pdf), '-'],
                          capture_output=True, text=True).stdout


def page_count(pdf):
    info = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True).stdout
    return int(re.search(r'Pages:\s+(\d+)', info).group(1))


# ------------------------------------------------------------------ answers
ANSWER_SCHEMA = ('{"items": [{"chapter": int (the chapter or unit number the answer belongs to, from the nearest '
                 '"Chapter N" / "Unit N" heading or from the question number itself), "set": str or null (the '
                 'exercise heading the answer sits under, e.g. "1.1" for EXERCISE 1.1, "misc" for a Miscellaneous '
                 'Exercise; null when the page has no exercise headings), "number": str (the question number exactly '
                 'as printed, e.g. "1.17" or "3"), "answer": str (the whole answer, every sub-part, as printed; '
                 'powers written with ^, e.g. 1.5 × 10^4, never LaTeX)}]}')


def answer_errors(result, text):
    items = result.get('items')
    if not isinstance(items, list):
        return ['"items" must be a list']
    errors = []
    for n, item in enumerate(items, 1):
        if not str(item.get('answer', '')).strip():
            errors.append(f'item {n}: the answer is empty')
        number = str(item.get('number', '')).strip()
        first = re.split(r'\s*(?:,|and|&)\s*', number)[0]
        if not first or not re.search(rf'(?<![\d.]){re.escape(first)}(?![\d])', text):
            errors.append(f'item {n}: question number "{number}" is not on this page')
        if not isinstance(item.get('chapter'), int):
            errors.append(f'item {n}: chapter must be a number')
    return errors


def read_answers(model, book):
    pdf = ANSWERS / f'{book}an.pdf'
    items = []
    previous = None
    for page in range(1, page_count(pdf) + 1):
        text = page_text(pdf, page)
        image = digest.render(str(pdf), page, ANSWERS / 'pages' / book)
        prompt = (f'The image is page {page} of the Answers section of the NCERT book {book}. List every answer on '
                  'the page, in reading order (left column, then right). '
                  + (f'The previous page ended in chapter {previous["chapter"]}'
                     + (f', exercise {previous["set"]}' if previous.get('set') else '') + '. ' if previous else '')
                  + f'Return JSON: {ANSWER_SCHEMA}\nPAGE TEXT (from the PDF; superscripts are lost, so read powers '
                  f'from the image):\n{text}')
        result = model.call(f'answers-{book}-{page:02d}', prompt, images=[image], thinking=0, max_tokens=12000,
                            attempts=3, validate=lambda r: digest.kb.raise_if(answer_errors(r, text)))
        for item in result['items']:
            items.append({**item, 'page': page})
        if result['items']:
            previous = result['items'][-1]
    return items


def answer_key(ref, chapter=None):
    """The digest's printed label as (chapter, set, question): Exercise 5.23 -> (5, None, 23);
    Exercise 7.1 Q4 -> (7, '1', 4); Miscellaneous Exercise on Chapter 2 Q3 -> (2, 'misc', 3); a bare Exercise 4 (the
    end-of-chapter questions of books that number them 1, 2, 3 ... per chapter) -> (chapter, 'end', 4)."""
    ref = str(ref or '')
    m = re.match(r'(?i)(?:Exercise|Question)s?\s*Q?(\d+)$', ref)
    if m and chapter is not None:
        return chapter, 'end', int(m.group(1))
    m = re.match(r'(?i)Miscellaneous Exercise on Chapter (\d+)\s*Q(\d+)$', ref)
    if m:
        return int(m.group(1)), 'misc', int(m.group(2))
    m = re.match(r'(?i)Exercise (\d+)\.(\d+)\s*Q(\d+)$', ref)
    if m:
        return int(m.group(1)), m.group(2), int(m.group(3))
    m = re.match(r'(?i)Exercise (\d+)\.(\d+)$', ref)
    if m:
        return int(m.group(1)), None, int(m.group(2))
    return None


def item_key(item):
    number = str(item['number']).strip().rstrip('.')
    chapter = item['chapter']
    m = re.match(r'(\d+)\.(\d+)$', number)
    if m and not item.get('set'):
        return int(m.group(1)), None, int(m.group(2))
    if not number.isdigit():
        return None
    kind = item.get('set')
    if kind and str(kind).lower().startswith('misc'):
        return chapter, 'misc', int(number)
    if kind:
        m = re.match(r'(\d+)\.(\d+)', str(kind))
        return (int(m.group(1)), m.group(2), int(number)) if m else None
    return chapter, '*', int(number)


def match_answers(book, items):
    """Attach each answer item to the exercise blocks of the book's digests with the same printed label."""
    blocks = collections.defaultdict(list)
    for folder, d in chapters(0, {book}):
        for b in d['blocks']:
            if b['type'] == 'exercise':
                for ref in b.get('ref') or []:
                    key = answer_key(ref, d['source'].get('chapter'))
                    if key:
                        blocks[key].append((folder, b['id'], ref))
    found, unmatched = collections.defaultdict(dict), []
    for item in items:
        targets = []
        for number in re.split(r'\s*(?:,|and|&)\s*', str(item['number'])):   # "7.10 and 7.11": one answer, two
            key = item_key({**item, 'number': number})                          # questions
            if key and key[1] == '*':      # no exercise headings in the answers: the question number within the chapter,
                end = (key[0], 'end', key[2])                          # the end-of-chapter questions first
                options = {k for k in blocks if k[0] == key[0] and k[2] == key[2]}
                targets += blocks[end] if end in blocks else blocks[options.pop()] if len(options) == 1 else []
            elif key:
                targets += blocks.get(key, [])
        if not targets:
            unmatched.append(item)
        for folder, block_id, ref in targets:
            found[folder][block_id] = {'ref': ref, 'answer': item['answer'].strip(),
                                       'source': {'pdf': f'ncert-banks/answers/{book}an.pdf', 'page': item['page']}}
    for folder, answers in found.items():
        (folder / 'answers.json').write_text(json.dumps(answers, indent=1, ensure_ascii=False))
    return sum(len(a) for a in found.values()), unmatched


def run_answers(books, endpoint, log=print):
    model = digest.chat(endpoint, ANSWERS, 'answers', 1800)
    for book in books:
        if not (ANSWERS / f'{book}an.pdf').exists():
            log(f'{book}: no answers PDF')
            continue
        started = time.monotonic()
        items = read_answers(model, book)
        matched, unmatched = match_answers(book, items)
        log(f'{book}: {len(items)} answers read, {matched} exercise blocks answered, {len(unmatched)} unmatched '
            f'({time.monotonic() - started:.0f} s)')
        (ANSWERS / f'{book}-unmatched.json').write_text(json.dumps(unmatched, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ figures
def fig_ref(block):
    return next((r for r in block.get('ref') or [] if re.match(r'(?i)fig', r)), None)


def slug(ref):
    return re.sub(r'[^\w.]+', '_', ref).strip('_')


def furniture(pdf):
    """Objects repeated on many pages (header strips, page frames): never part of a figure."""
    seen = collections.Counter()
    for p in pdf.pages:
        for o in p.images + p.rects:
            seen[tuple(round(o[k]) for k in ('x0', 'top', 'x1', 'bottom'))] += 1
    return {k for k, n in seen.items() if n >= max(3, len(pdf.pages) // 3)}


def _touches(o, b, m=2):
    return o[0] < b[2] + m and o[2] > b[0] - m and o[1] < b[3] + m and o[3] > b[1] - m


def _inside(o, b):
    return o[0] >= b[0] and o[2] <= b[2] and o[1] >= b[1] and o[3] <= b[3]


def text_lines(page):
    """Body text lines (long) and captions; a figure's labels are short lines."""
    lines = [(l['x0'], l['top'], l['x1'], l['bottom'], l['text']) for l in page.extract_text_lines()]
    body = [l for l in lines if l[2] - l[0] > 120]
    captions = [l for l in lines if re.match(r'\s*Fig(ure)?\.?\s*\d', l[4])]
    return body, captions


def gradient_strips(page, least=10):
    """(x0, x1) of thin rects stacked by the dozen: a box shaded as a gradient (jesc1-12 p.7: the QUESTIONS box's
    hundreds of 1-pt strips each touched Fig. 12.11's box and pulled body text into its crop, 2026-10-29)."""
    spans = collections.Counter((round(o['x0']), round(o['x1'])) for o in page.rects if o['bottom'] - o['top'] < 1.5)
    return {span for span, n in spans.items() if n >= least}


PAD = 4  # points around a figure's box when it is cut


def prose(page, words, least_width=0):
    """Lines of running text: 4 or more ordinary lowercase words, no wide gap and at least least_width wide (a figure's
    labels are spread out, numbers or names: a chart's months, an axis's numbers, a table's rows; and two columns'
    text can read as one line: leph2-06 Fig. 14.12's "p n bias)..."), and a paragraph's short last line just under
    one, at its left margin (keph1-06 Fig. 6.21(a) was cut with "magnetic field." on top, 2026-10-30)."""
    out = []
    for l in page.extract_text_lines():
        h = l['bottom'] - l['top']
        ws = sorted((w for w in words if w['top'] >= l['top'] - 1 and w['bottom'] <= l['bottom'] + 1
                     and w['x0'] >= l['x0'] - 1 and w['x1'] <= l['x1'] + 1), key=lambda w: w['x0'])
        gaps = [b['x0'] - a['x1'] for a, b in zip(ws, ws[1:])]
        plain = sum(bool(re.fullmatch(r"[a-z]{3,}[,.;:]?", w.get('text', ''))) for w in ws)
        if plain >= 4 and max(gaps, default=0) < 2 * h and l['x1'] - l['x0'] >= least_width:
            out.append((l['x0'], l['top'], l['x1'], l['bottom']))
        elif out and abs(out[-1][0] - l['x0']) < 3 and 0 <= l['top'] - out[-1][3] < .8 * h and plain < 4:
            out.append((l['x0'], l['top'], l['x1'], l['bottom']))
    return out


def widen(page, box, skip):
    """Grow the model's box (PDF points) to the drawing objects and the short label lines it cuts through, never to
    body text, captions or text boxes; then trim a caption caught at its bottom."""
    body, captions = text_lines(page)
    words = page.extract_words()
    shading = gradient_strips(page)
    b = list(box)
    for _ in range(2):
        grown = list(b)
        for o in page.curves + page.lines + page.rects + page.images:
            r = (o['x0'], o['top'], o['x1'], o['bottom'])
            if tuple(round(v) for v in r) in skip or r[2] - r[0] > .8 * page.width or not _touches(r, b):
                continue
            if (round(r[0]), round(r[2])) in shading and r[3] - r[1] < 1.5:
                continue                            # a strip of a shaded band (a box's gradient), not a drawing
            if sum(_inside((w['x0'], w['top'], w['x1'], w['bottom']), r) for w in words) >= 5:
                continue                            # a shaded box of text (an Example), not part of a drawing
            if (r[2] - r[0]) * (r[3] - r[1]) < 2 * max(1, (b[2] - b[0]) * (b[3] - b[1])):
                grown = [min(grown[0], r[0]), min(grown[1], r[1]), max(grown[2], r[2]), max(grown[3], r[3])]
        b = grown
    for l in page.extract_text_lines():                 # labels the box cuts through: short lines only
        r = (l['x0'], l['top'], l['x1'], l['bottom'])
        if r[2] - r[0] <= 120 and _touches(r, box, 0) and not _inside(r, box) and \
                not re.match(r'\s*Fig(ure)?\.?\s*\d', l['text']):
            b = [min(b[0], r[0]), min(b[1], r[1]), max(b[2], r[2]), max(b[3], r[3])]
    for c in captions:                                  # a caption caught at the bottom is cut off
        if _touches(c, b, 0) and c[1] > b[1] + .5 * (b[3] - b[1]):
            b[3] = min(b[3], c[1] - 1)
    for l in prose(page, words, .8 * (b[2] - b[0])):    # prose at the box's top or bottom edge is cut off (half of it
        inside = max(0, min(l[2], b[2]) - max(l[0], b[0]))   # in the box's width: kemh1-09 Fig. 9.18 lost its x-axis
        if inside >= .5 * (l[2] - l[0]) and l[1] < b[3] and l[3] > b[1]:   # to the next column's text)
            mid = (l[1] + l[3]) / 2
            if mid < b[1] + .2 * (b[3] - b[1]):                     # clear of the crop's padding too
                b[1] = max(b[1], l[3] + PAD + 1)
            elif mid > b[3] - .2 * (b[3] - b[1]):
                b[3] = min(b[3], l[1] - PAD - 1)
    return b


SVG_NS = 'http://www.w3.org/2000/svg'
XLINK = '{http://www.w3.org/1999/xlink}href'


def page_svg(pdf_path, page, folder):
    """The page as SVG (poppler's cairo backend), cached beside the page images, and the offset of its crop box."""
    path = folder / f'p-{page:02d}.svg'
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run(['pdftocairo', '-svg', '-f', str(page), '-l', str(page), str(pdf_path), str(path)],
                       check=True, capture_output=True)
    info = subprocess.run(['pdfinfo', '-f', str(page), '-l', str(page), '-box', str(pdf_path)],
                          capture_output=True, text=True).stdout
    media = [float(v) for v in re.search(rf'Page\s+{page} MediaBox:\s+(.*)', info).group(1).split()]
    crop = [float(v) for v in re.search(rf'Page\s+{page} CropBox:\s+(.*)', info).group(1).split()]
    return path, (crop[0] - media[0], media[3] - crop[3])          # pdfplumber measures from the media box's top left


def figure_svg(pdf_path, page, box, folder, target):
    """The figure exactly as the book drew it: the page's own vector drawing, cut to the box (PDF points), with every
    element outside the box removed, full-page images (watermarks, backgrounds) dropped and unused glyphs pruned.
    Returns 'vector', 'raster' (only bitmaps inside the box: a photograph or a scan, for vtracer later) or None
    (nothing drawn there)."""
    import xml.etree.ElementTree as ET
    import svgelements as se
    ET.register_namespace('', SVG_NS)
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
    path, (dx, dy) = page_svg(pdf_path, page, folder)
    root = ET.parse(path).getroot()
    page_w, page_h = (float(v) for v in root.get('viewBox').split()[2:])
    x0, y0, x1, y1 = box[0] - dx, box[1] - dy, box[2] - dx, box[3] - dy
    q = lambda tag: f'{{{SVG_NS}}}{tag}'  # noqa: E731
    defs = {e.get('id'): e for e in root.iter() if e.get('id')}
    parent = {c: p for p in root.iter() for c in p}

    def local_box(e):
        tag = e.tag.split('}')[1]
        if tag == 'path' and (e.get('d') or '').strip():
            return se.Path(e.get('d')).bbox()
        if tag == 'rect':
            x, y = float(e.get('x', 0)), float(e.get('y', 0))
            return x, y, x + float(e.get('width', 0)), y + float(e.get('height', 0))
        if tag == 'image':
            x, y = float(e.get('x', 0)), float(e.get('y', 0))
            return x, y, x + float(e.get('width', 0)), y + float(e.get('height', 0))
        if tag == 'use':
            ref = defs.get((e.get(XLINK) or '').lstrip('#'))
            inner = [b for b in (local_box(c) for c in ref.iter() if c is not ref) if b] if ref is not None else []
            if ref is not None and ref.tag.split('}')[1] in ('image', 'path', 'rect'):
                inner = [b for b in [local_box(ref)] if b]
            if not inner:
                return None
            x, y = float(e.get('x', 0)), float(e.get('y', 0))
            return (min(b[0] for b in inner) + x, min(b[1] for b in inner) + y,
                    max(b[2] for b in inner) + x, max(b[3] for b in inner) + y)
        return None

    def matrix(e):
        m = se.Matrix()
        chain = []
        while e is not None and e is not root:
            chain.append(e)
            e = parent.get(e)
        for node in reversed(chain):
            if node.get('transform'):
                m = se.Matrix(node.get('transform')) * m
        return m

    drawn = [e for e in root.iter() if e.tag in (q('path'), q('use'), q('image'), q('rect'))
             and not any(a.tag in (q('defs'), q('clipPath'), q('mask'), q('symbol')) for a in _ancestors(e, parent))]
    kept = images = 0
    for e in drawn:
        b = local_box(e)
        if b is None:                              # draws nothing measurable (an empty glyph: a space)
            parent[e].remove(e)
            continue
        m = matrix(e)
        corners = [m.point_in_matrix_space((x, y)) for x in (b[0], b[2]) for y in (b[1], b[3])]
        bx0, by0 = min(c[0] for c in corners), min(c[1] for c in corners)
        bx1, by1 = max(c[0] for c in corners), max(c[1] for c in corners)
        whole_page = (bx1 - bx0) > .8 * page_w and (by1 - by0) > .8 * page_h
        if whole_page or bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            parent[e].remove(e)
        else:
            kept += 1
            images += e.tag == q('image') or (e.tag == q('use') and (e.get(XLINK) or '').startswith('#source'))

    def refs(e):
        out = {(e.get(XLINK) or '').lstrip('#')} if e.get(XLINK) else set()
        return out | {u for a in ('clip-path', 'mask', 'filter') for u in re.findall(r'url\(#([^)]+)\)', e.get(a) or '')}

    def drawing(e):
        return any(x.tag in (q('path'), q('use'), q('image'), q('rect')) for x in e.iter())

    pruned = True                                  # groups left empty (a watermark's masked wrapper) go too
    while pruned:
        pruned = False
        for e in list(root.iter(q('g'))):
            if e in parent and not drawing(e) and not any(a.tag == q('defs') for a in _ancestors(e, parent)):
                parent[e].remove(e)
                pruned = True
        parent = {c: p for p in root.iter() for c in p}
    defs_nodes = [d for d in root.iter(q('defs'))]
    in_defs = {x for d in defs_nodes for x in d.iter()}
    used = set().union(*(refs(e) for e in root.iter() if e not in in_defs))
    while True:                                    # what the used definitions themselves use (mask -> image)
        more = set().union(set(), *(refs(x) for i in used if i in defs for x in defs[i].iter())) - used
        if not more:
            break
        used |= more
    parent = {c: p for p in root.iter() for c in p}
    for e in [x for d in defs_nodes for x in d.iter() if x is not d]:     # unused definitions at any depth (glyphs
        if e.get('id') and e.get('id') not in used and e in parent:      # sit inside an unnamed group)
            parent[e].remove(e)
    for d in defs_nodes:
        for g in [x for x in d.iter(q('g')) if not x.get('id') and not len(x)]:
            parent = {c: p for p in root.iter() for c in p}
            if g in parent:
                parent[g].remove(g)
    root.set('viewBox', f'{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}')
    root.set('width', f'{x1 - x0:.2f}')
    root.set('height', f'{y1 - y0:.2f}')
    if not kept:
        return None
    ET.ElementTree(root).write(target, encoding='utf-8', xml_declaration=True)
    return 'raster' if images == kept else 'vector'


def _ancestors(e, parent):
    while e in parent:
        e = parent[e]
        yield e


def text_share(page, b):
    """How much of the box is body text: a high share means the box missed the drawing."""
    body, _ = text_lines(page)
    area = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    covered = sum(max(0, min(l[2], b[2]) - max(l[0], b[0])) * max(0, min(l[3], b[3]) - max(l[1], b[1]))
                  for l in body)
    return covered / area


def find_figure(model, pdf_path, page, ref, caption, folder, hint=''):
    # The model's boxes came back sometimes in 0-1000 units and sometimes in pixels: on a 1000 x 1000 picture (the
    # page scaled to 1000 high, white to its right) the two agree, and both axes share one scale.
    from PIL import Image
    square = folder / 'pages' / f'p-{page:02d}.square.png'
    if not square.exists():
        rendered = Image.open(digest.render(pdf_path, page, folder / 'pages')).convert('RGB')
        rendered.thumbnail((1000, 1000))
        canvas = Image.new('RGB', (1000, 1000), 'white')
        canvas.paste(rendered, (0, 0))
        canvas.save(square)
    image = square
    prompt = (f'This is a page of an NCERT textbook. Find the figure labelled "{ref}"'
              + (f' (caption: "{caption[:160]}")' if caption else '') +
              ': the drawing, graph or photograph itself, with all its parts (a), (b)... and their labels, but not '
              'its caption and not any example box or body text. Return JSON {"found": true|false, "box": [x0, y0, '
              'x1, y1]} in pixels of this 1000 x 1000 image (0,0 top left), tight around the figure. found is false '
              'if this page does not show it.' + (f' {hint}' if hint else ''))

    def errors(r):
        if not r.get('found'):
            return []
        box = r.get('box')
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)
                and 0 <= box[0] < box[2] <= 1000 and 0 <= box[1] < box[3] <= 1000):
            return ['box must be [x0, y0, x1, y1] within 0-1000 with x0 < x1 and y0 < y1']
        return []
    return model.call(f'figure-{page:02d}-{slug(ref)}{"-retry" if hint else ""}', prompt, images=[image], thinking=0, max_tokens=600,
                      attempts=3, validate=lambda r: digest.kb.raise_if(errors(r)))


def panels_named(block):
    """The part letters a figure's own words name, (a) to (d): a crop must hold every one of them. NCERT draws the
    letters as shapes, so the PDF's text can't confirm them; a look at the crop does."""
    if re.search(r'\([a-h]\)\s*$', fig_ref(block) or ''):
        return []                            # one part filed on its own (Fig. 9.7 (a)): its crop is that part
    words = ' '.join(str(block.get(k) or '') for k in ('caption', 'title', 'text', 'shows'))
    letters = sorted(set(re.findall(r'\(([a-h])\)', words)))
    return letters if len(letters) >= 2 else []


def panels_missing(model, folder, entry, letters):
    """The named parts the crop does not show (Fig. 2.10 of keph1-02 was cut with (c) and (d) only, and a film said
    four graphs over two, 2026-10-26)."""
    def errors(r):
        seen = r.get('visible')
        return [] if isinstance(seen, list) and all(isinstance(x, str) for x in seen) else ['visible must be a list of letters']
    r = model.call(f'panels-{slug(entry["ref"])}', (
        f'This is a crop of NCERT figure {entry["ref"]}, which has parts {", ".join(f"({x})" for x in letters)}. '
        'Which of these part labels can you see in this picture, each with its own drawing? Return JSON '
        '{"visible": ["a", ...]} with the letters only.'), images=[folder / entry['image']], thinking=0, max_tokens=300,
        attempts=3, validate=lambda r: digest.kb.raise_if(errors(r)))
    seen = {str(x).strip('() ').lower() for x in r.get('visible') or []}
    return [x for x in letters if x not in seen]


def cut_figure(model, pdf, src, folder, block, entry, skip, hint=''):
    """Find the figure on its pages and cut it (PNG, and SVG from the PDF's drawing); True when cut."""
    for page in block.get('pages') or []:
        try:
            r = find_figure(model, src, page, entry['ref'], entry['caption'], folder, hint)
        except Exception as exc:  # noqa: BLE001 - a failed figure is recorded, the chapter goes on
            entry['error'] = str(exc)[:200]
            continue
        if not r.get('found'):
            continue
        p = pdf.pages[page - 1]
        scale = max(p.width, p.height) / 1000           # the square picture: one scale, both axes
        box = widen(p, tuple(v * scale for v in r['box']), skip)
        pad, k = PAD, FIG_DPI / 72
        target = folder / 'figures' / f'{slug(entry["ref"])}.png'
        target.parent.mkdir(exist_ok=True)
        subprocess.run(['pdftoppm', '-r', str(FIG_DPI), '-png', '-singlefile', '-f', str(page), '-l',
                        str(page), '-x', str(int((box[0] - pad) * k)), '-y', str(int((box[1] - pad) * k)),
                        '-W', str(int((box[2] - box[0] + 2 * pad) * k)),
                        '-H', str(int((box[3] - box[1] + 2 * pad) * k)), src, str(target.with_suffix(''))],
                       check=True, capture_output=True)
        share = text_share(p, box)
        entry.update(image=f'figures/{target.name}', page=page, box_pt=[round(v, 1) for v in box],
                     box_model=r['box'], text_share=round(share, 2), suspect=share > .25)
        entry.pop('error', None)
        add_svg(folder, src, entry)
        return True
    return False


def check_panels(model, pdf, src, folder, block, entry, skip, log=print):
    """Every named part in the crop, or one more cut told which parts were left out; still missing, it is suspect
    (a film then leaves it out)."""
    letters = panels_named(block)
    if not letters or not entry.get('image'):
        return
    missing = panels_missing(model, folder, entry, letters)
    if missing:
        hint = (f'It has parts {", ".join(f"({x})" for x in letters)}; a box that held only some of them left out '
                f'{", ".join(f"({x})" for x in missing)}, which may sit beside or above the others: include every part.')
        if cut_figure(model, pdf, src, folder, block, entry, skip, hint):
            missing = panels_missing(model, folder, entry, letters)
    entry['panels_missing'] = missing
    entry['suspect'] = bool(entry.get('suspect')) or bool(missing)
    log(f'{folder.name} {entry["ref"]}: ' + (f'parts {", ".join(missing)} still missing: suspect' if missing else f'all {len(letters)} parts'))


def run_figures(selected, endpoint, log=print):
    import pdfplumber
    for folder, d in selected:
        figures = [b for b in d['blocks'] if b['type'] == 'figure' and fig_ref(b)]
        if not figures:
            continue
        index_path = folder / 'figures.json'
        done = json.loads(index_path.read_text()) if index_path.exists() else {}
        model = digest.chat(endpoint, folder, 'figures', 1800)
        src = d['source']['pdf']
        started, out = time.monotonic(), {}
        with pdfplumber.open(src) as pdf:
            skip = furniture(pdf)
            for b in figures:
                ref = fig_ref(b)
                if ref in out:
                    continue                      # one figure, several blocks (continued across pages)
                if ref in done and (folder / done[ref].get('image', '')).is_file():
                    out[ref] = done[ref]
                    continue
                entry = {'ref': ref, 'block': b['id'], 'caption': b.get('caption') or b.get('title', ''),
                         'image': None, 'page': None}
                if cut_figure(model, pdf, src, folder, b, entry, skip):
                    check_panels(model, pdf, src, folder, b, entry, skip, log)
                out[ref] = entry
        index_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        cut = sum(bool(e['image']) for e in out.values())
        log(f'{folder.name}: {cut}/{len(out)} figures cut ({time.monotonic() - started:.0f} s)')


def add_svg(folder, src, entry):
    """The figure's exact SVG from the PDF's own drawing, beside its PNG (no model: the box is already known)."""
    target = folder / 'figures' / f'{slug(entry["ref"])}.svg'
    try:
        kind = figure_svg(src, entry['page'], entry['box_pt'], folder / 'pages', target)
    except Exception as exc:  # noqa: BLE001 - the PNG stands; the SVG is recorded as failed
        entry.update(svg=None, svg_kind=None, svg_error=str(exc)[:200])
        return
    entry.update(svg=f'figures/{target.name}' if kind else None, svg_kind=kind)
    entry.pop('svg_error', None)


def run_svgs(selected, log=print):
    """SVGs for figures already cut (their boxes are in figures.json)."""
    for folder, d in selected:
        path = folder / 'figures.json'
        if not path.exists():
            continue
        figures, started = json.loads(path.read_text()), time.monotonic()
        for entry in figures.values():
            if entry.get('box_pt') and not (entry.get('svg') and (folder / entry['svg']).is_file()):
                add_svg(folder, d['source']['pdf'], entry)
        path.write_text(json.dumps(figures, indent=1, ensure_ascii=False))
        kinds = collections.Counter(e.get('svg_kind') for e in figures.values() if e.get('box_pt'))
        log(f'{folder.name}: SVG {dict(kinds)} ({time.monotonic() - started:.0f} s)')


def run_panels(selected, endpoint, log=print):
    """Check the figures already cut: each multi-part figure must show all its named parts (re-cut once if not)."""
    import pdfplumber
    for folder, d in selected:
        path = folder / 'figures.json'
        if not path.exists():
            continue
        figures, blocks = json.loads(path.read_text()), {b['id']: b for b in d['blocks']}
        todo = [e for e in figures.values() if e.get('image') and 'panels_missing' not in e
                and panels_named(blocks.get(e['block'], {}))]
        if not todo:
            continue
        model = digest.chat(endpoint, folder, 'figures', 1800)
        with pdfplumber.open(d['source']['pdf']) as pdf:
            skip = furniture(pdf)
            for entry in todo:
                try:
                    check_panels(model, pdf, d['source']['pdf'], folder, blocks[entry['block']], entry, skip, log)
                except Exception as exc:  # noqa: BLE001 - one figure's check failing leaves the rest
                    log(f'{folder.name} {entry["ref"]}: check failed: {str(exc)[:120]}')
                path.write_text(json.dumps(figures, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ index
def build_index():
    INDEX.unlink(missing_ok=True)
    db = sqlite3.connect(INDEX)
    db.executescript('''
        CREATE TABLE answers (chapter TEXT, block TEXT, ref TEXT, answer TEXT, source_pdf TEXT, source_page INT);
        CREATE TABLE figures (chapter TEXT, block TEXT, ref TEXT, caption TEXT, image TEXT, page INT, svg TEXT,
                              svg_kind TEXT, suspect INT, incomplete INT);
        CREATE INDEX answers_ref ON answers (chapter, ref);
        CREATE INDEX figures_ref ON figures (chapter, ref);''')
    counts = collections.Counter()
    for folder in sorted(OUT.iterdir()):
        chapter = folder.name
        if (folder / 'answers.json').exists():
            for block, a in json.loads((folder / 'answers.json').read_text()).items():
                db.execute('INSERT INTO answers VALUES (?,?,?,?,?,?)', (chapter, block, a['ref'], a['answer'],
                                                                       a['source']['pdf'], a['source']['page']))
                counts['answers'] += 1
        if (folder / 'figures.json').exists():
            for ref, f in json.loads((folder / 'figures.json').read_text()).items():
                db.execute('INSERT INTO figures VALUES (?,?,?,?,?,?,?,?,?,?)', (
                    chapter, f['block'], ref, f['caption'], f'{chapter}/{f["image"]}' if f['image'] else None,
                    f['page'], f'{chapter}/{f["svg"]}' if f.get('svg') else None, f.get('svg_kind'),
                    int(bool(f.get('suspect'))), int(bool(f.get('panels_missing')))))
                counts['figures'] += 1
    db.commit()
    return dict(counts)


def lookup(chapter, ref):
    """The answer and figure the book gives for one label in one chapter, from the index: e.g.
    lookup('keph1-05', 'Exercise 5.23') or lookup('keph1-05', 'Fig. 5.10'). Paths are relative to textbook-digest."""
    db = sqlite3.connect(f'file:{INDEX}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    answer = db.execute('SELECT * FROM answers WHERE chapter = ? AND ref = ?', (chapter, ref)).fetchone()
    figure = db.execute('SELECT * FROM figures WHERE chapter = ? AND ref = ?', (chapter, ref)).fetchone()
    return {'answer': dict(answer) if answer else None, 'figure': dict(figure) if figure else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('what', choices=['answers', 'figures', 'svgs', 'panels', 'index'])
    parser.add_argument('names', nargs='*', help='books (answers) or chapter folders like keph1-05 (figures)')
    parser.add_argument('--min-class', type=int, default=9)
    parser.add_argument('--endpoint', default=SPARK)
    args = parser.parse_args(argv)
    log = lambda text: print(time.strftime('%H:%M:%S'), text, flush=True)  # noqa: E731
    if args.what == 'answers':
        books = args.names or sorted(p.name[:-6] for p in ANSWERS.glob('*an.pdf'))
        run_answers(books, args.endpoint, log)
    elif args.what == 'figures':
        selected = [(f, d) for f, d in chapters(args.min_class) if not args.names or f.name in args.names]
        run_figures(selected, args.endpoint, log)
    elif args.what == 'panels':
        selected = [(f, d) for f, d in chapters(args.min_class) if not args.names or f.name in args.names]
        run_panels(selected, args.endpoint, log)
    elif args.what == 'svgs':
        selected = [(f, d) for f, d in chapters(args.min_class) if not args.names or f.name in args.names]
        run_svgs(selected, log)
    log(f'index: {build_index()}')


if __name__ == '__main__':
    main()
