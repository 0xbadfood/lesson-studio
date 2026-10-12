"""Ask Qwen to write and repair its own complete Manim video source.

No handwritten video source is provided to the model or patched afterward.
Every installed candidate is copied verbatim from its saved model response.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import qwen_workflow as qwen

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "qwen_generated_forces.py"
CONTRACT = """Write a COMPLETE runnable Manim Community 0.21.0 Python module.
You are the coding model, not only the planner. No existing animation code is
provided: author it yourself from the storyboard. Return ONE JSON object:
{"code": "the complete Python source as a JSON string", "notes": ["..."]}.
Use class QwenForces(Scene), with construct calling seven scene methods in
storyboard order. One video, landscape 16:9, dark navy, silent, about 116 s.
Use Text with DejaVu Sans exclusively; no Tex, MathTex, DecimalNumber, LaTeX,
empty Text, or dynamic font-weight arguments. Equations use Unicode Text.
Use green velocity arrows, red inward net force, amber centrifugal pseudo-force,
cyan balls, soft white labels. Use ValueTracker + always_redraw for motion.
Use Arrow(start,end,buff=0.05), never zero-length arrows.
Clear all updaters recursively before fading a moving object or scene out.
No download, network, subprocess, shell, external assets, or other side effects.
Only permitted filesystem write: artifacts/qwen-coded-scene-timings.json.
No external video files or footage. Code must not call another renderer.
Use numpy for computed positions. Circular p=center+r*[cos θ,sin θ,0], tangent
v=ωr*[-sin θ,cos θ,0], inward arrow end=p-L*[cos θ,sin θ,0].
Arrow(start,end) points from start to end. Minus radial is inward, plus outward.
Post-release p=p0+v0*t, with SAME speed as just before release. Fit the release
distance AND its velocity arrow inside the scene. A 270° release is at the BOTTOM
with tangent to the RIGHT. A 0°/360° release is at the RIGHT with tangent UP.
Rotating coordinates after release: R(-ωt)*(p0+v0*t), relative to circle center.
Include a short Coriolis note after release. No claim that centrifugal alone
explains the relative trajectory. Before release show inward real and equal
outward fictitious forces only in the rotating panel, with stationary ball.
For graph numbers use m=1 kg,r=2 m,v=2,4,6 m/s => F=2,8,18 N.
Use manually created Text number labels for axes, not add_numbers.
Keep title in y=3.2 area, caption in y=-3.2 area, ALL other content in
x=[-6.2,6.2], y=[-2.65,2.65]. Text must never overlap diagrams, paths or arrows.
Wrap captions and scale text to a maximum width. Titles <=11 units wide.
Moving ball/arrow must stay within the content box, including at the end.
Every scene has substantial animated objects, not merely a static slide.
Show a trail and rotating force/velocity arrows, cut and tangent flight, force
vs speed graph, two viewpoints, left-turning car, animated comparison summary.
For the car, distinguish road friction on the car from inward contact on the
passenger. A passenger's initial unconstrained trajectory is straight, tangent.
Draw centrifugal arrows ONLY in an explicitly labeled rotating viewpoint.
Prefer clear large labeled schematic diagrams over a complex collision model.
Each scene's duration is the storyboard duration including opening/closing
fades; use remaining=max(0,target-(self.time-start)-closing_fade_time) before
closing. Use linear animation time for physics. No coordinate jumps during
flight. Pedagogical freeze holds may follow completed motion.
Record a list [{id,start,end,duration},...] using self.time. On construct end,
create artifacts/ if missing and write that list as JSON to
artifacts/qwen-coded-scene-timings.json, relative to this script's folder.
Import only manim, numpy, math, json, pathlib. No reads of other Python source.
Keep code compact, ideally 220-350 lines. Return the full source, no omissions.
"""


def install_candidate(name, result):
    code = result.get("code")
    if not isinstance(code,str) or not code.strip():
        raise ValueError("No complete code string in Qwen result")
    candidate = ROOT/"artifacts/qwen"/(name+".py")
    candidate.write_text(code.rstrip()+"\n")
    # Validate before executing any model-authored source. This does not repair it.
    tree = ast.parse(code,filename=str(candidate))
    imports = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module}
    imports.update(alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names)
    if imports-{"manim","numpy","math","json","pathlib"}:
        raise ValueError("Unexpected imports: "+str(imports))
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            name_called=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ""
            if name_called in {"Tex","MathTex","DecimalNumber","eval","exec","__import__"}:
                raise ValueError("Forbidden or unsupported call: "+name_called)
    if not any(isinstance(node,ast.ClassDef) and node.name=="QwenForces" for node in tree.body):
        raise ValueError("QwenForces class missing")
    DEST.write_text(code.rstrip()+"\n")
    qwen.write(ROOT/"artifacts/qwen-code-author.json",{
        "author":"Qwen3.8-27B-Q4_K_M.gguf","endpoint":qwen.BASE,
        "response":str(ROOT/"artifacts/qwen"/(name+".response.json")),
        "candidate":str(candidate),"source":str(DEST),
        "sha256":hashlib.sha256(DEST.read_bytes()).hexdigest(),
        "hand_edits_to_generated_source":False,"notes":result.get("notes",[])})
    print("Installed Qwen source: "+str(DEST),flush=True)


def generate(attempt=0, feedback_path=None):
    storyboard=json.loads((ROOT/"storyboard.json").read_text())
    prompt=CONTRACT+"\nGrounding physics:\n"+qwen.FACTS+"\nQwen storyboard:\n"+json.dumps(storyboard)
    if feedback_path:
        previous=ROOT/"artifacts/qwen"/f"code-generation-{attempt-1}.py"
        if previous.exists(): prior=previous.read_text()
        elif DEST.exists(): prior=DEST.read_text()
        else:
            response=json.loads((ROOT/"artifacts/qwen"/f"code-generation-{attempt-1}.response.json").read_text())
            prior=response["choices"][0]["message"].get("content","")
        prompt+="\nRepair your last code, returning the complete replacement JSON code object. Address the specific errors without dropping scenes or simplifying away motion.\nPrior code:\n"+prior+"\nFeedback:\n"+Path(feedback_path).read_text()
    name=f"code-generation-{attempt}"
    result=qwen.call(name,prompt,max_tokens=15000,request_timeout=480)
    install_candidate(name,result)


def review(paths, name):
    source=DEST.read_text()
    selected={sid for sid in qwen.IDS if any(p.name.startswith(sid+'-') for p in paths)}
    if selected:
        tree=ast.parse(source)
        chunks=[]
        for node in tree.body:
            if isinstance(node,ast.ClassDef):
                methods=[ast.get_source_segment(source,n) for n in node.body
                         if isinstance(n,ast.FunctionDef) and
                         (n.name in {'start_scene','change_caption','end_scene'} or
                          n.name in {'scene_'+s for s in selected})]
                chunks.append('Class methods (shown separately):\n'+'\n\n'.join(methods))
            else:
                chunks.append(ast.get_source_segment(source,node))
        source='\n\n'.join(chunks)
    prompt=("Review Qwen's own Manim implementation and the attached checkpoint frames. "
        "Check executable API usage, legibility, clipping, overlap, force direction, tangent release, graph values, frame distinctions and fulfillment of its storyboard. "
        "Do not confuse a ball's position AFTER release with the original release point. "
        "Calculate angular positions from code (0=right, pi/2=top, pi=left, 3pi/2=bottom); subtracting an outward radial vector points inward. "
        "The origin of a velocity subtraction diagram is a vector-space anchor, not the circle's position-space center. "
        "Any proposed physics repair must agree with the computed vectors. "
        "Optional changes are minor. Missing core explanation, clipping, illegibility or demonstrably incorrect physics are major. "
        "Return {pass:boolean,issues:[{severity:'major'|'minor',checkpoint:string,problem:string,correction:string}],strengths:[string],limitations:[string]}. "
        "Pass requires no major issues. Only stills and source are available, not full playback. "
        "Review only these scene IDs: "+', '.join(sorted(selected or set(qwen.IDS)))+
        ". Source helper functions and selected class methods are shown separately for review.\nPhysics:\n"+qwen.FACTS+
        "\nStoryboard:\n"+(ROOT/"storyboard.json").read_text()+"\nSource:\n"+source)
    return qwen.call(name,prompt,images=paths,max_tokens=6000,
                     enable_thinking=True,thinking_budget_tokens=1024,request_timeout=480)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["generate","review"])
    p.add_argument("--attempt",type=int,default=0)
    p.add_argument("--feedback",type=Path)
    p.add_argument("--name",default="qwen-coded-review")
    p.add_argument("--external-transport",action="store_true")
    p.add_argument("--images",nargs="*",default=[])
    args=p.parse_args()
    qwen.EXTERNAL_TRANSPORT=args.external_transport
    if args.action=="generate": generate(args.attempt,args.feedback)
    else: review([Path(x) for x in args.images],args.name)
