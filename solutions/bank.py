"""The question bank: JEE Advanced papers with an official answer key (user, 2026-10-23: the studios show only years
whose key we have), as structured questions.

Sources differ by year (SOURCES): a question paper (its pages are what the models see) and a key document (where the
answers come from), which may be the same PDF when the answers are printed on the paper. Pages are read from the PDF's
text layer, or by OCR (tesseract) for scans and garbled fonts. Each subject's part begins with SECTION 1; a keyword
score names the part. Answers come from the key's text ("Answer: B", "Answer Q4: B", "Ans for Q.2: (D)") or its answer
table (2019).

The models never see an answer: where the paper prints them, every answer line is painted out of the page image, and
the masked image is read again by OCR; a page that still shows one is withheld, and its questions with it.

    python -m solutions.bank            # every year in SOURCES -> questions-data/jee-advanced/bank/<year>.json
    python -m solutions.bank 2019 2022  # some years
"""
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'questions-data' / 'jee-advanced'
PAGES = DATA / 'pages'
OCR = DATA / 'ocr'
DPI = 110            # page images the models see
OCR_DPI = 200
SUBJECTS = ['mathematics', 'physics', 'chemistry']
K = 'keys/candidates/'
# year -> paper -> (question paper, key document, how the key is read, pages to OCR: 'paper' | 'key' | 'both' | None)
SOURCES = {
    2016: {p: (f'papers/2016_{p}.pdf', f'papers/2016_{p}.pdf', 'inline', 'both') for p in (1, 2)},
    2017: {1: (K + '2017_P1_revised.pdf', K + '2017_P1_revised.pdf', 'inline', None),
           2: (K + '2017_P2_x.pdf', K + '2017_P2_x.pdf', 'inline', None)},
    2019: {p: (f'papers/2019_{p}.pdf', K + f'2019_{p}_key.pdf', 'table', 'paper') for p in (1, 2)},
    2022: {p: (f'papers/2022_{p}.pdf', K + '2022_key.pdf', 'inline', 'key') for p in (1, 2)},
    2023: {p: (f'papers/2023_{p}.pdf', f'keys/2023_{p}_final.pdf', 'inline', None) for p in (1, 2)},
    2024: {p: (f'papers/2024_{p}.pdf', K + f'2024_{p}_key.pdf', 'inline', None) for p in (1, 2)},
    2025: {p: (f'papers/2025_{p}.pdf', f'papers/2025_{p}.pdf', 'inline', None) for p in (1, 2)},
    2026: {p: (f'papers/2026_{p}.pdf', f'keys/2026_{p}_final.pdf', 'inline', None) for p in (1, 2)},
}
QUESTION = re.compile(r'^\s*Q\.?\s?(\d{1,2})\b[.:]?', re.M)
SECTION = re.compile(r'SECTION\s*[-–]?\s*(\d)\b', re.I)
STEM = re.compile(r'(?:Question Stem|Paragraph).{0,40}?(?:Question Nos?\.?|Q\.)\s*(\d+)\s*(?:and|&|-|to)\s*(\d+)', re.I)
# Answer lines as printed: "Answer: A, C", "Answer Q4: B", "Ans for Q.2: (D)", "Answer for the above question".
ANSWER_LINE = re.compile(r'^\s*(?:Ans(?:wer)?s?\s+for\s+(?:Q|the above)|Answer\s*(?:Q\s*\d+)?\s*:|Ans\s*(?:Q\s*\d+)?\s*:)',
                         re.I | re.M)
LETTERS = r'\(?[A-D](?!(?-i:[a-z]))\)?(?:[ ,]*\(?[A-D](?!(?-i:[a-z]))\)?)*'
NUMBER = r'-?[\d.]+(?:\s*(?:to|TO)\s*-?[\d.]+)?'
NUMBERED = re.compile(r'Ans(?:wer)?\s*(?:for)?\s*Q\.?\s*(\d{1,2})\s*:\s*('
                      rf'\[[^\]]*\](?:\s*or\s*\[[^\]]*\])*|{LETTERS}(?:\s+or\s+{LETTERS})*|{NUMBER}(?:\s+or\s+{NUMBER})*)', re.I)
