"""Teacher Studio pilot (teacher.photovault.live, :18680): a teacher records a voice, picks a look, and gets a chapter's films
re-voiced from their bundles (infofilm/rendition.py). No planning and no digest. One access code, one workspace.

Usage: python -m teacher_studio.app --host 0.0.0.0 --port 18680
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

REMOTION = Path('/home/nitin/remotion')
sys.path.insert(0, str(REMOTION))
from infofilm import rendition  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / 'teacher-data'
BUNDLES = REMOTION / 'artifacts' / 'bundles' / 'keph1-04'
CHAPTER = 'Laws of Motion'
CONSENT = ('I am the person recording this voice. I agree that it may be used to narrate these lesson films for my school, '
           'and that each film will say its narration is an AI voice used with my consent.')
MAX_RECORDING = 30 * 1024 * 1024
MAX_LOGO = 2 * 1024 * 1024
COOKIE = 'teacher_session'
PYTHON = str(REMOTION / '.venv' / 'bin' / 'python')
STAGES = [('rendition] voice', 'Recording the narration'), ('audio-audit', 'Checking the narration'), ('alignment', 'Timing the words'),
          ('narration-room', 'Timing the words'), ('render] running', 'Drawing the film')]


def film_list(root=BUNDLES):
    films = []
    found = [p for p in Path(root).glob('*/bundle.json') if re.fullmatch(r'C\d+', p.parent.name)]     # never a folder set aside
    for path in sorted(found, key=lambda p: int(p.parent.name[1:])):
        manifest = rendition.read(path)
        films.append({'id': path.parent.name, 'title': manifest['title'].split(':')[0], 'minutes': round(rendition.read(path.parent / 'master.json')['seconds'] / 60, 1)})
    return films


def job_id(film, voice_sha, template, logo_sha):
    return f"{film}-{hashlib.sha256(f'{voice_sha}{template}{logo_sha}'.encode()).hexdigest()[:12]}"


def progress_of(log):
    """A teacher's words for how far a film has got, from the rendition's log."""
    if not log.exists():
        return ''
    text, found = log.read_text(errors='replace'), 'Starting'     # never 'ready': only a finished job, with its QA, says that
    for mark, words in STAGES:
        if mark in text:
            found = words
    return found


class Studio:
    def __init__(self, root=DATA):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        for name, make in (('access-code', lambda: '-'.join(secrets.token_hex(2) for _ in range(3))), ('session-key', lambda: secrets.token_hex(32))):
            path = self.root / name
            if not path.exists():
                path.write_text(make())
                path.chmod(0o600)
        self.code = (self.root / 'access-code').read_text().strip()
        self.key = (self.root / 'session-key').read_text().strip().encode()
        self.jobs_path = self.root / 'jobs.json'
        self.jobs = json.loads(self.jobs_path.read_text()) if self.jobs_path.exists() else {}
        for job in self.jobs.values():
            if job['state'] == 'running':       # the service restarted under it: its stages are cached, so it carries on
                job['state'] = 'queued'
        self.save_jobs()

    def save_jobs(self):
        self.jobs_path.write_text(json.dumps(self.jobs, indent=1))

    def token(self):
        stamp = str(int(time.time()))
        return f"{stamp}.{hmac.new(self.key, stamp.encode(), hashlib.sha256).hexdigest()}"

    def signed_in(self, request):
        value = request.cookies.get(COOKIE, '')
        stamp, _, mac = value.partition('.')
        return bool(mac) and hmac.compare_digest(mac, hmac.new(self.key, stamp.encode(), hashlib.sha256).hexdigest())

    def settings(self):
        path = self.root / 'settings.json'
        return json.loads(path.read_text()) if path.exists() else {'template': 'teal'}

    def save_settings(self, **changes):
        value = {**self.settings(), **changes}
        (self.root / 'settings.json').write_text(json.dumps(value, indent=1))
        return value

    def voice(self):
        path = self.root / 'voice' / 'consent.json'
        return json.loads(path.read_text()) if path.exists() and (self.root / 'voice' / 'voice.wav').exists() else None

    def record_voice(self, body, consent, name):
        if not consent:
            raise HTTPException(400, 'Please tick the consent box before recording.')
        if not name.strip():
            raise HTTPException(400, 'Please enter your name.')
        if not 1000 < len(body) <= MAX_RECORDING:
            raise HTTPException(400, 'That recording could not be read. Please record again.')
        takes = self.root / 'takes'
        takes.mkdir(exist_ok=True)
        take = takes / f'{time.strftime("%Y%m%d-%H%M%S")}.webm'
        take.write_bytes(body)
        trial = takes / (take.stem + '-check')
        try:
            report = rendition.prepare_voice(take, trial, rendition.load_config())
        except subprocess.CalledProcessError:
            raise HTTPException(400, 'That recording could not be read. Please record again.') from None
        if not report['ok']:
            return report
        voice = self.root / 'voice'
        if voice.exists():                      # kept aside, never overwritten: films made in it still name it
            voice.rename(self.root / f'voice.old-{time.strftime("%Y%m%d-%H%M%S")}')
        voice.mkdir()
        (voice / 'voice.wav').write_bytes((trial / 'voice.wav').read_bytes())
        (voice / 'voice.json').write_text(json.dumps({'reference_audio': str((voice / 'voice.wav').resolve()), 'reference_transcript': rendition.PASSAGE}))
        sha = hashlib.sha256((voice / 'voice.wav').read_bytes()).hexdigest()
        (voice / 'consent.json').write_text(json.dumps({'name': ' '.join(name.split()), 'consent_text': CONSENT, 'passage': rendition.PASSAGE, 'live_recording': True,
                                                        'when': time.strftime('%Y-%m-%d %H:%M:%S %z'), 'take': take.name, 'voice_sha256': sha, 'measures': report['measures']}, indent=1))
        return report

    def set_logo(self, body):
        import io
        from PIL import Image, UnidentifiedImageError
        if len(body) > MAX_LOGO:
            raise HTTPException(400, 'The logo must be under 2 MB.')
        try:
            image = Image.open(io.BytesIO(body))
            if image.format not in ('PNG', 'JPEG', 'WEBP'):
                raise HTTPException(400, 'Please use a PNG or JPG logo.')
            image = image.convert('RGBA')
        except (UnidentifiedImageError, OSError):
            raise HTTPException(400, 'Please use a PNG or JPG logo.') from None
        image.thumbnail((256, 256))
        image.save(self.root / 'logo.png')
        self.save_settings(logo=True, logo_sha=hashlib.sha256((self.root / 'logo.png').read_bytes()).hexdigest()[:16])

    def enqueue(self, film):
        voice, settings = self.voice(), self.settings()
        if not voice:
            raise HTTPException(400, 'Please record your voice in Settings first.')
        if film not in {f['id'] for f in film_list()}:
            raise HTTPException(404, 'No such film.')
        ident = job_id(film, voice['voice_sha256'], settings['template'], settings.get('logo_sha', ''))
        with self.lock:
            job = self.jobs.get(ident)
            if not job or job['state'] == 'failed':
                self.jobs[ident] = {'id': ident, 'film': film, 'template': settings['template'], 'logo': settings.get('logo_sha', ''), 'voice_sha': voice['voice_sha256'], 'name': voice['name'],
                                    'state': 'queued', 'queued': time.time()}
                self.save_jobs()
        self.wake.set()
        return ident

    def next_job(self):
        with self.lock:
            waiting = sorted((j for j in self.jobs.values() if j['state'] == 'queued'), key=lambda j: j['queued'])
            if not waiting:
                return None
            waiting[0]['state'] = 'running'
            self.save_jobs()
            return waiting[0]

    def run_job(self, job):
        out = self.root / 'renditions' / job['id']
        out.mkdir(parents=True, exist_ok=True)
        # Only the current voice is at root/voice; a job whose voice has since been replaced would otherwise take the new one.
        voice = self.voice()
        if not voice or voice['voice_sha256'] != job['voice_sha']:
            return {'state': 'failed', 'error': 'The voice changed while this film was waiting. Please start it again.'}
        command = [PYTHON, '-m', 'infofilm.rendition', 'render', str(BUNDLES / job['film']), str(out), '--voice', str(self.root / 'voice'), '--template', job['template'], '--name', job['name']]
        if job.get('logo') and (self.root / 'logo.png').exists():
            command += ['--logo', str(self.root / 'logo.png')]
        with (out / 'log.txt').open('a') as log:
            finished = subprocess.run(command, cwd=REMOTION, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        result = out / 'rendition.json'
        if finished.returncode == 0 and result.exists():
            value = json.loads(result.read_text())
            if value.get('qa'):
                return {'state': 'done', 'video': value['video'], 'seconds': value['seconds']}
            return {'state': 'failed', 'error': 'The finished film did not pass its final check.'}
        text = (out / 'log.txt').read_text(errors='replace')
        return {'state': 'failed', 'error': ('Some narration in this voice did not come out clearly. Please try recording your voice again.'
                                             if 'did not pass its audit' in text or 'Narration' in text[-1500:] else 'This film could not be made. We have kept the details.')}

    def worker(self):
        while True:
            job = self.next_job()
            if not job:
                self.wake.wait(5)
                self.wake.clear()
                continue
            try:
                outcome = self.run_job(job)
            except Exception as exc:  # noqa: BLE001 - one film's failure must not stop the queue
                (self.root / 'worker-errors.log').open('a').write(f'{job["id"]}: {exc!r}\n')
                outcome = {'state': 'failed', 'error': 'This film could not be made. We have kept the details.'}
            with self.lock:
                job.update(outcome)
                self.save_jobs()

    def state(self):
        voice, settings = self.voice(), self.settings()
        current = job_id('', voice['voice_sha256'] if voice else '', settings['template'], settings.get('logo_sha', ''))[1:]
        films = []
        for film in film_list():
            ident = film['id'] + '-' + current
            job = self.jobs.get(ident)
            row = {**film, 'state': job['state'] if job else 'none', 'job': ident}
            if job:
                row['error'] = job.get('error')
                if job['state'] == 'running':
                    row['progress'] = progress_of(self.root / 'renditions' / ident / 'log.txt')
                if job['state'] == 'done':
                    row['actual_minutes'] = round(job['seconds'] / 60, 1)
            films.append(row)
        return {'chapter': CHAPTER, 'passage': rendition.PASSAGE, 'consent': CONSENT, 'films': films, 'settings': settings,
                'voice': {'name': voice['name'], 'when': voice['when']} if voice else None,
                'templates': [{'id': k, 'label': v['label'], 'background': v['background'], 'accent': v['accent'], 'text': v['text']} for k, v in rendition.TEMPLATES.items()],
                'samples': sorted(p.stem for p in (self.root / 'samples').glob('*.jpg')) if (self.root / 'samples').exists() else []}


def build_app(studio):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def need(request):
        if not studio.signed_in(request):
            raise HTTPException(401, 'Please sign in.')

    @app.get('/', response_class=HTMLResponse)
    def index():
        return (HERE / 'index.html').read_text()

    @app.post('/api/login')
    async def login(request: Request):
        given = str((await request.json()).get('code', '')).strip()
        if not hmac.compare_digest(given.encode(), studio.code.encode()):
            time.sleep(1)
            raise HTTPException(401, 'That code is not right.')
        response = JSONResponse({'ok': True})
        response.set_cookie(COOKIE, studio.token(), httponly=True, secure=True, samesite='lax', max_age=30 * 86400)
        return response

    @app.get('/api/state')
    def state(request: Request):
        need(request)
        return studio.state()

    @app.post('/api/voice')
    async def voice(request: Request, consent: int = 0, name: str = ''):
        need(request)
        body = await request.body()
        return await run_in_thread(studio.record_voice, body, bool(consent), name)

    @app.post('/api/template')
    async def template(request: Request):
        need(request)
        chosen = (await request.json()).get('template')
        if chosen not in rendition.TEMPLATES:
            raise HTTPException(400, 'No such background.')
        studio.save_settings(template=chosen)
        return {'ok': True}

    @app.post('/api/logo')
    async def logo(request: Request):
        need(request)
        studio.set_logo(await request.body())
        return {'ok': True}

    @app.delete('/api/logo')
    def no_logo(request: Request):
        need(request)
        studio.save_settings(logo=False, logo_sha='')
        return {'ok': True}

    @app.get('/api/logo')
    def get_logo(request: Request):
        need(request)
        return FileResponse(studio.root / 'logo.png', headers={'Cache-Control': 'no-store'})

    @app.get('/api/voice.wav')
    def voice_file(request: Request):
        need(request)
        return FileResponse(studio.root / 'voice' / 'voice.wav', headers={'Cache-Control': 'no-store'})

    @app.get('/api/sample/{name}')
    def sample(name: str, request: Request):
        need(request)
        if not re.fullmatch(r'[a-z]+-[a-z]+', name) or not (studio.root / 'samples' / f'{name}.jpg').exists():
            raise HTTPException(404)
        return FileResponse(studio.root / 'samples' / f'{name}.jpg')

    @app.post('/api/make/{film}')
    def make(film: str, request: Request):
        need(request)
        return {'job': studio.enqueue(film)}

    @app.get('/api/film/{job}')
    def film(job: str, request: Request, download: int = 0):
        need(request)
        row = studio.jobs.get(job)
        if not row or row['state'] != 'done':
            raise HTTPException(404)
        title = next((f['title'] for f in film_list() if f['id'] == row['film']), row['film'])
        return FileResponse(row['video'], media_type='video/mp4', filename=f'{title}.mp4' if download else None)

    threading.Thread(target=studio.worker, daemon=True).start()
    return app


async def run_in_thread(fn, *args):
    import asyncio
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18680)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(build_app(Studio()), host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
