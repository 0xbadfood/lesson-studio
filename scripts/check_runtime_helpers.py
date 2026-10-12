"""Render a trusted probe of helper APIs, separate from generated lesson code."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.renderer import render
from manim_api.settings import Settings
from manim_api.storage import write_json

code='''import manim as m
import numpy as np
from lesson_runtime import begin,finish,arrow,polyline,CYAN,GREEN
class GeneratedScene(m.Scene):
    def construct(self):
        started=begin(self,"Runtime helper check","Open paths and custom arrow styling")
        path=polyline([[-2,-1,0],[0,0,0],[2,1,0]],color=CYAN)
        marker=m.Dot(path.point_from_proportion(.5))
        vector=arrow([-2,1,0],[-1,1,0],color=GREEN,stroke_width=3,buff=.05)
        self.add(path,marker,vector)
        finish(self,started,2)
'''
video,geometry=render(Settings.from_env(),ROOT/'artifacts/runtime-helper-probe',code,'preview',2)
result={'scope':'Trusted runtime probe; separate from all model-authored scenes',
        'arrow_accepts_styling_overrides':True,'polyline_has_sampleable_points':True,
        'video':str(video),'duration':geometry['duration']}
write_json(ROOT/'artifacts/runtime-helper-validation.json',result)
print(json.dumps(result,indent=2))
