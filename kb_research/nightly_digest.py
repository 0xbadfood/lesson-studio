#!/usr/bin/env python3
"""Nightly digest job: builds the chapters listed in digest-queue.txt that have no digest yet.

Runs on the Spark (systemd user timer `nightly-digest.timer`). Two lanes when the amdserver is free:
  - spark: Qwen 27B (vision) on the Spark's own llama.cpp, :8001;
  - amd:   the amdserver switched to LLM mode through its gpu-mode API (:8099), Qwen 27B FP8 on vLLM, :8001.
The amdserver is borrowed only while no infofilm job is queued or running (films need its image factory), and it
is switched back to image mode when the job ends, or at once if a film job appears. The job also skips the night
when a film is running, since the Spark's Qwen and GPU are shared. No new chapter starts after the deadline; a
chapter cut short keeps its cached model calls, so the next night resumes it.

  .venv/bin/python kb_research/nightly_digest.py [--deadline 07:00] [--no-amd] [--queue kb_research/digest-queue.txt]
"""
from __future__ import annotations

import argparse
import json
import queue
import sqlite3
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import digest  # noqa: E402

SPARK_LLM = 'http://127.0.0.1:8001/v1'
AMD_MODE = 'http://192.168.0.103:8099'
AMD_LLM = 'http://192.168.0.103:8001/v1'
FILM_QUEUE = Path('/home/nitin/remotion/artifacts/interface/queue.sqlite3')
QUEUE_FILE = HERE / 'digest-queue.txt'
LOGS = digest.OUT / 'nightly'


def film_busy(path=FILM_QUEUE):
    """True while an infofilm job is queued or running."""
    if not path.exists():
        return False
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=10) as db:
        return db.execute("select count(*) from jobs where status in ('queued', 'running')").fetchone()[0] > 0


def wanted(path=QUEUE_FILE, out_root=digest.OUT):
    """Chapter ids from the queue file (one per line, # comments) that have no digest yet."""
    refs = [line.split('#')[0].strip() for line in path.read_text().splitlines()]
    return [r for r in refs if r and not (digest.chapter_folder({'id': r}, out_root) / 'digest.json').exists()]


def http(url, method='GET', timeout=10):
    request = urllib.request.Request(url, method=method, data=b'' if method == 'POST' else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class Amd:
    """The amdserver's mode, borrowed for the night and given back."""

    def __init__(self, log):
        self.log, self.switched = log, False

    def status(self):
        try:
            return http(AMD_MODE + '/status')
        except OSError:
            return None

    def borrow(self, wait=1200):
        status = self.status()
        if status is None:
            self.log('amd: not reachable, Spark only')
            return False
        if status['mode'] != 'llm' or status['services'].get('llm') != 'up':
            if status['mode'] not in ('image', 'off') and status.get('target') != 'llm':
                self.log(f'amd: in mode {status["mode"]}, left alone')
                return False
            if status.get('target') != 'llm':
                http(AMD_MODE + '/mode/llm', 'POST')
            self.switched = status['mode'] == 'image' or status.get('target') == 'llm'
            self.log('amd: switching to LLM mode')
            started = time.monotonic()
            while time.monotonic() - started < wait:
                time.sleep(20)
                status = self.status() or {}
                if status.get('mode') == 'llm' and status.get('services', {}).get('llm') == 'up':
                    break
            else:
                self.log('amd: LLM mode not ready in time, Spark only')
                self.give_back()
                return False
        self.log('amd: LLM ready')
        return True

    def give_back(self):
        if not self.switched:
            return
        self.switched = False
        try:
            http(AMD_MODE + '/mode/image', 'POST')
            self.log('amd: switched back to image mode')
        except OSError as exc:
            self.log(f'amd: could not switch back to image mode: {exc}')


def lane(name, endpoint, todo, deadline, stop, results, log):
    while not stop.is_set() and datetime.now() < deadline:
        try:
            ref = todo.get_nowait()
        except queue.Empty:
            return
        log(f'{name}: {ref} starting')
        failures = digest.run([ref], digest.OUT, endpoint, endpoint, endpoint, log=lambda m: log(f'{name}: {m}'))
        results.append({'chapter': ref, 'lane': name, 'ok': not failures,
                        'error': failures[0][1] if failures else None})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--deadline', default='07:00', help='no chapter starts after this time (HH:MM)')
    parser.add_argument('--no-amd', action='store_true', help='do not borrow the amdserver')
    parser.add_argument('--queue', type=Path, default=QUEUE_FILE)
    args = parser.parse_args(argv)
    LOGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d-%H%M')
    log_file = (LOGS / f'{stamp}.log').open('a')
    lock = threading.Lock()

    def log(message):
        line = f'{time.strftime("%H:%M:%S")} {message}'
        with lock:
            print(line, flush=True)
            log_file.write(line + '\n')
            log_file.flush()

    now = datetime.now()
    hour, minute = map(int, args.deadline.split(':'))
    deadline = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if deadline <= now:
        deadline += timedelta(days=1)
    refs = wanted(args.queue)
    log(f'{len(refs)} chapters to build, deadline {deadline:%Y-%m-%d %H:%M}: {", ".join(refs)}')
    if not refs:
        return 0
    if film_busy():
        log('an infofilm job is queued or running: skipping tonight')
        return 0

    amd = Amd(log)
    lanes = [('spark', SPARK_LLM)]
    if not args.no_amd and amd.borrow():
        lanes.append(('amd', AMD_LLM))
    todo = queue.Queue()
    for ref in refs:
        todo.put(ref)
    stop, results = threading.Event(), []
    threads = [threading.Thread(target=lane, args=(name, url, todo, deadline, stop, results, log), daemon=True)
               for name, url in lanes]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(30)
            if amd.switched and film_busy():          # a film needs the image factory back now
                log('an infofilm job appeared: giving the amdserver back and stopping after the current chapters')
                stop.set()
                amd.give_back()
    finally:
        amd.give_back()
    summary = {'started': stamp, 'ended': datetime.now().isoformat(timespec='seconds'),
               'lanes': [n for n, _ in lanes], 'results': results, 'left': wanted(args.queue)}
    (LOGS / f'{stamp}.json').write_text(json.dumps(summary, indent=1))
    log(f'done: {sum(r["ok"] for r in results)} built, {sum(not r["ok"] for r in results)} failed, '
        f'{len(summary["left"])} left')
    return 0 if all(r['ok'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
