"""Recheck Qwen review findings against its generated source and evaluated vectors."""
import argparse
import hashlib
import importlib
import inspect
import json

import qwen_generated_forces as generated
import qwen_workflow as qwen


def audit_motion_review(report, name):
    importlib.reload(generated)
    v1 = generated.tangent_velocity(-0.32, 1.1, 1.0)
    v2 = generated.tangent_velocity(0.32, 1.1, 1.0)
    evidence = {
        'helper_source': inspect.getsource(generated.tangent_velocity),
        'v1': v1.tolist(), 'v2': v2.tolist(), 'v2_minus_v1': (v2-v1).tolist(),
        'inward_at_right_side': [-1, 0, 0],
        'dot_product_with_inward': float((v2-v1) @ [-1, 0, 0]),
        'release_marker_relative_position': generated.free_flight(0, 0, 1.3, 1).tolist(),
        'release_marker_note': 'Marker denotes initial release point; later ghost/flight positions need not remain on the marker.',
    }
    qwen.write(qwen.ART/(name+'-evidence.json'), evidence)
    source='\n\n'.join(inspect.getsource(getattr(generated.QwenForces,'scene_'+s))
                           for s in ('hook','circular_motion','release','frames'))
    result=qwen.call(name,
        'Audit every issue in the prior report against the exact generated source and evaluated numerical vectors. '
        'Determine independently whether its major findings are factual or mistaken. '
        'The source function tangent_velocity returns omega*r*[-sin(theta),cos(theta),0], NOT [cos(theta),sin(theta),0]. '
        'Evaluate the subtraction and inspect the actual Arrow endpoints; do not transpose components. '
        'At angular samples -0.32 and +0.32 around the right side, velocities are nearly vertical and their difference is horizontal. '
        'A shared origin of velocity arrows is a vector-space anchor. It does not locate the physical circle center. '
        'Preserve valid minor presentation suggestions. Do not infer release location from a later flight position. '
        'Return {pass:boolean,findings:[{checkpoint:string,verdict:"valid"|"incorrect"|"optional",reason:string}],'
        'issues:[{severity:"major"|"minor",checkpoint:string,problem:string,correction:string}],limitations:[string]}. '
        'Pass means no verified major issue. This is a code and numerical audit, not full video playback.\n'
        'Report:\n'+json.dumps(report)+'\nEvaluated coordinates:\n'+json.dumps(evidence)+'\nSource:\n'+source,
        max_tokens=5000,request_timeout=480,enable_thinking=True,thinking_budget_tokens=1024)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--external-transport', action='store_true')
    args = parser.parse_args()
    qwen.EXTERNAL_TRANSPORT = args.external_transport
    stamp=hashlib.sha256((qwen.ROOT/'qwen_generated_forces.py').read_bytes()).hexdigest()[:12]
    report=json.loads((qwen.ART/('qwen-coded-motion-'+stamp+'.result.json')).read_text())
    result=audit_motion_review(report,'qwen-coded-motion-audit-'+stamp)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
