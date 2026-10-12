"""Lesson Studio API + portal. `python -m scivid --port 18610`."""
from contextlib import asynccontextmanager
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import shutil
import time
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from . import curriculum, findings, models
from .contract import LessonRequest, STAGES, STAGE_LABELS
from .jobs import FILES, Store, Worker, read_json
from .settings import Settings

STATIC = Path(__file__).with_name('portal')


class Login(BaseModel):
    token: str


def load_token(root):
    if os.environ.get('SCIVID_API_KEY'):
        return os.environ['SCIVID_API_KEY']
    path = Path(root) / 'api-token'
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_urlsafe(24) + '\n')
    return path.read_text().strip()


def create_app(settings=None, *, start_worker=True):
    settings = settings or Settings.from_env()
    store = Store(settings.data_root)
    worker = Worker(store, settings)
    token = load_token(store.root)
    registry = models.Registry(store.root, models.default_settings(settings))
    cookie = hmac.new(token.encode(), b'lesson-studio', hashlib.sha256).hexdigest()
    bearer = HTTPBearer(auto_error=False)
    health_cache = {}
    auditor = findings.Auditor(store.root, lambda step: models.client_for(
        registry.snapshot(), step, Path(store.root) / 'review-audit', store.root))

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            if start_worker:
                worker.close()

    app = FastAPI(title='Lesson Studio', version='0.1.0', lifespan=lifespan)

    def authorize(request: Request, credentials: HTTPAuthorizationCredentials | None = Security(bearer)):
        supplied = credentials.credentials if credentials else ''
        if not (secrets.compare_digest(supplied, token) or
                secrets.compare_digest(request.cookies.get('studio_session', ''), cookie)):
            raise HTTPException(401, 'Sign in to continue')

    @app.middleware('http')
    async def guard(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and urlsplit(origin).netloc != request.url.netloc:
            return JSONResponse({'detail': 'Cross-origin writes are not allowed'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @app.get('/', response_class=HTMLResponse, include_in_schema=False)
    def portal():
        return (STATIC / 'index.html').read_text()

    @app.get('/static/{name}', include_in_schema=False)
    def static(name: str):
        path = (STATIC / name).resolve()
        if path.parent != STATIC.resolve() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.post('/api/session', include_in_schema=False)
    def login(payload: Login):
        if not secrets.compare_digest(payload.token.strip(), token):
            raise HTTPException(401, 'That access key is not right')
        response = JSONResponse({'signed_in': True})
        response.set_cookie('studio_session', cookie, httponly=True, samesite='strict', max_age=14 * 86400)
        return response

    @app.get('/api/session', include_in_schema=False)
    def session(request: Request):
        return {'signed_in': secrets.compare_digest(request.cookies.get('studio_session', ''), cookie)}

    @app.delete('/api/session', include_in_schema=False)
    def logout():
        response = JSONResponse({'signed_in': False})
        response.delete_cookie('studio_session')
        return response

    @app.get('/api/health', dependencies=[Depends(authorize)])
    def health():
        if time.time() - health_cache.get('t', 0) < 15:
            return health_cache['v']

        def reachable(url):
            try:
                return httpx.get(url, timeout=4).status_code < 500
            except httpx.HTTPError:
                return False
        services = {
            'planner': reachable(settings.planner_url + '/models'),
            'images': reachable(settings.image_url + '/api/status'),
            'voice': reachable('http://127.0.0.1:8092/health') or reachable('http://127.0.0.1:8092/'),
            'animation': Path(settings.manim_python).is_file() and bool(shutil.which('bwrap')),
            'textbooks': Path(settings.ncert_root).is_dir(),
        }
        value = {'services': services, 'ready': all(services.values()), 'stages': STAGES, 'labels': STAGE_LABELS}
        health_cache.update(t=time.time(), v=value)
        return value

    # ---------------------------------------------------------------- model settings
    @app.get('/api/settings/models', dependencies=[Depends(authorize)])
    def model_settings():
        return registry.public()

    @app.post('/api/settings/connections', dependencies=[Depends(authorize)])
    async def save_connection(request: Request):
        try:
            cid = registry.upsert(await request.json())
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc))
        return {'id': cid, **registry.public()}

    @app.delete('/api/settings/connections/{cid}', dependencies=[Depends(authorize)])
    def delete_connection(cid: str):
        try:
            registry.delete(cid)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return registry.public()

    @app.post('/api/settings/detect', dependencies=[Depends(authorize)])
    async def detect(request: Request):
        body = await request.json()
        kind = body.get('type', 'openai_chat')
        key = body.get('api_key') or None
        if not key and body.get('id'):
            data = registry.load()
            if body['id'] in data['connections']:
                key = registry.api_key(body['id'], data['connections'][body['id']])
        url = str(body.get('url') or models.TYPES.get(kind, {}).get('default_url', '')).strip()
        if kind != 'anthropic' and not url.startswith(('http://', 'https://')):
            raise HTTPException(422, 'Enter an http(s) URL')
        try:
            return {'models': models.detect_models(url, key, kind=kind)}
        except Exception as exc:  # report the provider's answer to the admin, without secrets
            message = str(exc).replace(key, '[key]') if key else str(exc)
            raise HTTPException(502, f'Could not list models: {message[:300]}')

    @app.put('/api/settings/steps', dependencies=[Depends(authorize)])
    async def assign(request: Request):
        try:
            registry.assign((await request.json()).get('assignments', {}))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return registry.public()

    @app.put('/api/settings/options', dependencies=[Depends(authorize)])
    async def set_options(request: Request):
        try:
            registry.set_options((await request.json()).get('options', {}))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return registry.public()

    @app.get('/api/findings', dependencies=[Depends(authorize)])
    def list_findings(limit: int = 60, review: str = '', reviewer: str = '', judged: str = ''):
        found, marks = findings.collect(store.root), findings.labels(store.root)
        shown = [f for f in found if (not review or f['review'] == review) and (not reviewer or f['reviewer'] == reviewer)
                 and (judged != 'no' or not findings.verdict(marks.get(f['id'])))]
        return {'stats': findings.stats(found, marks), 'total': len(found), 'audit': auditor.state,
                'findings': [{**{k: v for k, v in f.items() if k not in ('call', 'images')},
                              'has_image': bool(f['images']), 'label': f['label'], 'marks': marks.get(f['id'], {})}
                             for f in shown[:max(1, min(limit, 300))]]}

    @app.post('/api/findings/{fid}/label', dependencies=[Depends(authorize)])
    async def label_finding(fid: str, request: Request):
        body = await request.json()
        try:
            return findings.set_label(store.root, fid, body.get('verdict'), 'teacher', body.get('note', ''))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get('/api/findings/{fid}/image', dependencies=[Depends(authorize)])
    def finding_image(fid: str):
        found = next((f for f in findings.collect(store.root) if f['id'] == fid), None)
        path = Path(found['images'][0]) if found and found['images'] else None
        if not path or not path.exists() or Path(store.root).resolve() not in path.resolve().parents:
            raise HTTPException(404, 'No image for this finding')
        return FileResponse(path)

    @app.post('/api/findings/audit', dependencies=[Depends(authorize)])
    async def audit_findings(request: Request):
        body = await request.json() if (await request.body()) else {}
        try:
            return auditor.start(int(body.get('limit', 40)))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.put('/api/settings/review-rules', dependencies=[Depends(authorize)])
    async def set_review_rules(request: Request):
        try:
            registry.set_review_rules((await request.json()).get('rules', {}))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return registry.public()

    @app.post('/api/settings/presets', dependencies=[Depends(authorize)])
    async def save_preset(request: Request):
        body = await request.json()
        try:
            registry.save_preset(body.get('label'), body.get('note', ''), bool(body.get('benchmark')))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return registry.public()

    @app.post('/api/settings/presets/{pid}/apply', dependencies=[Depends(authorize)])
    def apply_preset(pid: str):
        try:
            registry.apply_preset(pid)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return registry.public()

    @app.delete('/api/settings/presets/{pid}', dependencies=[Depends(authorize)])
    def delete_preset(pid: str):
        registry.delete_preset(pid)
        return registry.public()

    @app.post('/api/settings/test/{cid}', dependencies=[Depends(authorize)])
    def test_connection(cid: str):
        import tempfile
        data = registry.load()
        if cid not in data['connections']:
            raise HTTPException(404, 'Unknown connection')
        snapshot = {'connections': data['connections'], 'steps': {'test': cid}}
        started = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                client = models.client_for(snapshot, 'test', tmp, store.root)
                reply = client.call('connection-test', 'Reply with the JSON object {"ok": true}.', thinking=0,
                                    max_tokens=200, attempts=1)
            except Exception as exc:
                return {'ok': False, 'error': str(exc)[:400]}
        return {'ok': reply.get('ok') is True, 'seconds': round(time.time() - started, 1)}

    @app.get('/api/catalog', dependencies=[Depends(authorize)])
    def catalog():
        return {'chapters': [{k: c[k] for k in ('id', 'class', 'subject', 'book_title', 'chapter', 'title')}
                             for c in curriculum.catalog(settings.ncert_root)]}

    @app.get('/api/lessons', dependencies=[Depends(authorize)])
    def lessons():
        return {'lessons': store.list()}

    @app.post('/api/lessons', status_code=202, dependencies=[Depends(authorize)])
    async def submit(request: Request):
        body = await request.json()
        config = body.pop('config', None) if isinstance(body, dict) else None
        try:
            payload = LessonRequest.model_validate(body)
        except ValidationError as exc:
            names = {'topic': 'Topic', 'duration_seconds': 'Length (seconds)', 'class_level': 'Class level',
                     'chapter': 'Chapter', 'notes': 'Notes', 'voice': 'Narrator', 'mode': 'Lesson type'}
            messages = [(names.get(str(e['loc'][-1]), '') + ': ' if e.get('loc') and str(e['loc'][-1]) in names else '')
                        + e['msg'].removeprefix('Value error, ') for e in exc.errors()]
            raise HTTPException(422, ' '.join(messages))
        if payload.chapter:
            try:
                curriculum.find(settings.ncert_root, payload.chapter)
            except KeyError:
                raise HTTPException(422, 'That chapter is not in the textbook catalogue')
        try:
            snapshot = registry.snapshot(config or None)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        lesson = store.submit(payload.model_dump(), settings, snapshot)
        worker.wake.set()
        return lesson

    @app.get('/api/lessons/{lesson_id}', dependencies=[Depends(authorize)])
    def get(lesson_id: str):
        try:
            return store.get(lesson_id)
        except KeyError:
            raise HTTPException(404, 'Lesson not found')

    @app.get('/api/lessons/{lesson_id}/details', dependencies=[Depends(authorize)])
    def details(lesson_id: str):
        try:
            folder = store.directory(lesson_id)
            store.get(lesson_id)
        except KeyError:
            raise HTTPException(404, 'Lesson not found')
        plan = (read_json(folder / 'plan.json') or {}).get('plan')
        script = (read_json(folder / 'script.json') or {}).get('script')
        evidence = read_json(folder / 'evidence.json') or {}
        events = []
        if (folder / 'events.jsonl').exists():
            import json
            events = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines()[-200:]]
        return {'plan': plan, 'script': script, 'evidence': evidence, 'report': read_json(folder / 'output/report.json'),
                'scope': read_json(folder / 'scope.json'), 'events': events}

    @app.post('/api/lessons/{lesson_id}/cancel', dependencies=[Depends(authorize)])
    def cancel(lesson_id: str):
        try:
            return worker.cancel(lesson_id)
        except KeyError:
            raise HTTPException(404, 'Lesson not found')
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post('/api/lessons/{lesson_id}/resume', dependencies=[Depends(authorize)])
    def resume(lesson_id: str):
        try:
            lesson = store.resume(lesson_id)
        except KeyError:
            raise HTTPException(404, 'Lesson not found')
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        worker.wake.set()
        return lesson

    @app.post('/api/lessons/{lesson_id}/chapters/{chapter_id}/redo', dependencies=[Depends(authorize)])
    def redo(lesson_id: str, chapter_id: str):
        try:
            lesson = store.redo(lesson_id, chapter_id)
        except KeyError:
            raise HTTPException(404, 'Lesson or chapter not found')
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        worker.wake.set()
        return lesson

    @app.delete('/api/lessons/{lesson_id}', dependencies=[Depends(authorize)])
    def delete(lesson_id: str):
        try:
            store.delete(lesson_id)
        except KeyError:
            raise HTTPException(404, 'Lesson not found')
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {'deleted': lesson_id}

    @app.get('/api/lessons/{lesson_id}/files/{kind}', dependencies=[Depends(authorize)])
    def download(lesson_id: str, kind: str):
        try:
            lesson = store.get(lesson_id)
            folder = store.directory(lesson_id)
        except KeyError:
            raise HTTPException(404, 'Lesson not found')
        if kind not in FILES:
            raise HTTPException(404, 'Unknown file')
        path = folder / FILES[kind]
        if not path.is_file() or (kind == 'video' and lesson['status'] != 'succeeded'):
            raise HTTPException(409, 'Not ready yet')
        media = {'video': 'video/mp4', 'captions': 'text/vtt', 'log': 'text/plain', 'poster': 'image/jpeg'}.get(kind,
                                                                                                         'application/json')
        name = f"{(lesson.get('title') or 'lesson').replace('/', '-')[:60]}{path.suffix}"
        return FileResponse(path, media_type=media, filename=name if kind != 'poster' else None)

    return app
