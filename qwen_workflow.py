"""Qwen planning and review for the Manim circular-motion explainer.

Uses curl for transport; all requests/responses stay in artifacts/qwen.
Python writes the animation code; Qwen supplies and reviews its storyboard.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts" / "qwen"
BASE = os.environ.get("QWEN_BASE_URL","http://10.8.0.5:8001/v1").rstrip("/")
EXTERNAL_TRANSPORT = False
IDS = ["hook", "circular_motion", "release", "force_law", "frames", "car", "summary"]
FACTS = """Uniform circular motion in an inertial frame:
velocity is tangent, acceleration and NET force are inward; F_net=m*v*v/r.
Centripetal names the radial net force, not a new force alongside tension/friction.
On cutting the string with no other horizontal forces, the object follows the
instantaneous tangent at constant speed. This is an ideal horizontal top view.
The rotating frame has a fixed angular speed omega. Its centrifugal pseudo-force
is m*omega*omega*r radially outward. Before release, v=omega*r, and the inward
tension balances it for an object stationary in that rotating frame.
After release, the inertial trajectory is p(t)=p0+v0*t; rotating coordinates are
R(-omega*t)*p(t). Relative motion also requires Coriolis force -2m omega cross v_rel;
centrifugal force alone does not explain the curved rotating-frame path.
For a left-turning car, road friction supplies inward net force to the car, and
the seat/belt/door supplies inward contact force to the passenger. In a top view,
the unconstrained passenger continues tangent until contact; no real outward
force is required in the inertial account. Centrifugal force is useful in a
rotating frame, but is not an extra interaction with another object.
Force comparisons at fixed mass and radius: v,2v,3v -> F,4F,9F.
Example m=1 kg,r=2 m: v=2,4,6 m/s -> F=2,8,18 N. Diagrams are schematic.
"""


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def call(name, prompt, images=(), max_tokens=5500, request_timeout=240, enable_thinking=False, thinking_budget_tokens=None):
    ART.mkdir(parents=True, exist_ok=True)
    result_file = ART / (name + ".result.json")
    request_file = ART / (name + ".request.json")
    signature = hashlib.sha256(json.dumps({"base_url":BASE,"prompt":prompt,"max_tokens":max_tokens,
        **({"enable_thinking":True} if enable_thinking else {}),
        **({"thinking_budget_tokens":thinking_budget_tokens} if thinking_budget_tokens is not None else {}),
        "images":[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in images]},sort_keys=True).encode()).hexdigest()
    if result_file.exists() and request_file.exists():
        saved = json.loads(request_file.read_text())
        if saved.get("input_hash")==signature or (
            "input_hash" not in saved and not images and saved.get("prompt")==prompt
            and saved.get("settings",{}).get("max_tokens")==max_tokens):
            saved["input_hash"] = signature
            write(request_file,saved)
            return json.loads(result_file.read_text())
        raise RuntimeError(f"Inputs changed for {name}; choose a new --name (or archive old planning artifacts for a new plan)")
    if EXTERNAL_TRANSPORT:
        model = json.loads((ART / "models.json").read_text())["data"][0]["id"]
    else:
        identity = subprocess.run(["curl", "-sS", "--fail-with-body", "--max-time", "20",
                                   BASE + "/models"], capture_output=True, text=True, check=True)
        model = json.loads(identity.stdout)["data"][0]["id"]
    content = prompt
    if images:
        content = [{"type": "text", "text": prompt}]
        for path in images:
            content.append({"type": "text", "text": "Checkpoint: " + Path(path).name})
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()}})
    body = {"model": model, "messages": [
        {"role": "system", "content": "Return one complete valid JSON object, without Markdown fences. Review independently and report actual evidence. Never claim you watched video when given still frames."},
        {"role": "user", "content": content}], "temperature": 0.15, "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}, "chat_template_kwargs": {"enable_thinking": enable_thinking}}
    if thinking_budget_tokens is not None:
        body["thinking_budget_tokens"] = thinking_budget_tokens
    transport = ART / (name + ".transport.json")
    start = time.monotonic()
    if EXTERNAL_TRANSPORT:
        incoming = ART / (name + ".incoming.json")
        if not incoming.exists():
            write(transport, body)
            print("Pending external transport: " + str(transport), flush=True)
            raise SystemExit(0)
        raw = json.loads(incoming.read_text())
        transport.unlink(missing_ok=True)
        incoming.unlink()
    else:
        write(transport, body)
        try:
            proc = subprocess.run(["curl", "-sS", "--fail-with-body", "--max-time", str(request_timeout), BASE + "/chat/completions",
                                   "-H", "Content-Type: application/json", "--data-binary", "@" + str(transport)],
                                  capture_output=True, text=True, check=True)
        finally:
            transport.unlink(missing_ok=True)
        raw = json.loads(proc.stdout)
    write(request_file, {"base_url": BASE, "model": model, "prompt": prompt,"input_hash":signature,
        "images": [str(x) for x in images], "settings": {k:v for k,v in body.items() if k != "messages"}})
    raw["elapsed_seconds"] = round(time.monotonic() - start, 3) if not EXTERNAL_TRANSPORT else None
    write(ART / (name + ".response.json"), raw)
    choice = raw["choices"][0]
    if choice["finish_reason"] == "length":
        raise RuntimeError("Qwen output truncated; inspect saved response")
    text = re.sub(r"<think>.*?</think>", "", choice["message"].get("content") or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    result = json.loads(text)
    write(ART / (name + ".result.json"), result)
    print(json.dumps({"stage":name,"model":model,"seconds":raw["elapsed_seconds"],"result":result},ensure_ascii=False),flush=True)
    return result


def validate_plan(plan):
    scenes = plan["scenes"]
    assert [s["id"] for s in scenes] == IDS, "Unexpected scene IDs/order"
    for scene in scenes:
        assert 8 <= scene["duration_seconds"] <= 28
        assert 0 < len(scene["caption"].split()) <= 18
        assert scene["title"] and scene["motion"] and scene["goal"]
    assert 100 <= sum(s["duration_seconds"] for s in scenes) <= 150


def plan_video():
    prompt = """Plan a compelling silent Manim explainer for high-school students,
