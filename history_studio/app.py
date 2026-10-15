"""History Studio: short films of textbook concepts, for students.

A viewer picks a class, a chapter and a concept; the film is made by the infofilm queue (shared with the other film
runs, one at a time) from the chapter's digest, with the book as its source. While it is made, the page shows what
exists so far (the book passages, the key ideas, the storyline and narration, the scenes as they are painted),
never the pipeline's internal steps.

Runs with the remotion virtualenv (it imports infofilm.queue):
  /home/nitin/remotion/.venv/bin/python -m history_studio.app --port 18620
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from history_studio import catalog

REMOTION = Path('/home/nitin/remotion')
sys.path.insert(0, str(REMOTION))
from infofilm.queue import Queue  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = catalog.ROOT / 'history-data'
QUEUE_ROOT = REMOTION / 'artifacts' / 'interface'
VOICE = {'reference_audio': str(REMOTION / 'references' / 'kane.wav'), 'voice_id': 'kane', 'narrator_label': 'Kane'}
VOICES = DATA / 'voices.json'     # narrators offered: [{id, label, reference_audio, reference_transcript}]
COOKIE = 'history_session'
SESSION_DAYS = 30

# What the viewer sees instead of the pipeline's steps: (key, title, line shown while it runs).
PHASES = [('reading', 'Reading the chapter', 'Turning the pages of your textbook'),
          ('ideas', 'Finding the key ideas', 'Picking out what the book teaches about this'),
          ('story', 'Writing the story', 'Shaping the ideas into a story worth watching'),
          ('voice', 'Recording the voice', 'Our narrator is in the recording booth'),
          ('scenes', 'Painting the scenes', 'Illustrating each moment of the story'),
          ('cut', 'Final cut', 'Putting pictures, voice and titles together')]
STAGE_PHASE = {'research': 'reading', 'evidence': 'ideas', 'creative': 'story', 'script': 'story',
               'narration': 'voice', 'timing': 'voice', 'scenes': 'scenes', 'images': 'scenes', 'music': 'cut',
               'video': 'cut'}


def nice(text):
    """Book titles from folder names: "India And The Contemporary World Ii" -> "India and the Contemporary World II"."""
    text = re.sub(r'\bIii\b', 'III', re.sub(r'\bIi\b', 'II', text))
    return re.sub(r'(?<=\w )(And|The|Of|In|For|To|A|An)\b', lambda m: m.group(1).lower(), text)


# ------------------------------------------------------------------ access
class Access:
    """One access code for the pilot (history-data/access-code, 0600); signed session cookies."""

    def __init__(self, root=DATA):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name, make in (('access-code', lambda: '-'.join(secrets.token_hex(2) for _ in range(3))),
                           ('session-key', lambda: secrets.token_hex(32))):
            path = self.root / name
            if not path.exists():
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as handle:
                    handle.write(make() + '\n')
        self.code = (self.root / 'access-code').read_text().strip()
        self.key = (self.root / 'session-key').read_text().strip().encode()

    def check(self, code):
        return hmac.compare_digest(code.strip().lower().encode(), self.code.lower().encode())

    def token(self):
        expires = str(int(time.time()) + SESSION_DAYS * 86400)
        return expires + '.' + hmac.new(self.key, expires.encode(), hashlib.sha256).hexdigest()

    def valid(self, token):
        expires, _, signature = (token or '').partition('.')
        good = hmac.new(self.key, expires.encode(), hashlib.sha256).hexdigest()
        return expires.isdigit() and int(expires) > time.time() and hmac.compare_digest(signature, good)


# ------------------------------------------------------------------ films
class Films:
    """Concept -> film job, kept in history-data/films.json. One film per concept: asking again shows the same film
    unless the earlier attempt failed."""

    def __init__(self, queue, root=DATA):
        self.queue, self.path, self.lock = queue, Path(root) / 'films.json', threading.Lock()

    def load(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self, value):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, indent=1))
        temporary.replace(self.path)

    def job(self, job_id):
        try:
            return self.queue.get(job_id)
        except (KeyError, ValueError, LookupError):
            return None

    def make(self, chapter_id, concept_id, voice=None):
        digest = catalog.digest_for(chapter_id)
        concept = next((c for c in digest['concepts'] if c['id'] == concept_id), None)
        if concept is None or not catalog.filmable(digest, concept):
            raise KeyError(concept_id)
        key = f'{chapter_id}:{concept_id}'
        with self.lock:
            films = self.load()
            existing = films.get(key)
            job = self.job(existing['job']) if existing else None
            if job and job['status'] not in ('failed', 'interrupted'):
                return existing['film']
            if job and voice is None:                # "make it again" keeps the narrator the film was started with
                voice = job['request'].get('voice_id')
            if job and job['request'].get('voice_id') == narrator(voice)['voice_id']:
                self.queue.resume(job['id'])        # same narrator: carry on from the saved run, not from scratch
                return existing['film']
            built = catalog.film_request(digest, concept)
            request = {'subject': built['subject'], 'durations': [built['record']['seconds']],
                       'generation_mode': 'short', 'orientation': 'landscape', 'review_mode': 'experimental',
                       'image_review': True, 'premium_rescue': False, 'tts_engine': 'vibevoice', 'mood': 'auto',
                       'mood_intensity': 'restrained', 'visual_balance': 'auto', 'music_engine': 'none',
                       **narrator(voice),
                       'curriculum': {'record': built['record'], 'sources': built['sources']}}
            job = self.queue.submit(request, f'history-{uuid.uuid4().hex}')
            film = uuid.uuid4().hex[:12]
            films[key] = {'film': film, 'job': job['id'], 'chapter': chapter_id, 'concept': concept_id,
                          'created': time.time()}
            self.save(films)
            return film

    def cancel(self, film):
        """Stop a queued or running film (started by mistake). It can be made again later from its saved stages."""
        self.queue.cancel(self.find(film)['job'])

    def find(self, film):
        for key, value in self.load().items():
            if value['film'] == film:
                return value
        raise KeyError(film)

    def by_concept(self):
        return {k: v for k, v in self.load().items()}


def voices():
    """The narrators viewers can choose: Kane (the studio default), then the voices in history-data/voices.json."""
    out = [{'id': 'kane', 'label': 'Kane (studio narrator)', 'gender': 'male', **VOICE,
            'reference_transcript': kane_transcript()}]
    listed = json.loads(VOICES.read_text()) if VOICES.exists() else []
    return out + [v for v in listed if v['id'] != 'kane' and Path(v['reference_audio']).is_file()]


def narrator(voice):
    chosen = next((v for v in voices() if v['id'] == (voice or 'kane')), None)
    if chosen is None:
        raise KeyError(voice)
    return {'reference_audio': chosen['reference_audio'], 'reference_transcript': chosen.get('reference_transcript'),
            'voice_id': chosen['id'], 'narrator_label': chosen['label'].split(' (')[0]}


def kane_transcript():
    """The narrator's reference transcript, as the last film run used it."""
    with sqlite3.connect(f'file:{QUEUE_ROOT / "queue.sqlite3"}?mode=ro', uri=True) as db:
        for (raw,) in db.execute('SELECT request FROM jobs ORDER BY created DESC'):
            request = json.loads(raw)
            if request.get('voice_id') == 'kane' and request.get('reference_transcript'):
                return request['reference_transcript']
    return None


