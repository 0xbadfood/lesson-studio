"""What History Studio offers, and how one concept becomes a film request.

The unit of a film is one concept of a textbook digest (textbook-digest/<chapter>/digest.json). The film is rooted in
the book: its first source is the book's own text for the concept, read whole; the other sources are the digest's
accepted additions (gaps the book leaves, each checked). Coverage points come from what the book teaches about the
concept, and the film's length comes from how much there is to cover, not from the viewer, with no upper cap.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGESTS = ROOT / 'textbook-digest'
SUBJECTS = {'history', 'geography', 'political_science', 'economics', 'sociology', 'social_science'}
SUBJECT_NAMES = {'history': 'History', 'geography': 'Geography', 'political_science': 'Political Science',
                 'economics': 'Economics', 'sociology': 'Sociology', 'social_science': 'Social Science'}
NOT_TAUGHT = {'exercise', 'discuss', 'activity'}       # questions practise a concept; they are not narrated
WORDS_PER_MINUTE = 123                                  # measured: Salt March 120, Unification of Italy 127 (2026-10-15)
SHORTEST = 90                                           # a concept film runs at least 1.5 minutes; no upper cap:
                                                        # it runs as long as its coverage needs (user, 2026-10-15)
NCERT_PDF = 'https://ncert.nic.in/textbook/pdf/{code}.pdf'


def _says(block):
    return ' '.join(str(block.get(k, '')) for k in ('title', 'term', 'name', 'quote', 'text')).lower()


def linked_blocks(digest, concept, own):
    """Blocks elsewhere in the chapter that the concept's objectives need: an alias the objectives name that none of
    the concept's own blocks mention, found in another block's title or quote (at most 3 per term). The digest assigns
    each block to one concept, so 'from the Zollverein to the German Empire' (Unification of Germany) had no
    Zollverein text and the film's evidence review could never pass (2026-10-17)."""
    objectives = ' '.join(concept.get('objectives') or []).lower()
    said = ' '.join(_says(b) for b in own)
    have = {b['id'] for b in own}
    out = []
    for alias in concept.get('aliases') or []:
        term = alias.lower().strip()
        if len(term) < 4 or term not in objectives or term in said:
            continue
        hits = [b for b in digest['blocks'] if b['id'] not in have and b['type'] not in NOT_TAUGHT
                and term in (str(b.get('title', '')) + ' ' + str(b.get('quote', ''))).lower()]
        for b in hits[:3]:
            have.add(b['id'])
            out.append(b)
    return out


def teaching_blocks(digest, concept, linked=True):
    by_id = {b['id']: b for b in digest['blocks']}
    own = [by_id[x] for x in concept['blocks'] if x in by_id and by_id[x]['type'] not in NOT_TAUGHT]
    if not linked:
        return own
    extra = linked_blocks(digest, concept, own)
    if not extra:
        return own
    order = {b['id']: n for n, b in enumerate(digest['blocks'])}
    return sorted(own + extra, key=lambda b: order[b['id']])          # the book's reading order


def teaching_ids(digest, concept):
    return [b['id'] for b in teaching_blocks(digest, concept)]


def words(blocks):
    return sum(len(str(b.get('text', '')).split()) for b in blocks)


def additions_for(digest, concept):
    gaps = {g['id'] for g in digest['gaps'] if g['concept'] == concept['id']}
    return [a for a in digest['additions'] if a['gap'] in gaps and a.get('status') == 'accepted']


def filmable(digest, concept):
    """A concept a film can teach: chapter reviews and question sets are not."""
    name = concept['name'].lower()
    return words(teaching_blocks(digest, concept)) >= 100 and not re.search(r'\b(assessment|review|exercises)\b', name)


def film_seconds(digest, concept):
    """Length from coverage: the narration runs about as long as the book's own text for the concept (measured 0.95x on
    the first two films: 459 s predicted vs 456 s, 304 s vs 305 s), plus room for each gap the film fills and for an
    opening and a close."""
    narration = .95 * words(teaching_blocks(digest, concept)) + 30 * len(additions_for(digest, concept)) + 60
    seconds = narration / WORDS_PER_MINUTE * 60
    return int(max(SHORTEST, round(seconds / 15) * 15))


@lru_cache(maxsize=64)
def _load(path, mtime):
    return json.loads(Path(path).read_text())


def digests(root=None):
    out = []
    for path in sorted(Path(root or DIGESTS).glob('*/digest.json')):
        d = _load(str(path), path.stat().st_mtime)
        if d['source'].get('subject') in SUBJECTS:
            out.append(d)
    return out


def digest_for(chapter_id, root=None):
    for d in digests(root):
        if d['source']['id'] == chapter_id:
            return d
    raise KeyError(chapter_id)