PLAIN = re.compile(r'^\s*Answer\s*:\s*(.+?)\s*$', re.I | re.M)
KEYWORDS = {
    'physics': r'velocity|acceleration|force|momentum|current|voltage|magnetic|lens|wavelength|frictionless|pendulum|'
               r'capacitor|resistance|gravity|oscillat|photon|refractive|kinetic energy|torque|charge',
    'chemistry': r'\bmol\b|reaction|compound|aqueous|solution of|\bpH\b|enthalpy|oxidation|catalyst|isomer|acid|'
                 r'molar|electrolys|bond|\bion\b|gas constant|product[s]? (?:P|Q|X)',
    'mathematics': r'function|matrix|matrices|integral|\blim\b|probability|real number|ellipse|parabola|hyperbola|'
                   r'complex number|determinant|differentiable|sequence|\bsum of\b|\bf\s?\(x\)',
}


def run(args, **kw):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, **kw)


def page_count(pdf):
    return int(re.search(r'Pages:\s+(\d+)', run(['pdfinfo', pdf]).stdout).group(1))


def render(pdf, page, out, dpi):
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        run(['pdftoppm', '-png', '-r', dpi, '-f', page, '-l', page, '-singlefile', pdf, out.with_suffix('')], check=True)
    return out


def ocr_text(png):
    cache = png.with_suffix('.txt')
    if not cache.exists():
        cache.write_text(run(['tesseract', png, '-', '--psm', '4']).stdout)
    return cache.read_text()


@lru_cache(maxsize=None)
def pages_of(rel, ocr):
    """The text of each page of a PDF: its text layer, or OCR when asked (scans, garbled fonts)."""
    pdf = DATA / rel
    stem = Path(rel).with_suffix('').as_posix().replace('/', '_')
    out = []
    for n in range(1, page_count(pdf) + 1):
        if ocr:
            out.append(ocr_text(render(pdf, n, OCR / f'{stem}-p{n:02d}.png', OCR_DPI)))
        else:
            out.append(run(['pdftotext', '-layout', '-f', n, '-l', n, pdf, '-']).stdout)
    return out


def kind_of(section):
    s = ' '.join(section.split()).lower()
    if 'matching list' in s or 'list-i' in s or 'list i ' in s or 'match' in s and 'column' in s:
        return 'match'
    if 'one or more' in s:
        return 'multiple'
    if 'numerical' in s or 'integer' in s or 'single digit' in s:
        return 'numerical'
    if 'paragraph' in s and 'only one' in s:
        return 'single'
    if 'only one' in s:
        return 'single'
    return 'unknown'


def parse_answer(raw):
    """'(D)', 'AC', 'A, C, D', '[A, D] or [D]', 'A or B' -> {'options': [[...], ...]};
    '(7.00 to 10.00)*', '0.75', '4 OR 5', '80 or 150 or 220' -> {'ranges': [[lo, hi], ...]}."""
    raw = ' '.join(str(raw).split()).strip()
    parts = [p.replace('*', '').strip('[]() ') for p in re.split(r'\bor\b', raw, flags=re.I)]
    if parts and all(re.fullmatch(r'-?[\d.]+(\s*(to|–|-)\s*-?[\d.]+)?', p, re.I) for p in parts):
        ranges = []
        for p in parts:
            nums = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?|-?\.\d+', p)]
            ranges.append([nums[0], nums[-1]])
        return {'raw': raw, 'ranges': ranges}
    alternatives = [sorted(set(re.findall(r'[A-D]', p.upper()))) for p in parts]
    alternatives = [a for a in alternatives if a]
    return {'raw': raw, 'options': alternatives} if alternatives and not re.search(r'\d', raw) else None


def marked(answer, given):
    """True when a model's answer earns full marks: an option set equal to an accepted one, or a number in range."""
    if given is None or not answer:
        return False
    ranges = answer.get('ranges') or ([answer['range']] if 'range' in answer else None)
    if ranges:
        try:
            value = float(str(given).strip().strip('[]'))
        except ValueError:
            return False
        return any(lo - 1e-9 <= value <= hi + 1e-9 for lo, hi in ranges)
    picked = sorted(set(re.sub(r'[^A-D]', '', str(given).upper())))
    return picked in answer['options']


def classify(text):
    scores = {s: len(re.findall(p, text, re.I)) for s, p in KEYWORDS.items()}
    return max(scores, key=scores.get)