# ------------------------------------------------------------------ progress (what exists so far)
def events(project):
    path = Path(project) / 'jobs.sqlite3'
    if not path.exists():
        return []
    try:
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=3) as db:
            return [(stage, state, json.loads(detail or '{}')) for stage, state, detail in
                    db.execute("SELECT stage, state, detail FROM events WHERE stage LIKE 'pipeline:%' OR stage = 'images' "
                               'ORDER BY id')]
    except sqlite3.Error:
        return []


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def progress(queue, record):
    job = queue.get(record['job'])
    project = Path(job['project'])
    curriculum = read_json(project / 'curriculum.json') or {}
    sources = read_json(project / 'curriculum-sources.json') or {'results': []}
    status = job['status']
    phase, images_total, images_done = None, None, 0
    for stage, state, detail in events(project):
        name = stage.split(':', 1)[1] if ':' in stage else stage
        if stage == 'images':
            images_total = detail.get('planned_images', images_total)
            images_done = detail.get('completed_images', images_done)
            continue
        if name in STAGE_PHASE and state in ('running', 'succeeded'):
            phase = STAGE_PHASE[name]
    if status == 'succeeded':
        phase = 'done'
    ahead = 0
    if status == 'queued':
        ahead = sum(1 for j in queue.list() if j['status'] == 'running' or
                    (j['status'] == 'queued' and j['created'] < job['created']))
    book = sources['results'][0] if sources['results'] else {}
    passages = [p.split('\n', 1)[1][:260] for p in (book.get('raw_content') or '').split('\n\n')
                if '\n' in p and len(p.split('\n', 1)[1]) > 80][:4]
    evidence = read_json(project / 'evidence-final.json')
    seconds = (curriculum.get('seconds') or 0)
    film_dir = project / f'film-{seconds}'
    script = read_json(film_dir / 'script.json')
    audio = read_json(film_dir / 'audio-selection.json')
    scenes = []
    for selected in sorted((project / 'images').glob('*/selected.json'), key=lambda p: p.stat().st_mtime):
        value = read_json(selected) or {}
        if value.get('file') and Path(value['file']).is_file():
            scenes.append({'src': f'/media/{record["film"]}/scene/{selected.parent.name}',
                           'caption': value.get('visual_message', '')})
    delivery = read_json(project / 'delivery.json')
    video = None
    if delivery and delivery.get('outputs'):
        video = f'/media/{record["film"]}/video'
    return {
        'film': record['film'], 'chapter_id': record['chapter'], 'concept_id': record['concept'],
        'status': 'stopped' if status == 'interrupted' and str(job.get('error') or '').startswith('Cancelled') else
        'failed' if status in ('failed', 'interrupted') else
        'done' if status == 'succeeded' else 'waiting' if status == 'queued' else 'making',
        'ahead': ahead, 'phase': phase, 'phases': [{'key': k, 'title': t, 'line': l} for k, t, l in PHASES],
        'concept': curriculum.get('concept'), 'summary': curriculum.get('summary'),
        'chapter': curriculum.get('chapter'), 'chapter_no': curriculum.get('chapter_no'),
        'book': nice(curriculum.get('book', '')), 'minutes': round(seconds / 60, 1),
        'pages': re.findall(r'pages ([\d, ]+)$', book.get('title', ''))[:1],
        'passages': passages,
        'ideas': [f['claim'] for f in (evidence or {}).get('facts', [])] if evidence else None,
        'storyline': [{'heading': p.get('heading'), 'line': p.get('narration')} for p in script['points']] if script else None,
        'narration': f'/media/{record["film"]}/narration' if audio and audio.get('audio') else None,
        'scenes': scenes, 'scenes_total': images_total, 'scenes_done': images_done, 'video': video,
        'notes': [{'title': s['title'].replace("Teacher's note: ", ''), 'url': s['url']}
                  for s in sources['results'][1:] if s['url'].startswith('http') and 'ncert.nic.in' not in s['url']],
        'source_url': book.get('url')}