def catalog(root=None):
    """Classes -> subjects -> chapters -> concepts, for the chooser."""
    classes = {}
    for d in digests(root):
        s = d['source']
        order = {b['id']: n for n, b in enumerate(d['blocks'])}
        first = lambda c: min((order.get(b['id'], 1e9) for b in teaching_blocks(d, c, linked=False)),  # noqa: E731
                              default=1e9)
        concepts = [{'id': c['id'], 'name': c['name'], 'summary': c.get('summary', ''),
                     'minutes': round(film_seconds(d, c) / 60, 1), 'sections': c.get('sections', [])}
                    for c in sorted(d['concepts'], key=first) if filmable(d, c)]       # in the book's order
        chapter = {'id': s['id'], 'number': s['chapter'], 'title': s['title'], 'book': s['book_title'],
                   'concepts': concepts}
        subject = classes.setdefault(s['class'], {}).setdefault(s['subject'], {
            'id': s['subject'], 'name': SUBJECT_NAMES.get(s['subject'], s['subject']), 'chapters': []})
        subject['chapters'].append(chapter)
    return [{'class': k, 'subjects': [{**v, 'chapters': sorted(v['chapters'], key=lambda c: c['number'])}
                                      for v in sorted(subjects.values(), key=lambda v: v['name'])]}
            for k, subjects in sorted(classes.items())]


def coverage(digest, concept):
    """What the film must teach: the concept's learning objectives, then the key terms, events and people the book
    gives for it, in book order."""
    points = [f'Objective: {o}' for o in concept.get('objectives') or []]
    for b in teaching_blocks(digest, concept):
        if b['type'] == 'key_term':
            points.append(f'Key term: {b.get("term") or b.get("title")} - {b.get("meaning") or b.get("text", "")}')
        elif b['type'] == 'event':
            when = f' ({b["date"]})' if b.get('date') else ''
            points.append(f'Event: {b.get("title")}{when} - {b.get("text", "")[:160]}')
        elif b['type'] == 'person':
            points.append(f'Person: {b.get("name") or b.get("title")} - {b.get("role") or b.get("text", "")[:120]}')
    seen, unique = set(), []
    for p in points:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)
    return [{'id': f'K{n}', 'point': p} for n, p in enumerate(unique, 1)]


def book_text(digest, concept):
    """The book's own words for the concept, in reading order, with the page of each block."""
    lines = []
    for b in teaching_blocks(digest, concept):
        label = {'source': 'Primary source', 'figure': 'Figure', 'map': 'Map', 'key_term': 'Key term',
                 'box': 'Box'}.get(b['type'], b['type'].replace('_', ' ').title())
        head = f'[{label}, p.{",".join(map(str, b.get("pages", [])))}] {b.get("title", "")}'.strip()
        body = b.get('text') or b.get('caption') or ''
        if b['type'] in ('figure', 'map') and b.get('shows'):
            body = f'{b.get("caption", "")} Shows: {b["shows"]}'
        if b['type'] == 'source' and b.get('author'):
            head += f' ({b["author"]}{", " + str(b["year"]) if b.get("year") else ""})'
        if b.get('items'):
            body += ' ' + '; '.join(map(str, b['items']))
        lines.append(f'{head}\n{body}'.strip())
    return '\n\n'.join(lines)


def film_request(digest, concept):
    """The curriculum record and sources History Studio submits to the film queue."""
    s = digest['source']
    code = Path(s['pdf']).stem
    record = {'kind': 'textbook_concept', 'chapter_id': s['id'], 'concept_id': concept['id'],
              'concept': concept['name'], 'summary': concept.get('summary', ''),
              'audience': f'Class {s["class"]} students in India (NCERT/CBSE)',
              'book': f'Class {s["class"]} {SUBJECT_NAMES.get(s["subject"], s["subject"])}: {s["book_title"]}',
              'chapter_no': s['chapter'], 'chapter': s['title'], 'coverage': coverage(digest, concept),
              'seconds': film_seconds(digest, concept)}
    pages = sorted({p for b in teaching_blocks(digest, concept) for p in b.get('pages', [])})
    sources = [{'url': NCERT_PDF.format(code=code), 'complete': True,
                'title': f'NCERT {record["book"]}, Chapter {s["chapter"]} "{s["title"]}", pages {", ".join(map(str, pages))}',
                'raw_content': book_text(digest, concept)}]
    for a in additions_for(digest, concept):
        urls = [x['url'] for x in a.get('sources') or [] if isinstance(x, dict) and x.get('url')]
        sources.append({'url': urls[0] if urls else f'{NCERT_PDF.format(code=code)}#note-{a["gap"].lower()}',
                        'complete': True, 'title': f'Teacher\'s note: {a["title"]}',
                        'raw_content': a['content'] + (('\nSources: ' + ', '.join(urls)) if urls else '')})
    subject = f'{concept["name"]} (NCERT Class {s["class"]} {SUBJECT_NAMES.get(s["subject"], "")}, {s["title"]})'
    return {'subject': subject[:300], 'record': record, 'sources': {'results': sources}}
