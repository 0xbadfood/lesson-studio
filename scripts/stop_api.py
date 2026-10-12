"""Stop only the API; detached video workers keep running."""
import json
import os
from pathlib import Path
import signal
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.settings import Settings
from manim_api.worker import process_identity

path=Path(Settings.from_env().data_root)/'server.json'
if not path.exists():raise SystemExit('No saved API process')
saved=json.loads(path.read_text())
if process_identity(saved['pid'])!=saved['identity']:raise SystemExit('Saved API process is no longer running')
os.kill(saved['pid'],signal.SIGTERM)
print('Stopping API PID',saved['pid'],'; active video jobs continue.')
