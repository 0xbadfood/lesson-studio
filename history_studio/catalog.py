"""What History Studio (and Chemistry Studio, the same code with another profile) offers, and how one concept becomes a
film request.

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
SUBJECTS = {'history', 'political_science', 'economics', 'sociology', 'social_science'}   # Humanities Studio
SUBJECT_NAMES = {'history': 'History', 'geography': 'Geography', 'political_science': 'Political Science',
                 'economics': 'Economics', 'sociology': 'Sociology', 'social_science': 'Social Science',
                 'chemistry': 'Chemistry', 'biology': 'Biology', 'physics': 'Physics', 'science': 'Science', 'maths': 'Maths',
                 'beyond': 'Beyond the book'}
# Class 6-10 have one Science book; each chapter belongs to one subject studio, by what it teaches (user, 2026-10-24:
# no duplicates). The opening "world of science" chapters go to Chemistry, the lightest of the three.
SCIENCE_SPLIT = {
    'physics': ['fecu1-04', 'fecu1-05', 'fecu1-07', 'fecu1-12', 'gecu1-03', 'gecu1-07', 'gecu1-08',
                'gecu1-11', 'gecu1-12', 'hecu1-04', 'hecu1-05', 'hecu1-06', 'hecu1-10', 'hecu1-11', 'iesc1-04',
                'iesc1-06', 'iesc1-07', 'iesc1-10', 'jesc1-09', 'jesc1-10', 'jesc1-11', 'jesc1-12'],
    'chemistry': ['fecu1-01', 'gecu1-01', 'hecu1-01', 'iesc1-01', 'fecu1-06', 'fecu1-08', 'fecu1-09', 'gecu1-02', 'gecu1-04', 'gecu1-05', 'hecu1-07', 'hecu1-08',
                  'hecu1-09', 'iesc1-05', 'iesc1-08', 'iesc1-09', 'jesc1-01', 'jesc1-02', 'jesc1-03', 'jesc1-04'],
    'biology': ['fecu1-02', 'fecu1-03', 'fecu1-10', 'fecu1-11', 'gecu1-06', 'gecu1-09', 'gecu1-10', 'hecu1-02',
                'hecu1-03', 'hecu1-12', 'hecu1-13', 'iesc1-02', 'iesc1-03', 'iesc1-11', 'iesc1-12', 'iesc1-13',
                'jesc1-05', 'jesc1-06', 'jesc1-07', 'jesc1-08', 'jesc1-13'],
}
# A studio is one profile of this code (slug: its path under the learn.photovault.live shell): its subjects, its own data folder (access code, films), cookie and job names.
# Chemistry films also get exact figures (code-drawn chemistry and credited Commons diagrams, 2026-10-19).
PROFILES = {
    # Humanities Studio (renamed from History Studio, 2026-10-24): history, political science, economics, sociology
    # and the combined social science books, at history.photovault.live. Geography has its own studio (maps).
    'history': {'name': 'Humanities Studio', 'slug': 'humanities', 'mark': 'H', 'subjects': SUBJECTS, 'data': 'history-data',
                'cookie': 'history_session', 'job': 'history', 'textbook': 'humanities', 'figures': False,
                'questions': True},              # Test yourself: creative questions on a finished film (2026-10-22)
    # Geography Studio (2026-10-24): its own studio because of maps (code-drawn, India's boundaries; map kit to come).
    'geography': {'name': 'Geography Studio', 'slug': 'geography', 'mark': 'G', 'subjects': {'geography'}, 'data': 'geography-data',
                  'cookie': 'geography_session', 'job': 'geography', 'figures': False, 'questions': True},
    'chemistry': {'name': 'Chemistry Studio', 'slug': 'chemistry', 'mark': 'C', 'subjects': {'chemistry'}, 'data': 'chemistry-data',
                  'cookie': 'chemistry_session', 'job': 'chemistry', 'figures': True,
                  'key_ideas': True,             # simplified films of a finished film's key ideas (2026-10-20)
                  'questions': True},
    # Biology Studio (2026-10-22): Class 11-12 Biology; films get the ~/biology SVG library's diagrams as figures.
    'biology': {'name': 'Biology Studio', 'slug': 'biology', 'mark': 'B', 'subjects': {'biology'}, 'data': 'biology-data',
                'cookie': 'biology_session', 'job': 'biology', 'figures': 'biology', 'key_ideas': True,
                'questions': True},
    # Physics Studio (2026-10-23): Class 11-12 Physics, and Solve: JEE questions solved by two students and a teacher
    # model, checked against the official key, then planned as worked-solution clips with their drawing aids.
    'physics': {'name': 'Physics Studio', 'slug': 'physics', 'mark': 'P', 'subjects': {'physics'}, 'data': 'physics-data',
                'cookie': 'physics_session', 'job': 'physics', 'figures': 'book', 'key_ideas': True,
                'questions': True, 'solve': 'physics', 'linkwork': 'physics', 'plays': True},
    # Maths Studio (2026-10-24): Class 11-12 Maths concept and key-idea films; Solve for maths comes with questions.
    'maths': {'name': 'Maths Studio', 'slug': 'maths', 'mark': 'M', 'subjects': {'maths'}, 'data': 'maths-data',
              'cookie': 'maths_session', 'job': 'maths', 'figures': 'book', 'key_ideas': True, 'questions': True, 'linkwork': 'maths'},
}
NOT_TAUGHT = {'exercise', 'discuss', 'activity', 'ponder_point'}   # questions practise a concept; not narrated
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


# Words an objective uses to set a task, not to name what is taught.
TASK_WORDS = {'problems', 'involving', 'situations', 'examples', 'numerical', 'numericals', 'calculate', 'identify',
              'distinguish', 'explain', 'describe', 'understand', 'between', 'different', 'various', 'including',
              'related', 'questions', 'everyday', 'applications', 'exercise', 'exercises', 'activity',
              'justify', 'determine', 'classify', 'predict', 'estimate', 'compute', 'simplify', 'statement',
              'statements', 'compare', 'discuss', 'suggest', 'arrange', 'imagine', 'provide', 'propose', 'contrast',
              'whether', 'chapter', 'multiple', 'missing', 'correct', 'correctly', 'methods', 'solution', 'solutions',
              'measure', 'project', 'projects', 'interest', 'reflect', 'features', 'advantages', 'disadvantages',
              'conditions', 'knowledge'}


def asked_exercises(digest, concept, taught):
    """The concept's own exercises that carry a thing its objectives name and its teaching text never mentions. The
    digest writes objectives from all of a concept's blocks, questions included: Laws of Motion C3's objective asks for
    "collisions, recoil, and disintegration", and only Exercise 4.17 (a nucleus at rest splits in two) says
    disintegration, so with the exercises left out every evidence brief was refused for the missing source (2026-10-29)."""
    # The thing must be one the chapter's teaching never says at all, not just this concept's: words that set a task
    # ('compare', 'answer', 'define') are said somewhere in any chapter, so they never bring a question in.
    said = ' '.join(_says(b) + ' ' + str(b.get('meaning', '')) for b in taught + [
        b for b in digest['blocks'] if b['type'] not in NOT_TAUGHT])
    stems = {w[:8] for w in re.findall(r'[a-z]{7,}', ' '.join(concept.get('objectives') or []).lower())
             if w not in TASK_WORDS} - {w[:8] for w in re.findall(r'[a-z]{7,}', said)}
    by_id = {b['id']: b for b in digest['blocks']}
    out = []
    for x in concept.get('blocks') or []:
        b = by_id.get(x)
        if b and b['type'] == 'exercise' and stems & {w[:8] for w in re.findall(r'[a-z]{7,}', _says(b))}:
            out.append(b)
    return out[:3]


def teaching_ids(digest, concept):
    return [b['id'] for b in teaching_blocks(digest, concept)]


def words(blocks):
    return sum(len(str(b.get('text', '')).split()) for b in blocks)


def additions_for(digest, concept):
    gaps = {g['id'] for g in digest['gaps'] if g['concept'] == concept['id']}
    return [a for a in digest['additions'] if a['gap'] in gaps and a.get('status') == 'accepted']


# What makes a concept filmable is decided once, when the digest is built, and stamped on the concept, so the studios,
# the run scripts and the night jobs agree (user, 2026-10-29: "the concepts that are not filmable should be marked at
# digest level and should not really be shown in the studios"). A stamp from an older rule is worked out afresh.
FILM_RULE = 1


def film_status(digest, concept):
    """'' for a concept a film can teach, else why not."""
    if re.search(r'\b(assessment|review|exercises)\b', concept['name'].lower()):
        return 'a chapter review or question set: its questions belong with the solutions'
    by_id = {b['id']: b for b in digest['blocks']}
    own = [by_id[x] for x in concept['blocks'] if x in by_id]
    if own and all(b['type'] in NOT_TAUGHT for b in own):
        return 'questions only (exercises): they belong with the solutions'
    n = words(teaching_blocks(digest, concept))
    if n < 100:
        kinds = sorted({b['type'] for b in own}) or ['no blocks']
        return f'{n} words of teaching text ({", ".join(kinds)}): too little for a film; its teaching sits in another concept'
    return ''


def mark_filmable(digest):
    """Stamp each concept's filmable and film_note; True when anything changed."""
    changed = False
    for c in digest['concepts']:
        note = film_status(digest, c)
        stamp = {'filmable': not note, 'film_note': note, 'film_rule': FILM_RULE}
        if any(c.get(k) != v for k, v in stamp.items()):
            c.update(stamp)
            changed = True
    return changed


