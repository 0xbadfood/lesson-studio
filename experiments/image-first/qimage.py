"""Minimal cached client for the local Qwen Image 2.1 service (GPU-leased)."""
import contextlib
import fcntl
import hashlib
import json
import time
from pathlib import Path

import httpx

URL = 'http://127.0.0.1:8075'
LOCK = '/tmp/infofilm-rtx3090.lock'
ROOT = Path(__file__).resolve().parent


@contextlib.contextmanager
def gpu_lease():
    # Same cooperative lock as infofilm, so narration/images never collide.
    with open(LOCK, 'a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def ensure_loaded(client):
    status = client.get(URL + '/api/status').json()
    if status['state'] != 'loaded':
        client.post(URL + '/api/load')
        while True:
            status = client.get(URL + '/api/status').json()
            if status['state'] == 'loaded':
                return
            if status['state'] not in ('loading', 'unloaded'):
                raise RuntimeError(status)
            time.sleep(3)


def generate(name, prompt, *, width=1024, height=1024, steps=30, seed=12345, references=(), out_dir=None):
    """Return the saved PNG path; identical requests reuse the cached result."""
    out_dir = Path(out_dir or ROOT / 'images')
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = [Path(r) for r in references]
    key = hashlib.sha256(json.dumps({'prompt': prompt, 'w': width, 'h': height, 'steps': steps, 'seed': seed,
        'refs': [hashlib.sha256(r.read_bytes()).hexdigest() for r in refs]}, sort_keys=True).encode()).hexdigest()[:12]
    path = out_dir / f'{name}-{key}.png'
    meta = path.with_suffix('.json')
    if path.exists() and meta.exists():
        return path
    with gpu_lease(), httpx.Client(timeout=120) as client:
        ensure_loaded(client)
        files = [('references', (r.name, r.read_bytes(), 'image/png')) for r in refs]
        data = {'prompt': prompt, 'width': width, 'height': height, 'steps': steps, 'seed': seed, 'output_format': 'png'}
        started = time.time()
        job = client.post(URL + '/api/generate', data=data, files=files or None).raise_for_status().json()
        while True:
            job = client.get(URL + f"/api/jobs/{job['id']}").json()
            if job['status'] == 'complete':
                break
            if job['status'] == 'error':
                raise RuntimeError(job['message'])
            time.sleep(2)
        path.write_bytes(client.get(URL + job['url']).raise_for_status().content)
    meta.write_text(json.dumps({'name': name, 'prompt': prompt, 'width': width, 'height': height, 'steps': steps,
        'seed': seed, 'references': [str(r) for r in refs], 'seconds': round(time.time() - started, 1),
        'job': {k: job.get(k) for k in ('inference_seconds', 'peak_allocated_gb', 'seed')}}, indent=2))
    return path
