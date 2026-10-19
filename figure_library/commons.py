"""Figure library: diagrams from Wikimedia Commons that a film may show as they are (apparatus, experiment set-ups).

Only files whose licence lets a film use them with a credit are kept: public domain, CC0 and CC BY (user decision
2026-10-19; CC BY-SA and GFDL are skipped). Each file is saved with its credit line, its licence and its page, a PNG
preview, and the words printed on it (labels in another language make a figure unusable as is).

  .venv/bin/python -m figure_library.commons --set chemistry      # figure_library/sets/chemistry.json
  .venv/bin/python -m figure_library.commons --set chemistry --dry-run

A set lists Commons categories and searches: {"categories": ["SVG laboratory glassware icons", ...],
"searches": ["cathode ray tube diagram", ...]}. Everything lands in figure-library/commons/ with figure-library/
commons/index.json, one record per file; running again only fetches what is new.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'figure-library' / 'commons'
API = 'https://commons.wikimedia.org/w/api.php'
HEADERS = {'User-Agent': 'NCERTFilmPilot/0.1 (https://history.photovault.live; figure library for school films)'}
PAUSE = 0.5                       # seconds between API requests: Commons asks bots to go gently
DOWNLOAD_PAUSE = 2.0              # upload.wikimedia.org answered 429 at one file per 0.5 s (2026-10-19)
MAX_BYTES = 3_000_000             # bigger SVGs are maps and posters, not diagrams


def allowed(licence):
    """Public domain, CC0 and CC BY (any version): usable with a credit. Share-alike and GFDL are not."""
    name = (licence or '').strip().lower()
    if 'sa' in re.split(r'[\s\-]+', name) or 'gfdl' in name or 'nc' in re.split(r'[\s\-]+', name):
        return False
    return name.startswith(('public domain', 'pd', 'cc0', 'cc-zero')) or bool(re.match(r'cc[ -]by \d', name))


def plain(value):
    """Commons metadata is HTML: tags, entities and runs of space removed."""
    text = re.sub(r'<[^>]+>', ' ', html.unescape(str(value or '')))
    return re.sub(r'\s+', ' ', text).strip()


def labels(svg_bytes):
    """The words printed on the drawing (its <text> elements). Text converted to outlines is not found, which is fine:
    then nothing in another language can show either way."""
    try:
        root = ElementTree.fromstring(svg_bytes)
    except ElementTree.ParseError:
        return []
    out = []
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1] == 'text':
            words = ' '.join(t.strip() for t in element.itertext() if t.strip())
            if words:
                out.append(words)
    return out


def short_author(author):
    """'File:X.svg : Drawn by User:Fastfission in Illustrator and Inkscape. -- Fastfission' -> 'Fastfission': the
    user name when Commons gives one, else the text up to the first sentence, at most 60 characters."""
    users = re.findall(r'User:([^\s,;.()]+)', author)
    if users:
        return users[-1].replace('_', ' ')
    first = re.split(r'(?<=[a-z])\. | -- ', author)[0].strip()
    return first if len(first) <= 60 else first[:57].rsplit(' ', 1)[0] + '...'


def slug(title):
    stem = re.sub(r'^File:', '', title)
    stem = re.sub(r'\.svg$', '', stem, flags=re.I)
    safe = re.sub(r'[^A-Za-z0-9]+', '-', stem).strip('-').lower()[:60] or 'figure'
    return f'{safe}-{hashlib.sha1(title.encode()).hexdigest()[:6]}'


class Commons:
    def __init__(self, client=None):
        self.client = client or httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True)

    def get(self, **params):
        time.sleep(PAUSE)
        response = self.client.get(API, params={'action': 'query', 'format': 'json', **params})
        response.raise_for_status()
        return response.json()

    def _pages(self, most, **params):
        """Pages of a generator query, following 'continue' up to `most` pages (a search matches thousands)."""
        extra, count = {}, 0
        while True:
            data = self.get(prop='imageinfo', iiprop='url|extmetadata|mime|size', **params, **extra)
            for page in (data.get('query') or {}).get('pages', {}).values():
                yield page
                count += 1
            if 'continue' not in data or count >= most:
                return
            extra = data['continue']

    def category(self, name):
        return self._pages(500, generator='categorymembers', gcmtitle='Category:' + name, gcmtype='file', gcmlimit=50)

    def search(self, words, limit=50):
        return self._pages(limit, generator='search', gsrnamespace=6, gsrsearch=f'{words} filemime:image/svg+xml',
                           gsrlimit=limit)

    def download(self, url, tries=4):
        for attempt in range(1, tries + 1):
            time.sleep(DOWNLOAD_PAUSE)
            response = self.client.get(url)
            if response.status_code != 429 or attempt == tries:
                response.raise_for_status()
                return response.content
            wait = response.headers.get('retry-after', '')
            time.sleep(int(wait) if wait.isdigit() else 30 * attempt)     # told to slow down: wait, then retry


def record_for(page, origin):
    """The library record for one Commons file page, or None when it is not an SVG we may use."""
    info = (page.get('imageinfo') or [{}])[0]
    meta = info.get('extmetadata') or {}
    value = lambda key: (meta.get(key) or {}).get('value', '')               # noqa: E731
    licence = plain(value('LicenseShortName'))
    if info.get('mime') != 'image/svg+xml' or not allowed(licence) or info.get('size', 0) > MAX_BYTES:
        return None
    author = plain(value('Artist')) or 'Unknown author'
    title = page['title']
    return {'id': slug(title), 'title': title, 'name': re.sub(r'^File:|\.svg$', '', title),
            'page': info.get('descriptionurl', ''), 'url': info.get('url', ''),
            'description': plain(value('ImageDescription'))[:600], 'author': author[:200], 'licence': licence,
            'licence_url': plain(value('LicenseUrl')), 'restrictions': plain(value('Restrictions')),
            'categories': [c for c in plain(value('Categories')).split('|') if c][:20],
            'width': info.get('width'), 'height': info.get('height'), 'origin': origin,
            'credit': f'{re.sub(r"^File:", "", title)} by {short_author(author)}, {licence}, via Wikimedia Commons'}


def preview(svg_path, png_path, width=1024):
    import cairosvg
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=width, background_color='white')


def collect(spec, commons, root=ROOT, dry_run=False, log=print):
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / 'index.json'
    index = {r['id']: r for r in json.loads(index_path.read_text())} if index_path.exists() else {}
    seen, skipped = set(), {'licence or type': 0, 'failed': 0}
    sources = [('category', name, commons.category(name)) for name in spec.get('categories', [])]
    sources += [('search', words, commons.search(words)) for words in spec.get('searches', [])]
    for kind, name, pages in sources:
        kept = 0
        for page in pages:
            if page.get('title') in seen:
                continue
            seen.add(page.get('title'))
            record = record_for(page, f'{kind}: {name}')
            if record is None:
                skipped['licence or type'] += 1
                continue
            kept += 1
            if dry_run or record['id'] in index:
                continue
            try:
                svg = commons.download(record['url'])
                (root / f'{record["id"]}.svg').write_bytes(svg)
                record['labels'] = labels(svg)
                preview(root / f'{record["id"]}.svg', root / f'{record["id"]}.png')
            except Exception as exc:                                    # noqa: BLE001 - one bad file, not the set
                skipped['failed'] += 1
                log(f'  failed {record["title"]}: {type(exc).__name__}: {str(exc)[:120]}')
                (root / f'{record["id"]}.svg').unlink(missing_ok=True)
                continue
            index[record['id']] = record
        log(f'{kind} "{name}": {kept} usable')
        if not dry_run:
            index_path.write_text(json.dumps(sorted(index.values(), key=lambda r: r['id']), indent=1,
                                             ensure_ascii=False))
    log(f'library: {len(index)} figures; skipped {skipped}')
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--set', required=True, help='name of a file in figure_library/sets/ (without .json)')
    parser.add_argument('--dry-run', action='store_true', help='count usable files without downloading')
    args = parser.parse_args(argv)
    spec = json.loads((HERE / 'sets' / f'{args.set}.json').read_text())
    collect(spec, Commons(), dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
