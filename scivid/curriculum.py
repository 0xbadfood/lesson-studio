"""NCERT curriculum index for science and maths, Classes 6-12 (English).

Grounding source of truth. Today it reads the official chapter PDFs page by page
(pdftotext); the frozen knowledge banks can replace `chapter_pages` once readable.
Every passage carries a page reference so claims can be cited.
"""
import json
import math
import re
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path

# Classes 6-10 have one Science book; Classes 11-12 split it into Physics, Chemistry and Biology.
SUBJECTS = {'Science': 'science', 'Mathematics': 'maths', 'Physics': 'physics', 'Chemistry': 'chemistry',
            'Biology': 'biology'}
CLASSES = ['06', '07', '08', '09', '10', '11', '12']
STOP = set('''a an the and or of to in on for with by from at as is are was were be been it its this that these those
which what when where who how why can could would should will may might do does did not no yes than then so such
into about over under between your you we our they their them he she his her i me my us also there here very more
most some any each other one two three many much all both only just like up down out if but because while'''.split())


def tokens(text):
    return [w for w in re.findall(r"[a-z][a-z\-']+|\d+(?:\.\d+)?", text.lower()) if w not in STOP and len(w) > 2]


def chapter_id(book, number):
    return f'{book}:{number:02d}'


@lru_cache(maxsize=1)
def catalog(root):
    """All science/maths chapters, with titles read from each chapter's first page. The cache keeps titles already
    cleaned from the contents pages; books missing from it (a class added later) are scanned and appended."""
    root = Path(root)
    cache = Path(__file__).resolve().parent / 'cache' / 'curriculum-catalog.json'
    chapters = json.loads(cache.read_text()) if cache.exists() else []
    known = {c['book'] for c in chapters}
    added = False
    for cls in CLASSES:
        for folder, subject in SUBJECTS.items():
            base = root / f'class_{cls}' / folder
            if not base.is_dir():
                continue
            for book_dir in sorted(base.iterdir()):
                book = book_dir.name.split('-', 1)[0]
                if book in known or not book_dir.is_dir():
                    continue
                book_title = book_dir.name.split('-', 1)[1].replace('-', ' ').title() if '-' in book_dir.name else book
                for pdf in sorted(book_dir.glob(f'{book}[0-9][0-9].pdf')):
                    number = int(pdf.stem[-2:])
                    chapters.append({'id': chapter_id(book, number), 'class': int(cls), 'subject': subject,
                                     'book': book, 'book_title': book_title, 'chapter': number,
                                     'title': chapter_title(pdf, number), 'pdf': str(pdf)})
                    added = True
    if added:
        number_parts(chapters)
    if added or not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(chapters, indent=1))
    return chapters


def number_parts(chapters):
    """Classes 11-12 Part II books carry on Part I's chapter numbers (keph201.pdf is Physics Chapter 8). 'chapter'
    becomes the printed number; ids and file names keep the file's own number."""
    count = {}
    for c in chapters:
        count[c['book']] = count.get(c['book'], 0) + 1
    for c in chapters:
        if c['class'] >= 11 and c['book'].endswith('2') and 'part' not in c:
            first = c['book'][:-1] + '1'
            if first in count:
                c['chapter'] += count[first]
                c['part'] = 2


def chapter_title(pdf, number):
    text = subprocess.run(['pdftotext', '-f', '1', '-l', '1', '-layout', str(pdf), '-'],
                          capture_output=True, text=True, timeout=60).stdout
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = []
    for line in lines[:8]:
        clean = re.sub(r'\s{2,}', ' ', re.sub(rf'(^|\s){number}(\s|$)', ' ', line)).strip()
        clean = re.sub(r'^(chapter|unit)\s*\d*\s*', '', clean, flags=re.I).strip()
        if not clean:
            continue
        # Titles are short lines; the first sentence-like line ends the title.
        if len(clean) > 48 or (title and clean[0].islower()) or clean.endswith('.'):
            break
        title.append(clean)
        if len(' '.join(title)) > 60:
            break
    return ' '.join(title).strip(' ,:-') or f'Chapter {number}'


