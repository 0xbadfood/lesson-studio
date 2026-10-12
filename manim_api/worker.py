"""One durable queue worker; active pipeline processes survive API restarts."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

from .settings import ROOT
from .storage import read_json,write_json


def process_identity(pid):
    try:
        stat=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()
        return None if stat[0]=='Z' else stat[19]
    except (OSError,IndexError):return None


def stop_process(pid,identity):
    if not pid or process_identity(pid)!=identity:return
    try:os.killpg(pid,signal.SIGTERM)
    except ProcessLookupError:return
    deadline=time.monotonic()+2
    while time.monotonic()<deadline and process_identity(pid)==identity:
        time.sleep(.05)
    if process_identity(pid)==identity:
        try:os.killpg(pid,signal.SIGKILL)
        except ProcessLookupError:pass


class Worker:
    def __init__(self,store,settings):
        self.store,self.settings=store,settings
        self.stop=threading.Event()
        self.wake=threading.Event()
        self.thread=None
        self.lock=None
        self.children={}

    def start(self):
        self.lock=(self.store.root/'worker.lock').open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError('Another API worker already owns this queue')
        self.thread=threading.Thread(target=self.loop,name='manim-video-worker',daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set();self.wake.set()
        if self.thread:self.thread.join(timeout=3)
        if self.lock:self.lock.close()

    def cancel(self,job_id):
        with self.store.connection() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if row is None:raise KeyError(job_id)
            if row['status'] not in ('queued','running'):
                raise ValueError('Only queued or running jobs can be cancelled')
            db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?",(time.time(),job_id))
        stop_process(row['pid'],row['pid_start'])
        write_json(self.store.directory(job_id)/'state.json',{'stage':'cancelled','message':'Cancelled'})
        self.wake.set()
        return self.store.get(job_id)

    def tick(self):
        with self.store.connection() as db:
            active=db.execute("SELECT * FROM jobs WHERE status='running' ORDER BY created LIMIT 1").fetchone()
        if active:
            job=self.store.directory(active['id'])
            child=self.children.get(active['id'])
            if child and child.poll() is not None:self.children.pop(active['id'],None)
            terminal=job/'terminal.json'
            if terminal.exists() and read_json(terminal).get('run_id')==active['run_id']:
                result=read_json(terminal)
                with self.store.connection() as db:
                    db.execute("UPDATE jobs SET status=?,error=?,updated=? WHERE id=? AND status='running'",
                               (result['status'],result.get('error'),time.time(),active['id']))
                return
            if process_identity(active['pid'])!=active['pid_start']:
                with self.store.connection() as db:
                    db.execute("UPDATE jobs SET status='interrupted',error=?,updated=? WHERE id=? AND status='running'",
                               ('Worker process stopped; resume to reuse saved artifacts',time.time(),active['id']))
                return
            state=job/'state.json'
            started=read_json(job/'process.json')['started']
            if time.time()-started>self.settings.job_timeout:
                stop_process(active['pid'],active['pid_start'])
                with self.store.connection() as db:
                    db.execute("UPDATE jobs SET status='failed',error='Job timeout exceeded',updated=? WHERE id=?",(time.time(),active['id']))
                write_json(state,{'stage':'failed','message':'Job timeout exceeded'})
            return
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:return
            job=self.store.directory(row['id'])
            run_id=uuid.uuid4().hex
            (job/'terminal.json').unlink(missing_ok=True)
            with (job/'worker.log').open('a') as log:
                process=subprocess.Popen([sys.executable,'-u','-m','manim_api.pipeline','--job',str(job),'--run-id',run_id],
                    cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            identity=process_identity(process.pid)
            write_json(job/'process.json',{'pid':process.pid,'identity':identity,'started':time.time(),'run_id':run_id})
            db.execute("UPDATE jobs SET status='running',pid=?,pid_start=?,run_id=?,updated=? WHERE id=?",
                       (process.pid,identity,run_id,time.time(),row['id']))
            self.children[row['id']]=process

    def loop(self):
        while not self.stop.is_set():
            try:self.tick()
            except Exception as exc:
                # Keep a durable diagnostic rather than silently losing the queue.
                write_json(self.store.root/'worker-error.json',{'error':str(exc),'time':time.time()})
            self.wake.wait(.5);self.wake.clear()
