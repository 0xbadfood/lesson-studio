"""Remote voice adapter: lets the frozen infofilm narration code use a VibeVoice server on another machine.

infofilm assumes VibeVoice and Qwen Image share the local RTX 3090: it takes the local GPU lock, unloads the local
image model before recording and asks VibeVoice to unload afterwards (failing if the server refuses, as a resident
production server does). With a remote voice server none of that applies. This adapter runs on 127.0.0.1 for the
length of one narration, forwards every VibeVoice request to the remote server unchanged, and answers the GPU
housekeeping calls (VibeVoice unload/release, image status/unload) with "nothing to release". The local image
model therefore stays loaded, and the remote server keeps its own settings.

Run as a service (`python -m scivid.voice_proxy --remote ... --image ... --port ...`), it is infofilm's permanent
local front for remote media: voice goes to the remote VibeVoice and <base>/image/... goes to a remote image server
(the amdserver image factory). The remote servers keep their models resident: unload calls are answered without
touching them, a later load answers "loaded" at once, and "busy" is never reported, so infofilm does not abort a
narration while the factory serves someone else. VibeVoice health is reported idle (the server queues jobs itself),
so infofilm waits in the remote queue instead of refusing to share it.
"""
import argparse
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time

import httpx

HOUSEKEEPING = {
    ('POST', '/unload'): {'ok': True, 'model_loaded': None},
    ('POST', '/release-vram'): {'ok': True, 'terminating': False, 'model_loaded': None},
    ('GET', '/image/api/status'): {'state': 'unloaded', 'busy': False, 'note': 'remote voice: local image model untouched'},
    ('POST', '/image/api/unload'): {'ok': True},
}


def _handler(remote, image_remote=None, shared=False):
    image = {'state': 'loaded'}            # what infofilm believes about the image model (the factory stays loaded)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _answer(self, status, body, content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _forward(self, method):
            path = self.path.split('?', 1)[0]
            if image_remote and path.startswith('/image/'):
                return self._image(method, path)
            fixed = HOUSEKEEPING.get((method, path))
            if fixed is not None:
                return self._answer(200, json.dumps(fixed).encode())
            if path.startswith('/image/'):
                return self._answer(404, b'{"detail":"not served by the voice adapter"}')
            response = self._relay(method, remote, self.path, 'voice')
            if response is None:
                return
            content = response.content
            if shared and method == 'GET' and path == '/health' and response.status_code == 200:
                content = json.dumps({**response.json(), 'active_job': None, 'queued_or_running_jobs': 0}).encode()
            self._answer(response.status_code, content, response.headers.get('content-type', 'application/octet-stream'))

        def _image(self, method, path):
            rest = self.path[len('/image'):]
            if method == 'POST' and path == '/image/api/unload':
                image['state'] = 'unloaded'
                return self._answer(200, b'{"state":"unloaded","detail":"remote image server stays resident"}')
            if method == 'POST' and path == '/image/api/load':
                image['state'] = 'loaded'
                return self._answer(202, b'{"state":"loaded","detail":"remote image server is resident"}')
            response = self._relay(method, image_remote, rest, 'image')
            if response is None:
                return
            content = response.content
            if method == 'GET' and path == '/image/api/status' and response.status_code == 200:
                status = response.json()
                if status.get('state') == 'loaded':
                    status['state'] = image['state']
                content = json.dumps({**status, 'busy': False}).encode()
            self._answer(response.status_code, content, response.headers.get('content-type', 'application/octet-stream'))

        def _relay(self, method, base, path, what):
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() in ('content-type', 'accept')}
            try:
                with httpx.Client(timeout=600) as client:
                    return client.request(method, base + path, content=body, headers=headers)
            except httpx.HTTPError as exc:
                self._answer(502, json.dumps({'detail': f'{what} server unreachable: {exc}'}).encode())
                return None

        def do_GET(self):
            self._forward('GET')

        def do_POST(self):
            self._forward('POST')
    return Handler


def wait_until_idle(remote, log=print, timeout=3600):
    """The remote server may be busy with other work: wait for it rather than disturb it."""
    start, said = time.monotonic(), False
    while time.monotonic() - start < timeout:
        health = httpx.get(remote + '/health', timeout=20).raise_for_status().json()
        if not health.get('active_job') and not health.get('queued_or_running_jobs'):
            return health
        if not said:
            log('The voice server is busy with other work; waiting for it to finish')
            said = True
        time.sleep(15)
    raise TimeoutError('The voice server stayed busy for an hour')


@contextlib.contextmanager
def adapter(remote):
    """Yields the local base URL; image calls go to <base>/image."""
    server = ThreadingHTTPServer(('127.0.0.1', 0), _handler(remote.rstrip('/')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description='Permanent local front for remote voice and image servers')
    parser.add_argument('--remote', required=True, help='VibeVoice server, e.g. http://10.8.0.4:8092')
    parser.add_argument('--image', help='image server for <base>/image/..., e.g. http://10.8.0.8:8075')
    parser.add_argument('--port', type=int, default=18092)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port),
                                 _handler(args.remote.rstrip('/'), (args.image or '').rstrip('/') or None, shared=True))
    print(f'voice adapter on 127.0.0.1:{args.port} -> voice {args.remote}, image {args.image}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