def clean_titles(root, chat):
    """Replace heuristic titles with the book's own contents page, read once per book by the model."""
    path = Path(__file__).resolve().parent / 'cache' / 'curriculum-catalog.json'
    chapters = catalog(str(root))
    by_book = {}
    for c in chapters:
        by_book.setdefault(c['book'], []).append(c)
    for book, items in by_book.items():
        if all(c.get('title_source') == 'contents' for c in items):
            continue
        prelims = Path(items[0]['pdf']).with_name(f'{book}ps.pdf')
        text = subprocess.run(['pdftotext', '-layout', str(prelims), '-'], capture_output=True, text=True,
                              timeout=60).stdout if prelims.exists() else ''
        heuristic = [{'chapter': c['chapter'], 'first_page_guess': c['title'],
                      'first_page_text': ' '.join(chapter_pages(c)[0]['text'].split())[:300]} for c in items]
        numbers = sorted(c['chapter'] for c in items)

        def check(result):
            got = sorted(int(r['chapter']) for r in result.get('chapters', []))
            if got != numbers:
                raise ValueError(f'Return exactly chapters {numbers}; you returned {got}')
        result = chat.call(f'titles-{book}', (
            'Give the official title of every chapter of this NCERT book. Use the CONTENTS page when present; '
            'otherwise the chapter openings. Titles in normal title case, without page numbers or the word Chapter. '
            f'Chapters present: {numbers}.\nReturn {{"chapters":[{{"chapter":int,"title":str}}]}}.\n'
            'CONTENTS / PRELIMS TEXT:\n' + text[-9000:] + '\nCHAPTER OPENINGS:\n' + json.dumps(heuristic)),
            thinking=0, max_tokens=3000, validate=check)
        titles = {int(r['chapter']): r['title'].strip() for r in result['chapters']}
        for c in items:
            c['title'], c['title_source'] = titles[c['chapter']], 'contents'
    path.write_text(json.dumps(chapters, indent=1))
    catalog.cache_clear()
    return chapters


def find(root, chapter_ref):
    for c in catalog(str(root)) + humanities_catalog(str(root)):
        if c['id'] == chapter_ref:
            return c
    raise KeyError(f'Unknown chapter {chapter_ref}')


# Humanities books (infofilm digests, not Lesson Studio): Classes 8-10 have Social Science books, Classes 11-12 one
# folder per subject. A Social Science book's subject comes from its title; the new integrated books (Exploring
# Society, Understanding Society) mix subjects and stay "social_science".
HUMANITIES_CLASSES = ['08', '09', '10', '11', '12']
HUMANITIES_FOLDERS = {'Social Science': None, 'History': 'history', 'Geography': 'geography',
                      'Political Science': 'political_science', 'Economics': 'economics', 'Sociology': 'sociology'}
SOCIAL_SCIENCE_TITLES = [('india-and-the-contemporary-world', 'history'), ('our-pasts', 'history'),
                         ('contemporary-india', 'geography'), ('resources-and-development', 'geography'),
                         ('economic', 'economics'), ('democratic-politics', 'political_science'),
                         ('social-and-political-life', 'political_science')]
HUMANITIES_SUBJECTS = {'history', 'geography', 'political_science', 'economics', 'sociology', 'social_science'}


def contents_titles(prelims):
    """{chapter number: title} from a humanities book's contents page, where chapters are listed as roman numerals
    ("II. Nationalism in India") or plain numbers ("2. Nationalism in India")."""
    if not Path(prelims).exists():
        return {}
    text = subprocess.run(['pdftotext', str(prelims), '-'], capture_output=True, text=True, timeout=60).stdout
    start = [m.end() for m in re.finditer(r'(?mi)^\s*contents\s*$', text)]
    if not start:
        return {}
    text = text[start[-1]:start[-1] + 3000]          # the contents page only (forewords list numbered people)
    roman = {'I': 1, 'V': 5, 'X': 10}
    to_int = lambda r: sum(-roman[a] if roman[a] < roman.get(b, 0) else roman[a]  # noqa: E731
                           for a, b in zip(r, r[1:] + ' '))
    titles = {}
    for m in re.finditer(r'(?m)^\s*([IVX]{1,5}|\d{1,2})\.\s+([A-Z][^\n]{2,90}?)\s*$', text):
        number = int(m.group(1)) if m.group(1).isdigit() else to_int(m.group(1))
        titles.setdefault(number, m.group(2).strip())
    return titles


@lru_cache(maxsize=1)
def humanities_catalog(root):
    """Humanities chapters of Classes 8-12, cached like the science catalog."""
    cache = Path(__file__).resolve().parent / 'cache' / 'humanities-catalog.json'
    if cache.exists():
        return json.loads(cache.read_text())
    chapters = []
    for cls in HUMANITIES_CLASSES:
        for folder, subject in HUMANITIES_FOLDERS.items():
            base = Path(root) / f'class_{cls}' / folder
            for book_dir in sorted(base.iterdir()) if base.is_dir() else []:
                if not book_dir.is_dir() or '-' not in book_dir.name:
                    continue
                book, slug = book_dir.name.split('-', 1)
                book_subject = subject or next((s for key, s in SOCIAL_SCIENCE_TITLES if key in slug), 'social_science')
                titles = contents_titles(book_dir / f'{book}ps.pdf')
                for pdf in sorted(book_dir.glob(f'{book}[0-9][0-9].pdf')):
                    number = int(pdf.stem[-2:])
                    title = titles.get(number)
                    chapters.append({'id': chapter_id(book, number), 'class': int(cls), 'subject': book_subject,
                                     'book': book, 'book_title': slug.replace('-', ' ').title(), 'chapter': number,
                                     'title': title or chapter_title(pdf, number),
                                     'title_source': 'contents' if title else 'first_page', 'pdf': str(pdf)})
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(chapters, indent=1))
    return chapters


