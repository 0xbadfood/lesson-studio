"""Start the API detached with durable logs; active jobs remain resumable."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.settings import Settings
from manim_api.worker import process_identity


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=18610)
    args=parser.parse_args()
    root=Path(Settings.from_env().data_root);root.mkdir(parents=True,exist_ok=True)
    saved=root/'server.json'
    if saved.exists():
        old=json.loads(saved.read_text())
        if process_identity(old['pid'])==old['identity']:
            print('API already running on port',old['port']);return
    with (root/'server.log').open('a') as log:
        process=subprocess.Popen([sys.executable,'-u','-m','manim_api','--host','0.0.0.0','--port',str(args.port)],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise SystemExit('API startup failed; inspect '+str(root/'server.log'))
        try:
            response=httpx.get(f'http://127.0.0.1:{args.port}/',timeout=1)
            response.raise_for_status();break
        except httpx.HTTPError:time.sleep(.2)
    else:
        process.terminate();raise SystemExit('API did not become ready in time')
    saved.write_text(json.dumps({'pid':process.pid,'identity':process_identity(process.pid),'port':args.port},indent=2)+'\n')
    print(f'Running on 0.0.0.0:{args.port}, PID {process.pid}')
    print('API token:',root/'api-token')
    print('Log:',root/'server.log')


if __name__=='__main__':main()