def media_path(queue, record, kind, item=None):
    """Only files that belong to this film: its narration, its selected scene pictures and its final video."""
    project = Path(queue.get(record['job'])['project'])
    curriculum = read_json(project / 'curriculum.json') or {}
    if kind == 'scene' and item and re.fullmatch(r'[0-9a-f]{8,40}', item):
        value = read_json(project / 'images' / item / 'selected.json') or {}
        path = Path(value.get('file', ''))
    elif kind == 'narration':
        path = Path((read_json(project / f'film-{curriculum.get("seconds")}' / 'audio-selection.json') or {}).get('audio', ''))
    elif kind == 'video':
        outputs = (read_json(project / 'delivery.json') or {}).get('outputs') or []
        path = Path(outputs[0]['video']) if outputs else Path()
    else:
        raise KeyError(kind)
    path = path.resolve()
    if not path.is_file() or project.resolve() not in path.parents:
        raise KeyError(kind)
    return path


# ------------------------------------------------------------------ app
class FilmAsk(BaseModel):
    chapter: str = Field(pattern=r'^[a-z0-9]+-\d{2}$')
    concept: str = Field(pattern=r'^C\d{1,3}$')
    voice: str | None = Field(default=None, max_length=80)


class Login(BaseModel):
    code: str = Field(min_length=1, max_length=80)