def structure(pages):
    """Questions in reading order: (part, number, page, text, section, instructions). A part starts at SECTION 1."""
    found, part, section, instructions = [], -1, None, ''
    for page_no, text in enumerate(pages, 1):
        events = sorted([(m.start(), 'q', m) for m in QUESTION.finditer(text)] +
                        [(m.start(), 's', m) for m in SECTION.finditer(text)], key=lambda e: e[0])
        for at, kind, m in events:
            if kind == 's':
                n = int(m.group(1))
                if n == 1 and (section != 1 or part < 0):
                    part += 1
                section = n
                instructions = text[at:at + 1500]
            else:
                found.append({'part': max(part, 0), 'number': int(m.group(1)), 'page': page_no, 'at': at,
                              'section': section, 'instructions': instructions})
    # each question's text runs to the next marker (across a page break)
    flat = [(q['page'], q['at']) for q in found]
    for i, q in enumerate(found):
        end_page, end_at = flat[i + 1] if i + 1 < len(flat) else (len(pages), len(pages[-1]))
        chunks = []
        for p in range(q['page'], end_page + 1):
            text = pages[p - 1]
            start = q['at'] if p == q['page'] else 0
            stop = end_at if p == end_page else len(text)
            chunks.append(text[start:stop])
        q['text'] = '\n'.join(chunks).strip()
        q['end_page'] = end_page
    # drop repeats of a number inside one part (a marker read twice), keeping the first
    seen, out = set(), []
    for q in found:
        key = (q['part'], q['number'])
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out


def name_parts(questions):
    """Name each part by its keywords, so a wrong split shows up instead of mislabelling a subject."""
    parts = {}
    for q in questions:
        parts.setdefault(q['part'], []).append(q['text'])
    names = {p: classify(' '.join(t)) for p, t in parts.items()}
    return names


def answers_inline(pages):
    """(part, number) -> raw answer, from a key printed with the questions."""
    out = {}
    qs = structure(pages)
    full = [(p, t) for p, t in enumerate(pages, 1)]
    for q in qs:
        hit = None
        for m in NUMBERED.finditer(q['text']):
            if int(m.group(1)) == q['number']:
                hit = m.group(2)
        if hit is None:
            m = PLAIN.search(q['text'])
            hit = m.group(1) if m else None
        if hit is None:      # answers grouped after a pair or set of questions: search the following pages
            for p, t in full[q['page'] - 1:q['end_page'] + 1]:
                for m in NUMBERED.finditer(t):
                    if int(m.group(1)) == q['number']:
                        hit = m.group(2)
                        break
                if hit:
                    break
        if hit:
            out[(q['part'], q['number'])] = hit
    return out, qs


def answers_table(pages, names):
    """(part, number) -> raw answer from a one-page table: 'Question No. Physics Chemistry Mathematics' rows."""
    out = {}
    text = pages[0]
    header = re.search(r'Question\s+No\.?(.*)', text)
    order = re.findall(r'Physics|Chemistry|Mathematics', header.group(1), re.I) if header else []
    part_of = {name: part for part, name in names.items()}
    for line in text.splitlines():
        m = re.match(r'^\s*(\d{1,2})\s{2,}(.+)$', line)
        if not m:
            continue
        cells = [c.strip() for c in re.split(r'\s{3,}', m.group(2).strip()) if c.strip()]
        if len(cells) != len(order):
            continue
        for subject, cell in zip(order, cells):
            part = part_of.get(subject.lower())
            if part is not None:
                out[(part, int(m.group(1)))] = cell
    return out


# ------------------------------------------------------------------ answers the text cannot give
VISION = 'http://10.8.0.4:8001/v1'      # Qwen 27B (vision) on the Spark, a local model (user, 2026-10-23)
VISION_CACHE = OCR / 'vision-answers.json'


def squash(text):
    return re.sub(r'[\s\[\]()*,]', '', str(text)).upper()


