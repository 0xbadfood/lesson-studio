"""Full Qwen planning -> coding -> render -> review -> Qwen repairs workflow."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

import qwen_codegen as coding
import qwen_scene_codegen as scene_coding
import qwen_workflow as qwen

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--reuse-plan",action="store_true")
    p.add_argument("--start-attempt",type=int,default=0)
    p.add_argument("--max-repairs",type=int,default=3)
    p.add_argument("--preview-only",action="store_true")
    p.add_argument("--whole-script",action="store_true",help="Experimental whole-film coding; default generates each scene separately")
    p.add_argument("--reuse-code",action="store_true",help="Use the currently installed Qwen-authored source")
    args=p.parse_args()
    os.chdir(ROOT)
    if not args.reuse_plan: qwen.plan_video()
    qwen.validate_plan(json.loads((ROOT/"storyboard.json").read_text()))
    python=os.environ.get("MANIM_PYTHON") or (sys.executable if importlib.util.find_spec("manim") else "/home/nitin/remotion/.venv-manim-pilot/bin/python")
    feedback=None
    art=ROOT/"artifacts"
    art.mkdir(exist_ok=True)
    targets=[]
    repair_scaffold=False
    if not args.whole_script and not args.reuse_code:
        if not (scene_coding.STORE/"scaffold.py").exists(): scene_coding.scaffold()
        for sid in qwen.IDS:
            if not (scene_coding.STORE/(sid+".py")).exists(): scene_coding.scene(sid,thinking=True,thinking_budget=1024)
        scene_coding.assemble()
    for attempt in range(args.start_attempt,args.start_attempt+args.max_repairs+1):
        try:
            if args.whole_script and (feedback or not args.reuse_code):
                coding.generate(attempt,feedback)
            elif feedback:
                if repair_scaffold:
                    meta=json.loads((scene_coding.STORE/"scaffold.metadata.json").read_text())
                    scene_coding.scaffold(meta['attempt']+1,feedback)
                else:
                    for sid in targets or qwen.IDS:
                        meta=json.loads((scene_coding.STORE/(sid+".metadata.json")).read_text())
                        scene_coding.scene(sid,meta['attempt']+1,feedback,thinking=True,thinking_budget=1024)
                scene_coding.assemble()
        except (ValueError,SyntaxError,RuntimeError) as exc:
            feedback=art/f"qwen-code-feedback-{attempt}.txt"
            feedback.write_text("Your generated source failed parsing or static validation. Return a complete valid JSON code object and runnable Python.\n"+str(exc))
            continue
        log=art/f"qwen-scene-coded-render-{attempt}.log"
        print(f"Rendering Qwen candidate {attempt}",flush=True)
        with log.open("w") as out:
            proc=subprocess.run([python,"-m","manim","-ql","--fps","15",str(coding.DEST),"QwenForces"],stdout=out,stderr=subprocess.STDOUT)
        if proc.returncode:
            feedback=art/f"qwen-code-feedback-{attempt}.txt"
            feedback.write_text("The low-quality Manim render failed. Repair the traceback, preserving all scenes.\n"+log.read_text()[-18000:])
            matches=re.findall(r'in scene_(\w+)',log.read_text())
            targets=[matches[-1]] if matches and matches[-1] in qwen.IDS else []
            relevant=re.findall(r'in (construct|start_scene|change_caption|end_scene|scene_\w+)',log.read_text())
            repair_scaffold=not matches or (relevant and not relevant[-1].startswith('scene_'))
            continue
        if not args.whole_script:
            with (art/"qwen-coded-physics-validation.txt").open("w") as out:
                subprocess.run([python,"-m","unittest","-v","test_qwen_physics.py"],stdout=out,stderr=subprocess.STDOUT,check=True)
        video=ROOT/"media/videos/qwen_generated_forces/480p15/QwenForces.mp4"
        name=f"qwen-coded-preview-{attempt}"
        subprocess.run([python,str(ROOT/"check_render.py"),str(video),"--name",name,
                        "--timings",str(art/"qwen-coded-scene-timings.json")],check=True)
        stamp=hashlib.sha256(coding.DEST.read_bytes()).hexdigest()[:12]
        groups={"motion":["hook","circular_motion","release","frames"],"examples":["force_law","car","summary"]}
        reports={g:coding.review([art/name/(s+"-4.png") for s in scenes],f"qwen-coded-{g}-{stamp}") for g,scenes in groups.items()}
        audits={}
        decisions=dict(reports)
        if not args.whole_script and (not reports['motion'].get('pass') or
                any(i.get('severity')=='major' for i in reports['motion'].get('issues',[]))):
            # A review can misread correct vector components. Audit the source
            # and computed coordinates before sending a proposed repair to Qwen.
            # The audit is additional evidence, not a replacement for tests/stills.
            subprocess.run([python,str(ROOT/'audit_qwen_coded_review.py')],
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
            audits['motion']=json.loads((qwen.ART/f'qwen-coded-motion-audit-{stamp}.result.json').read_text())
            decisions['motion']=audits['motion']
        if any(not r.get("pass") or any(i.get("severity")=="major" for i in r.get("issues",[])) for r in decisions.values()):
            feedback=art/f"qwen-code-feedback-{attempt}.txt"
            feedback.write_text("Frame/code review findings: verify factual findings against your computed coordinates before changing correct physics. Repair actual major errors, not false findings.\n"+json.dumps({'reviews':reports,'audits':audits,'decisions':decisions},indent=2))
            targets=sorted({i.get('checkpoint','').split('-')[0].removeprefix('scene_') for r in decisions.values()
                            for i in r.get('issues',[]) if i.get('severity')=='major'} & set(qwen.IDS))
            repair_scaffold=False
            continue
        if not args.preview_only:
            subprocess.run([python,"-m","manim","-qh","--fps","30",str(coding.DEST),"QwenForces"],check=True)
            video=ROOT/"media/videos/qwen_generated_forces/1080p30/QwenForces.mp4"
            subprocess.run([python,str(ROOT/"check_render.py"),str(video),"--name","qwen-coded-final",
                            "--timings",str(art/"qwen-coded-scene-timings.json")],check=True)
        subprocess.run(["ffmpeg","-v","error","-i",str(video),"-f","null","-"],check=True)
        output=ROOT/("qwen_coded_forces_preview.mp4" if args.preview_only else "centripetal_centrifugal_qwen_coded.mp4")
        shutil.copy2(video,output)
        qwen.write(art/"qwen-coded-build.json",{"video":str(output),"author":json.loads((art/"qwen-code-author.json").read_text()),
            "attempt":attempt,"qwen_reviews":reports,"qwen_review_audits":audits,
            "review_scope":"Preview stills and source; mathematical audit of major motion findings; final MP4 decode/checkpoints",
            "sha256":hashlib.sha256(output.read_bytes()).hexdigest()})
        print("Qwen-authored video: "+str(output),flush=True)
        return
    raise SystemExit("Qwen exhausted the bounded repair budget; inspect saved source, render logs and feedback.")


if __name__=="__main__": main()