def filmable(digest, concept):
    """A concept a film can teach: chapter reviews, question sets and concepts with almost no text are not."""
    if concept.get('film_rule') == FILM_RULE:
        return concept['filmable']
    return not film_status(digest, concept)


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


# Class 6-9 "Exploring Society" books mix history, geography and civics; their geography chapters (maps) belong to
# Geography Studio, whatever the digest labelled them (2026-10-24).
SOCIETY_GEOGRAPHY = {'fees1-02', 'fees1-03', 'gees1-01', 'gees1-02', 'gees1-03', 'gees2-01', 'gees2-02', 'hees2-01',
                     'hees2-06', 'hees2-07', 'iest1-02', 'iest1-03'}


def subjects_of(source):
    """The studio subjects a chapter belongs to: its own; for a Class 6-10 Science chapter, what it teaches; for a
    geography chapter of the combined social science books, geography; for a topic, the studio it names."""
    if source.get('kind') == 'topic':
        return {source['studio']}
    if source.get('id') in SOCIETY_GEOGRAPHY:
        return {'geography'}
    if source.get('subject') == 'science':
        return {s for s, ids in SCIENCE_SPLIT.items() if source.get('id') in ids}
    return {source.get('subject')}


# Beyond the book (2026-10-25): topics written from cited sources (a reviewer asked for a heart procedure explained to
# parents) load like chapters, in the class and studio they name, with their own audience, sources and figures.
TOPICS = ROOT / 'topics'


