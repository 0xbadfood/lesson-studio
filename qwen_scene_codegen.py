"""Qwen-authored scaffold and individual scenes, assembled without hand repairs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import textwrap

import qwen_workflow as qwen

ROOT=Path(__file__).resolve().parent
STORE=ROOT/"artifacts/qwen-scenes"
SOURCE=ROOT/"qwen_generated_forces.py"
STYLE="""Manim Community 0.21.0 is installed. Valid APIs: Text, Dot, Circle,
Line, Arrow, DashedLine, VGroup, ValueTracker, always_redraw, TracedPath, Axes,
ParametricFunction, Arc, RoundedRectangle, FadeIn, FadeOut, Create, Write.
Use import manim as m, numpy as np, math, json, pathlib. Only these imports.
m.Color, m.CYAN, m.AMBER, mob.clear_updater, VMobject.add_points DO NOT EXIST.
Use hex strings, mob.clear_updaters(recursive=True), TracedPath.
No Tex/MathTex/DecimalNumber, no LaTeX, no external files or network.
Dark background '#0B1220', cyan '#49D6F5', velocity green '#71E3A2', inward
force red '#FF727C', rotating-frame pseudo-force amber '#FFC768'.
Text must remain within the frame: title y=3.2, caption y=-3.2, body content
x=[-6.2,6.2],y=[-2.65,2.65]. All moving dots AND arrows must fit.
Use m.linear for all continuous physics. No cumulative rotate in updaters:
rebuild a car with always_redraw and an absolute angle.
Arrow(start,end) points from start to end; subtracting an outward radial
vector is inward. No zero-length arrows. Only rotate viewpoints after using
the correct inertial straight-line trajectory.
Return ONE JSON object {code:string,notes:[string]}, no Markdown.
"""
BRIEFS={
"hook":"""12 s. Center=(0,0.25), radius=1.35. Angle begins -pi/2 and
increases by 2pi over 5 seconds (omega=2pi/5), ending at 3pi/2, the BOTTOM.
Show circle, cyan dot, string, red inward and green tangent arrows, and trail.
Use ValueTracker+always_redraw. Remove string and force at the cut. Release
from the bottom with SAME speed omega*r: RIGHT. Animate time from 0 to 1.2
over 1.2 seconds; flight length about 2.04, safely inside body bounds.
Ghost ball continues orbit during release. Static legend below diagram.
Freeze the dot/arrows before clearing updaters so the flight replaces the
circle updater. Use the scaffold physics functions and end_scene padding.""",
"circular_motion":"""15 s. Circle center=(-3,0), r=1.4. Animate two full
rotations with cyan dot, string, green tangent velocity and red inward force
arrows updating continuously. Static legend in right upper region. Also
illustrate velocity subtraction at the RIGHT side of a circle: v1 at angle
pi/2-0.32 and v2 at pi/2+0.32, same origin=(3,-1), length=1.1. Draw red
delta-v arrow from the v1 tip to the v2 tip (LEFT is inward for the right-side
position). Put 'Δv points inward' ABOVE the vectors at (3,0.6), not across
them. Label the vector diagram 'Near the right side of the circle'. Radius
label below left circle, away from rotating arrows. Pad to 15 seconds.""",
"release":"""14 s. Circle center=(-2.7,0), r=1.3. Angle starts -2pi and
reaches 0 over 5 seconds, omega=2pi/5. Show string and inward force and
tangent velocity. Release point p0=center+(r,0): RIGHT side, tangent UP.
Fade string+force and mark string cut. Released displacement 1.4 units UP,
flight_time=1.4/(omega*r); animate the flight time tracker with exactly that
run_time so speed is continuous. Keep velocity arrow length .65: its tip
ends at y=2.05, safely below title. Show ghost continuing circle while real
dot flies. Right-side text: 'Without inward force, the ball follows the
tangent.' Use scaffold free_flight. No acceleration or curved flight.
Always clear circle updaters before replacing with flight motion.""",
"force_law":"""20 s. Keep miniature circle left center=(-3,0), r=.8,
and graph right center=(2.6,0) visible SIMULTANEOUSLY. Physics m=1kg,r=2m;
v=2,4,6m/s gives F=2,8,18N. Graph xlength4.4, ylength3.0; curve v²/2.
Create manual Text axis ticks and labels; never use add_numbers/DecimalNumber.
ValueTracker speed changes 2->4->6 with live Text readout at (2.6,2.35),
graph dot/guides, circle motion and red inward arrow length .04*F. On the
circle the physical angular speed is v/2; increment a phase ValueTracker
using dt and add tracker to scene so its updater runs. Display 'F = mv²/r'
at (-3,1.8), 'm=1 kg, r=2 m' below circle, '2× speed ->4× force' then
'3× speed ->9× force'. Keep graph labels away from readout and caption.
Use force_magnitude helper. Scene is comparisons of steady speeds.""",
"frames":"""22 s. Left/right centers=(-3,0),(3,0), circle r=.9.
Headings at y2.15 'From outside'/'Rotating viewpoint'. Initially left dot
orbits omega=1 for one full revolution in 2pi seconds; right dot fixed at
rightmost point. Red inward force on both dots; equally long amber dashed
outward pseudo-force ONLY on rotating side. Label force accounts below.
Then remove real force arrows AND pseudo arrow at release; remove old
stationary balance caption. Both release from (r,0). Time tracker 0->1.5
over1.5 seconds, left free_flight(t,0,r,1), right rotating_flight(t,0,r,1).
Both have trails. No left dot drifting from top of circle: initial position
must be right side and flight must go UP. Rotating path must use R(-t) of
the SAME inertial path. Change bottom caption to 'After release: straight
outside, curved in the rotating view.' Coriolis note at y=-2.35. Do not put
explanatory text across the right trajectory. Keep all elements in bounds.""",
"car":"""18 s. Left diagram: quarter-circle road centered=(-3,.5),
radius1.6, starttheta=-pi/2, endtheta=0: car initially goes RIGHT and turns
LEFT toward UP. Draw thick muted Arc road and lane guide. Car is rounded
rectangle width=.8 height=.5 rebuilt via always_redraw and rotated by
theta+pi/2. White passenger dot always follows car center for belt-held
example. Red road-friction arrow from car toward curve center. First show
a green ghost passenger travelling initial straight tangent, explicitly
labeled 'Without inward contact'. Car turns away from the ghost. Remove
ghost/label and road-friction arrow, replay the turn with an inward red
contact force on the belt-held passenger. Right side: explanatory texts
'Road friction turns the car', 'Seat, belt or door turns the passenger'.
At bottom-right show a separate simple explicitly labeled 'Rotating view'
diagram with red inward contact and amber outward pseudo-force. Never draw
an unlabeled outward real force on the inertial car. No elaborate collision
model required; the unconstrained ghost is a hypothetical comparison.""",
"summary":"""15 s. Two clearly separated diagrams centered(-3,0),(3,0),
r=.9. Both circles have a cyan ball at their RIGHT side and red arrow from
ball toward circle center. ONLY right diagram has outward amber dashed
pseudo-force of equal length. Headings at y2.2: 'CENTRIPETAL' and
'CENTRIFUGAL'. Left explanatory rows below: 'Inward net force', 'Supplied by
real interactions'; right: 'Outward pseudo-force', 'Used in a rotating frame'.
Animate drawing circles/arrows, writing comparison rows and a gentle dot
pulse. All force arrows originate at their respective balls, not at the
circle center. Avoid overlapping text and arrows. Pad to 15 seconds."""}


def scaffold(attempt=0, feedback=None):
    prompt=STYLE+"""\nAuthor only the scaffold for a seven-scene video, not the