def vision_answer(rel, ocr, kq, subject):
    """Read one answer off the key's page image with the local vision model. Kept only if that answer also appears
    in the key's own text (text layer or OCR) for this question, so a misreading cannot become a wrong key."""
    import base64
    import httpx
    cache = json.loads(VISION_CACHE.read_text()) if VISION_CACHE.exists() else {}
    name = f'{rel}:{subject}:{kq["number"]}'
    if name not in cache:
        pdf = DATA / rel
        stem = Path(rel).with_suffix('').as_posix().replace('/', '_')
        images = [render(pdf, p, OCR / f'{stem}-p{p:02d}-key150.png', 150)
                  for p in range(kq['page'], min(kq['end_page'], kq['page'] + 1) + 1)]
        prompt = (f'These are pages of the official JEE Advanced answer key. In the {subject.upper()} part, find '
                  f'question Q.{kq["number"]}. Its official answer is printed with it: after "Answer", or written '
                  'into the answer blank, or in a list such as "Ans for Q.12: (B)". Report exactly what is printed '
                  '(letters like "A, C" or a number or range like "0.75" or "1.70 to 1.75"). If you cannot see it, '
                  'say so. Return JSON {"answer": "..." or null}.')
        content = [{'type': 'text', 'text': prompt}] + [
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(i.read_bytes()).decode()}}
            for i in images]
        body = {'model': 'local', 'messages': [{'role': 'user', 'content': content}], 'temperature': 0,
                'max_tokens': 300, 'response_format': {'type': 'json_object'},
                'chat_template_kwargs': {'enable_thinking': False}}
        try:
            reply = httpx.post(VISION + '/chat/completions', json=body, timeout=600).json()
            text = reply['choices'][0]['message']['content']
            cache[name] = json.loads(re.search(r'\{.*\}', text, re.S).group(0)).get('answer')
        except Exception as exc:  # noqa: BLE001 - an unread answer leaves the question out
            print(f'  vision {name}: {exc}', file=sys.stderr)
            return None
        VISION_CACHE.write_text(json.dumps(cache, indent=1))
    got = cache[name]
    if not got:
        return None
    want = squash(got)
    lines = '\n'.join(pages_of(rel, ocr)[kq['page'] - 1:kq['end_page'] + 1]).splitlines()
    for line in lines:      # printed on an answer line, or alone on its own line (an answer written into the blank)
        if want and ((ANSWER_LINE.search(line) or NUMBERED.search(line)) and want in squash(line) or squash(line) == want):
            return got
    return None


# ------------------------------------------------------------------ answer masking
def answer_boxes_text(pdf, page, scale):
    """Pixel boxes of answer lines on a text-layer page (pdftotext -bbox-layout)."""
    xml = run(['pdftotext', '-bbox-layout', '-f', page, '-l', page, pdf, '-']).stdout
    boxes = []
    for line in re.finditer(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', xml, re.S):
        words = ' '.join(re.findall(r'>([^<]+)</word>', line.group(5)))
        if ANSWER_LINE.search(words) or NUMBERED.search(words):
            x0, y0, x1, y1 = (float(v) for v in line.groups()[:4])
            boxes.append((x0 * scale - 4, y0 * scale - 3, x1 * scale + 60, y1 * scale + 3))
    return boxes


def answer_boxes_ocr(png):
    """Pixel boxes of answer lines on a scanned page (tesseract TSV, grouped into lines)."""
    tsv = run(['tesseract', png, '-', '--psm', '4', 'tsv']).stdout
    lines = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter='\t', quoting=csv.QUOTE_NONE):
        if row.get('level') != '5' or not (row.get('text') or '').strip():
            continue
        key = (row['block_num'], row['par_num'], row['line_num'])
        x, y, w, h = (int(row[k]) for k in ('left', 'top', 'width', 'height'))
        words, box = lines.get(key, ([], [x, y, x + w, y + h]))
        words.append(row['text'])
        box = [min(box[0], x), min(box[1], y), max(box[2], x + w), max(box[3], y + h)]
        lines[key] = (words, box)
    return [(b[0] - 6, b[1] - 4, b[2] + 80, b[3] + 4) for words, b in lines.values()
            if ANSWER_LINE.search(' '.join(words)) or NUMBERED.search(' '.join(words))]


