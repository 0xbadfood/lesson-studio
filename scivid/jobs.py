"""Durable lesson queue: SQLite rows + one detached pipeline process per job.

Pipeline processes survive API restarts; a restarted worker reattaches by PID identity.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from .settings import ROOT

FILES = {'video': 'output/lesson.mp4', 'captions': 'output/lesson.vtt', 'script': 'output/script.json',
         'sources': 'output/sources.json', 'report': 'output/report.json', 'log': 'pipeline.log',
         'poster': 'output/poster.jpg'}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    tmp.replace(path)


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def process_identity(pid):
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
        return None if stat[0] == 'Z' else stat[19]
    except (OSError, IndexError, TypeError):
        return None


def stop_process(pid, identity):
    if not pid or process_identity(pid) != identity:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and process_identity(pid) == identity:
        time.sleep(.1)
    if process_identity(pid) == identity:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)


def production_seconds(folder, status):
    """Time the pipeline actually worked on a lesson: each run from its first to its last event (queue waits and
    the gap between a cancel and a resume are not counted); a running lesson counts up to now."""
    runs = {}
    try:
        with open(Path(folder) / 'events.jsonl') as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t, rid = e.get('updated'), e.get('run_id')
                if isinstance(t, (int, float)):
                    lo, hi = runs.get(rid, (t, t))
                    runs[rid] = (min(lo, t), max(hi, t))
    except OSError:
        return None
    if not runs:
        return None
    if status in ('queued', 'running'):
        last = max(runs, key=lambda r: runs[r][1])
        runs[last] = (runs[last][0], max(runs[last][1], time.time()))
    return round(sum(hi - lo for lo, hi in runs.values()))


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.root / 'lessons.sqlite3'
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, pid INTEGER, pid_start TEXT,
                run_id TEXT, error TEXT, title TEXT)''')

    @contextlib.contextmanager
    def connection(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def directory(self, lesson_id):
        if len(lesson_id) != 32 or any(c not in '0123456789abcdef' for c in lesson_id):
            raise KeyError(lesson_id)
        return self.root / 'lessons' / lesson_id

    def submit(self, request, settings, models=None):
        lesson_id, now = uuid.uuid4().hex, time.time()
        folder = self.directory(lesson_id)
        write_json(folder / 'request.json', request)
        write_json(folder / 'settings.json', settings.public())
        if models is not None:
            write_json(folder / 'models.json', models)   # frozen per lesson; changing settings never alters it
        with self.connection() as db:
            db.execute('INSERT INTO lessons(id,request,status,created,updated) VALUES(?,?,?,?,?)',
                       (lesson_id, json.dumps(request), 'queued', now, now))
        return self.get(lesson_id)

    def get(self, lesson_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM lessons WHERE id=?', (lesson_id,)).fetchone()
        if row is None:
            raise KeyError(lesson_id)
        folder = self.directory(lesson_id)
        value = {k: row[k] for k in ('id', 'status', 'created', 'updated', 'error', 'title')}
        value['request'] = json.loads(row['request'])
        value['progress'] = read_json(folder / 'state.json', {'stage': 'queued', 'message': 'Waiting to start'})
        value['chapters'] = read_json(folder / 'chapters-status.json', [])
        frozen = read_json(folder / 'models.json', {}) or {}
        value['config'] = {'preset': (frozen.get('preset') or {}).get('label'),
                           'scene_route': (frozen.get('options') or {}).get('scene_route', 'diagram')}
        usage = read_json(folder / 'usage.json', {}) or {}
        value['usage'] = {'cost': round(sum(u.get('cost', 0) for u in usage.values()), 4),
                          'input_tokens': sum(u.get('input_tokens', 0) for u in usage.values()),
                          'output_tokens': sum(u.get('output_tokens', 0) for u in usage.values()),
                          'by_connection': usage}
        value['production_seconds'] = production_seconds(folder, row['status'])
        value['files'] = {k: f'/api/lessons/{lesson_id}/files/{k}' for k, name in FILES.items()
                          if (folder / name).is_file() and (k != 'video' or row['status'] == 'succeeded')}
        return value

    def list(self, limit=100):
        with self.connection() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM lessons ORDER BY created DESC LIMIT ?', (limit,))]
        return [self.get(i) for i in ids]

    def set(self, lesson_id, **fields):
        fields['updated'] = time.time()
        with self.connection() as db:
            db.execute(f"UPDATE lessons SET {','.join(k + '=?' for k in fields)} WHERE id=?",
                       (*fields.values(), lesson_id))

    def resume(self, lesson_id):
        with self.connection() as db:
            changed = db.execute("UPDATE lessons SET status='queued',error=NULL,pid=NULL,pid_start=NULL,updated=? "
                                 "WHERE id=? AND status IN ('failed','interrupted','cancelled')",
                                 (time.time(), lesson_id)).rowcount
        if not changed:
            self.get(lesson_id)
            raise ValueError('Only failed, interrupted or cancelled lessons can resume')
        (self.directory(lesson_id) / 'terminal.json').unlink(missing_ok=True)
        write_json(self.directory(lesson_id) / 'state.json', {'stage': 'queued', 'message': 'Queued to resume saved work'})
        return self.get(lesson_id)

    def redo(self, lesson_id, chapter_id):
        """Redraw one chapter's visuals (new picture seed or diagram variation) and reassemble."""
        import re
        import shutil
        lesson = self.get(lesson_id)
        if lesson['status'] in ('queued', 'running'):
            raise ValueError('Wait for the lesson to finish before redoing a chapter')
        if not re.fullmatch(r'c[0-9]{1,2}', chapter_id) or not any(c['id'] == chapter_id for c in lesson['chapters']):
            raise KeyError(chapter_id)
        folder = self.directory(lesson_id)
        chapter = folder / 'chapters' / chapter_id
        counter = read_json(chapter / 'redo.json', {'count': 0})
        counter['count'] += 1
        write_json(chapter / 'redo.json', counter)
        for name in ('scene/scene.json', 'scene/background.png', 'diagram/accepted.json', 'diagram/progress.json',
                     'code/accepted.json',
                     'chapter.mp4',
                     'cues-resolved.json', 'render-spec.json'):
            (chapter / name).unlink(missing_ok=True)
        import glob
        for d in glob.glob(str(chapter / 'diagram-*')):
            shutil.rmtree(d, ignore_errors=True)
        (chapter / 'diagram-accepted.json').unlink(missing_ok=True)
        for name in ('media', 'scene/layers'):
            shutil.rmtree(chapter / name, ignore_errors=True)
        shutil.rmtree(folder / 'output', ignore_errors=True)
        (folder / 'lesson-raw.mp4').unlink(missing_ok=True)
        (folder / 'terminal.json').unlink(missing_ok=True)
        with self.connection() as db:
            db.execute("UPDATE lessons SET status='queued',error=NULL,pid=NULL,pid_start=NULL,updated=? WHERE id=?",
                       (time.time(), lesson_id))
        write_json(folder / 'state.json', {'stage': 'queued', 'message': f'Queued to redo chapter {chapter_id[1:]}'})
        return self.get(lesson_id)

    def delete(self, lesson_id):
        row = self.get(lesson_id)
        if row['status'] in ('queued', 'running'):
            raise ValueError('Cancel the lesson before deleting it')
        with self.connection() as db:
            db.execute('DELETE FROM lessons WHERE id=?', (lesson_id,))


