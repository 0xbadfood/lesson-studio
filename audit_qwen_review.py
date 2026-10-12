"""Audit the final review's claims against computed coordinates and source."""
import inspect
import json
import numpy as np

import qwen_workflow as qwen
from centripetal_centrifugal import CentripetalCentrifugal, point


def main():
    qwen.EXTERNAL_TRANSPORT=True
    cls=CentripetalCentrifugal
    evidence={
        "hook":{
            "cut_angle_radians":float(2*np.pi-np.pi/2),
            "angle_description":"3pi/2, bottom of circle, not 3 o'clock",
            "relative_release_position":point(2*np.pi-np.pi/2,1.7).round(12).tolist(),
            "relative_tangent_velocity":point(2*np.pi-np.pi/2+np.pi/2,1.7*2*np.pi/5).round(12).tolist(),
            "note":"The later screenshot shows a ball that has already travelled away from the bottom release point."},
        "delta_v":{
            "v1":point(np.pi/2-0.32,1.15).round(12).tolist(),
            "v2":point(np.pi/2+0.32,1.15).round(12).tolist(),
            "v2_minus_v1":(point(np.pi/2+0.32,1.15)-point(np.pi/2-0.32,1.15)).round(12).tolist(),
            "note":"For positions at angular samples -0.32 and +0.32, midpoint is right of circle center. LEFT is inward. The common origin of velocity vectors is a vector-space anchor, not the position-space center of the circle. A subtraction arrow need not point toward that vector anchor."},
        "frames":{
            "relative_release_position":[1.05,0,0],"relative_velocity":[0,1.05,0],
            "note":"phase ends at TAU, which is the right side, not the top. After moving upwards, the ball's later position is not its release point."},
        "cut_label":{
            "note":"A string can be cut anywhere along its length, not only at the ball. The label marks the string's midpoint, offset slightly below for readability. No physical claim requires cutting at the ball. Treat a preference to put the label at the ball as optional, not a major factual error."}}
    qwen.write(qwen.ART/"review-audit-evidence.json",evidence)
    code="\n\n".join(inspect.getsource(getattr(cls,"scene_"+s)) for s in ("hook","circular_motion","release","frames"))
    old=json.loads((qwen.ART/"final-motion-review.result.json").read_text())
    tests=(qwen.ROOT/"artifacts/physics-validation.txt").read_text()
    qwen.call("final-motion-review-audit",
        "Audit a prior reviewer report against the exact source and computed coordinates. "
        "Determine independently which of its four major findings are correct, incorrect, or optional. "
        "Do not invent a new release point based on a later screenshot. Angular conventions are x=r*cos(theta), y=r*sin(theta). "
        "Check each proposed code change; accept it only if it improves the physics. "
        "The initial visual layout issues (text over vectors, arrow near heading, Coriolis text over path) have already been corrected. "
        "Return {pass:boolean,findings:[{checkpoint:string,verdict:'valid'|'incorrect'|'optional',reason:string}],issues:[{severity:'major'|'minor',checkpoint:string,problem:string,correction:string}],limitations:[string]}. "
        "pass is true if no verified major defect remains. If an old review is wrong, say so. "
        "You are auditing code/math, not conducting a new full playback review.\nPrevious report:\n"+json.dumps(old)+
        "\nComputed coordinates:\n"+json.dumps(evidence)+"\nNumerical tests:\n"+tests+"\nActual source:\n"+code,max_tokens=3500)


if __name__=="__main__": main()