def build(queue=None, access=None, data=DATA):
    queue = queue or Queue(QUEUE_ROOT, REMOTION / 'config.json')
    access = access or Access(data)
    films = Films(queue, data)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def signed_in(request):
        if not access.valid(request.cookies.get(COOKIE)):
            raise HTTPException(401, 'Sign in first')

    @app.get('/', response_class=HTMLResponse)
    def index():
        return FileResponse(HERE / 'static' / 'index.html', headers={'Cache-Control': 'no-cache'})

    @app.get('/static/{name}')
    def static(name: str):
        path = (HERE / 'static' / name).resolve()
        if path.parent != (HERE / 'static').resolve() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={'Cache-Control': 'no-cache'})

    @app.get('/healthz')
    def health():
        return {'ok': True}

    @app.get('/api/session')
    def session(request: Request):
        return {'signed_in': access.valid(request.cookies.get(COOKIE))}

    @app.post('/api/login')
    def login(body: Login, request: Request):
        if not access.check(body.code):
            time.sleep(1)
            raise HTTPException(403, 'That code is not right')
        response = JSONResponse({'signed_in': True})
        response.set_cookie(COOKIE, access.token(), max_age=SESSION_DAYS * 86400, httponly=True, samesite='lax',
                            secure=request.headers.get('x-forwarded-proto', request.url.scheme) == 'https')
        return response

    @app.post('/api/logout')
    def logout():
        response = JSONResponse({'signed_in': False})
        response.delete_cookie(COOKIE)
        return response

    @app.get('/api/catalog')
    def get_catalog(request: Request):
        signed_in(request)
        made = films.by_concept()
        out = catalog.catalog()
        for cls in out:
            for subject in cls['subjects']:
                for chapter in subject['chapters']:
                    chapter['book'] = nice(chapter['book'])
                    for concept in chapter['concepts']:
                        record = made.get(f'{chapter["id"]}:{concept["id"]}')
                        job = films.job(record['job']) if record else None
                        concept['film'] = record['film'] if job and job['status'] not in ('failed', 'interrupted') else None
                        concept['ready'] = bool(job and job['status'] == 'succeeded')
        return {'classes': out, 'all_classes': [8, 9, 10, 11, 12]}

    @app.post('/api/films', status_code=202)
    def make_film(body: FilmAsk, request: Request):
        signed_in(request)
        try:
            return {'film': films.make(body.chapter, body.concept, body.voice)}
        except KeyError:
            raise HTTPException(404, 'No such concept or narrator')

    @app.get('/api/voices')
    def get_voices(request: Request):
        signed_in(request)
        return {'voices': [{'id': v['id'], 'label': v['label'], 'gender': v.get('gender') or 'other',
                            'sample': f'/api/voices/{v["id"]}/sample'} for v in voices()]}

    @app.get('/api/voices/{voice}/sample')
    def voice_sample(voice: str, request: Request):
        signed_in(request)
        chosen = next((v for v in voices() if v['id'] == voice), None)
        if chosen is None:
            raise HTTPException(404)
        return FileResponse(chosen['reference_audio'], media_type='audio/wav',
                            headers={'Cache-Control': 'private, max-age=86400'})

    @app.post('/api/films/{film}/cancel')
    def cancel_film(film: str, request: Request):
        signed_in(request)
        try:
            films.cancel(film)
        except KeyError:
            raise HTTPException(404, 'No such film')
        except ValueError:
            raise HTTPException(409, 'This film is not being made')
        return progress(queue, films.find(film))

    @app.get('/api/films/{film}')
    def film_progress(film: str, request: Request):
        signed_in(request)
        try:
            return progress(queue, films.find(film))
        except KeyError:
            raise HTTPException(404, 'No such film')

    @app.get('/api/library')
    def library(request: Request):
        signed_in(request)
        out = []
        for record in sorted(films.load().values(), key=lambda r: -r['created']):
            job = films.job(record['job'])
            if not job or job['status'] in ('failed', 'interrupted'):
                continue
            item = progress(queue, record)
            out.append({k: item[k] for k in ('film', 'status', 'concept', 'chapter', 'chapter_no', 'book', 'minutes')}
                       | {'cover': item['scenes'][0]['src'] if item['scenes'] else None})
        return {'films': out}

    @app.get('/media/{film}/{kind}')
    @app.get('/media/{film}/{kind}/{item}')
    def media(film: str, kind: str, request: Request, item: str | None = None):
        signed_in(request)
        try:
            path = media_path(queue, films.find(film), kind, item)
        except KeyError:
            raise HTTPException(404)
        return FileResponse(path, headers={'Cache-Control': 'private, max-age=3600'})

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=18620)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(build(), host=args.host, port=args.port, proxy_headers=True, forwarded_allow_ips='10.8.0.1',
                log_level='warning')


if __name__ == '__main__':
    main()
