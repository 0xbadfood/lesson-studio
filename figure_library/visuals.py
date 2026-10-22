"""The visual registry: every diagram the films need, once, with the chapters and concepts that use it, what it must
be able to do on screen, and whether we already have it (user, 2026-10-22: an SVG library "with defined animation
scope ... a database easily searchable by the pipeline").

Built from the chapters' visual needs (kb_research/visual_needs.py, textbook-digest/<chapter>/visual-needs.json):
  1. merge: per subject, the model groups the needs that are the same diagram (the heart of Class 10 Life Processes
     and of Class 11 Body Fluids) and names the asset that already draws it, if one does: a biology library SVG
     (figure_library/biology.py) or a chemistry figure type drawn by code (figure_library/chem.py). Code checks that
     every need is placed once and every asset exists; a biology need whose book figure number the library's sidecar
     cites is matched by code, whatever the model said.
  2. store: figure-library/visuals.sqlite3, with full-text search over names, what they show and their parts.
Status of an entry: 'have' (an asset draws it), 'code' (a code-drawn chemistry type draws it from data), 'to_build'.
Commons files that may fit are listed with an entry as candidates only (credit and a look are still needed).

  .venv/bin/python -m figure_library.visuals build      # merge and store
  .venv/bin/python -m figure_library.visuals report     # what we have and what to build, by reuse
  .venv/bin/python -m figure_library.visuals search "heart"
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGESTS = ROOT / 'textbook-digest'
DB = ROOT / 'figure-library' / 'visuals.sqlite3'
CACHE = DIGESTS / '_visuals'
CHEM_TYPES = {'molecule': 'a molecule\'s structure from SMILES', 'reaction': 'an organic reaction drawn with structures',
              'mechanism': 'a curly-arrow mechanism', 'resonance': 'resonance structures', 'equation': 'an equation',
              'bohr': 'a Bohr atom model', 'orbital_boxes': 'electron configuration boxes',
              'energy_levels': 'hydrogen energy levels and transitions', 'orbital': 'an atomic orbital shape',
              'spectrum': 'the electromagnetic, hydrogen or a continuous spectrum',
              'newman': 'a Newman projection', 'sawhorse': 'a sawhorse projection', 'chair': 'a cyclohexane chair'}

MERGE_TASK = '''Below are the diagrams that teaching films of NCERT {subject} chapters need, one line each (key, name,
kind, what it shows, its parts). Several may be the same diagram needed by different chapters (the same organ section,
the same apparatus, the same graph): group those, and keep different diagrams apart (a heart section and a double
circulation flow chart are different; the same heart section in two books is one). Then, for each group, name the
asset that already draws it, if one clearly does, from ASSETS, else null.

Return {{"groups":[{{"name":"a short general name","kind":"its kind","members":["key", ...],"asset":"biology:heart-section"
or "code:molecule" or null}}]}}. Every key appears in exactly one group.

ASSETS:
{assets}

NEEDS:
{needs}'''


def needs(root=DIGESTS):
    """Every chapter's needs, keyed chapter:Nn."""
    out = []
    for path in sorted(root.glob('*/visual-needs.json')):
        v = json.loads(path.read_text())
        for n in v['needs']:
            out.append({**n, 'key': f'{v["chapter"]}:{n["id"]}', 'chapter': v['chapter'], 'class': v['class'],
                        'subject': v['subject'], 'book': v.get('book'), 'chapter_no': v.get('chapter_no')})
    return out


def assets(subject):
    """The assets a subject's needs can match: 'biology:<id>' and 'code:<chem type>'."""
    out = {}
    if subject in ('biology', 'science'):
        from figure_library import biology
        for fid, entry in biology.entries().items():
            out[f'biology:{fid}'] = entry['sidecar'].get('title', fid)
    if subject in ('chemistry', 'science'):
        out.update({f'code:{k}': v for k, v in CHEM_TYPES.items()})
    return out


def figure_number(ref):
    found = re.search(r'(\d+\.\d+)', str(ref or ''))
    return found.group(1) if found else None