class Worker:
    """Runs one lesson at a time (GPU and reviewer are single-slot today)."""

    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.stop, self.wake = threading.Event(), threading.Event()
        self.thread = self.lock = None

    def start(self):
        self.lock = (self.store.root / 'worker.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError('Another worker already owns this queue')
        self.thread = threading.Thread(target=self.loop, name='scivid-worker', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.lock:
            self.lock.close()

    def cancel(self, lesson_id):
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM lessons WHERE id=?', (lesson_id,)).fetchone()
            if row is None:
                raise KeyError(lesson_id)
            if row['status'] not in ('queued', 'running'):
                raise ValueError('Only queued or running lessons can be cancelled')
            db.execute("UPDATE lessons SET status='cancelled',updated=? WHERE id=?", (time.time(), lesson_id))
        stop_process(row['pid'], row['pid_start'])
        write_json(self.store.directory(lesson_id) / 'state.json', {'stage': 'cancelled', 'message': 'Cancelled'})
        self.wake.set()
        return self.store.get(lesson_id)

    def tick(self):
        with self.store.connection() as db:
            active = db.execute("SELECT * FROM lessons WHERE status='running' ORDER BY created LIMIT 1").fetchone()
        if active:
            folder = self.store.directory(active['id'])
            terminal = read_json(folder / 'terminal.json')
            if terminal and terminal.get('run_id') == active['run_id']:
                self.store.set(active['id'], status=terminal['status'], error=terminal.get('error'))
                return
            if process_identity(active['pid']) != active['pid_start']:
                self.store.set(active['id'], status='interrupted',
                               error='The pipeline process stopped; resume to continue from saved work')
                return
            started = read_json(folder / 'process.json', {}).get('started', time.time())
            if time.time() - started > self.settings.job_timeout:
                stop_process(active['pid'], active['pid_start'])
                self.store.set(active['id'], status='failed', error='Lesson exceeded the time limit')
            return
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM lessons WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return
            folder = self.store.directory(row['id'])
            run_id = uuid.uuid4().hex
            (folder / 'terminal.json').unlink(missing_ok=True)
            with (folder / 'pipeline.log').open('a') as log:
                process = subprocess.Popen([sys.executable, '-u', '-m', 'scivid.pipeline', '--lesson', str(folder),
                                            '--run-id', run_id], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
            identity = process_identity(process.pid)
            write_json(folder / 'process.json', {'pid': process.pid, 'identity': identity, 'started': time.time(),
                                                  'run_id': run_id})
            db.execute("UPDATE lessons SET status='running',pid=?,pid_start=?,run_id=?,updated=? WHERE id=?",
                       (process.pid, identity, run_id, time.time(), row['id']))

    def loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # keep a durable diagnostic rather than losing the queue
                write_json(self.store.root / 'worker-error.json', {'error': repr(exc), 'time': time.time()})
            self.wake.wait(.7)
            self.wake.clear()