def chapter_pages(chapter):
    """Page-indexed text for one chapter, cached beside the catalog."""
    cache = Path(__file__).resolve().parent / 'cache' / 'pages' / (chapter['id'].replace(':', '-') + '.json')
    if cache.exists():
        return json.loads(cache.read_text())
    info = subprocess.run(['pdfinfo', chapter['pdf']], capture_output=True, text=True, timeout=60).stdout
    count = int(re.search(r'Pages:\s+(\d+)', info).group(1))
    pages = []
    for p in range(1, count + 1):
        text = subprocess.run(['pdftotext', '-f', str(p), '-l', str(p), chapter['pdf'], '-'],
                              capture_output=True, text=True, timeout=60).stdout
        text = re.sub(r'Reprint \d{4}-\d{2}|Chapter \d+\.indd.*|\f', ' ', text)
        pages.append({'page': p, 'text': text.strip()})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(pages))
    return pages


def passages(chapter):
    """Paragraph-sized passages with stable ids '<chapter>/p<page>.<n>'."""
    out = []
    for page in chapter_pages(chapter):
        paras = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n\s*\n', page['text'])]
        n = 0
        buffer = ''
        for para in paras:
            buffer = (buffer + ' ' + para).strip()
            if len(buffer) < 220:
                continue
            n += 1
            out.append({'id': f"{chapter['id']}/p{page['page']}.{n}", 'page': page['page'], 'text': buffer[:1400]})
            buffer = ''
        if len(buffer) > 60:
            n += 1
            out.append({'id': f"{chapter['id']}/p{page['page']}.{n}", 'page': page['page'], 'text': buffer[:1400]})
    return out


def search(chapter, query, limit=12):
    """BM25 over the chapter's passages."""
    items = passages(chapter)
    docs = [Counter(tokens(p['text'])) for p in items]
    q = tokens(query)
    if not q or not items:
        return items[:limit]
    avg = sum(sum(d.values()) for d in docs) / len(docs)
    df = Counter(t for d in docs for t in set(d))
    scored = []
    for item, d in zip(items, docs):
        size = sum(d.values()) or 1
        score = 0.0
        for t in q:
            if d[t]:
                idf = math.log(1 + (len(docs) - df[t] + .5) / (df[t] + .5))
                score += idf * d[t] * 2.2 / (d[t] + 1.2 * (.25 + .75 * size / avg))
        scored.append((score, item))
    scored.sort(key=lambda s: -s[0])
    return [dict(item, score=round(score, 3)) for score, item in scored[:limit] if score > 0] or items[:limit]


# Classes 1-8 come from the ingestion tool's own frozen scope; Classes 11-12 are built by the same tool into
# ncert-banks/ (scope-english-11-12.json), because the tool's folder is not writable here.
BANKS = [Path('/home/nitin/story_generator/ncert_downloader/phase1_artifacts/frozen'),
         Path(__file__).resolve().parents[1] / 'ncert-banks']


def knowledge_bank(chapter):
    """The frozen Phase-1 knowledge bank for a chapter, or None."""
    code = Path(chapter['pdf']).stem
    pattern = f"*/knowledge-banks/class_{chapter['class']:02d}/{chapter['book']}/{code}/current.json"
    for current in (c for root in BANKS for c in root.glob(pattern)):
        try:
            version = current.parent / json.loads(current.read_text())['version_path']
            banks = sorted(version.glob('enrichment/*/knowledge-bank.json'), key=lambda p: p.stat().st_mtime)
            if banks:
                return json.loads(banks[-1].read_text())['content']
        except (OSError, ValueError, KeyError):
            return None
    return None


def bank_facts(content, query, limit=8):
    """Grounded facts ranked by overlap with the query (high-confidence facts first on ties)."""
    q = set(tokens(query))
    rows = []
    for fact in content.get('grounded_facts', []):
        overlap = len(q & set(tokens(fact.get('statement', ''))))
        rows.append((overlap, fact.get('confidence') == 'high', fact))
    rows.sort(key=lambda r: (-r[0], not r[1]))
    return [r[2] for r in rows[:limit]]


def search_catalog(root, query, subject=None, limit=8):
    """Map a free topic to likely chapters (title + first-page text)."""
    q = set(tokens(query))
    rows = []
    for c in catalog(str(root)):
        if subject and c['subject'] != subject:
            continue
        rows.append((len(q & set(tokens(c['title']))) * 3, c))
    rows.sort(key=lambda r: -r[0])
    return [c for s, c in rows[:limit] if s > 0]