scene bodies yet. No existing script is provided. Return complete imports,
constants and these pure functions used by later scene code:
circle_point(theta,radius): radius*[cos theta,sin theta,0];
tangent_velocity(theta,radius,omega): omega*radius*[-sin theta,cos theta,0];
free_flight(t,theta,radius,omega): circle_point(theta,radius)+t*tangent_velocity(...);
rotating_flight(t,theta,radius,omega): R(-omega*t) @ free_flight(...);
force_magnitude(mass,speed,radius): mass*speed**2/radius;
txt(text,size=28,color='#EDF3FF',max_width=11): Text font DejaVu Sans,
wrap long text to about70 chars, scale to maximum width;
vec(start,end,color): Arrow buff .04 stroke_width4, nonzero endpoints.
Define class QwenForces(m.Scene) with ONLY these methods:
construct: set navy background, call methods scene_hook, scene_circular_motion,
scene_release, scene_force_law, scene_frames, scene_car, scene_summary in order;
record actual self.time [{id,start,end,duration}], save JSON to
artifacts/qwen-coded-scene-timings.json relative to __file__. This is the only
filesystem write. The seven scene methods will be appended later. Do NOT
define stubs or scene methods in this scaffold.
start_scene(self,title,caption): start=self.time, add title at y3.2 and caption
at y-3.2 using txt(), return start. Set self.caption to the caption mobject.
change_caption(self,text): fade-transform self.caption to new txt at y-3.2.
end_scene(self,start,target): pad remaining=max(0,target-(self.time-start)-.7),
then clear_updaters(recursive=True) on ALL current root scene objects and
fade ALL out with run_time=.7. Scene transitions must not leave ghosts.
Class must be LAST top-level item in file so indented scene definitions can
be appended to it. Do not put any top-level code below the class.\n"""
    if feedback:
        frozen=STORE/f"scaffold.prior-{attempt}.py"
        if not frozen.exists():
            prev=qwen.ART/f"scene-code-scaffold-{attempt-1}.result.json"
            frozen.write_text(json.loads(prev.read_text())["code"].rstrip()+"\n" if prev.exists() else (STORE/"scaffold.py").read_text())
        prior=frozen.read_text()
        prompt+="\nRepair scaffold:\n"+prior+"\nFeedback:\n"+Path(feedback).read_text()
    result=qwen.call(f"scene-code-scaffold-{attempt}",prompt,max_tokens=6000,request_timeout=480)
    STORE.mkdir(parents=True,exist_ok=True)
    (STORE/"scaffold.py").write_text(result["code"].rstrip()+"\n")
    ast.parse(result["code"])
    qwen.write(STORE/"scaffold.metadata.json",{"attempt":attempt,"response":str(qwen.ART/f"scene-code-scaffold-{attempt}.result.json")})


def scene(scene_id,attempt=0,feedback=None,thinking=False,thinking_budget=None):
    plan=json.loads((ROOT/"storyboard.json").read_text())
    spec=next(s for s in plan["scenes"] if s["id"]==scene_id)
    prompt=STYLE+"\nWrite ONLY the method def scene_"+scene_id+"(self) to append to the class below. "
    prompt+="Return the whole method as code in JSON. Do not rewrite scaffold, imports or any other scenes. Method may have nested helpers. "
    prompt+="Call start=self.start_scene(title,caption) first, and self.end_scene(start,target_duration) last. Use the scaffold functions exactly. "
    prompt+="Keep this method about50-100 lines with clear animations.\nScaffold:\n"+(STORE/"scaffold.py").read_text()
    prompt+="\nScene storyboard:\n"+json.dumps(spec)+"\nImplementation brief:\n"+BRIEFS[scene_id]+"\nPhysics:\n"+qwen.FACTS
    if feedback:
        frozen=STORE/f"{scene_id}.prior-{attempt}.py"
        if not frozen.exists():
            prev=qwen.ART/f"scene-code-{scene_id}-{attempt-1}.result.json"
            frozen.write_text(textwrap.dedent(json.loads(prev.read_text())["code"]).strip()+"\n" if prev.exists() else (STORE/(scene_id+".py")).read_text())
        prior=frozen.read_text()
        prompt+="\nRepair prior scene:\n"+prior+"\nFeedback:\n"+Path(feedback).read_text()
    result=qwen.call(f"scene-code-{scene_id}-{attempt}",prompt,max_tokens=7000,request_timeout=480,enable_thinking=thinking,thinking_budget_tokens=thinking_budget)
    code=textwrap.dedent(result["code"]).strip()+"\n"
    tree=ast.parse(code)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef) or tree.body[0].name!="scene_"+scene_id:
        raise ValueError("Expected one complete scene method")
    (STORE/(scene_id+".py")).write_text(code)
    qwen.write(STORE/(scene_id+".metadata.json"),{"attempt":attempt,"response":str(qwen.ART/f"scene-code-{scene_id}-{attempt}.result.json")})


def assemble():
    from qwen_codegen import install_candidate
    base=(STORE/"scaffold.py").read_text()
    code=base.rstrip()+"\n\n"+"\n\n".join(textwrap.indent((STORE/(sid+".py")).read_text().rstrip(),"    ") for sid in qwen.IDS)+"\n"
    ast.parse(code)
    install_candidate("scene-code-assembled",{"code":code,"notes":["All scaffold and scene methods authored by Qwen, assembled with indentation normalization only."]})
    provenance=json.loads((ROOT/"artifacts/qwen-code-author.json").read_text())
    provenance.pop("response",None)
    provenance["generation_mode"]="One Qwen scaffold plus seven Qwen scene methods"
    provenance["source_fragments"]=[str(STORE/"scaffold.py")]+[str(STORE/(s+".py")) for s in qwen.IDS]
    provenance["model_responses"]=[json.loads((STORE/(s+".metadata.json")).read_text())["response"] for s in ["scaffold"]+qwen.IDS]
    provenance["assembly_adjustments"]="Indentation and trailing newline normalization only"
    qwen.write(ROOT/"artifacts/qwen-code-author.json",provenance)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["scaffold","scene","assemble"])
    p.add_argument("--scene",choices=qwen.IDS)
    p.add_argument("--attempt",type=int,default=0)
    p.add_argument("--feedback",type=Path)
    p.add_argument("--external-transport",action="store_true")
    p.add_argument("--thinking",action="store_true",help="Enable Qwen reasoning for code repairs")
    p.add_argument("--thinking-budget",type=int,help="llama.cpp reasoning budget, for example 1024 tokens")
    args=p.parse_args()
    qwen.EXTERNAL_TRANSPORT=args.external_transport
    if args.action=="scaffold": scaffold(args.attempt,args.feedback)
    elif args.action=="scene": scene(args.scene,args.attempt,args.feedback,args.thinking,args.thinking_budget)
    else: assemble()
