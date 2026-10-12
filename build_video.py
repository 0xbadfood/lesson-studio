"""Repeat Qwen planning, Manim rendering, physics checks and frame review."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import qwen_workflow as qwen

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview",action="store_true",help="480p at 15 fps instead of 1080p at 30 fps")
    parser.add_argument("--reuse-plan",action="store_true",help="Use the saved Qwen storyboard")
    args = parser.parse_args()
    os.chdir(ROOT)
    if not args.reuse_plan:
        qwen.plan_video()
    qwen.validate_plan(json.loads((ROOT/"storyboard.json").read_text()))
    python = os.environ.get("MANIM_PYTHON")
    if not python:
        python = sys.executable if importlib.util.find_spec("manim") else str(Path("/home/nitin/remotion/.venv-manim-pilot/bin/python"))
    if not Path(python).exists():
        raise RuntimeError("Install requirements.txt in a Python environment and set MANIM_PYTHON to its interpreter")
    directory = ROOT/"artifacts"
    directory.mkdir(exist_ok=True)
    print("Checking physics equations and force-arrow geometry",flush=True)
    with (directory/"physics-validation.txt").open("w") as out:
        subprocess.run([python,"-m","unittest","-v","test_physics.py"],stdout=out,stderr=subprocess.STDOUT,check=True)
    quality,fps,folder = ("-ql","15","480p15") if args.preview else ("-qh","30","1080p30")
    print("Rendering with Manim",flush=True)
    subprocess.run([python,"-m","manim",quality,"--fps",fps,"centripetal_centrifugal.py","CentripetalCentrifugal"],check=True)
    video = ROOT/"media/videos/centripetal_centrifugal"/folder/"CentripetalCentrifugal.mp4"
    name = "preview" if args.preview else "final"
    subprocess.run([python,str(ROOT/"check_render.py"),str(video),"--name",name],check=True)
    fingerprint = hashlib.sha256(video.read_bytes()+(ROOT/"centripetal_centrifugal.py").read_bytes()
        +(ROOT/"storyboard.json").read_bytes()+(ROOT/"qwen_workflow.py").read_bytes()
        +(directory/"physics-validation.txt").read_bytes()).hexdigest()[:12]
    groups = {"motion":["hook","circular_motion","release","frames"],"examples":["force_law","car","summary"]}
    reviews = {}
    for group,scenes in groups.items():
        request_name = f"{name}-{group}-{fingerprint}"
        qwen.review_frames([directory/name/(scene+"-4.png") for scene in scenes],request_name)
        reviews[group] = json.loads((qwen.ART/(request_name+".result.json")).read_text())
    destination = ROOT/("centripetal_centrifugal_preview.mp4" if args.preview else "centripetal_centrifugal_qwen.mp4")
    shutil.copy2(video,destination)
    accepted = all(r.get("pass") and not any(i.get("severity")=="major" for i in r.get("issues",[])) for r in reviews.values())
    qwen.write(directory/(name+"-build.json"),{"video":str(destination),"sha256":hashlib.sha256(destination.read_bytes()).hexdigest(),
        "code_sha256":hashlib.sha256((ROOT/"centripetal_centrifugal.py").read_bytes()).hexdigest(),
        "qwen_visual_review_passed":accepted,"reviews":reviews,
        "review_scope":"Selected still frames plus source code; no audio or full playback review"})
    print(f"Video: {destination}\nQwen review passed: {accepted}",flush=True)
    if not accepted:
        raise SystemExit("Review found major issues. Inspect the saved reports and verify suggested changes against the numerical checks.")


if __name__=="__main__": main()