def digests(root=None, subjects=SUBJECTS):
    out = []
    paths = sorted(Path(root or DIGESTS).glob('*/digest.json')) + ([] if root else sorted(TOPICS.glob('*/digest.json')))
    for path in paths:
        d = _load(str(path), path.stat().st_mtime)
        if subjects_of(d['source']) & set(subjects):
            out.append(d)
    return out


def digest_for(chapter_id, root=None, subjects=SUBJECTS):
    for d in digests(root, subjects):
        if d['source']['id'] == chapter_id:
            return d
    raise KeyError(chapter_id)


def catalog(root=None, subjects=SUBJECTS):
    """Classes -> subjects -> chapters -> concepts, for the chooser."""
    classes = {}
    for d in digests(root, subjects):
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
        elif b['type'] in ('definition', 'law', 'principle', 'theorem'):       # science chapters
            points.append(f'{b["type"].title()}: {b.get("title")} - {b.get("text", "")[:160]}')
        elif b['type'] == 'equation' and b.get('latex'):
            ref = ', '.join(b.get('ref') or [])
            points.append(f'Equation{" " + ref if ref else ""}: {b.get("title")} - {b["latex"]}')
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
        where = (f', {b["source"]["title"]}' if isinstance(b.get('source'), dict) else       # a topic cites its source
                 f', p.{",".join(map(str, b.get("pages", [])))}')
        head = f'[{label}{where}] {b.get("title", "")}'.strip()
        body = b.get('text') or b.get('meaning') or b.get('caption') or ''   # some key terms carry only 'meaning'
        if b['type'] in ('figure', 'map') and b.get('shows'):
            body = f'{b.get("caption", "")} Shows: {b["shows"]}'
        # A table's rows are in 'shows' (658 of 841 tables had no rows anywhere else): without them a film saw only
        # its title, and Class 10 Light C3's brief could not say what image each object position gives (2026-10-28).
        if b['type'] == 'table' and b.get('shows') and str(b['shows'])[:60] not in body:
            body = f'{body} Shows: {b["shows"]}'.strip()
        if b['type'] == 'figure' and b.get('section') == 'end':    # its meaning is the exercise's question
            head = head.replace('[Figure', '[Exercise figure', 1)
            body += (f' It belongs to an end-of-chapter exercise ("{b.get("quote", "")}"), not to the teaching: '
                     'its drawings are the question, and may be ones the student must spot as impossible.')
        if b['type'] == 'source' and b.get('author'):
            head += f' ({b["author"]}{", " + str(b["year"]) if b.get("year") else ""})'
        if b.get('latex'):                                   # science: the book's equation, as printed
            body += f' [Equation: {b["latex"]}]'
        if b['type'] == 'worked_example' and b.get('problem'):
            steps = ' '.join(str(x.get('latex', '')) for x in b.get('steps') or [] if isinstance(x, dict))
            body = (f'Problem: {b["problem"]} Given: {"; ".join(map(str, b.get("given") or []))} '
                    f'Working: {steps} Answer: {b.get("answer", "")}').strip()
        if b.get('items'):
            body += ' ' + '; '.join(map(str, b['items']))
        lines.append(f'{head}\n{body}'.strip())
    for b in asked_exercises(digest, concept, teaching_blocks(digest, concept)):
        lines.append(f'[Exercise, p.{",".join(map(str, b.get("pages", [])))}] {b.get("title", "")}\n{b.get("text", "")} '
                     'This end-of-chapter question is the only place the book takes the concept to this case: the film '
                     'may show the situation it poses, worked with the concept\'s own law; the book prints no answer.')
    return '\n\n'.join(lines)


