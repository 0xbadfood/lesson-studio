from contextlib import asynccontextmanager
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import shutil
import time
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import httpx

from .models import VideoRequest
from .settings import Settings,research_environment
from .storage import DOWNLOADS,JobStore
from .worker import Worker


class Login(BaseModel):
    token: str


def load_token(root):
    if os.environ.get('MANIM_API_KEY'):return os.environ['MANIM_API_KEY']
    path=Path(root)/'api-token'
    if not path.exists():
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as file:file.write(secrets.token_urlsafe(32)+'\n')
        except FileExistsError:pass
    return path.read_text().strip()


def create_app(settings=None,*,start_worker=True):
    settings=settings or Settings.from_env()
    store=JobStore(settings.data_root)
    worker=Worker(store,settings)
    token=load_token(store.root)
    cookie=hmac.new(token.encode(),b'manim-browser-session',hashlib.sha256).hexdigest()
    bearer=HTTPBearer(auto_error=False)
    cache={}

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:worker.start()
        try:yield
        finally:
            if start_worker:worker.close()

    app=FastAPI(title='Manim Video API',version='1.1.0',lifespan=lifespan)
    app.state.store=store;app.state.worker=worker;app.state.settings=settings;app.state.api_key=token

    def authorize(request:Request,credentials:HTTPAuthorizationCredentials|None=Security(bearer)):
        supplied=credentials.credentials if credentials else ''
        if not (secrets.compare_digest(supplied,token) or secrets.compare_digest(request.cookies.get('manim_session',''),cookie)):
            raise HTTPException(401,'Sign in or send Authorization: Bearer <API token>')

    @app.middleware('http')
    async def origins(request,call_next):
        origin=request.headers.get('origin')
        if request.method not in ('GET','HEAD','OPTIONS') and origin and urlsplit(origin).netloc!=request.url.netloc:
            return JSONResponse({'detail':'Cross-origin writes are not allowed'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        return response

    @app.get('/',response_class=HTMLResponse,include_in_schema=False)
    def page():return (Path(__file__).parent/'index.html').read_text()

    @app.post('/api/session',include_in_schema=False)
    def login(payload:Login):
        if not secrets.compare_digest(payload.token,token):raise HTTPException(401,'Invalid API token')
        response=JSONResponse({'authenticated':True})
        response.set_cookie('manim_session',cookie,httponly=True,samesite='strict',max_age=86400)
        return response

    @app.delete('/api/session',include_in_schema=False)
    def logout():
        response=JSONResponse({'authenticated':False});response.delete_cookie('manim_session');return response

    @app.get('/api/health',dependencies=[Depends(authorize)])
    def health():
        if time.time()-cache.get('time',0)<10:return cache['value']
        services={'manim_runtime':Path(settings.manim_python).is_file(),
            'research_runtime':Path(settings.research_python).is_file(),
            'remotion_research':(Path(settings.remotion_root)/'infofilm/research_worker.py').is_file(),
            'research_key':bool(research_environment(settings).get('TAVILY_API_KEY')),
            'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),'sandbox':bool(shutil.which('bwrap'))}
        model=None
        if settings.coding_provider=='luna':
            services['coding_credential']=bool(os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENAI_TOKEN'))
        try:
            response=httpx.get(settings.qwen_url+'/models',timeout=5)
            response.raise_for_status();model=response.json()['data'][0]['id'];services['qwen']=True
        except (httpx.HTTPError,KeyError,IndexError,ValueError):services['qwen']=False
        result={'ready':all(services.values()),'services':services,'model':model,'qwen_url':settings.qwen_url,
                'coding_provider':settings.coding_provider,
                'coding_model':settings.luna_model if settings.coding_provider=='luna' else model,
                'audio':False,'queue_concurrency':1}
        cache.update(time=time.time(),value=result);return result

    @app.post('/api/jobs',status_code=202,dependencies=[Depends(authorize)])
    def submit(payload:VideoRequest,request:Request):
        key=request.headers.get('idempotency-key')
        if key and len(key)>200:raise HTTPException(422,'Idempotency-Key is too long')
        try:job=store.submit(payload.model_dump(),settings,key)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        worker.wake.set();return job

    @app.get('/api/jobs',dependencies=[Depends(authorize)])
    def jobs():return {'jobs':store.list()}

    @app.get('/api/jobs/{job_id}',dependencies=[Depends(authorize)])
    def get(job_id:str):
        try:return store.get(job_id)
        except KeyError:raise HTTPException(404,'Job not found')

    @app.post('/api/jobs/{job_id}/resume',dependencies=[Depends(authorize)])
    def resume(job_id:str):
        try:job=store.resume(job_id)
        except KeyError:raise HTTPException(404,'Job not found')
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        worker.wake.set();return job

    @app.post('/api/jobs/{job_id}/cancel',dependencies=[Depends(authorize)])
    def cancel(job_id:str):
        try:return worker.cancel(job_id)
        except KeyError:raise HTTPException(404,'Job not found')
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc

    @app.get('/api/jobs/{job_id}/files/{kind}',dependencies=[Depends(authorize)])
    def download(job_id:str,kind:str):
        try:job=store.get(job_id)
        except KeyError:raise HTTPException(404,'Job not found')
        if kind not in DOWNLOADS:raise HTTPException(404,'Unknown artifact')
        path=store.directory(job_id)/DOWNLOADS[kind]
        if not path.is_file() or (kind=='video' and job['status']!='succeeded'):
            raise HTTPException(409,'This output is not ready')
        media='video/mp4' if kind=='video' else 'application/zip' if kind=='code' else 'text/plain' if kind=='log' else 'text/csv' if kind=='token_csv' else 'application/json'
        return FileResponse(path,media_type=media,filename=path.name)

    return app
