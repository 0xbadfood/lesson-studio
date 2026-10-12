import contextlib
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


class JobStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.root / 'jobs.sqlite3'
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, request TEXT NOT NULL, request_hash TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                pid INTEGER, pid_start TEXT, error TEXT, run_id TEXT,
                idempotency_key TEXT UNIQUE)''')

    @contextlib.contextmanager
    def connection(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def directory(self, job_id):
        if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
            raise KeyError(job_id)
        return self.root / 'runs' / job_id

    def get(self, job_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        value = dict(row)
        value['request'] = json.loads(value['request'])
        state = self.directory(job_id) / 'state.json'
        value['progress'] = read_json(state) if state.exists() else {'stage': 'queued', 'message': 'Waiting for the worker'}
        value['downloads'] = {}
        for kind, name in DOWNLOADS.items():
            if (self.directory(job_id)/name).is_file() and (kind != 'video' or value['status'] == 'succeeded'):
                value['downloads'][kind] = f'/api/jobs/{job_id}/files/{kind}'
        for private in ['pid', 'pid_start', 'request_hash', 'idempotency_key']:
            value.pop(private, None)
        return value

    def submit(self, payload, settings, key=None):
        encoded = json.dumps(payload, sort_keys=True)
        signature = hashlib.sha256(encoded.encode()).hexdigest()
        now, job_id = time.time(), uuid.uuid4().hex
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                existing = db.execute('SELECT id,request_hash FROM jobs WHERE idempotency_key=?', (key,)).fetchone()
                if existing:
                    if existing['request_hash'] != signature:
                        raise ValueError('Idempotency key was already used for different input')
                    return self.get(existing['id'])
            directory = self.directory(job_id)
            write_json(directory/'request.json', payload)
            write_json(directory/'settings.json', settings.public())
            db.execute('INSERT INTO jobs(id,request,request_hash,status,created,updated,idempotency_key) VALUES(?,?,?,?,?,?,?)',
                       (job_id, encoded, signature, 'queued', now, now, key))
        return self.get(job_id)

    def list(self, limit=50):
        with self.connection() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM jobs ORDER BY created DESC LIMIT ?', (limit,))]
        return [self.get(i) for i in ids]

    def resume(self, job_id):
        with self.connection() as db:
            changed = db.execute("UPDATE jobs SET status='queued',error=NULL,pid=NULL,pid_start=NULL,updated=? WHERE id=? AND status IN ('failed','interrupted','cancelled')", (time.time(), job_id)).rowcount
        if not changed:
            self.get(job_id)
            raise ValueError('Only failed, interrupted or cancelled jobs can resume')
        (self.directory(job_id)/'terminal.json').unlink(missing_ok=True)
        write_json(self.directory(job_id)/'state.json', {'stage': 'queued', 'message': 'Queued to resume saved work'})
        return self.get(job_id)


DOWNLOADS = {'video': 'output.mp4', 'code': 'source.zip', 'storyboard': 'storyboard.json',
             'research': 'research.json', 'report': 'report.json', 'log': 'worker.log',
             'token_usage': 'token-usage.json', 'token_csv': 'token-usage.csv'}