def cited_by_library(need):
    """The biology library SVGs whose sidecars cite this need's book figure (a code match, not a guess)."""
    number = figure_number(need.get('figure_ref'))
    if not number or need.get('subject') not in ('biology', 'science'):
        return []
    from figure_library import biology
    return [f'biology:{fid}' for fid, entry in sorted(biology.entries().items())
            if any(ref.get('book') == need.get('book') and str(ref.get('figure', '')).split('(')[0] == number
                   for ref in entry['sidecar'].get('ncert') or [])]


def choose_asset(name, cited, proposed, titles):
    """Several SVGs can cite one book figure (Fig. 8.3: the animal cell, the plant cell and their comparison): take
    the one whose name is closest to the diagram's, the model's choice breaking a tie."""
    if not cited:
        return proposed
    words = set(re.findall(r'[a-z]{3,}', name.lower()))
    return max(cited, key=lambda a: (len(words & set(re.findall(r'[a-z]{3,}', (a + ' ' + titles.get(a, '')).lower()))),
                                     a == proposed, -cited.index(a)))


def merge_errors(value, keys, known):
    groups = value.get('groups')
    if not isinstance(groups, list):
        return ['return a "groups" list']
    placed = [k for g in groups for k in g.get('members') or []]
    missing = sorted(set(keys) - set(placed))
    twice = sorted({k for k in placed if placed.count(k) > 1})
    unknown = sorted(set(placed) - set(keys))
    errors = []
    if missing or twice or unknown:
        errors.append(f'every key in exactly one group: missing {missing[:20]}, twice {twice[:20]}, unknown {unknown[:20]}')
    for g in groups:
        if g.get('asset') not in (None, *known):
            errors.append(f'group "{g.get("name")}": asset must be one of ASSETS or null, not {g.get("asset")}')
        if not g.get('name') or not g.get('members'):
            errors.append('each group has a name and members')
    return errors


def merge(model, subject, items):
    import textbook_kb as kb
    known = assets(subject)
    lines = [json.dumps({'key': n['key'], 'name': n['name'], 'kind': n['kind'], 'shows': n['shows'][:160],
                         'parts': n['parts'][:8]}, ensure_ascii=False) for n in items]
    prompt = MERGE_TASK.format(subject=subject, assets=json.dumps(known, ensure_ascii=False, indent=0),
                               needs='\n'.join(lines))
    return model.call(f'merge-{subject}', prompt, thinking=2000, max_tokens=16000, attempts=3,
                      system='You organise a library of teaching diagrams. Reply with JSON only.',
                      validate=lambda r: kb.raise_if(merge_errors(r, [n['key'] for n in items], known)))['groups']


def build(endpoint='http://127.0.0.1:8001/v1', db=DB, log=print):
    sys.path.insert(0, str(ROOT / 'kb_research'))
    import digest
    from figure_library import pick
    everything = needs()
    by_key = {n['key']: n for n in everything}
    CACHE.mkdir(parents=True, exist_ok=True)
    model = digest.chat(endpoint, CACHE, 'visuals', 3600)
    entries = []
    for subject in sorted({n['subject'] for n in everything}):
        items = [n for n in everything if n['subject'] == subject]
        for g in merge(model, subject, items):
            members = [by_key[k] for k in g['members']]
            cited = sorted({a for n in members for a in cited_by_library(n)})
            asset = choose_asset(g['name'], cited, g.get('asset'), assets(subject))
            status = 'to_build' if not asset else 'code' if asset.startswith('code:') else 'have'
            first = max(members, key=lambda n: len(n['parts']))
            # Commons files whose own name shares at least two words with the diagram's (a looser match on what
            # it shows offered noise: a hydrogen fine-structure file for the Aufbau order)
            commons = [] if asset else [c['id'] for c in pick.candidates(g['name'], limit=3, minimum=4)]
            entries.append({'name': g['name'], 'kind': g.get('kind') or first['kind'], 'subject': subject,
                            'shows': first['shows'], 'parts': sorted({p for n in members for p in n['parts']}),
                            'stages': first['stages'], 'motions': sorted({m for n in members for m in n['motions']}),
                            'status': status, 'asset': asset, 'commons': commons, 'members': members})
        log(f'{subject}: {len(items)} needs -> {sum(e["subject"] == subject for e in entries)} diagrams')
    store(entries, db)
    return entries


