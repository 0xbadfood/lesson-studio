#!/usr/bin/env python3
"""Nightly digest job: builds the chapters listed in digest-queue.txt that have no digest yet.

Runs on the Spark (systemd user timer `nightly-digest.timer`). Three lanes when the amdserver is free:
  - spark:      Qwen 27B (vision) on the Spark's own llama.cpp, :8001;
  - amd0, amd1: the amdserver switched to LLM mode through its gpu-mode API (:8099): one Lucebox Qwen3.8-27B
                server per R9700 (DFlash2 drafter, vision), :8001 and :8002, about 8 s a page each.
The amdserver is borrowed only while no infofilm job is queued or running (films need its image factory), and it
is switched back to image mode when the job ends, or at once if a film job appears. The job also skips the night
when a film is running, since the Spark's Qwen and GPU are shared. No new chapter starts after the deadline; a
chapter cut short keeps its cached model calls, so the next night resumes it.

  .venv/bin/python kb_research/nightly_digest.py [--deadline 10:30] [--no-amd] [--queue kb_research/digest-queue.txt]
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import queue
import signal
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
AMD_LLMS = {'amd0': 'http://192.168.0.103:8001/v1', 'amd1': 'http://192.168.0.103:8002/v1'}
FILM_QUEUE = Path('/home/nitin/remotion/artifacts/interface/queue.sqlite3')
QUEUE_FILE = HERE / 'digest-queue.txt'
LOGS = digest.OUT / 'nightly'
BORROWED = LOGS / 'amd-borrowed'      # present while this job holds the amdserver in LLM mode (survives a restart)


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


def visual_backlog(books, out_root=digest.OUT):
    """Digested chapters of these books that have no visual needs yet, as chapter refs (kech1:02)."""
    out = []
    for book in books:
        for folder in sorted(out_root.glob(f'{book}-[0-9][0-9]')):
            if (folder / 'digest.json').exists() and not (folder / 'visual-needs.json').exists():
                out.append(f'{book}:{folder.name[-2:]}')
    return out


MODE_KEY = Path.home() / '.config/gpu-mode/api-key'    # the amdserver's mode switch needs it for a POST (2026-10-22)


def http(url, method='GET', timeout=10):
    headers = {'X-Caller': 'nightly-digest'}
    if method == 'POST' and MODE_KEY.exists():
        headers['Authorization'] = 'Bearer ' + MODE_KEY.read_text().strip()
    request = urllib.request.Request(url, method=method, data=b'' if method == 'POST' else None, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class Amd:
    """The amdserver's mode, borrowed for the night and given back."""

    def __init__(self, log, marker=BORROWED):
        self.log, self.marker = log, marker

    @property
    def switched(self):
        return self.marker.exists()

    def mark(self, held):
        if held:
            self.marker.parent.mkdir(parents=True, exist_ok=True)
            self.marker.write_text(datetime.now().isoformat(timespec='seconds'))
        else:
            self.marker.unlink(missing_ok=True)

    def status(self):
        try:
            return http(AMD_MODE + '/status')
        except OSError:
            return None

    def borrow(self, wait=1200):
        status = self.status()
        started = time.monotonic()
        while status and status.get('target') not in (None, 'llm') and time.monotonic() - started < wait:
            time.sleep(20)                            # another switch is running (409 until it ends): let it finish
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
            self.mark(self.switched or status['mode'] == 'image' or status.get('target') == 'llm')
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
        try:
            http(AMD_MODE + '/mode/image', 'POST')
        except OSError as exc:                        # keep the marker: the next run gives it back
            self.log(f'amd: could not switch back to image mode: {exc}')
            return
        self.mark(False)
        self.log('amd: switched back to image mode')


def lane(name, endpoint, todo, deadline, stop, results, log):
    while not stop.is_set() and datetime.now() < deadline:
        try:
            ref = todo.get_nowait()
        except queue.Empty:
            return
        if ref.startswith('visual:'):                 # an already digested chapter: only its visual needs
            try:
                import visual_needs
                visual_needs.run([ref.split(':', 1)[1]], endpoint, log=lambda m: log(f'{name}: visual needs {m}'))
            except Exception as exc:                  # noqa: BLE001 - logged; the next run picks it up again
                log(f'{name}: visual needs {ref} FAILED: {type(exc).__name__}: {exc}'[:300])
            continue
        log(f'{name}: {ref} starting')
        failures = digest.run([ref], digest.OUT, endpoint, endpoint, endpoint, log=lambda m: log(f'{name}: {m}'))
        results.append({'chapter': ref, 'lane': name, 'ok': not failures,
                        'error': failures[0][1] if failures else None})
        if not failures:                              # its visual needs, a few minutes on the same lane (2026-10-22)
            try:
                import visual_needs
                visual_needs.run([ref], endpoint, log=lambda m: log(f'{name}: visual needs {m}'))
            except Exception as exc:                  # noqa: BLE001 - the digest is built; the pass can be rerun
                log(f'{name}: visual needs {ref} FAILED: {type(exc).__name__}: {exc}'[:300])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--deadline', default='10:30',
                        help='no chapter starts after this time (HH:MM), or "none" to run until the queue is done')
    parser.add_argument('--visual-backlog', default='',
                        help='books (e.g. keph1,kech1) whose digested chapters without visual needs get the pass first')
    parser.add_argument('--no-amd', action='store_true', help='do not borrow the amdserver')
    parser.add_argument('--queue', type=Path, default=QUEUE_FILE)
    args = parser.parse_args(argv)
    LOGS.mkdir(parents=True, exist_ok=True)
    instance = (LOGS / 'running.lock').open('w')     # one run at a time: a manual run and the 01:00 timer would
    try:                                              # build the same chapters and double the load on every server
        fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('another digest run is in progress: exiting', flush=True)
        return 0
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
    if args.deadline == 'none':                       # the digest is the priority work: run until the queue is done
        deadline = now + timedelta(days=30)           # (user, 2026-10-22)
    else:
        hour, minute = map(int, args.deadline.split(':'))
        deadline = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if deadline <= now:
            deadline += timedelta(days=1)
    backlog = visual_backlog([b for b in args.visual_backlog.split(',') if b])
    refs = wanted(args.queue)
    log(f'{len(backlog)} visual passes, then {len(refs)} chapters to build, deadline {deadline:%Y-%m-%d %H:%M}: '
        f'{", ".join(refs)}')
    if not refs and not backlog:
        return 0
    if film_busy():
        log('an infofilm job is queued or running: skipping tonight')
        Amd(log).give_back()                          # left in LLM mode by an interrupted night
        return 0

    amd = Amd(log)

    def stopped(*_):                                  # systemctl stop: give the amdserver back, then exit at once
        log('stopped: giving the amdserver back')      # (the digest's worker threads would hold up a normal exit;
        amd.give_back()                               # finished model calls are cached, so nothing is lost)
        os._exit(143)

    signal.signal(signal.SIGTERM, stopped)
    todo = queue.Queue()
    for ref in [f'visual:{r}' for r in backlog] + refs:
        todo.put(ref)
    stop, results, lanes, threads = threading.Event(), [], [], []

    def start(name, url):
        lanes.append((name, url))
        threads.append(threading.Thread(target=lane, args=(name, url, todo, deadline, stop, results, log), daemon=True))
        threads[-1].start()

    start('spark', SPARK_LLM)                         # the Spark works while the amdserver loads (~1 min)
    if len(backlog) + len(refs) > 1 and not args.no_amd and amd.borrow():
        for name, url in AMD_LLMS.items():
            if not todo.empty():
                start(name, url)
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
