"""The question bank: JEE Advanced papers and their official answer keys, as structured questions.

The official key PDF (jeeadv.ac.in, 2026 onward) prints each question followed by "Answer Qn: ...", so one text pass
gives question, section and answer together. Models never see the key: the page images they get are rendered from the
question paper itself, and the question text is the key's text with the answer lines removed.

A paper is Mathematics, Physics, Chemistry in that order; question numbers restart at Q.1 for each subject. Layout text
garbles fractions and loses figures, so the page images are the primary input and the text a reading aid.

    python -m solutions.bank 2026            # writes questions-data/jee-advanced/bank/2026.json and page images
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'questions-data' / 'jee-advanced'
SUBJECTS = ['mathematics', 'physics', 'chemistry']
DPI = 110
QUESTION = re.compile(r'^\s*Q\.\s?(\d+)\b', re.M)
ANSWER = re.compile(r'^\s*Answer\s+Q(\d+)\s*:\s*(.+?)\s*$', re.M)
STEM = re.compile(r'Question Stem for Question Nos?\.\s*(\d+)\s*and\s*(\d+)', re.I)


def text(pdf, first=None, last=None):
    args = ['pdftotext', '-layout'] + (['-f', str(first), '-l', str(last)] if first else []) + [str(pdf), '-']
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def pages(pdf):
    out = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True, check=True).stdout
    return int(re.search(r'Pages:\s+(\d+)', out).group(1))


def kind_of(section):
    """The question type from its section's instructions."""
    s = ' '.join(section.split()).lower()
    if 'matching list' in s or 'list-i' in s:
        return 'match'
    if 'one or more' in s:
        return 'multiple'
    if 'numerical value' in s or 'non-negative integer' in s or 'integer' in s:
        return 'numerical'
    if 'only one' in s:
        return 'single'
    return 'unknown'


def parse_answer(raw, kind):
    """'AC', 'A or B', 'BD or D' -> {'options': [['A','C']]...}; '[3.9 TO 4.1]' -> {'range': [3.9, 4.1]}."""
    raw = raw.strip()
    if raw.startswith('['):
        inner = raw.strip('[]').strip()
        m = re.match(r'^(-?[\d.]+)\s*(?:to|TO|-)\s*(-?[\d.]+)$', inner)
        lo, hi = (float(m.group(1)), float(m.group(2))) if m else (float(inner), float(inner))
        return {'raw': raw, 'range': [lo, hi]}
    alternatives = [sorted(set(re.sub(r'[^A-D]', '', part.upper()))) for part in re.split(r'\bor\b', raw, flags=re.I)]
    return {'raw': raw, 'options': [a for a in alternatives if a]}


def marked(answer, given):
    """True when a model's answer earns full marks: an option set equal to an accepted one, or a number in range."""
    if given is None:
        return False
    if 'range' in answer:
        try:
            value = float(str(given).strip().strip('[]'))
        except ValueError:
            return False
        lo, hi = answer['range']
        return lo - 1e-9 <= value <= hi + 1e-9
    picked = sorted(set(re.sub(r'[^A-D]', '', str(given).upper())))
    return picked in answer['options']


def blocks(full):
    """Split the key's text into subjects: a new subject starts where the question number falls back to 1."""
    found, subject, last = [], -1, 10 ** 6
    for m in QUESTION.finditer(full):
        n = int(m.group(1))
        if n <= last and n == 1:
            subject += 1
        last = n
        found.append((subject, n, m.start()))
    return found


def page_starts(pdf):
    """(subject, number) -> the page of the question paper where it starts."""
    where, subject, last = {}, -1, 10 ** 6
    for page in range(1, pages(pdf) + 1):
        for m in QUESTION.finditer(text(pdf, page, page)):
            n = int(m.group(1))
            if n == 1 and n <= last:
                subject += 1
            last = n
            where[(subject, n)] = page
    return where


def render(pdf, page, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        stem = out.with_suffix('')
        subprocess.run(['pdftoppm', '-png', '-r', str(DPI), '-f', str(page), '-l', str(page), '-singlefile',
                        str(pdf), str(stem)], check=True)
    return out


def build(year, paper):
    key_pdf = DATA / 'keys' / f'{year}_{paper}_final.pdf'
    paper_pdf = DATA / 'papers' / f'{year}_{paper}.pdf'
    full = text(key_pdf)
    marks = blocks(full)
    answers = list(ANSWER.finditer(full))
    starts = page_starts(paper_pdf)
    last_page = pages(paper_pdf)
    questions = []
    for index, (subject, n, at) in enumerate(marks):
        end = marks[index + 1][2] if index + 1 < len(marks) else len(full)
        body = full[at:end]
        answer = next((a for a in answers if at <= a.start() < end and int(a.group(1)) == n), None)
        # The section instructions and a paragraph's stem sit before the question, after the previous one ends.
        before = full[(marks[index - 1][2] if index else 0):at]
        cut = ANSWER.search(before)
        tail = before[cut.end():] if cut else before
        section = re.findall(r'SECTION\s+(\d+)', tail)
        stem = STEM.search(tail)
        q = {'id': f'{year}-P{paper}-{SUBJECTS[subject][:4]}-Q{n:02d}', 'year': year, 'paper': paper,
             'subject': SUBJECTS[subject], 'number': n,
             'text': ANSWER.sub('', body).strip(),
             'answer': parse_answer(answer.group(2), 'unknown') if answer else None}
        if section:
            q['section'] = int(section[-1])
            q['instructions'] = ' '.join(tail[tail.rfind('SECTION'):].split())[:1600]
        if stem:
            q['stem_for'] = [int(stem.group(1)), int(stem.group(2))]
            q['stem'] = ' '.join(tail[stem.end():].split())
        questions.append(q)
    # Section, instructions and paragraph stems carry forward to the questions that follow them.
    current, stems = {}, {}
    for q in questions:
        key = q['subject']
        if 'section' in q:
            current[key] = (q['section'], q['instructions'])
        q['section'], q['instructions'] = current.get(key, (None, ''))
        q['type'] = kind_of(q['instructions'])
        if 'stem' in q:
            for m in q['stem_for']:
                stems[(key, m)] = q['stem']
        if (key, q['number']) in stems:
            q['stem'] = stems[(key, q['number'])]
        q.pop('stem_for', None)
        q.pop('instructions', None)
        page = starts.get((SUBJECTS.index(key), q['number']))
        nxt = starts.get((SUBJECTS.index(key), q['number'] + 1))
        if page:
            span = range(page, min((nxt or page + 1), page + 2, last_page) + 1) if nxt != page else [page]
            q['pages'] = [str(render(paper_pdf, p, DATA / 'pages' / f'{year}_{paper}-p{p:02d}.png').relative_to(ROOT))
                          for p in span]
    return questions


def main(argv=None):
    year = int((argv or sys.argv[1:])[0])
    bank = []
    for paper in (1, 2):
        bank += build(year, paper)
    out = DATA / 'bank' / f'{year}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bank, indent=1, ensure_ascii=False))
    counts = {}
    for q in bank:
        counts.setdefault((q['paper'], q['subject']), []).append(q['type'])
    for (paper, subject), kinds in sorted(counts.items()):
        print(f'P{paper} {subject}: {len(kinds)} questions, ' +
              ', '.join(f'{k} {kinds.count(k)}' for k in sorted(set(kinds))))
    missing = [q['id'] for q in bank if not q['answer'] or not q.get('pages')]
    print('without answer or page:', missing or 'none')
    print(out)


if __name__ == '__main__':
    main()
