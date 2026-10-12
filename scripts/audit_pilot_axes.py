"""Ask Qwen to audit its disputed frame finding using measured endpoints."""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.llm import Qwen
from manim_api.pipeline import passed
from manim_api.renderer import render,checkpoints
from manim_api.settings import Settings
from manim_api.storage import read_json,write_json
from manim_api.validation import validate_code,validate_geometry

job=ROOT/'api-data/runs/f809a309194c4736967cd1513eca10ce'
scene=job/'scenes/s02'
settings=Settings(**read_json(job/'settings.json'))
candidate=read_json(scene/'candidate-88baf433574d49abb4285093a33ad218-0.json')
code=candidate['code']
validate_code(code)
(scene/'scene.py').write_text(code)
preview,geometry=render(settings,scene/'preview',code,'preview',15)
validate_geometry(geometry)
images=checkpoints(preview,scene/'preview',geometry['duration'])
angle=1.35
numeric={'angle':angle,'row_vector_x_axis_at_final_angle':[1.95*math.cos(angle),-1.95*math.sin(angle),0],
         'row_vector_y_axis_at_final_angle':[1.35*math.sin(angle),1.35*math.cos(angle),0],
         'x_axis_angle_radians':-angle,
         'identity':'[1,0] @ [[cos(a),-sin(a)],[sin(a),cos(a)]] = [cos(a),-sin(a)]',
         'scope':'Trusted arithmetic and measured endpoints; not a complete physics proof'}
write_json(job/'numeric-frame-audit.json',numeric)
review=read_json(scene/'review-88baf433574d49abb4285093a33ad218-0.json')
research=read_json(job/'research.json')
sources=[source for source in research['sources'] if source['id'] in {'R01','R05','R06'}]
qwen=Qwen(settings,job)
result=qwen.call('pilot-grounded-frame-review',
    'Audit the disputed axes-label finding against the exact code, the trusted numerical '
    'matrix product and ACTUAL measured white-line endpoints. Recompute the row-vector product, '
    'do not treat v @ R as R @ v. At a=1.35 the x-axis points down/right, so its on-screen '
    'angle is negative. The object/string are stationary in the rotating camera; an inertial '
    'reference basis turns negatively in that view. Decide whether the on-screen label '
    'inertial reference axes is correct. The source variable name axes does not determine '
    'its reference frame; use the measured motion and displayed label. Retract false claims; '
    'retain genuinely verified major problems. Optional bracket styling/crowding is minor '
    'when text is legible and there is no measured overlap. This is not full playback. '
    'Return compact JSON {pass:boolean,issues:[{severity:"major"|"minor",problem:string,evidence:string,correction:string}],'
    'findings:[{verdict:string,reason:string}],limitations:[string]}; max 500 words.\n'
    'Exact code:\n'+code+'\nNumerical calculation:\n'+json.dumps(numeric)+
    '\nMeasured samples:\n'+json.dumps(geometry['samples'][::4])+
    '\nDisputed review:\n'+json.dumps(review)+'\nSource evidence:\n'+json.dumps(sources),
    images=images,max_tokens=2500)
write_json(scene/'grounded-frame-review.json',result)
if not passed(result):raise SystemExit('Grounded Qwen audit did not pass; examine saved findings')
saved={'id':'s02','preview':str(preview),'duration':geometry['duration'],
       'source_sha256':hashlib.sha256(code.encode()).hexdigest(),'author_model':qwen.model,
       'review':review['review'],'review_audit':result,'geometry':str(scene/'preview/geometry.json'),
       'source':str(scene/'scene.py'),'notes':candidate['notes'],
       'supplemental_numerical_audit':str(job/'numeric-frame-audit.json')}
write_json(scene/'accepted.json',saved)
print(json.dumps({'pass':result['pass'],'issues':result['issues'],'findings':result['findings']},indent=2))