centripetal versus centrifugal force. Landscape 1920x1080, dark navy background;
cyan ball, green velocity, red inward net force, amber rotating-frame fictitious
force. Show substantial motion, trails, tangent release, a live numerical graph,
side-by-side inertial/rotating views and a left-turning car. No photographs,
audio or LaTeX. The coding agent will implement computed physics.
Return {title:string, audience:string, assumptions:[string], scenes:[{
id:string,title:string,goal:string,motion:[string],caption:string,
duration_seconds:number,physics_checks:[string]}]}.
Exactly seven scenes in this order, with these IDs:
hook,circular_motion,release,force_law,frames,car,summary.
Total duration 100-150 seconds, each scene 8-28 seconds. Captions max 18 words,
titles max 7 words. Distinguish real interactions and frame-dependent forces.
Summary should compare directions and frames, with both forces represented.
Grounding facts:\n""" + FACTS
    plan = call("storyboard-draft-0", prompt)
    for attempt in range(3):
        validate_plan(plan)
        review = call("storyboard-review-" + str(attempt),
            "Independently review the storyboard for physics errors, clarity and executable Manim visuals. "
            "Do not ask for audio or an interactive MP4. Return {pass:boolean,issues:[{severity:'major'|'minor',scene:string,problem:string,correction:string}],strengths:[string]}. "
            "Pass means no major issues. Grounding facts:\n" + FACTS + "\nStoryboard:\n" + json.dumps(plan))
        if review.get("pass") and not any(x.get("severity") == "major" for x in review["issues"]):
            write(ROOT / "storyboard.json", plan)
            return
        if attempt < 2:
            plan = call("storyboard-draft-" + str(attempt+1), prompt + "\nRepair this storyboard:\n" + json.dumps(plan) + "\nReview:\n" + json.dumps(review))
    raise RuntimeError("Storyboard still has major issues; inspect Qwen reviews")


def review_frames(paths, name):
    plan = json.loads((ROOT / "storyboard.json").read_text())
    code = (ROOT / "centripetal_centrifugal.py").read_text()
    checks = (ROOT / "artifacts" / "physics-validation.txt")
    evidence = checks.read_text() if checks.exists() else "Not supplied"
    call(name, "Review this implementation and the attached render checkpoints. Check actual image geometry, clipping, text overlap, arrow direction, physics and whether the planned explanations are implemented. "
         "Cite checkpoint filenames and code methods. These are selected stills, not a complete playback; do not claim motion is fully validated. "
         "For arrow direction calculate radial projection from the code. Arrow(start,end) points from start to end. "
         "For p=center+r*e_r and L>0, end=p-L*e_r is inward (negative radial projection); end=p+L*e_r is outward. "
         "An inward arrow can cross the center if its force scale is longer than the diagram radius. Do not infer outward direction from that endpoint location alone. "
         "Separate factual/legibility errors (major) from optional style suggestions (minor). "
         "Return {pass:boolean,issues:[{severity:'major'|'minor',checkpoint:string,problem:string,correction:string}],strengths:[string],limitations:[string]}. "
         "Pass means no major issues.\nGrounding:\n" + FACTS + "\nNumerical checks:\n" + evidence + "\nStoryboard:\n" + json.dumps(plan) + "\nCode:\n" + code, paths, max_tokens=4500)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "review"])
    parser.add_argument("images", nargs="*")
    parser.add_argument("--name", default="render-review")
    parser.add_argument("--external-transport", action="store_true", help="Prepare requests for a network-enabled shell and consume *.incoming.json responses")
    args = parser.parse_args()
    EXTERNAL_TRANSPORT = args.external_transport
    if args.action == "plan": plan_video()
    else: review_frames([Path(x) for x in args.images], args.name)
