"""Trusted helpers imported by LLM-coded chapter scenes (copied into the render sandbox).

The chapter clock starts at begin(); at(scene, t) waits until narration second t and records any cue the
animations reached late, so the host can send timing defects back to the coder.
"""
import textwrap

import manim as m
import numpy as np

BG = '#0B1220'
WHITE = '#EDF3FF'
CYAN = '#49D6F5'
GREEN = '#71E3A2'
RED = '#FF727C'
AMBER = '#FFC768'
VIOLET = '#B49CFF'
GREY = '#8A97AD'
FONT = 'DejaVu Sans'
TITLE_Y = 3.4
BODY = (-6.6, -2.7, 6.6, 2.9)     # x0, y0, x1, y1: the heading sits above, burned-in subtitles below


def text(value, size=28, color=WHITE, width=11):
    value = str(value)
    if not value.strip():
        raise ValueError('Do not create empty text')
    wrapped = '\n'.join(textwrap.fill(line, width=60) for line in value.splitlines())
    obj = m.Text(wrapped, font=FONT, font_size=size, color=color)
    if obj.width > width:
        obj.scale(width / obj.width)
    return obj


def tex(latex, size=40, color=WHITE, width=11):
    """Mathematics typeset with LaTeX (MathTex)."""
    obj = m.MathTex(latex, font_size=size, color=color)
    if obj.width > width:
        obj.scale(width / obj.width)
    return obj


def arrow(start, end, color=RED, **kwargs):
    start, end = np.array(start, dtype=float), np.array(end, dtype=float)
    if np.linalg.norm(end - start) < .03:
        raise ValueError('Arrow endpoints are too close')
    return m.Arrow(start, end, color=color, **{'buff': .01, 'stroke_width': 4, **kwargs})


def polyline(points, color=RED, width=4):
    """An open path through coordinates, ready for point_from_proportion."""
    path = m.VMobject(color=color, stroke_width=width).set_points_as_corners(np.array(points, dtype=float))
    return path.set_fill(opacity=0)


def begin(scene, title):
    """Background and heading; returns 0, the start of the chapter clock."""
    scene.camera.background_color = BG
    scene._kit_start = scene.time
    scene._kit_late = []
    heading = text(title, 32, CYAN, width=12.6).move_to([0, TITLE_Y, 0])
    heading._kit_reserved = True
    scene.play(m.FadeIn(heading), run_time=.4)
    return 0.0


def now(scene):
    return scene.time - scene._kit_start


def at(scene, t):
    """Wait until chapter second t (a cue's start). Animations that ran past it are recorded as late."""
    current = now(scene)
    if current > t + .3:
        scene._kit_late.append({'cue_time': round(float(t), 2), 'reached_at': round(float(current), 2)})
    elif t - current > 1 / 60:
        scene.wait(t - current)


def finish(scene, duration):
    """Hold the last picture until the chapter's narration ends, then fade out."""
    at(scene, max(0.0, duration - .4))
    for obj in list(scene.mobjects):
        obj.clear_updaters(recursive=True)
    if scene.mobjects:
        scene.play(*[m.FadeOut(obj) for obj in list(scene.mobjects)], run_time=.4)