def store(entries, db=DB):
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_suffix('.tmp')
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript('''
        CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT, kind TEXT, subject TEXT, shows TEXT, parts TEXT,
            stages TEXT, motions TEXT, status TEXT, asset TEXT, commons TEXT, reuse INTEGER);
        CREATE TABLE uses (entry INTEGER, need TEXT, chapter TEXT, class INTEGER, concepts TEXT, figure_ref TEXT,
            beyond_book INTEGER, name TEXT);
        CREATE VIRTUAL TABLE search USING fts5(name, shows, parts, content='entries', content_rowid='id');''')
    for n, e in enumerate(entries, 1):
        con.execute('INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (n, e['name'], e['kind'], e['subject'], e['shows'], json.dumps(e['parts']), json.dumps(e['stages']),
                     json.dumps(e['motions']), e['status'], e['asset'], json.dumps(e['commons']),
                     len({m['chapter'] for m in e['members']})))
        for m in e['members']:
            con.execute('INSERT INTO uses VALUES (?,?,?,?,?,?,?,?)',
                        (n, m['key'], m['chapter'], m['class'], json.dumps(m['concepts']), m.get('figure_ref', ''),
                         int(bool(m.get('beyond_book'))), m['name']))
    con.execute("INSERT INTO search(rowid, name, shows, parts) SELECT id, name, shows, parts FROM entries")
    con.commit()
    con.close()
    tmp.replace(db)


def search(text=None, chapter=None, concept=None, subject=None, status=None, db=DB):
    """Entries matching words, a chapter (kebo1-15), a concept (kebo1-15:C6), a subject or a status."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    sql, args = 'SELECT DISTINCT e.* FROM entries e', []
    where = []
    if text:
        sql += ' JOIN search s ON s.rowid = e.id'
        where.append('search MATCH ?')
        args.append(' OR '.join(re.findall(r'\w+', text)))
    if chapter or concept:
        sql += ' JOIN uses u ON u.entry = e.id'
        ch = (concept or '').split(':')[0] or chapter
        where.append('u.chapter = ?')
        args.append(ch)
        if concept:
            where.append('u.concepts LIKE ?')
            args.append(f'%"{concept.split(":")[1]}"%')
    if subject:
        where.append('e.subject = ?')
        args.append(subject)
    if status:
        where.append('e.status = ?')
        args.append(status)
    rows = con.execute(sql + (' WHERE ' + ' AND '.join(where) if where else '') + ' ORDER BY e.reuse DESC, e.name',
                       args).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        for k in ('parts', 'stages', 'motions', 'commons'):
            item[k] = json.loads(item[k])
        item['uses'] = [dict(u) for u in con.execute('SELECT * FROM uses WHERE entry = ?', (r['id'],))]
        out.append(item)
    con.close()
    return out


def report(db=DB):
    con = sqlite3.connect(db)
    lines = []
    for subject, in con.execute('SELECT DISTINCT subject FROM entries ORDER BY subject'):
        counts = dict(con.execute('SELECT status, COUNT(*) FROM entries WHERE subject=? GROUP BY status', (subject,)))
        lines.append(f'{subject}: {sum(counts.values())} diagrams: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))
        for name, kind, reuse, motions in con.execute(
                "SELECT name, kind, reuse, motions FROM entries WHERE subject=? AND status='to_build' "
                "ORDER BY reuse DESC, name LIMIT 12", (subject,)):
            lines.append(f'   to build: {name} ({kind}, {reuse} chapter{"s" if reuse > 1 else ""}) {json.loads(motions)}')
    con.close()
    return '\n'.join(lines)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('command', choices=['build', 'report', 'search'])
    parser.add_argument('text', nargs='?')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8001/v1')
    args = parser.parse_args()
    if args.command == 'build':
        build(args.endpoint)
        print(report())
    elif args.command == 'report':
        print(report())
    else:
        for e in search(args.text):
            print(f'{e["status"]:9s} {e["name"]} ({e["kind"]}, {e["asset"] or "-"}) used in '
                  + ', '.join(sorted({u["chapter"] for u in e["uses"]})))
