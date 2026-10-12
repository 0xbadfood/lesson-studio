"""Resolve only the pilot's disputed matrix claim, preserving rejected reviews."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from manim_api.llm import Qwen
from manim_api.settings import Settings
from manim_api.storage import read_json, write_json
from manim_api.validation import validate_code, validate_geometry

job = ROOT / "api-data/runs/f809a309194c4736967cd1513eca10ce"
scene = job / "scenes/s02"
qwen = Qwen(Settings(**read_json(job / "settings.json")), job)
result = qwen.call(
    "pilot-isolated-row-vector-check",
    "Check this isolated arithmetic and frame question independently. "
    "R(a)=[[cos(a),-sin(a)],[sin(a),cos(a)]]. A drawing uses ROW vectors "
    "x=[1.95,0] @ R(a), y=[0,1.35] @ R(a). At a=1.35, x=[0.42706,-1.90266], "
    "y=[1.31723,0.29566]. A separate background marker is "
    "p=[r*cos(-a),r*sin(-a)]. Recompute both products. Does x have angle -a? "
    "Do the axes and marker turn in the same sense? In a camera turning by +a "
    "with a circling object, stationary inertial reference axes appear at -a. "
    "The object and string stay fixed in this camera. Is the label 'inertial "
    "reference axes' correct for the drawn white axes? Answer JSON "
    "{x_angle_negative:boolean,same_rotation_as_marker:boolean,"
    "inertial_reference_label_correct:boolean,derivation:string}. "
    "Do not infer the rotation direction from the sign in the variable name; "
    "use the actual row-vector product. Maximum 150 words.",
    thinking=256,
    max_tokens=650,
)
write_json(scene / "isolated-row-vector-check.json", result)
print(json.dumps(result, indent=2), flush=True)
if not all(result.get(k) is True for k in (
    "x_angle_negative", "same_rotation_as_marker", "inertial_reference_label_correct"
)):
    raise SystemExit("The isolated check remains unresolved")

candidate = read_json(scene / "candidate-88baf433574d49abb4285093a33ad218-0.json")
code = candidate["code"]
assert (scene / "scene.py").read_text() == code
validate_code(code)
geometry = read_json(scene / "preview/geometry.json")
validate_geometry(geometry)
grounded = read_json(scene / "grounded-frame-review.json")
major = [i for i in grounded["issues"] if i["severity"] == "major"]
assert len(major) == 1 and "axes" in major[0]["problem"]
resolution = {
    "pass": True,
    "issues": [i for i in grounded["issues"] if i["severity"] == "minor"],
    "findings": [{"verdict": "retracted", "reason": result["derivation"]}],
    "limitations": grounded["limitations"],
    "scope": "Pilot-specific human arbitration: retained Qwen's undisputed findings; "
             "retracted only its contradictory matrix claim after a fresh isolated Qwen "
             "arithmetic check and deterministic endpoint calculation. Original rejected "
             "reviews are preserved. This is not independent full-playback model approval.",
    "raw_review": str(scene / "grounded-frame-review.json"),
    "isolated_qwen_check": str(scene / "isolated-row-vector-check.json"),
    "deterministic_check": str(job / "numeric-frame-audit.json"),
}
write_json(scene / "review-resolution.json", resolution)
review = read_json(scene / "review-88baf433574d49abb4285093a33ad218-0.json")
accepted = {
    "id": "s02", "preview": str(scene / "preview/media/videos/480p15/clip.mp4"),
    "duration": geometry["duration"],
    "source_sha256": hashlib.sha256(code.encode()).hexdigest(),
    "author_model": qwen.model or read_json(job / "report.json")["author_model"],
    "review": review["review"], "review_audit": resolution,
    "geometry": str(scene / "preview/geometry.json"),
    "source": str(scene / "scene.py"), "notes": candidate["notes"],
    "supplemental_numerical_audit": str(job / "numeric-frame-audit.json"),
}
assert Path(accepted["preview"]).exists()
write_json(scene / "accepted.json", accepted)