# Animated beats are coded by Lesson Studio's coder in its sandbox, with the Manim environment its service uses
# (lesson-studio.service: SCIVID_MANIM_PYTHON, SCIVID_PYTHON_BASE) and its model settings (user, 2026-10-20).
ANIMATION = {'manim_python': str(ROOT / '.venv' / 'bin' / 'python'), 'python_base': '/home/nitin/.pyenv/versions/3.11.15',
             'scivid_data': str(ROOT / 'scivid-data'), 'kits': ['chem']}


EXTRAS = ROOT / 'textbook-digest'


def book_figures(digest, concept):
    """The book's numbered figures that this concept teaches from, as figure-library entries: the exact SVG cut from
    the PDF's own drawing (book_extras.py), or its PNG crop for a photograph. Read from the digest's index, never the
    PDF (user, 2026-10-24: Physics and Maths films show the book's figures and LaTeX equations)."""
    import sqlite3
    s = digest['source']
    # An exercise's figure is its question (Fig. 2.10 of keph1-02: graphs that cannot be motion), so films leave it
    # to the solutions phase; a figure whose crop misses some of its named parts (a) to (d) stays out too.
    blocks = {r: b for b in teaching_blocks(digest, concept) if b.get('type') == 'figure' and b.get('section') != 'end'
              for r in (b.get('ref') or [])}
    refs = list(blocks)
    if not refs or not (EXTRAS / 'extras.sqlite3').exists():
        return []
    db = sqlite3.connect(f'file:{EXTRAS / "extras.sqlite3"}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    out = []
    for ref in dict.fromkeys(refs):
        row = db.execute('SELECT * FROM figures WHERE chapter = ? AND ref = ?', (s['id'], ref)).fetchone()
        if not row or ('incomplete' in row.keys() and row['incomplete']):
            continue
        drawn = row['svg'] if row['svg'] and row['svg_kind'] == 'vector' else row['image']
        if not drawn or not (EXTRAS / drawn).exists():
            continue
        caption = re.sub(r'^Fig\.?\s*[\d.]+\s*', '', row['caption'] or '').strip()
        shows = ' '.join(str(blocks[ref].get(k) or '') for k in ('caption', 'shows')).strip()
        shows = re.sub(r'^Fig\.?\s*[\d.]+\s*', '', shows)
        about = shows if caption[:40] in shows else f'{caption} {shows}'.strip()
        if not about:                    # a figure nobody can say anything about is no use to a planner
            continue
        out.append({'id': re.sub(r'[^A-Za-z0-9]+', '-', ref).strip('-'), 'name': ref,
                    'description': about[:400], 'file': str(EXTRAS / drawn),
                    'credit': f'NCERT Class {s["class"]} {SUBJECT_NAMES.get(s["subject"], s["subject"])}, {ref}'})
    db.close()
    return out


def film_request(digest, concept, figures=False):
    """The curriculum record and sources the studio submits to the film queue. `figures`: give the film exact figures:
    True (Chemistry Studio) for code-drawn chemistry and the Commons diagrams that match this concept, 'biology'
    (Biology Studio) for the biology library's diagrams of this chapter, 'book' (Physics and Maths Studios) for LaTeX
    equations and the book's own figures this concept teaches from (exact SVGs from the digest's index)."""
    s = digest['source']
    if s.get('kind') == 'topic':
        return topic_request(digest, concept, figures)
    code = Path(s['pdf']).stem
    record = {'kind': 'textbook_concept', 'chapter_id': s['id'], 'concept_id': concept['id'],
              'concept': concept['name'], 'summary': concept.get('summary', ''),
              'audience': f'Class {s["class"]} students in India (NCERT/CBSE)',
              'book': f'Class {s["class"]} {SUBJECT_NAMES.get(s["subject"], s["subject"])}: {s["book_title"]}',
              'chapter_no': s['chapter'], 'chapter': s['title'], 'coverage': coverage(digest, concept),
              'seconds': film_seconds(digest, concept)}
    if figures == 'biology':                     # Biology Studio: the ~/biology diagrams this chapter cites
        from figure_library import biology, visuals
        related = [a.split(':', 1)[1] for a in visuals.related_assets(s['id'], concept['id'])]
        record['figures'] = {'subject': 'biology', 'code_root': str(ROOT), 'level': biology.level_for(s['class']),
                             'library': biology.candidates(s['id'], s['class'], extra=related)}
    elif figures == 'book':
        record['figures'] = {'subject': s['subject'], 'book': True, 'code_root': str(ROOT),
                             'library': book_figures(digest, concept)}
    elif figures:
        from figure_library import pick
        about = ' '.join([concept['name'], concept.get('summary', '')] + [
            f'{b.get("title", "")} {b.get("caption", "")} {b.get("shows", "")}' for b in teaching_blocks(digest, concept)])
        record['figures'] = {'code_root': str(ROOT), 'library_root': str(pick.LIBRARY),
                             'library': pick.candidates(about), 'animation': ANIMATION}
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


def topic_request(digest, concept, figures=False):
    """A topic's film request: its audience, its blocks grouped by the source each cites (the film's sources), and
    for Biology Studio the topic's own diagrams (beyond the book) with those of the chapter it builds on, labelled at
    the topic's level."""
    s = digest['source']
    record = {'kind': 'textbook_concept', 'topic': True, 'chapter_id': s['id'], 'concept_id': concept['id'],
              'concept': concept['name'], 'summary': concept.get('summary', ''), 'audience': s['audience'],
              'book': f'{s["book_title"]}: {s["title"]}', 'chapter_no': s['chapter'], 'chapter': s['title'],
              'coverage': coverage(digest, concept), 'seconds': film_seconds(digest, concept)}
    if figures == 'biology':
        from figure_library import biology
        level_class = s.get('figure_class', s['class'])
        record['figures'] = {'subject': 'biology', 'code_root': str(ROOT), 'level': biology.level_for(level_class),
                             'library': biology.candidates(s.get('anchor_chapter', s['id']), level_class,
                                                           extra=s.get('figures') or [])}
    by_source = {}
    for b in teaching_blocks(digest, concept):
        src = b['source']
        entry = by_source.setdefault(src['url'], {'url': src['url'], 'complete': True, 'title': src['title'], 'raw_content': ''})
        entry['raw_content'] += f'{b.get("title", "")}\n{b.get("text", "")}\n\n'
    sources = [{**e, 'raw_content': e['raw_content'].strip()} for e in by_source.values()]
    subject = f'{concept["name"]} ({s["book_title"]}: {s["title"]})'
    return {'subject': subject[:300], 'record': record, 'sources': {'results': sources}}