def masked_page(rel, page, scanned):
    """The page image the models see, with every printed answer painted out. None if an answer still shows."""
    from PIL import Image, ImageDraw
    pdf = DATA / rel
    stem = Path(rel).with_suffix('').as_posix().replace('/', '_')
    out = PAGES / f'{stem}-p{page:02d}.png'
    if out.exists():
        return out
    raw = render(pdf, page, OCR / f'{stem}-p{page:02d}-view.png', DPI)
    if scanned:
        big = render(pdf, page, OCR / f'{stem}-p{page:02d}.png', OCR_DPI)
        k = DPI / OCR_DPI
        boxes = [tuple(v * k for v in b) for b in answer_boxes_ocr(big)]
    else:
        boxes = answer_boxes_text(pdf, page, DPI / 72)
    image = Image.open(raw).convert('RGB')
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle(box, fill='white')
    check = OCR / f'{stem}-p{page:02d}-check.png'
    image.resize((image.width * 2, image.height * 2)).save(check)
    left = ocr_text(check)
    if ANSWER_LINE.search(left) or NUMBERED.search(left):
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out


def view_page(rel, page, printed, scanned):
    """A page image for the models: masked when the paper prints answers, as is otherwise."""
    if printed:
        return masked_page(rel, page, scanned)
    stem = Path(rel).with_suffix('').as_posix().replace('/', '_')
    return render(DATA / rel, page, PAGES / f'{stem}-p{page:02d}.png', DPI)


# ------------------------------------------------------------------ one paper
def build(year, paper):
    qrel, krel, how, ocr = SOURCES[year][paper]
    q_pages = pages_of(qrel, ocr in ('paper', 'both'))
    questions = structure(q_pages)
    names = name_parts(questions)
    printed = qrel == krel
    key_ocr = ocr in ('key', 'both')
    key_qs = []
    if how == 'table':
        answers = answers_table(pages_of(krel, False), names)
        key_names = names
    else:
        answers, key_qs = answers_inline(pages_of(krel, key_ocr))
        key_names = name_parts(key_qs)
    by_subject = {(key_names.get(part), n): a for (part, n), a in answers.items()}
    for kq in key_qs:                     # what the text could not give, the vision model reads (checked)
        subject = key_names.get(kq['part'])
        if (subject, kq['number']) not in by_subject:
            got = vision_answer(krel, key_ocr, kq, subject)
            if got:
                by_subject[(subject, kq['number'])] = got
    out, problems = [], []
    last = page_count(DATA / qrel)
    for q in questions:
        subject = names[q['part']]
        raw = by_subject.get((subject, q['number']))
        answer = parse_answer(raw) if raw else None
        qid = f'{year}-P{paper}-{subject[:4]}-Q{q["number"]:02d}'
        if not answer:
            problems.append(f'{qid}: no answer in the key')
            continue
        span = range(q['page'], min(q['end_page'], q['page'] + 2, last) + 1)
        views = [view_page(qrel, p, printed, ocr in ('paper', 'both')) for p in span]
        if any(v is None for v in views):
            problems.append(f'{qid}: an answer still shows on its page after masking; withheld')
            continue
        text = ANSWER_LINE.split(q['text'])[0] if printed else q['text']
        out.append({'id': qid, 'year': year, 'paper': paper, 'subject': subject, 'number': q['number'],
                    'section': q['section'], 'type': kind_of(q['instructions']),
                    'text': NUMBERED.sub('', text).strip(), 'answer': answer,
                    'pages': [str(v.relative_to(ROOT)) for v in views]})
    return out, problems, names


def main(argv=None):
    years = [int(a) for a in (argv or sys.argv[1:])] or sorted(SOURCES)
    for year in years:
        bank, problems = [], []
        for paper in sorted(SOURCES[year]):
            got, trouble, names = build(year, paper)
            bank += got
            problems += trouble
            counts = {}
            for q in got:
                counts.setdefault(q['subject'], []).append(q['type'])
            print(f'{year} P{paper} parts {list(names.values())}: ' + '; '.join(
                f'{s} {len(k)} ({", ".join(f"{t} {k.count(t)}" for t in sorted(set(k)))})' for s, k in counts.items()))
        out = DATA / 'bank' / f'{year}.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(bank, indent=1, ensure_ascii=False))
        print(f'  {year}: {len(bank)} questions; {len(problems)} left out' +
              (': ' + '; '.join(problems[:8]) + (' ...' if len(problems) > 8 else '') if problems else ''))


if __name__ == '__main__':
    main()
