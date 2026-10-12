"""Recheck an accepted scene against current deterministic rendering checks."""
import argparse
import hashlib
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.models import Storyboard
from manim_api.renderer import render,checkpoints
from manim_api.settings import Settings
from manim_api.storage import read_json,write_json

parser=argparse.ArgumentParser()
parser.add_argument('job_id')
parser.add_argument('scene_id')
args=parser.parse_args()
job=ROOT/'api-data/runs'/args.job_id
scene=job/'scenes'/args.scene_id
code=(scene/'scene.py').read_text()
plan=Storyboard.model_validate(read_json(job/'storyboard.json'))
spec=next(spec for spec in plan.scenes if spec.id==args.scene_id)
try:
    preview,geometry=render(Settings(**read_json(job/'settings.json')),scene/'preview',code,'preview',spec.duration_seconds)
    checkpoints(preview,scene/'preview',geometry['duration'])
except ValueError as exc:
    error=str(exc)
    (scene/'feedback.txt').write_text(error)
    write_json(scene/'feedback.json',{'source_sha256':hashlib.sha256(code.encode()).hexdigest(),
                                     'error':error,'reviewer':'Current deterministic preview checks'})
    print('Preview rejected by current checks; feedback saved for Qwen',flush=True)
    print(error[-2400:],flush=True)
    raise SystemExit(1)
else:
    print('Preview passed current checks',flush=True)
