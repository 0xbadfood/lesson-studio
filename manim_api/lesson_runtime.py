"""Trusted layout helpers supplied to model-authored scenes."""
import textwrap
import manim as m
import numpy as np

BG = '#0B1220'
WHITE = '#EDF3FF'
CYAN = '#49D6F5'
GREEN = '#71E3A2'
RED = '#FF727C'
AMBER = '#FFC768'


def text(value, size=28, color=WHITE, width=11):
    value = str(value)
    if not value.strip():
        raise ValueError('Do not create empty text')
    wrapped='\n'.join(textwrap.fill(line,width=65) for line in value.splitlines())
    obj=m.Text(wrapped,font='DejaVu Sans',font_size=size,color=color)
    if obj.width>width:
        obj.scale(width/obj.width)
    return obj


def arrow(start,end,color=RED,**kwargs):
    start,end=np.array(start,dtype=float),np.array(end,dtype=float)
    if np.linalg.norm(end-start)<.03:
        raise ValueError('Arrow endpoints are too close')
    options={'buff':.01,'stroke_width':4,**kwargs}
    return m.Arrow(start,end,color=color,**options)


def polyline(points,color=RED,width=4):
    """An open path through coordinates, ready for proportion sampling."""
    return m.VMobject(color=color,stroke_width=width).set_points_as_corners(np.array(points,dtype=float))


def begin(scene,title,caption):
    started=scene.time
    scene.camera.background_color=BG
    heading=text(title,36,CYAN,width=12).move_to([0,3.2,0])
    subtitle=text(caption,24,width=11).move_to([0,-3.2,0])
    heading._lesson_reserved='title'
    subtitle._lesson_reserved='caption'
    scene.play(m.FadeIn(heading),m.FadeIn(subtitle),run_time=.5)
    return started


def finish(scene,started,duration):
    remaining=max(0,duration-(scene.time-started)-.5)
    if remaining:
        scene.wait(remaining)
    for obj in list(scene.mobjects):
        obj.clear_updaters(recursive=True)
    if scene.mobjects:
        scene.play(*[m.FadeOut(obj) for obj in list(scene.mobjects)],run_time=.5)
