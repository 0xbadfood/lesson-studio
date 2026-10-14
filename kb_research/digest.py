#!/usr/bin/env python3
"""Textbook digest builder: one NCERT chapter -> digest.json in the format of DIGEST_FORMAT.md.

  1. pages     - each page image (+ its extracted text) is read by a vision model into blocks: definitions,
                 equations (LaTeX), derivations step by step, worked examples, figures, activities, exercises.
                 Code checks quotes against the page text, LaTeX braces, sections, and that every numbered
                 example / equation / activity / theorem on the page is there; figures and exercises are counted
                 over the chapter. Blocks running across pages are joined.
  2. concepts  - what the chapter teaches, as concepts a user can choose, each pointing at its blocks; every
                 block belongs to a concept.
  3. gaps      - per group of concepts: what a learner does not get from the book.
  4. research  - bounded web research (search agent) for gaps that need facts.
  5. additions - one per gap; every computed number is listed as a calculation that code re-evaluates.

Pages go to the vision server and the other steps to the text server; both default to the local 3090 vLLM (about
ten times faster than the Spark's Flash-Next, which can take whole chapters as a second text server). Every
model call is cached under the chapter's folder, so a rerun repeats only what changed.

  kb_research/env/bin/python kb_research/digest.py keph1:05 kemh1:03
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import operator
import os
import re
import shutil
from fractions import Fraction
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from scivid import curriculum, models  # noqa: E402
from scivid.llm import Chat  # noqa: E402
from scivid.settings import Settings  # noqa: E402

import search_agent  # noqa: E402
import textbook_kb as kb  # noqa: E402

LOCAL = 'http://127.0.0.1:7001/v1'
SPARK = 'http://192.168.1.102:8001/v1'
OUT = HERE.parent / 'textbook-digest'
BUILDER_VERSION = '1'
DPI = 150

BLOCK_TYPES = ('definition', 'law', 'principle', 'theorem', 'fact', 'equation', 'derivation', 'proof',
               'worked_example', 'figure', 'table', 'activity', 'experiment', 'box', 'summary_point',
               'ponder_point', 'exercise')
# Humanities chapters (history, geography, political science, economics): narrative, people, places, dates, maps
# and primary sources instead of equations and derivations.
HUMANITIES_TYPES = ('fact', 'event', 'person', 'place', 'key_term', 'source', 'figure', 'map', 'table', 'timeline',
                    'box', 'activity', 'discuss', 'summary_point', 'exercise')
PROSE = {'definition', 'law', 'principle', 'theorem', 'fact', 'derivation', 'proof', 'worked_example', 'activity',
         'experiment', 'box', 'summary_point', 'ponder_point', 'event', 'person', 'place', 'key_term', 'source',
         'discuss'}
DEPTHS = ('mentioned', 'stated', 'derived', 'applied', 'explained')
HUMANITIES_GAP_TYPES = ('term', 'chronology', 'causation', 'geography', 'person', 'prerequisite', 'context', 'visual')
DIFFICULTY = ('foundation', 'core', 'advanced')
TIERS = ('official', 'academic', 'reference', 'other')
SYSTEM = kb.SYSTEM
HUMANITIES_SYSTEM = ('You are an expert history and social science teacher and curriculum analyst for Indian schools. '
                     'The textbook is the authority: you never contradict it and you add no opinions of your own. '
                     'Reply with JSON only.')


def humanities(chapter):
    return chapter.get('subject') in curriculum.HUMANITIES_SUBJECTS


def numbering(chapter):
    """How sections are numbered: science books prefix the chapter (5.2, 5.11.2); humanities books number their
    own sections (1, 2.1). None stands for the humanities form in the helpers below."""
    return None if humanities(chapter) else chapter['chapter']


def section_pattern(chapter_no):
    return rf'{chapter_no}(?:\.\d+){{1,3}}' if chapter_no is not None else r'\d{1,2}(?:\.\d+){0,2}'


def system_for(chapter):
    return HUMANITIES_SYSTEM if humanities(chapter) else SYSTEM


# ------------------------------------------------------------------ inventory (code)
def headings(text, chapter_no):
    """Numbered section headings of this chapter found in the text: [(id, title)]."""
    found = []
    space = r'\s*\n*\s*' if chapter_no is not None else r'[ \t]+'     # "1 The French Revolution ..." on one line
    for m in re.finditer(rf'(?m)^\s*({section_pattern(chapter_no)}){space}([A-Z][^\n]{{2,90}})$', text):
        found.append((m.group(1), m.group(2).strip()))
    return found


def inventory(text, chapter_no):
    """Numbered things printed on a page: examples, equation labels, activities, theorems, figure captions."""
    found = {
        'example': {m.group(1) for m in re.finditer(r'(?m)^\s*Example\s+(\d+(?:\.\d+)?)\b', text)},
        'eq': {m.group(1) for m in re.finditer(rf'(?m)^\s*\(({chapter_no}\.\d+[a-z]?)\)\s*$', text)},
        'activity': {m.group(1) for m in re.finditer(r'(?m)^\s*Activity\s+(\d+(?:\.\d+)?)\b', text)},
        'theorem': {m.group(1) for m in re.finditer(r'(?m)^\s*Theorem\s+(\d+(?:\.\d+)?)\b', text)},
        'fig': {m.group(1) for m in re.finditer(rf'(?m)^\s*Fig(?:ure)?\.?\s*({chapter_no}\.\d+)\b', text)},
    }
    if chapter_no is None:                  # humanities: Fig. 3, Source A, Box 1
        found = {'activity': set(),
                 'fig': {m.group(1) for m in re.finditer(r'(?m)^\s*Fig(?:ure)?\.?\s*(\d+)\b', text)},
                 'source': {m.group(1) for m in re.finditer(r'(?m)^\s*Source\s+([A-Z])\s*$', text)},
                 'box': {m.group(1) for m in re.finditer(r'(?m)^\s*Box\s+(\d+)\s*$', text)}}
    return {k: sorted(v) for k, v in found.items() if v}


def exercise_numbers(block):
    """(set, number) for an exercise block from its ref: "Exercise 5.18" -> ('5', 18); "Exercise 3.1 Q4" -> ('3.1', 4)."""
    for ref in block.get('ref') or []:
        m = re.search(r'Exercise\s+(?:Set\s+)?([\d.]+?)\s*(?:Q|Question)\s*(\d+)', ref, re.I)
        if m:
            return m.group(1), int(m.group(2))
        m = re.search(r'Exercise\s+(\d+)\.(\d+)\b', ref, re.I)
        if m:
            return m.group(1), int(m.group(2))
        m = re.search(r'(?:Exercise|Q|Question)\s*(\d+)\b', ref, re.I)
        if m:
            return '', int(m.group(1))
    return None


def missing_exercises(per_page):
    """Exercise numbers skipped inside each numbered run, with the page that holds the number before the gap."""
    seen = {}
    for page, result in per_page:
        for b in result['blocks']:
            if b.get('type') == 'exercise' and (key := exercise_numbers(b)):
                seen.setdefault(key[0], {}).setdefault(key[1], page)
    missing = {}
    for name, numbers in seen.items():
        for n in range(1, max(numbers) + 1):
            if n not in numbers:
                before = max((k for k in numbers if k < n), default=min(numbers))
                missing.setdefault(numbers[before], []).append(f'{name + "." if name and "." not in name else name + " Q" if name else ""}{n}')
    return missing


def ref_present(block, kind, number):
    blob = json.dumps(block, ensure_ascii=False)
    if kind == 'eq':
        return number in blob
    name = {'example': r'Example', 'activity': r'Activity', 'theorem': r'Theorem', 'fig': r'Fig(?:ure)?\.?',
            'source': r'Source', 'box': r'Box'}[kind]
    return re.search(rf'{name}\s*\(?{re.escape(number)}(?![\d])', blob) is not None


def balanced(latex):
    depth = 0
    for ch in latex or '':
        depth += {'{': 1, '}': -1}.get(ch, 0)
        if depth < 0:
            return False
    sides = re.findall(r'\\(left|right)(?![A-Za-z])', str(latex))
    return depth == 0 and sides.count('left') == sides.count('right')


def latex_fields(block):
    yield block.get('latex')
    for step in block.get('steps') or []:
        yield step.get('latex') if isinstance(step, dict) else None


# ------------------------------------------------------------------ 1. pages
PAGE_SCHEMA = '''{"headings":[{"id":"5.6","title":str (complete, as printed)}] (section headings printed on this page),
"blocks":[{"type":"definition|law|principle|theorem|fact|equation|derivation|proof|worked_example|figure|table|activity|experiment|box|summary_point|ponder_point|exercise",
 "section":"5.6" (the section the block is in; "intro" before the first numbered section; "end" for the end-of-chapter summary, points to ponder and exercises),
 "title":str, "text":str (what the book says, in its words where possible),
 "ref":[str] (the book's numbers, e.g. "Example 5.6", "Eq. 5.8a", "Fig. 5.4", "Activity 3.1", "Theorem 1", "Exercise 5.18", "Exercise 3.1 Q4"),
 "latex":str (equation, formula, theorem statement),
 "symbols":[{"symbol":str,"meaning":str,"unit":str}] (equation only),
 "steps":[{"latex":str,"reason":str}] (derivation, proof, worked_example: every step, nothing skipped),
 "problem":str, "given":[str], "find":[str], "answer":str (worked_example; exercise answers only if printed),
 "caption":str, "shows":str (figure/table: what it depicts, enough to redraw it; table: its rows),
 "aim":str, "materials":[str], "procedure":[str], "observation":str (activity/experiment),
 "kind":str (box: history|application|note; exercise: numerical|conceptual|proof|diagram),
 "items":[str] (lists in facts: organelles, properties, classifications),
 "continued":bool (the block began on the previous page), "continues":bool (it runs onto the next page),
 "quote":str (6-20 consecutive words of prose copied exactly from the PAGE TEXT below)}]}
Omit fields that do not apply.'''

HUMANITIES_PAGE_SCHEMA = '''{"headings":[{"id":"2.1","title":str (complete, as printed)}] (section headings printed on this page),
"blocks":[{"type":"fact|event|person|place|key_term|source|figure|map|table|timeline|box|activity|discuss|summary_point|exercise",
 "section":"2.1" (the book's section number the block is in; "intro" before the first numbered section; "end" for the end-of-chapter questions and project),
 "title":str, "text":str (what the book says, in its words where possible),
 "ref":[str] (the book's labels, e.g. "Fig. 3", "Source A", "Box 1", "Write in brief Q2", "Discuss Q4", "Project"),
 "date":str, "place":str, "actors":[str], "causes":[str], "effects":[str] (event: as the book gives them),
 "name":str, "role":str, "dates":str (person: who they were, as the book says),
 "term":str, "meaning":str (key_term: the book's "New words" and terms it defines),
 "author":str, "year":str, "kind":str (source: speech|letter|essay|report|poem|poster|other; exercise: short|long|discuss|project|map),
 "caption":str, "shows":str (figure/map/table: what it depicts, enough to redraw it; a map: the places, routes and borders on it; table: its rows),
 "items":[str] (timeline entries "1848: ..."; lists in facts),
 "continued":bool (the block began on the previous page), "continues":bool (it runs onto the next page),
 "quote":str (6-20 consecutive words of prose copied exactly from the PAGE TEXT below)}]}
Omit fields that do not apply.'''


def anchored(block, pages, page):
    """The block is tied to the page text: its quote is there, or failing that some 8-word run of its own text
    (blocks are written in the book's words)."""
    if kb.find_quote(block.get('quote', ''), pages, [page]) is not None:
        return True
    words = str(block.get('text') or block.get('problem') or '').split()
    return any(kb.find_quote(' '.join(words[i:i + 8]), pages, [page]) is not None
               for i in range(0, max(0, len(words) - 7), 4))


def mathy(quote):
    """A quote written as LaTeX cannot be found in pdftotext output; on formula-only pages it is all there is."""
    quote = str(quote or '')
    plain = [w for w in re.findall(r'(?<!\\)\b[A-Za-z]{3,}\b', quote)]
    return bool(re.search(r'[\\^_{}]', quote)) and len(plain) < 6


def page_errors(result, page, pages, chapter_no, required):
    errors = []
    blocks = result.get('blocks')
    if not isinstance(blocks, list):
        return ['"blocks" must be a list']
    misses = []                             # quotes not found: tolerated unless many (the image is the evidence)
    section_re = re.compile(rf'^({section_pattern(chapter_no)}|intro|end)$')
    types = BLOCK_TYPES if chapter_no is not None else HUMANITIES_TYPES
    example = f'{chapter_no}.2' if chapter_no is not None else '2 or 2.1'
    for n, b in enumerate(blocks, 1):
        tag = f'block {n} ({b.get("type")}, "{str(b.get("title", ""))[:40]}")'
        if b.get('type') not in types:
            errors.append(f'{tag}: type must be one of {list(types)}')
        if not section_re.match(str(b.get('section', ''))):
            errors.append(f'{tag}: section must be a section number like {example}, or "intro" or "end"')
        if not all(balanced(x) for x in latex_fields(b) if x):
            errors.append(f'{tag}: LaTeX has unbalanced braces or \\left/\\right')
        if b.get('type') in ('derivation', 'proof') and not b.get('steps') and not b.get('continued'):
            errors.append(f'{tag}: give the steps')
        if b.get('type') == 'worked_example' and not b.get('continues') and not (b.get('steps') or b.get('answer')):
            errors.append(f'{tag}: give the solution steps and answer')
        if b.get('type') in PROSE and not b.get('continued'):
            quote = b.get('quote', '')
            b['quote_found'] = anchored(b, pages, page)
            if not b['quote_found'] and mathy(quote):
                b['quote_found'] = None           # formula only: the page image is the evidence
            elif not b['quote_found']:
                misses.append(f'{tag}: quote "{quote}" is not in the page text; copy 6-20 consecutive words of prose '
                              'exactly from the PAGE TEXT')
    prose = sum(b.get('type') in PROSE and not b.get('continued') for b in blocks)
    if len(misses) > max(1, prose // 2):
        errors += misses
    for kind, numbers in required.items():
        if kind == 'fig':
            continue                          # figures are counted over the chapter (captions can sit on a neighbour)
        for number in numbers:
            if not any(ref_present(b, kind, number) for b in blocks):
                label = {'example': 'Example', 'eq': 'Eq.', 'activity': 'Activity', 'theorem': 'Theorem',
                         'source': 'Source', 'box': 'Box'}[kind]
                errors.append(f'{label} {number} is on this page but in no block; include it (with its number in "ref")')
    return errors


def render(pdf, page, folder):
    path = folder / f'p-{page:02d}.png'
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run(['pdftoppm', '-r', str(DPI), '-png', '-singlefile', '-f', str(page), '-l', str(page), pdf,
                        str(path.with_suffix(''))], check=True, capture_output=True)
    return path


def ocr_text(pdf, page, folder):
    """Text for a page whose PDF has no usable text layer (some NCERT pages are outlines only): tesseract on a
    300 dpi render, cached beside the page images."""
    path = folder / f'p-{page:02d}.ocr.txt'
    if not path.exists() and not shutil.which('tesseract'):
        return ''                                   # no OCR on this host (the Spark): the page image is read anyway
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        image = folder / f'p-{page:02d}-300'
        subprocess.run(['pdftoppm', '-r', '300', '-png', '-singlefile', '-f', str(page), '-l', str(page), pdf,
                        str(image)], check=True, capture_output=True)
        text = subprocess.run(['tesseract', str(image) + '.png', '-', '-l', 'eng', '--psm', '3'], check=True,
                              capture_output=True, text=True).stdout
        image.with_suffix('.png').unlink()
        path.write_text(text)
    return path.read_text()


def with_text_layer(pdf, pages, folder, min_words=30):
    """Pages with almost no extractable words get OCR text instead (marked "ocr")."""
    out = []
    for p in pages:
        if len(re.findall(r'[A-Za-z]{3,}', p['text'])) < min_words:
            text = ocr_text(pdf, p['page'], folder)
            if len(re.findall(r'[A-Za-z]{3,}', text)) >= min_words:
                p = {**p, 'text': text.strip(), 'ocr': True}
        out.append(p)
    return out


def read_page(model, chapter, pages, page, section_at_start, note=''):
    text = next(p['text'] for p in pages if p['page'] == page)
    required = inventory(text, numbering(chapter))
    expected = '; '.join(f'{k}: {", ".join(v)}' for k, v in required.items())
    if humanities(chapter):
        prompt = humanities_page_prompt(chapter, page, section_at_start, expected, note, text)
    else:
        prompt = (
            f'The image is page {page} of NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter '
            f'{chapter["chapter"]} "{chapter["title"]}". Transcribe what this page teaches as blocks, in reading order '
            '(left column top to bottom, then the right column). Be complete and faithful: every definition, law, '
            'equation, derivation, worked example, figure, table, activity, box, summary point and exercise question on '
            'the page, in the book\'s words. Read equations from the image and write them in LaTeX; derivations and '
            'worked examples step by step exactly as printed. Each exercise question is its own block. Do not add '
            'anything the page does not say. Running headers, page numbers and footers are not blocks.\n'
            f'The page starts in section {section_at_start}.'
            + (f' Numbered items code found on this page: {expected}.' if expected else '')
            + (f'\n{note}' if note else '') +
            f'\nReturn JSON: {PAGE_SCHEMA}\n'
            f'PAGE TEXT (extracted from the PDF: columns may be interleaved and equations garbled; use it for exact '
            f'wording and quotes, and the image for equations and layout):\n{text}')
    image = render(chapter['pdf'], page, model.root / 'pages')
    return model.call(f'page-{page:02d}', prompt, images=[image], thinking=0, max_tokens=12000, attempts=3,
                      validate=lambda r: kb.raise_if(page_errors(r, page, pages, numbering(chapter), required)))


def humanities_page_prompt(chapter, page, section_at_start, expected, note, text):
    return (
        f'The image is page {page} of NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter '
        f'{chapter["chapter"]} "{chapter["title"]}" ({chapter["subject"].replace("_", " ")}). Transcribe what this '
        'page teaches as blocks, in reading order (the main text first, then the margin and side boxes in the order '
        'they sit beside it). Be complete and faithful, in the book\'s words: every fact and argument, event (with '
        'its date, place, actors, causes and effects as the book gives them), person, place, key term (the "New '
        'words" boxes are key_term blocks), primary source (each "Source A" box: author, year, and the quoted text), '
        'figure and map (caption and what it shows, enough to redraw it), table, timeline, box, activity, "Discuss" '
        'question and end-of-chapter question. Each question is its own block. Do not add anything the page does not '
        'say, and do not explain or judge it. Running headers, page numbers and footers are not blocks.\n'
        f'The page starts in section {section_at_start}.'
        + (f' Labelled items code found on this page: {expected}.' if expected else '')
        + (f'\n{note}' if note else '') +
        f'\nReturn JSON: {HUMANITIES_PAGE_SCHEMA}\n'
        f'PAGE TEXT (extracted from the PDF: the main text and side boxes may be interleaved; use it for exact '
        f'wording and quotes, and the image for layout, maps and pictures):\n{text}')


def join_blocks(per_page):
    """Blocks in book order with pages; a block marked as running onto the next page is joined with the first
    block of that page when that one is marked as continued and has the same type."""
    blocks = []
    for page, result in per_page:
        for n, b in enumerate(result['blocks']):
            b = {k: v for k, v in b.items() if v not in (None, '', [], {})}
            prev = blocks[-1] if blocks else None
            if (n == 0 and prev and b.get('continued') and prev.get('continues') and prev['type'] == b['type']):
                for key, value in b.items():
                    if key in ('text', 'problem', 'observation', 'shows'):
                        prev[key] = (prev.get(key, '') + ' ' + value).strip()
                    elif key in ('steps', 'given', 'find', 'items', 'procedure', 'materials', 'symbols'):
                        prev[key] = prev.get(key, []) + value
                    elif key == 'ref':
                        prev['ref'] = prev.get('ref', []) + [r for r in value if r not in prev.get('ref', [])]
                    elif key not in prev:
                        prev[key] = value
                prev['continues'] = b.get('continues', False)
                prev['pages'].append(page)
                continue
            b['pages'] = [page]
            blocks.append(b)
    for n, b in enumerate(blocks, 1):
        b.pop('continued', None)
        b.pop('continues', None)
        b = {'id': f'B{n}', **b}
        blocks[n - 1] = b
    return blocks


END_MATTER = re.compile(r'(?m)^\s*(SUMMARY|Summary|POINTS TO PONDER|EXERCISES|Exercises|Write in brief)\s*$')


def make_outline(pages, chapter_no, per_page):
    code = {}
    for p in pages:
        text, end = p['text'], END_MATTER.search(p['text']) if p['page'] > len(pages) / 2 else None
        for sid, title in headings(text[:end.start()] if end else text, chapter_no):
            code.setdefault(sid, {'id': sid, 'title': title, 'pages': [p['page']]})
        if end:
            break                                   # summary and exercises: numbered questions are not sections
    for page, result in per_page:                     # complete titles as read from the image
        for h in result.get('headings') or []:
            sid = str(h.get('id', ''))
            title = str(h.get('title', '')).strip()
            if sid in code and title and (len(title) >= len(code[sid]['title']) - 3 or        # code title cut off,
                                          code[sid]['title'].lower().startswith(title.lower())):   # or run into text
                code[sid]['title'] = h['title']
            elif sid not in code and re.match(rf'^{section_pattern(chapter_no)}$', sid):
                code[sid] = {'id': sid, 'title': h.get('title', ''), 'pages': [page], 'source': 'image'}
    key = lambda s: [int(x) for x in s.split('.')]   # noqa: E731
    outline = [code[s] for s in sorted(code, key=key)]
    for s in outline:
        if s['id'].count('.') >= 2:
            s['parent'] = s['id'].rsplit('.', 1)[0]
    return outline


def read_pages(model, chapter, pages, log):
    chapter_no = numbering(chapter)
    per_page, section = [], 'intro'
    started = time.monotonic()
    for p in pages:
        result = read_page(model, chapter, pages, p['page'], section)
        per_page.append((p['page'], result))
        sections = [b.get('section') for b in result['blocks'] if b.get('section') not in (None, 'intro')]
        if sections:
            section = sections[-1]
    # chapter-level counts: figures (captions can sit on a neighbouring page) and exercise questions
    reread = {}
    for p in pages:
        figs = inventory(p['text'], chapter_no).get('fig', [])
        near = [b for page, r in per_page if abs(page - p['page']) <= 1 for b in r['blocks']]
        missing = [f for f in figs if not any(ref_present(b, 'fig', f) for b in near)]
        if missing:
            reread.setdefault(p['page'], []).append(f'Include the figure(s) {", ".join("Fig. " + f for f in missing)} '
                                                    'as figure blocks with caption and what they show.')
    for page, numbers in missing_exercises(per_page).items():
        for near in (page, page + 1):
            reread.setdefault(near, []).append(f'Exercise question(s) {", ".join(numbers)} seem to be missing (on this '
                                               'page or the next): give every exercise question as its own block.')
    for n, (page, _) in enumerate(per_page):
        if page in reread:
            start = next((b['section'] for _, r in reversed(per_page[:n]) for b in reversed(r['blocks'])
                          if b.get('section') not in (None, 'intro')), 'intro')
            per_page[n] = (page, read_page(model, chapter, pages, page, start, ' '.join(reread[page])))
    blocks = join_blocks(per_page)
    outline = make_outline(pages, chapter_no, per_page)
    log(f'{chapter["id"]} pages: {len(pages)} read ({len(reread)} re-read), {len(blocks)} blocks, '
        f'{len(outline)} sections ({time.monotonic() - started:.0f} s)')
    return blocks, outline


# ------------------------------------------------------------------ 2. concepts
CONCEPT_SCHEMA = '''{"concepts":[{"id":"C1","name":str,"aliases":[str] (other names a teacher, parent or student might
type),"sections":["5.6"],"summary":str (one or two plain sentences),"depth":"mentioned|stated|derived|applied",
"difficulty":"foundation|core|advanced","blocks":["B12",...] (every block that teaches, illustrates or practises it),
"objectives":[str] (what a learner can do after it),"prerequisites":[{"name":str,"where":"this chapter|earlier class|other chapter"}]}]}'''


def concept_errors(result, blocks, outline, tolerate=0.0):
    errors = []
    concepts = result.get('concepts') or []
    known = {b['id'] for b in blocks}
    sections = {s['id'] for s in outline} | {'intro', 'end'}
    if not kb.ids(concepts, 'C'):
        errors.append('concept ids must be C1, C2, ... in order')
    if not 3 <= len(concepts) <= 40:
        errors.append(f'give 3-40 concepts (got {len(concepts)})')
    covered = set()
    for c in concepts:
        cid = c.get('id')
        bad = [x for x in c.get('blocks') or [] if x not in known]
        if bad or not c.get('blocks'):
            errors.append(f'{cid}: "blocks" must list block ids (unknown: {bad[:5]})')
        covered |= set(c.get('blocks') or [])
        if c.get('depth') not in DEPTHS:
            errors.append(f'{cid}: depth must be one of {list(DEPTHS)}')
        if c.get('difficulty') not in DIFFICULTY:
            errors.append(f'{cid}: difficulty must be one of {list(DIFFICULTY)}')
        if not c.get('sections') or any(s not in sections for s in c.get('sections') or []):
            errors.append(f'{cid}: sections must be from the outline {sorted(sections)}')
    names = [str(c.get('name', '')).lower() for c in concepts]
    if len(set(names)) != len(names):
        errors.append('concept names must be distinct')
    missing = [b['id'] for b in blocks if b['id'] not in covered]
    if len(missing) > tolerate * len(blocks):
        errors.append(f'every block must belong to a concept; not covered: {missing[:40]}')
    return errors


def uncovered(concepts, blocks):
    covered = {x for c in concepts for x in c.get('blocks') or []}
    return [b for b in blocks if b['id'] not in covered]


CONTEXT_TYPES = {'box', 'figure', 'fact', 'map', 'source'}   # may stay chapter-level: epigraphs, portraits, whole-chapter history


def assign_errors(result, left, concepts, blocks_total):
    known = {c['id'] for c in concepts}
    errors, context = [], []
    for b in left:
        got = (result.get('assign') or {}).get(b['id'])
        if got == [] and b.get('type') in CONTEXT_TYPES:
            context.append(b['id'])
        elif not isinstance(got, list) or not got or any(c not in known for c in got):
            errors.append(f'{b["id"]}: give the concept ids it belongs to (from {sorted(known)})' +
                          (' or [] if it is chapter-level context such as an epigraph, a portrait or a history note'
                           if b.get('type') in CONTEXT_TYPES else ''))
    if len(context) > max(4, blocks_total // 25):
        errors.append(f'{len(context)} blocks left without a concept ({", ".join(context)}): only epigraphs, portraits '
                      'and notes about the whole chapter may stay unassigned')
    return errors


def compact(block, words=28):
    text = block.get('text') or block.get('problem') or block.get('caption') or block.get('latex') or ''
    text = ' '.join(str(text).split()[:words])
    ref = ', '.join(block.get('ref') or [])
    return f'{block["id"]} [{block["type"]}, {block.get("section", "")}{", " + ref if ref else ""}] ' \
           f'{block.get("title", "")}: {text}'


def make_concepts(model, chapter, blocks, outline):
    if humanities(chapter):
        return make_humanities_concepts(model, chapter, blocks, outline)
    prompt = (
        f'Below are the blocks of NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter {chapter["chapter"]} '
        f'"{chapter["title"]}" in book order, and its sections. Group them into the CONCEPTS the chapter teaches: '
        'the units a teacher, a parent or a student would choose to learn in detail ("Work-energy theorem for a '
        'variable force", "Elastic collisions in one dimension"). A concept is bigger than one definition and '
        'smaller than a whole section when the section holds several ideas. Every block must belong to at least one '
        'concept: worked examples, figures and exercises go with the concept they illustrate or practise (an exercise '
        'may practise several). Depth is how far the book goes: mentioned, stated (without proof), derived, applied '
        '(used in worked problems). Prerequisites are ideas the concept needs, from this chapter or earlier.\n'
        f'Return JSON: {CONCEPT_SCHEMA}\n'
        'SECTIONS:\n' + '\n'.join(f'{s["id"]} {s["title"]}' for s in outline) +
        '\nBLOCKS:\n' + '\n'.join(compact(b) for b in blocks))
    result = model.call('concepts', prompt, thinking=0, max_tokens=16000, attempts=3, system=SYSTEM,
                        validate=lambda r: kb.raise_if(concept_errors(r, blocks, outline, tolerate=0.15)))
    concepts = result['concepts']
    if left := uncovered(concepts, blocks):        # a few blocks left out: place them without redoing everything
        prompt = ('Assign each block below to the concept(s) of this chapter it belongs to (an exercise to the '
                  'concepts it practises). Use [] only for chapter-level context that teaches no concept: an '
                  'epigraph, a portrait, a history note about the whole chapter.\nReturn JSON {"assign":{"B12":["C3"],...}}\nCONCEPTS:\n' +
                  '\n'.join(f'{c["id"]} {c["name"]}: {c.get("summary", "")}' for c in concepts) +
                  '\nBLOCKS:\n' + '\n'.join(compact(b, 60) for b in left))
        assign = model.call('concepts-assign', prompt, thinking=0, max_tokens=3000, attempts=3, system=SYSTEM,
                            validate=lambda r: kb.raise_if(assign_errors(r, left, concepts, len(blocks))))['assign']
        by_id = {c['id']: c for c in concepts}
        for b in left:
            for cid in assign[b['id']]:
                by_id[cid]['blocks'].append(b['id'])
        order = {b['id']: n for n, b in enumerate(blocks)}
        for c in concepts:
            c['blocks'] = sorted(set(c['blocks']), key=order.get)
    return concepts


def make_humanities_concepts(model, chapter, blocks, outline):
    """The same concept step with history and social science wording; leftovers are placed as for science."""
    prompt = (
        f'Below are the blocks of NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter {chapter["chapter"]} '
        f'"{chapter["title"]}" in book order, and its sections. Group them into the CONCEPTS the chapter teaches: '
        'the units a teacher or a student would choose to study or film ("The Napoleonic Code and its effects", '
        '"The Salt March"). A concept is an event, process, idea or development with its causes and consequences: '
        'bigger than one fact, smaller than a whole section when the section holds several. Follow the book\'s own '
        'framing and words. Every block must belong to at least one concept: sources, figures, maps, key terms and '
        'questions go with the concept they illustrate or practise. Depth is how far the book goes: mentioned, '
        'stated (told without causes or evidence), explained (causes, consequences or evidence given), applied (used '
        'in sources or questions). Prerequisites are ideas the concept needs, from this chapter or earlier.\n'
        f'Return JSON: {CONCEPT_SCHEMA}\n'
        'SECTIONS:\n' + '\n'.join(f'{s["id"]} {s["title"]}' for s in outline) +
        '\nBLOCKS:\n' + '\n'.join(compact(b) for b in blocks))
    result = model.call('concepts', prompt, thinking=0, max_tokens=16000, attempts=3, system=HUMANITIES_SYSTEM,
                        validate=lambda r: kb.raise_if(concept_errors(r, blocks, outline, tolerate=0.15)))
    concepts = result['concepts']
    if left := uncovered(concepts, blocks):
        prompt = ('Assign each block below to the concept(s) of this chapter it belongs to (a question to the '
                  'concepts it practises). Use [] only for chapter-level context that teaches no concept: an '
                  'opening picture, an epigraph, a note about the whole chapter.\nReturn JSON {"assign":{"B12":["C3"],...}}\nCONCEPTS:\n' +
                  '\n'.join(f'{c["id"]} {c["name"]}: {c.get("summary", "")}' for c in concepts) +
                  '\nBLOCKS:\n' + '\n'.join(compact(b, 60) for b in left))
        assign = model.call('concepts-assign', prompt, thinking=0, max_tokens=3000, attempts=3,
                            system=HUMANITIES_SYSTEM,
                            validate=lambda r: kb.raise_if(assign_errors(r, left, concepts, len(blocks))))['assign']
        by_id = {c['id']: c for c in concepts}
        for b in left:
            for cid in assign[b['id']]:
                by_id[cid]['blocks'].append(b['id'])
        order = {b['id']: n for n, b in enumerate(blocks)}
        for c in concepts:
            c['blocks'] = sorted(set(c['blocks']), key=order.get)
    return concepts


# ------------------------------------------------------------------ 3. gaps
GAP_SCHEMA = '''{"gaps":[{"concept":"C3","blocks":["B12"],"type":"intuition|skipped_step|prerequisite|misconception|context|visual|oversimplification|history",
"missing":str (what exactly a learner does not get from the book here),"why_it_matters":str,"priority":"high|medium|low",
"resolve":"knowledge|research","research_question":str (research only: specific and searchable)}]}'''


def gap_errors(result, group, blocks, humanities_mode=False):
    errors = []
    gap_types = HUMANITIES_GAP_TYPES if humanities_mode else kb.GAP_TYPES
    facts = ('chronology', 'geography', 'person') if humanities_mode else ('context', 'history')
    gaps = result.get('gaps') or []
    cids = {c['id'] for c in group}
    known = {b['id'] for b in blocks}
    if not gaps:
        errors.append('give at least one gap')
    for cid in sorted(cids):
        if (n := sum(g.get('concept') == cid for g in gaps)) > 3:
            errors.append(f'{cid} has {n} gaps: keep the 3 that matter most')
    for n, g in enumerate(gaps, 1):
        tag = f'gap {n}'
        if g.get('concept') not in cids:
            errors.append(f'{tag}: concept must be one of {sorted(cids)}')
        if any(x not in known for x in g.get('blocks') or []):
            errors.append(f'{tag}: unknown block ids')
        if g.get('type') not in gap_types:
            errors.append(f'{tag}: type must be one of {list(gap_types)}')
        if g.get('resolve') not in ('knowledge', 'research'):
            errors.append(f'{tag}: resolve must be "knowledge" or "research"')
        if g.get('type') in facts and g.get('resolve') != 'research':
            errors.append(f'{tag}: {g.get("type")} gaps need real values or facts: resolve "research" with a question')
        if g.get('resolve') == 'research' and len(str(g.get('research_question', '')).split()) < 5:
            errors.append(f'{tag}: a research gap needs a specific research_question')
    if sum(g.get('resolve') == 'research' for g in gaps) > 2:
        errors.append('at most 2 gaps in this group may need research: keep the 2 most useful '
                      + ('chronology/geography/person gaps' if humanities_mode else 'context/history gaps'))
    return errors


def concept_view(concepts, blocks):
    by_id = {b['id']: b for b in blocks}
    view = []
    for c in concepts:
        members = [by_id[x] for x in c['blocks'] if by_id[x]['type'] != 'exercise']
        exercises = [by_id[x].get('text', '')[:160] for x in c['blocks'] if by_id[x]['type'] == 'exercise']
        view.append({**{k: c[k] for k in ('id', 'name', 'summary', 'depth', 'sections', 'prerequisites') if k in c},
                     'blocks': [{k: v for k, v in b.items() if k not in ('quote', 'section')} for b in members],
                     'exercises': exercises[:6]})
    return json.dumps(view, ensure_ascii=False)


def make_gaps(model, chapter, group, blocks, n):
    if humanities(chapter):
        return make_humanities_gaps(model, chapter, group, blocks, n)
    prompt = (
        f'These concepts are from NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter {chapter["chapter"]} '
        f'"{chapter["title"]}", with everything the book says about them. The textbook defines what must be taught '
        'at this level, but every textbook has gaps. Find where THIS book falls short for a learner meeting these '
        'ideas for the first time (a student, or a parent helping one):\n'
        '- intuition: a law or formula given without the "why";\n'
        '- skipped_step: a derivation or worked example that jumps over a step a learner would stall on;\n'
        '- prerequisite: an idea the book assumes but learners at this level often lack;\n'
        '- misconception: a common wrong idea the book never confronts;\n'
        '- context: missing real-world use, scale or numbers that make the idea matter;\n'
        '- visual: something that only motion or change over time shows well;\n'
        '- oversimplification: a statement simplified in a way that can mislead later;\n'
        '- history: how the idea was discovered, only where it helps understanding.\n'
        'Report real, specific gaps, not generic advice, citing the blocks concerned: at most 3 per concept, the '
        'ones that matter most for understanding. A concept the book treats well may have no gap. Context and history gaps need real values, applications or dates: resolve them by "research" with a '
        'specific, searchable question (at most 2 such gaps in this group, the most useful). Other gaps are resolved '
        'from "knowledge": explanations a good teacher knows.\n'
        f'Return JSON: {GAP_SCHEMA}\nCONCEPTS:\n{concept_view(group, blocks)}')
    return model.call(f'gaps-{n}', prompt, thinking=4000, max_tokens=16000, attempts=3, system=SYSTEM,
                      validate=lambda r: kb.raise_if(gap_errors(r, group, blocks)))


HUMANITIES_GAP_SCHEMA = GAP_SCHEMA.replace(
    'intuition|skipped_step|prerequisite|misconception|context|visual|oversimplification|history',
    '|'.join(HUMANITIES_GAP_TYPES))


def make_humanities_gaps(model, chapter, group, blocks, n):
    """Gaps only where the book is visibly incomplete; the book's coverage and framing are never second-guessed."""
    prompt = (
        f'These concepts are from NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter {chapter["chapter"]} '
        f'"{chapter["title"]}", with everything the book says about them. The book is the authority: what it says '
        'and how it frames it stay as they are. Report a gap ONLY where the book is visibly incomplete for a student '
        'meeting the topic for the first time:\n'
        '- term: a word or idea the book uses but never explains;\n'
        '- chronology: a date, order or duration the narrative needs but does not give;\n'
        '- causation: a jump in a cause-and-effect chain, where the book says what happened but a step is missing;\n'
        '- geography: a place, region or route the text assumes the student can locate;\n'
        '- person: a person named without saying who they were;\n'
        '- prerequisite: an earlier event or idea the book assumes;\n'
        '- context: a fact (a number, a scale) without which the point is hard to grasp;\n'
        '- visual: something a map or timeline would show far better than words.\n'
        'Do not report a different interpretation, a debate among historians, or something the book chose to '
        'leave out: those are not gaps. Cite the blocks concerned, at most 3 gaps per concept; a concept the book '
        'treats fully has none. Chronology, geography and person gaps need real dates, places or facts: resolve them '
        'by "research" with a specific, searchable question (at most 2 research gaps in this group, the most '
        'useful). Other gaps are resolved from "knowledge".\n'
        f'Return JSON: {HUMANITIES_GAP_SCHEMA}\nCONCEPTS:\n{concept_view(group, blocks)}')
    return model.call(f'gaps-{n}', prompt, thinking=4000, max_tokens=16000, attempts=3, system=HUMANITIES_SYSTEM,
                      validate=lambda r: kb.raise_if(gap_errors(r, group, blocks, humanities_mode=True)))


# ------------------------------------------------------------------ 5. additions + calculation check
def real_pow(base, exponent):
    """Powers as in school maths: a negative base to p/q with q odd is the real root ((-8)**(1/3) = -2)."""
    if base < 0 and not float(exponent).is_integer():
        f = Fraction(exponent).limit_denominator(100)
        if f.denominator % 2 and math.isclose(f, exponent, abs_tol=1e-9):
            return (-1) ** f.numerator * abs(base) ** float(f)
        raise ValueError(f'({base})**({exponent}) is not a real number')
    return base ** exponent


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: real_pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
_NAMES = {'pi': math.pi, 'e': math.e, 'g': 9.8}
_FUNCS = {'sqrt': math.sqrt, 'ln': math.log, 'log': math.log, 'log10': math.log10, 'exp': math.exp,
          'sin': lambda x: math.sin(math.radians(x)), 'cos': lambda x: math.cos(math.radians(x)),   # degrees,
          'tan': lambda x: math.tan(math.radians(x)), 'asin': lambda x: math.degrees(math.asin(x)),  # as in books
          'acos': lambda x: math.degrees(math.acos(x)), 'atan': lambda x: math.degrees(math.atan(x)), 'abs': abs}


def evaluate(expr):
    """Arithmetic only: numbers, + - * / **, pi, e, and a few functions."""
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        if isinstance(node, ast.Name) and node.id in _NAMES:
            return _NAMES[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[walk(a) for a in node.args])
        raise ValueError(f'not plain arithmetic: {ast.dump(node)[:60]}')
    value = walk(ast.parse(str(expr).replace('^', '**').replace('×', '*').replace('−', '-'), mode='eval'))
    if isinstance(value, complex):
        raise ValueError('the result is not a real number')
    return value


NUMBER = r'[-−]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*[×x]\s*10\^?[-−]?\d+)?'


def number_value(text):
    text = text.replace('−', '-').replace(',', '')
    m = re.match(r'(-?\d+(?:\.\d+)?)(?:\s*[×x]\s*10\^?(-?\d+))?', text.strip())
    return float(m.group(1)) * (10 ** int(m.group(2)) if m.group(2) else 1)


def computed_results(content):
    """Numbers the content states as the result of a calculation: '= 20 J' where the left side has digits
    ('10 × 4 × 0.5 = 20 J'), not plain givens ('m = 5 kg')."""
    results = []
    parts = re.split(r'[=≈]', content)
    for left, right in zip(parts, parts[1:]):
        m = re.match(rf'\s*({NUMBER})(?![\d.,]|[A-Za-z_(\\])(?!\s*(?:[×x*+/^·−-]|\\times|\\cdot)\s*[\d(\\])', right)   # a bare result
        # the left side ends in arithmetic (a plain number or a bracket), not a symbol such as m_2, v^2 or x2
        if m and re.search(r'((?<![\w^_{}.])\d+(\.\d+)?|\))(\^\d+)?[²³]?\s*\$?\s*$', left):
            results.append(number_value(m.group(1)))
    return results


def close(a, b):
    return math.isclose(a, b, rel_tol=0.02, abs_tol=1e-9)


def calculation_errors(addition):
    errors = []
    values = []
    for c in addition.get('calculations') or []:
        try:
            got = evaluate(c.get('expr', ''))
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError, OverflowError) as exc:
            errors.append(f'calculation "{c.get("expr")}" cannot be evaluated ({exc}); write plain arithmetic')
            continue
        try:
            stated = float(c.get('value'))
        except (TypeError, ValueError):
            errors.append(f'calculation "{c.get("expr")}": value must be a number')
            continue
        if not close(got, stated):
            errors.append(f'calculation "{c.get("expr")}" = {got:.6g}, not {stated}: fix the number in the content too')
        values.append(got)
    for r in computed_results(str(addition.get('content', ''))):
        if not any(close(r, v) for v in values):
            errors.append(f'the content states a computed result {r:g} that is not in "calculations"; '
                          'list it as {"expr": arithmetic, "value": result}')
    return errors


ADDITION_SCHEMA = '''{"additions":[{"gap":"G1","title":str,"content":str (what a teacher adds, written to be taught:
precise, with units and numbers where relevant),"level":"within|extension","provenance":"standard_knowledge|web",
"sources":[{"url":str,"tier":"official|academic|reference|other"}],
"calculations":[{"expr":str (plain arithmetic, e.g. "0.5*2*3**2"; sin, cos, tan take degrees),"value":number,"unit":str}] (every number the
content computes),"textbook_note":str (how it sits with the book: notation kept, or the simplification it refines)}]}'''


def addition_errors(result, gaps, research, lenient=False):
    errors = []
    items = result.get('additions') or []
    want = [g['id'] for g in gaps]
    got = [a.get('gap') for a in items]
    if sorted(got) != sorted(want):
        errors.append(f'give exactly one addition per gap {want} (got {got})')
    for a in items:
        gid = a.get('gap')
        if a.get('level') not in kb.LEVELS:
            errors.append(f'{gid}: level must be "within" or "extension"')
        if a.get('provenance') not in ('standard_knowledge', 'web'):
            errors.append(f'{gid}: provenance must be "standard_knowledge" or "web"')
        if len(str(a.get('content', '')).split()) < 25:
            errors.append(f'{gid}: content must be a teachable explanation (at least 25 words)')
        allowed = set(map(search_agent.canonical_url, (research.get(gid) or {}).get('fetched', [])))
        sources = a.get('sources') or []
        urls = [s.get('url') if isinstance(s, dict) else s for s in sources]
        if a.get('provenance') == 'web':
            bad = [u for u in urls if search_agent.canonical_url(str(u)) not in allowed]
            if not urls or bad:
                errors.append(f'{gid}: web sources must be pages fetched for this gap (not fetched: {bad[:3]})')
            if any(isinstance(s, dict) and s.get('tier') not in TIERS for s in sources):
                errors.append(f'{gid}: source tier must be one of {list(TIERS)}')
        elif sources:
            errors.append(f'{gid}: standard_knowledge has no sources; use provenance "web" to cite')
        number_errors = calculation_errors(a)
        if number_errors and lenient:               # keep the addition, flagged, rather than lose the chapter
            a['number_errors'] = number_errors
        else:
            errors += [f'{gid}: {e}' for e in number_errors]
    return errors


HUMANITIES_RULES = (
    'For this history / social science chapter: fill only what the gap names, briefly; never contradict the book or '
    'reframe it. If a research finding disagrees with the book (a date, a number, an interpretation), leave that '
    'claim out rather than correct the book. Neutral wording: no opinions, praise or blame beyond what the book '
    'says. Dates, places and figures only from the research findings or certain standard knowledge. '
    'Calculations are needed only for numbers you compute (durations, totals); otherwise give [].\n')


def make_additions(model, chapter, group, blocks, gaps, research, n):
    findings = {gid: {k: r.get(k) for k in ('answer', 'cited', 'fetched', 'error')} for gid, r in research.items()}
    rules = HUMANITIES_RULES if humanities(chapter) else ''
    prompt = (
        f'Fill each gap in this NCERT chapter for {kb.audience(chapter["class"])}. For each gap write what a teacher '
        'adds: the missing intuition, the skipped steps worked in full, the prerequisite in brief, the misconception '
        'and its correction, real values with units, the history. Rules: never contradict the book (when it '
        'simplifies, keep its version and present the refinement as such); keep its notation and conventions; '
        '"within" if it is at this class level, "extension" if it goes beyond the syllabus. Use the research '
        'findings for researched gaps and cite only their fetched pages (provenance "web"), giving each source a '
        'tier: official (government, science agencies, standards bodies), academic (universities, journals), '
        'reference (encyclopaedias, textbooks), other; prefer official, academic and reference sources, and do not '
        'rest a figure on an "other" source alone. For the other gaps use standard knowledge (no sources). If a '
        'finding is missing or unreliable, use standard knowledge and do not invent figures. Every number you '
        'compute in the content must also appear in "calculations" as plain arithmetic with its value; code checks '
        'them.\n' + rules +
        f'Return JSON: {ADDITION_SCHEMA}\nCONCEPTS:\n{concept_view(group, blocks)}\n'
        f'GAPS:\n{json.dumps(gaps, ensure_ascii=False)}\nRESEARCH FINDINGS:\n{json.dumps(findings, ensure_ascii=False)}')
    seen = []

    def validate(result):                           # after two tries, wrong numbers are flagged, not fatal
        seen.append(1)
        kb.raise_if(addition_errors(result, gaps, research, lenient=len(seen) >= 3))

    return model.call(f'additions-{n}', prompt, thinking=0, max_tokens=12000, attempts=4, system=system_for(chapter),
                      validate=validate)


# ------------------------------------------------------------------ 6. audit (a different model reads the work)
SCIVID_DATA = HERE.parent / 'scivid-data'
AUDITOR = 'claude-haiku-5-5-openrouter'
AUDIT_SCHEMA = '''{"findings":[{"target":"C3|G4|A7" (the concept, gap or addition at fault),
"problem":"contradicts_book|factual_error|wrong_number|unsupported|not_a_gap|misleading",
"severity":"error|warning","detail":str (what is wrong, citing the block),
"fix":str (concepts: the corrected summary; otherwise how to fix it)}]}'''


def auditor(out):
    """The auditing model from Lesson Studio's model settings (key from its secret store, never printed)."""
    registry = models.Registry(SCIVID_DATA, dict)
    connection = registry.load()['connections'][AUDITOR]
    snapshot = {'steps': {'audit': AUDITOR}, 'connections': {AUDITOR: connection}}
    return guarded(models.client_for(snapshot, 'audit', out, SCIVID_DATA))


def audit_errors(result, known):
    errors = []
    for n, f in enumerate(result.get('findings') or [], 1):
        if f.get('target') not in known:
            errors.append(f'finding {n}: target must be one of the ids given')
        if f.get('problem') not in ('contradicts_book', 'factual_error', 'wrong_number', 'unsupported', 'not_a_gap',
                                    'misleading'):
            errors.append(f'finding {n}: unknown problem type')
        if f.get('severity') not in ('error', 'warning'):
            errors.append(f'finding {n}: severity must be error or warning')
    return errors


def audit_group(model, chapter, group, blocks, gaps, additions, research, n):
    """One independent read of a concept group: everything written about it, against what the book says."""
    ids = {c['id'] for c in group}
    group_gaps = [g for g in gaps if g['concept'] in ids]
    gap_ids = {g['id'] for g in group_gaps}
    group_additions = [a for a in additions if a['gap'] in gap_ids]
    known = ids | gap_ids | {a['id'] for a in group_additions}
    findings_by_gap = {g: {k: research[g].get(k) for k in ('answer', 'cited')} for g in gap_ids if g in research}
    prompt = (
        f'You are auditing a digest of NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter '
        f'{chapter["chapter"]} "{chapter["title"]}". The BLOCKS are what the textbook says (transcribed from its '
        'pages). Another model wrote the CONCEPTS (summaries and objectives), the GAPS (where the book falls short) '
        'and the ADDITIONS (what a teacher adds). Check that work against the book and against established '
        + ('scholarship; the book wins over any outside source' if humanities(chapter) else 'science') + ':\n'
        '- contradicts_book: a summary, objective or addition says something the book contradicts;\n'
        '- factual_error: a statement that is wrong;\n- wrong_number: a value, unit or calculation that is wrong;\n'
        '- unsupported: a specific figure in a web addition that its research findings do not support;\n'
        '- not_a_gap: the book does cover what the gap says is missing;\n'
        '- misleading: true but likely to give a learner a wrong idea.\n'
        'Report only real problems, each with the block that shows it. For a concept, "fix" is the corrected '
        'summary. An empty list is a good answer when the work is sound.\n'
        f'Return JSON: {AUDIT_SCHEMA}\nCONCEPTS:\n{concept_view(group, blocks)}\n'
        f'GAPS:\n{json.dumps(group_gaps, ensure_ascii=False)}\n'
        f'ADDITIONS:\n{json.dumps(group_additions, ensure_ascii=False)}\n'
        f'RESEARCH FINDINGS:\n{json.dumps(findings_by_gap, ensure_ascii=False)}')
    return model.call(f'audit-{n}', prompt, thinking=4000, max_tokens=8000, attempts=3,
                      validate=lambda r: kb.raise_if(audit_errors(r, known)))['findings']


def apply_audit(findings, concepts, gaps, additions):
    """Corrected summaries replace the old; additions with errors go to review; gaps the book covers are dropped."""
    by_concept = {c['id']: c for c in concepts}
    dropped = set()
    for f in findings:
        target, error = f['target'], f['severity'] == 'error'
        if target in by_concept and error and f.get('fix'):
            by_concept[target]['summary'] = f['fix']
        elif target.startswith('A') and error:
            for a in additions:
                if a['id'] == target:
                    a['status'] = 'needs_review'
        elif target.startswith('G') and f['problem'] == 'not_a_gap' and error:
            dropped.add(target)
    gaps[:] = [g for g in gaps if g['id'] not in dropped]
    additions[:] = [a for a in additions if a['gap'] not in dropped]
    for a in additions:
        a['audit'] = [f for f in findings if f['target'] in (a['id'], a['gap'])]
    return dropped


REPAIR_SCHEMA = '''{"addition":{same fields as the addition: "gap","title","content","level","provenance","sources",
"calculations","textbook_note"}}'''


def repair_addition(model, chapter, addition, gap, concept_blocks, findings, research):
    """Fix one addition the audit found wrong; code checks the result like any other addition."""
    found = {gap['id']: research[gap['id']]} if gap['id'] in research else {}
    keep = {k: addition[k] for k in ('gap', 'title', 'content', 'level', 'provenance', 'sources', 'calculations',
                                     'textbook_note') if k in addition}
    prompt = (
        f'This addition to NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter {chapter["chapter"]} '
        f'"{chapter["title"]}" was checked by an auditor, who found the problems below. Rewrite it so every problem '
        'is fixed and nothing else gets worse: keep what was right, correct what was wrong, and drop a claim you '
        'cannot support. Same rules as before: never contradict the book, keep its notation, list every computed '
        'number in "calculations" (plain arithmetic; sin, cos, tan take degrees). Sources are only web pages from '
        'the research findings; with no findings, provenance is "standard_knowledge" and sources is [].\n'
        f'Return JSON: {REPAIR_SCHEMA}\nAUDIT FINDINGS:\n{json.dumps(findings, ensure_ascii=False)}\n'
        f'ADDITION:\n{json.dumps(keep, ensure_ascii=False)}\nGAP:\n{json.dumps(gap, ensure_ascii=False)}\n'
        f'WHAT THE BOOK SAYS:\n{json.dumps(concept_blocks, ensure_ascii=False)}\n'
        f'RESEARCH FINDINGS:\n{json.dumps({g: {k: r.get(k) for k in ("answer", "cited", "fetched")} for g, r in found.items()}, ensure_ascii=False)}')
    def validate(result):
        fixed = result.get('addition') or {}
        fixed['gap'] = gap['id']
        if not found:                               # nothing was researched: it stays standard knowledge
            fixed.update(provenance='standard_knowledge', sources=[])
        result['addition'] = fixed
        kb.raise_if(addition_errors({'additions': [fixed]}, [gap], found))

    return model.call(f'repair-{addition["id"]}', prompt, thinking=4000, max_tokens=8000, attempts=3,
                      system=system_for(chapter),
                      validate=validate)['addition']


def audit_and_repair(text_model, checker, chapter, concepts, blocks, gaps, additions, research, log):
    """Audit every concept group; repair the additions with errors once and audit those again. What is still wrong
    after that stays flagged needs_review."""
    groups = groups_of(concepts, blocks)
    findings = []
    for n, group in enumerate(groups, 1):
        findings += audit_group(checker, chapter, group, blocks, gaps, additions, research, n)
    dropped = apply_audit(findings, concepts, gaps, additions)
    by_block = {b['id']: b for b in blocks}
    by_gap = {g['id']: g for g in gaps}
    by_concept = {c['id']: c for c in concepts}
    errors = {a['id']: [f for f in a.get('audit', []) if f['severity'] == 'error'] for a in additions}
    repaired = []
    for a in additions:
        if not errors[a['id']]:
            continue
        gap = by_gap[a['gap']]
        context = [by_block[x] for x in by_concept[gap['concept']]['blocks'] if by_block[x]['type'] != 'exercise']
        try:
            fixed = repair_addition(text_model, chapter, a, gap, context, errors[a['id']], research)
        except RuntimeError as exc:
            log(f'{chapter["id"]} repair {a["id"]} failed: {exc}')
            continue
        a.update({k: v for k, v in fixed.items() if k != 'gap'}, repaired=True)
        repaired.append(a)
    if repaired:
        concept_ids = {by_gap[a['gap']]['concept'] for a in repaired}
        group = [c for c in concepts if c['id'] in concept_ids]
        recheck = audit_group(checker, chapter, group, blocks, [by_gap[a['gap']] for a in repaired], repaired,
                              research, 'recheck')
        for a in repaired:
            mine = [f for f in recheck if f['target'] in (a['id'], a['gap'])]
            a['audit'] = a.get('audit', []) + [{**f, 'after_repair': True} for f in mine]
            still_wrong = any(f['severity'] == 'error' for f in mine) or calculation_errors(a)
            a['checks']['numbers'] = 'failed' if calculation_errors(a) else 'ok' if a.get('calculations') else 'none'
            a['status'] = 'needs_review' if still_wrong or a['checks']['sources'] == 'weak' else 'accepted'
        findings += [{**f, 'after_repair': True} for f in recheck]
    log(f'{chapter["id"]} audit: {len(findings)} findings, {len(dropped)} gaps dropped, {len(repaired)} additions '
        f'repaired, {sum(a["status"] == "needs_review" for a in additions)} still need review')
    return findings


def audit_existing(chapter, out_root=OUT, log=print, endpoint=LOCAL):
    """Audit a digest already built (for digests made before the audit step, or to re-check)."""
    out = chapter_folder(chapter, out_root)
    d = json.loads((out / 'digest.json').read_text())
    started = time.monotonic()
    d['audit'] = audit_and_repair(chat(endpoint, out, 'text', 3600), auditor(out), chapter, d['concepts'],
                                  d['blocks'], d['gaps'], d['additions'], d['research'], log)
    d['source']['timings_seconds']['audit'] = round(time.monotonic() - started, 1)
    (out / 'digest.json').write_text(json.dumps(d, indent=1, ensure_ascii=False))
    (out / 'digest.md').write_text(markdown(d))
    return d['audit']


# ------------------------------------------------------------------ chapter
def groups_of(concepts, blocks, budget=9000):
    """Consecutive concepts in groups whose block text stays within a budget (words)."""
    by_id = {b['id']: b for b in blocks}
    size = lambda c: sum(len(json.dumps(by_id[x]).split()) for x in c['blocks'] if by_id[x]['type'] != 'exercise')  # noqa: E731
    out, current, total = [], [], 0
    for c in concepts:
        if current and (total + size(c) > budget or len(current) >= 6):
            out.append(current)
            current, total = [], 0
        current.append(c)
        total += size(c)
    return out + ([current] if current else [])


def chapter_folder(chapter, out_root):
    return Path(out_root) / chapter['id'].replace(':', '-')


def stage_pages(chapter, out_root, endpoint, log):
    out = chapter_folder(chapter, out_root)
    out.mkdir(parents=True, exist_ok=True)
    model = chat(endpoint, out, 'pages', 1800)
    pages = with_text_layer(chapter['pdf'], curriculum.chapter_pages(chapter), model.root / 'pages')
    pages = [p for p in pages if p['text'].strip()]
    started = time.monotonic()
    blocks, outline = read_pages(model, chapter, pages, log)
    return {'pages': pages, 'blocks': blocks, 'outline': outline, 'pages_seconds': round(time.monotonic() - started, 1),
            'pages_model': model.model}


def stage_rest(chapter, read, out_root, text_endpoint, research_endpoint, log, audit=True):
    out = chapter_folder(chapter, out_root)
    model = chat(text_endpoint, out, 'text', 3600)
    blocks, outline = read['blocks'], read['outline']
    timings = {'pages': read['pages_seconds']}

    started = time.monotonic()
    concepts = make_concepts(model, chapter, blocks, outline)
    timings['concepts'] = round(time.monotonic() - started, 1)
    log(f'{chapter["id"]} concepts: {len(concepts)} ({timings["concepts"]} s)')

    started = time.monotonic()
    gaps, groups = [], groups_of(concepts, blocks)
    for n, group in enumerate(groups, 1):
        for g in make_gaps(model, chapter, group, blocks, n)['gaps']:
            gaps.append({'id': f'G{len(gaps) + 1}', 'group': n, **g})
    timings['gaps'] = round(time.monotonic() - started, 1)
    log(f'{chapter["id"]} gaps: {len(gaps)} in {len(groups)} groups, '
        f'{sum(g["resolve"] == "research" for g in gaps)} need research ({timings["gaps"]} s)')

    started = time.monotonic()
    research = {}
    todo = [g for g in gaps if g['resolve'] == 'research']
    if todo:
        key = api_key_for(research_endpoint)
        model_id = Chat(research_endpoint, out, api_key=key)._model(search_agent.httpx.Client(
            timeout=30, headers={'Authorization': f'Bearer {key}'} if key else {}))
        tavily = kb.tavily_key()
        for g in todo:
            research[g['id']] = kb.run_research(g, chapter, out, research_endpoint, model_id, key, tavily, log)
    timings['research'] = round(time.monotonic() - started, 1)

    started = time.monotonic()
    additions = []
    for n, group in enumerate(groups, 1):
        group_gaps = [{k: v for k, v in g.items() if k != 'group'} for g in gaps if g['group'] == n]
        if not group_gaps:
            continue
        for k in range(0, len(group_gaps), 4):           # a few gaps per call keeps each answer short
            chunk = group_gaps[k:k + 4]
            found = {g['id']: research[g['id']] for g in chunk if g['id'] in research}
            members = [c for c in group if c['id'] in {g['concept'] for g in chunk}]
            additions += make_additions(model, chapter, members, blocks, chunk, found, f'{n}-{k // 4 + 1}')['additions']
    for n, a in enumerate(additions, 1):
        weak = a.get('provenance') == 'web' and all(isinstance(s, dict) and s.get('tier') == 'other'
                                                    for s in a.get('sources') or [])
        numbers = 'failed' if a.get('number_errors') else 'ok' if a.get('calculations') else 'none'
        a.update(id=f'A{n}', checks={'numbers': numbers, 'sources': 'weak' if weak else 'ok'},
                 status='needs_review' if weak or numbers == 'failed' else 'accepted')
    timings['additions'] = round(time.monotonic() - started, 1)
    log(f'{chapter["id"]} additions: {len(additions)} ({timings["additions"]} s)')

    started = time.monotonic()
    findings = []
    if audit:
        findings = audit_and_repair(model, auditor(out), chapter, concepts, blocks, gaps, additions, research, log)
        timings['audit'] = round(time.monotonic() - started, 1)
    for g in gaps:
        g.pop('group', None)

    digest = {
        'schema': 'textbook_digest_v1',
        'source': {'id': chapter['id'].replace(':', '-'), 'class': chapter['class'], 'subject': chapter['subject'],
                   'book': chapter['book'], 'book_title': chapter['book_title'], 'chapter': chapter['chapter'],
                   'title': chapter['title'], 'pdf': chapter['pdf'], 'pages': len(read['pages']),
                   'models': {'pages': read['pages_model'], 'text': model.model},
                   'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   'builder_version': BUILDER_VERSION, 'timings_seconds': timings},
        'outline': outline, 'blocks': blocks, 'concepts': concepts,
        'chapter_context': [b['id'] for b in uncovered(concepts, blocks)],
        'gaps': gaps, 'additions': additions, 'audit': findings, 'research': research}
    (out / 'digest.json').write_text(json.dumps(digest, indent=1, ensure_ascii=False))
    (out / 'digest.md').write_text(markdown(digest))
    log(f'{chapter["id"]} wrote {out / "digest.md"}')
    return digest


def chat(endpoint, out, label, timeout):
    """A Chat whose model id is known before the first call. The cache key includes the model, and Chat learns it
    only on its first request, so without this a call's key depends on whether earlier calls were cached."""
    key = api_key_for(endpoint)
    model = Chat(endpoint, out, api_key=key)._model(search_agent.httpx.Client(
        timeout=30, headers={'Authorization': f'Bearer {key}'} if key else {}))
    return guarded(Chat(endpoint, out, label=label, model=model, api_key=key, local=True, timeout=timeout))


def guarded(client):
    """A reply of the wrong shape (a string where an object belongs) makes the checks fail with TypeError or
    AttributeError; treat that as a rejected answer, which is retried, instead of a crash."""
    call = client.call

    def checked_call(name, prompt, *, validate=None, **kw):
        def safe(result):
            try:
                return validate(result)
            except (TypeError, AttributeError, IndexError) as exc:
                raise ValueError(f'the JSON does not have the required shape ({exc}); follow the schema exactly') from exc
        return call(name, prompt, validate=safe if validate else None, **kw)

    client.call = checked_call
    return client


def api_key_for(endpoint):
    return os.environ.get('VLLM_API_KEY') if endpoint.startswith('http://127.0.0.1') else None


# ------------------------------------------------------------------ markdown (for reading)
def show_block(b):
    head = f'- **{b["id"]} · {b["type"]}** {b.get("title", "")}' + (f' ({", ".join(b["ref"])})' if b.get('ref') else '') \
        + f' p.{",".join(map(str, b["pages"]))}'
    lines = [head]
    for key in ('text', 'problem'):
        if b.get(key):
            lines.append(f'  {b[key]}')
    if b.get('latex'):
        lines.append(f'  $${b["latex"]}$$')
    for s in b.get('steps') or []:
        lines.append(f'  1. $${s.get("latex", "")}$$ {s.get("reason", "")}')
    if b.get('answer'):
        lines.append(f'  **Answer:** {b["answer"]}')
    if b.get('shows'):
        lines.append(f'  _Shows:_ {b["shows"]}')
    if b.get('items'):
        lines.append('  ' + '; '.join(map(str, b['items'])))
    return lines


def markdown(d):
    s = d['source']
    by_block = {b['id']: b for b in d['blocks']}
    by_gap = {a['gap']: a for a in d['additions']}
    lines = [f'# {s["title"]}', f'NCERT Class {s["class"]} · {s["book_title"]} · Chapter {s["chapter"]} · '
             f'{len(d["blocks"])} blocks · {len(d["concepts"])} concepts · {len(d["gaps"])} gaps', '',
             '## Outline', ''] + [f'- {x["id"]} {x["title"]}' for x in d['outline']] + ['', '## Concepts', '']
    for c in d['concepts']:
        lines += [f'### {c["id"]} · {c["name"]}', f'_{c.get("summary", "")}_ — {c["depth"]}, {c["difficulty"]}, '
                  f'sections {", ".join(c["sections"])}; aliases: {", ".join(c.get("aliases", []))}', '']
        if c.get('prerequisites'):
            lines.append('Prerequisites: ' + '; '.join(f'{p.get("name")} ({p.get("where", "")})' for p in c['prerequisites']))
        for g in [g for g in d['gaps'] if g['concept'] == c['id']]:
            a = by_gap.get(g['id'], {})
            lines += ['', f'**{g["id"]} gap · {g["type"]}** ({g.get("priority", "")}): {g["missing"]}',
                      f'> **{a.get("id", "")} {a.get("title", "")}** ({a.get("level", "")}, '
                      f'{a.get("provenance", "")}, numbers {a.get("checks", {}).get("numbers", "")}): {a.get("content", "")}']
            for src in a.get('sources') or []:
                lines.append(f'> source ({src.get("tier")}): {src.get("url")}' if isinstance(src, dict) else f'> {src}')
        lines.append('')
    lines += ['## Blocks', '']
    for b in d['blocks']:
        lines += show_block(b)
    return '\n'.join(lines) + '\n'


# ------------------------------------------------------------------ runner
def run(refs, out_root=OUT, pages_endpoint=LOCAL, text_endpoint=LOCAL, research_endpoint=LOCAL, log=print, lanes=1):
    """Build each chapter's digest; `lanes` chapters at a time (web research mostly waits on fetches, so the GPU
    serves several chapters at once). A chapter that fails is logged and the run goes on."""
    root = Settings.from_env().ncert_root
    chapters = [curriculum.find(root, r) for r in refs]
    failures = []

    def build_one(c):
        if (chapter_folder(c, out_root) / 'digest.json').exists():
            log(f'{c["id"]} already done')
            return
        started = time.monotonic()
        try:
            read = stage_pages(c, out_root, pages_endpoint, log)
            stage_rest(c, read, out_root, text_endpoint, research_endpoint, log)
            log(f'{c["id"]} DONE in {(time.monotonic() - started) / 60:.1f} min')
        except Exception as exc:                  # noqa: BLE001 - one bad chapter must not stop the run
            failures.append((c['id'], str(exc)))
            log(f'{c["id"]} FAILED: {exc}')

    with ThreadPoolExecutor(max_workers=lanes) as pool:
        list(pool.map(build_one, chapters))
    return failures


SUBJECT_ORDER = ('physics', 'maths', 'chemistry', 'biology', 'science')
CLASS_ORDER = (12, 11, 10, 9, 8, 7, 6)


def corpus():
    """Every Science and Maths chapter, Classes 11-12 first (equation-heavy subjects first), then 9-10, then 6-8."""
    chapters = curriculum.catalog(Settings.from_env().ncert_root)
    rank = lambda c: (CLASS_ORDER.index(c['class']) // 2 if c['class'] >= 9 else 3,   # noqa: E731
                      SUBJECT_ORDER.index(c['subject']), -c['class'], c['book'], c['chapter'])
    return [c['id'] for c in sorted(chapters, key=rank)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('chapters', nargs='*', help='Lesson Studio chapter ids, e.g. keph1:05 (none: the whole corpus)')
    parser.add_argument('--lanes', type=int, default=1, help='chapters built at the same time')
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--pages-endpoint', default=LOCAL, help='vision server for page reading')
    parser.add_argument('--text-endpoint', default=LOCAL, help='server for concepts, gaps and additions')
    parser.add_argument('--research-endpoint', default=LOCAL, help='tool-calling server for the search agent')
    parser.add_argument('--audit-only', action='store_true', help='audit digests that are already built')
    args = parser.parse_args(argv)
    log = lambda m: print(time.strftime('%H:%M:%S'), m, flush=True)  # noqa: E731
    if args.audit_only:
        root = Settings.from_env().ncert_root
        for ref in args.chapters:
            audit_existing(curriculum.find(root, ref), args.out, log)
        return 0
    refs = args.chapters or corpus()
    log(f'{len(refs)} chapters, {args.lanes} at a time')
    failures = run(refs, args.out, args.pages_endpoint, args.text_endpoint, args.research_endpoint, log, args.lanes)
    for cid, err in failures:
        log(f'failed {cid}: {err}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
