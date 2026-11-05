"""A finished film in another language (user, 2026-11-05: the paediatric cardiologist's films for parents, in English
and Hindi). The film engine's infofilm.languages makes it from the finished film: translation of its script, a Hindi
voice, the same pictures. Each version runs as its own process, so it survives a studio restart; its state is read
from what it leaves behind (language.json when done, the log otherwise).

<studio data>/versions.json: {"<film>:<lang>:<voice>": {film, lang, voice, run, out, log, pid, started}}
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

REMOTION = Path('/home/nitin/remotion')
OUT = REMOTION / 'artifacts' / 'languages'


def voices():
    """The voices a version can be made in, per language: [{id, label, lang}] (infofilm.languages.VOICES)."""
    from infofilm.languages import LANGUAGES, VOICES
    return [{'id': k, 'label': v['label'], 'lang': lang, 'language': LANGUAGES[lang]['name']}
            for k, v in VOICES.items() for lang in LANGUAGES]


def alive(pid):
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    try:                                   # a finished child the studio never waited for is a zombie: not alive
        return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
    except OSError:
        return False


class Versions:
    def __init__(self, root, python=REMOTION / '.venv' / 'bin' / 'python'):
        self.path, self.python, self.lock = Path(root) / 'versions.json', str(python), threading.Lock()

    def load(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self, value):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, indent=1))
        temporary.replace(self.path)

    def state(self, record):
        result = Path(record['out']) / 'language.json'
        if result.exists():
            return 'done', json.loads(result.read_text())
        if alive(record.get('pid')):
            return 'making', None
        return 'failed', None

    def of(self, film):
        out = []
        for key, record in self.load().items():
            if record['film'] == film:
                status, result = self.state(record)
                out.append({'id': key, 'lang': record['lang'], 'voice': record['voice'], 'status': status,
                            'started': record['started'], 'video': f'media/{film}/version/{key}' if result else None})
        return out

    def video(self, key):
        record = self.load()[key]
        status, result = self.state(record)
        if status != 'done':
            raise KeyError(key)
        return Path(result['video'])

    def make(self, film, run, lang, voice):
        """Start (or show) the version of a finished film; one per language and voice, made again only if it failed."""
        if not any(v['id'] == voice and v['lang'] == lang for v in voices()):
            raise KeyError(voice)
        key = f'{film}:{lang}:{voice}'
        with self.lock:
            versions = self.load()
            record = versions.get(key)
            if record and self.state(record)[0] != 'failed':
                return key
            out = OUT / f'{Path(run).name}-{lang}-{voice}'
            log = OUT / 'logs' / f'{Path(run).name}-{lang}-{voice}-{time.strftime("%Y%m%d-%H%M%S")}.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, 'w') as handle:
                process = subprocess.Popen([self.python, '-u', '-m', 'infofilm.languages', 'make', str(run), '--lang', lang, '--voice', voice],
                                           cwd=REMOTION, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                                           start_new_session=True)
            threading.Thread(target=process.wait, daemon=True).start()       # reap it, so a finished version is not a zombie
            versions[key] = {'film': film, 'lang': lang, 'voice': voice, 'run': str(run), 'out': str(out), 'log': str(log),
                             'pid': process.pid, 'started': time.time()}
            self.save(versions)
            return key
