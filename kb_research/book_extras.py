"""What a chapter's PDF holds besides its teaching text, extracted once so the pipeline never reads the PDF again.

1. answers: NCERT prints the answers to end-of-chapter questions in one PDF per book (<book>an.pdf, downloaded to
   ncert-banks/answers). A vision model reads each page into items (chapter, exercise set, question number, answer);
   code matches each item to the digest's exercise block by its printed label. Sub-parts stay in one answer string.
2. figures: every figure block of a digest is cut out of its page as a PNG. The vision model gives a box (0-1000 on
   both axes); code widens it to the PDF's own drawing objects and labels it cuts through, so a box that clips a label
   still yields the whole drawing. A figure the model cannot find is recorded as missing, not guessed.

Results sit beside each digest (answers.json, figures.json, figures/<ref>.png) and in one index,
textbook-digest/extras.sqlite3, for lookups by chapter and the book's own label (Exercise 5.23, Fig. 5.10).
digest.json is not modified: a rebuilt digest keeps them, and a chapter re-run repeats only what changed (every
model call is cached).

  .venv/bin/python kb_research/book_extras.py answers [books...]
  .venv/bin/python kb_research/book_extras.py figures [chapters...] [--min-class 9]
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


def answer_key(ref):
    """The digest's printed label as (chapter, set, question): Exercise 5.23 -> (5, None, 23);
    Exercise 7.1 Q4 -> (7, '1', 4); Miscellaneous Exercise on Chapter 2 Q3 -> (2, 'misc', 3)."""
    ref = str(ref or '')
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
                    key = answer_key(ref)
                    if key:
                        blocks[key].append((folder, b['id'], ref))
    found, unmatched = collections.defaultdict(dict), []
    for item in items:
        targets = []
        for number in re.split(r'\s*(?:,|and|&)\s*', str(item['number'])):   # "7.10 and 7.11": one answer, two
            key = item_key({**item, 'number': number})                          # questions
            if key and key[1] == '*':      # no exercise headings in the answers: the question number within the chapter
                options = {k for k in blocks if k[0] == key[0] and k[2] == key[2]}
                targets += blocks[options.pop()] if len(options) == 1 else []
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


def widen(page, box, skip):
    """Grow the model's box (PDF points) to the drawing objects and the short label lines it cuts through, never to
    body text, captions or text boxes; then trim a caption caught at its bottom."""
    body, captions = text_lines(page)
    words = page.extract_words()
    b = list(box)
    for _ in range(2):
        grown = list(b)
        for o in page.curves + page.lines + page.rects + page.images:
            r = (o['x0'], o['top'], o['x1'], o['bottom'])
            if tuple(round(v) for v in r) in skip or r[2] - r[0] > .8 * page.width or not _touches(r, b):
                continue
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
    return b


def text_share(page, b):
    """How much of the box is body text: a high share means the box missed the drawing."""
    body, _ = text_lines(page)
    area = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    covered = sum(max(0, min(l[2], b[2]) - max(l[0], b[0])) * max(0, min(l[3], b[3]) - max(l[1], b[1]))
                  for l in body)
    return covered / area


def find_figure(model, pdf_path, page, ref, caption, folder):
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
              'if this page does not show it.')

    def errors(r):
        if not r.get('found'):
            return []
        box = r.get('box')
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)
                and 0 <= box[0] < box[2] <= 1000 and 0 <= box[1] < box[3] <= 1000):
            return ['box must be [x0, y0, x1, y1] within 0-1000 with x0 < x1 and y0 < y1']
        return []
    return model.call(f'figure-{page:02d}-{slug(ref)}', prompt, images=[image], thinking=0, max_tokens=600,
                      attempts=3, validate=lambda r: digest.kb.raise_if(errors(r)))


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
                for page in b.get('pages') or []:
                    try:
                        r = find_figure(model, src, page, ref, entry['caption'], folder)
                    except Exception as exc:  # noqa: BLE001 - a failed figure is recorded, the chapter goes on
                        entry['error'] = str(exc)[:200]
                        continue
                    if not r.get('found'):
                        continue
                    p = pdf.pages[page - 1]
                    scale = max(p.width, p.height) / 1000           # the square picture: one scale, both axes
                    box = widen(p, tuple(v * scale for v in r['box']), skip)
                    pad, k = 4, FIG_DPI / 72
                    target = folder / 'figures' / f'{slug(ref)}.png'
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
                    break
                out[ref] = entry
        index_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        cut = sum(bool(e['image']) for e in out.values())
        log(f'{folder.name}: {cut}/{len(out)} figures cut ({time.monotonic() - started:.0f} s)')


# ------------------------------------------------------------------ index
def build_index():
    INDEX.unlink(missing_ok=True)
    db = sqlite3.connect(INDEX)
    db.executescript('''
        CREATE TABLE answers (chapter TEXT, block TEXT, ref TEXT, answer TEXT, source_pdf TEXT, source_page INT);
        CREATE TABLE figures (chapter TEXT, block TEXT, ref TEXT, caption TEXT, image TEXT, page INT);
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
                db.execute('INSERT INTO figures VALUES (?,?,?,?,?,?)', (chapter, f['block'], ref, f['caption'],
                                                                       f'{chapter}/{f["image"]}' if f['image'] else None,
                                                                       f['page']))
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
    parser.add_argument('what', choices=['answers', 'figures', 'index'])
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
    log(f'index: {build_index()}')


if __name__ == '__main__':
    main()
