"""Silent Manim explainer driven by a Qwen-reviewed storyboard.

Render without a player:
  python -m manim -qh --fps 30 centripetal_centrifugal.py CentripetalCentrifugal
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import numpy as np
from manim import *

ROOT = Path(__file__).resolve().parent
BG = "#0B1220"
PANEL = "#142238"
INK = "#EDF3FF"
MUTED = "#9BACCA"
BALL = "#49D6F5"
VEL = "#71E3A2"
FORCE = "#FF727C"
PSEUDO = "#FFC768"
config.background_color = BG


def label(value, size=28, color=INK, width=None):
    obj = Text(str(value), font="DejaVu Sans", font_size=size, color=color,
               line_spacing=1.0, disable_ligatures=True)
    if width and obj.width > width:
        obj.scale_to_fit_width(width)
    return obj


def point(angle, radius=1.6):
    return radius * np.array([np.cos(angle), np.sin(angle), 0.0])


def rotation(angle, value):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([c*value[0] - s*value[1], s*value[0] + c*value[1], 0.0])


def arrow(start, end, color, dashed=False):
    obj = Arrow(start, end, buff=0.06, color=color, stroke_width=5,
                max_tip_length_to_length_ratio=0.2)
    return DashedVMobject(obj, num_dashes=9) if dashed else obj


class CentripetalCentrifugal(Scene):
    def construct(self):
        self.plan = json.loads((ROOT / "storyboard.json").read_text())
        self.timings = []
        for index, spec in enumerate(self.plan["scenes"]):
            self.spec, self.index = spec, index
            self.start_time = self.time
            self.begin()
            getattr(self, "scene_" + spec["id"])()
            self.end()
        destination = ROOT / "artifacts" / "scene-timings.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.timings, indent=2) + "\n")

    def begin(self):
        title = label(self.spec["title"], 38, width=11.8).move_to([0, 3.25, 0])
        number = label(f"{self.index+1:02d} / 07", 18, MUTED).move_to([6.05, 3.3, 0])
        divider = Line([-6.35, 2.86, 0], [6.35, 2.86, 0], color=MUTED, stroke_opacity=0.24)
        caption = label(textwrap.fill(self.spec["caption"], 75), 27, width=12.4).move_to([0, -3.23, 0])
        self.caption = caption
        progress = VGroup(*[Line([-6.35+i*1.83, -3.82, 0], [-4.73+i*1.83, -3.82, 0],
                                color=BALL if i <= self.index else PANEL, stroke_width=5) for i in range(7)])
        self.play(FadeIn(title, shift=0.1*DOWN), FadeIn(number), FadeIn(divider),
                  FadeIn(caption), FadeIn(progress), run_time=0.65)

    def change_caption(self, text):
        new_caption = label(textwrap.fill(text,75),27,width=12.4).move_to(self.caption)
        self.play(FadeTransform(self.caption,new_caption),run_time=0.55)
        self.caption = new_caption

    def end(self):
        remaining = self.spec["duration_seconds"] - (self.time-self.start_time) - 0.65
        if remaining > 0:
            self.wait(remaining)
        objects = list(self.mobjects)
        for obj in objects:
            obj.clear_updaters(recursive=True)
        self.play(*[FadeOut(obj) for obj in objects], run_time=0.65)
        self.timings.append({"id":self.spec["id"], "start":round(self.start_time,3),
                             "end":round(self.time,3), "duration":round(self.time-self.start_time,3)})

    def card(self, text, center, width=5.4, color=INK, size=29):
        content = label(text, size, color, width=width-0.55)
        bg = RoundedRectangle(width=width, height=content.height+0.48,
                              corner_radius=0.15, fill_color=PANEL, fill_opacity=1,
                              stroke_color=color, stroke_opacity=0.25)
        return VGroup(bg, content).move_to(center)

    def scene_hook(self):
        center = np.array([3.3, 0.15, 0.0])
        phase = ValueTracker(-PI/2)
        track = Circle(radius=1.7, color=MUTED, stroke_opacity=0.45).move_to(center)
        ball = always_redraw(lambda: Dot(center+point(phase.get_value(),1.7), radius=0.13, color=BALL))
        string = always_redraw(lambda: Line(center, ball.get_center(), color=MUTED, stroke_width=2))
        inward = always_redraw(lambda: arrow(ball.get_center(), ball.get_center()-point(phase.get_value(),0.95), FORCE))
        tangent = always_redraw(lambda: arrow(ball.get_center(), ball.get_center()+point(phase.get_value()+PI/2,1.0), VEL))
        trail = TracedPath(ball.get_center, dissipating_time=1.2, stroke_color=BALL, stroke_width=4, stroke_opacity=0.55)
        hook = label("A pull inward.\nA feeling outward.", 42, width=5.8).move_to([-3.15, 0.85, 0])
        question = label("How can both be useful?", 27, MUTED, width=5.6).move_to([-3.15,-0.72,0])
        legend = VGroup(label("●  Velocity",24,VEL), label("●  Inward force",24,FORCE)).arrange(RIGHT,buff=0.45).move_to([3.3,-2.2,0])
        self.play(Write(hook), FadeIn(question), Create(track), run_time=1.4)
        self.add(trail, string, ball, inward, tangent)
        self.play(FadeIn(legend), phase.animate.set_value(TAU-PI/2), run_time=5, rate_func=linear)
        for obj in (ball,string,inward,tangent): obj.clear_updaters(recursive=True)
        ghost = Dot(ball.get_center(),radius=0.11,color=BALL,fill_opacity=0.25)
        flight = ValueTracker(0)
        ghost.add_updater(lambda m:m.move_to(center+point(TAU-PI/2+TAU/5*flight.get_value(),1.7)))
        self.add(ghost)
        self.play(FadeOut(string),FadeOut(inward),run_time=0.5)
        displacement = RIGHT*(1.7*TAU/5)
        self.play(ball.animate.shift(displacement),tangent.animate.shift(displacement),
                  flight.animate.set_value(1),run_time=1,rate_func=linear)
        self.play(Indicate(question,color=PSEUDO),run_time=0.7)

    def scene_circular_motion(self):
        center = np.array([-3.2,0.0,0.0])
        phase = ValueTracker(0)
        ball = always_redraw(lambda: Dot(center+point(phase.get_value()),radius=0.12,color=BALL))
        string = always_redraw(lambda: Line(center,ball.get_center(),color=MUTED,stroke_width=2))
        velocity = always_redraw(lambda: arrow(ball.get_center(),ball.get_center()+point(phase.get_value()+PI/2,0.95),VEL))
        force = always_redraw(lambda: arrow(ball.get_center(),ball.get_center()-point(phase.get_value(),0.95),FORCE))
        trail = TracedPath(ball.get_center,dissipating_time=1.5,stroke_color=BALL,stroke_opacity=0.4)
        self.play(Create(Circle(radius=1.6,color=MUTED,stroke_opacity=0.45).move_to(center)),run_time=0.7)
        self.add(trail,string,ball,velocity)
        radius_label = label("radius r",23,MUTED).move_to(center+[0,-2.1,0])
        self.play(FadeIn(radius_label),run_time=0.4)
        a = self.card("Speed can stay constant.\nVelocity changes direction.",[3.0,1.72,0],size=27)
        self.play(FadeIn(a),phase.animate.set_value(TAU),run_time=4,rate_func=linear)
        self.add(force)
        origin = np.array([3.0,-1.3,0.0])
        va, vb = point(PI/2-0.32,1.15), point(PI/2+0.32,1.15)
        vec1,vec2 = arrow(origin,origin+va,VEL),arrow(origin,origin+vb,VEL)
        dv = arrow(origin+va,origin+vb,FORCE)
        vl1 = label("v₁",24,VEL).next_to(vec1,RIGHT,buff=0.1)
        vl2 = label("v₂",24,VEL).next_to(vec2,LEFT,buff=0.1)
        dvl = label("Δv points inward",24,FORCE).move_to([3,0.32,0])
        self.play(Create(vec1),Create(vec2),FadeIn(vl1),FadeIn(vl2),run_time=1)
        self.play(Create(dv),FadeIn(dvl),run_time=1)
        self.play(phase.animate.set_value(3*TAU),run_time=5,rate_func=linear)
        bottom = label("CENTRIPETAL = inward net force",25,FORCE,width=5.8).move_to([2.9,-2.18,0])
        self.play(FadeIn(bottom),run_time=0.7)

    def scene_release(self):
        center = np.array([-2.5,-0.3,0.0])
        radius, cut_angle = 1.45, PI/4
        phase = ValueTracker(cut_angle-TAU)
        ball = Dot(center+point(phase.get_value(),radius),radius=0.13,color=BALL)
        ball.add_updater(lambda m: m.move_to(center+point(phase.get_value(),radius)))
        string = always_redraw(lambda: Line(center,ball.get_center(),color=MUTED))
        force = always_redraw(lambda: arrow(ball.get_center(),ball.get_center()-point(phase.get_value(),0.8),FORCE))
        velocity = always_redraw(lambda: arrow(ball.get_center(),ball.get_center()+point(phase.get_value()+PI/2,0.9),VEL))
        track = Circle(radius=radius,color=MUTED,stroke_opacity=0.3).move_to(center)
        before = self.card("Before: tension supplies\nthe inward force.",[3.6,1.0,0],width=4.8,size=27)
        self.play(Create(track),FadeIn(before),run_time=0.7)
        self.add(string,ball,force,velocity)
        orbit_trail = TracedPath(ball.get_center,dissipating_time=1.5,stroke_color=BALL,stroke_opacity=0.35)
        self.add(orbit_trail)
        self.play(phase.animate.set_value(cut_angle),run_time=6,rate_func=linear)
        for obj in (ball,string,force,velocity): obj.clear_updaters(recursive=True)
        p0 = center+point(cut_angle,radius)
        tangent = point(cut_angle+PI/2,1)
        flight_distance = 1.75
        endpoint = p0+flight_distance*tangent
        guide = DashedLine(p0-0.4*tangent,endpoint+0.25*tangent,color=VEL,stroke_opacity=0.65)
        cut = label("CUT",26,PSEUDO).move_to(center+0.5*point(cut_angle,radius)+0.35*DOWN)
        after = self.card("After: no inward force.\nThe ball follows the tangent.",[3.6,1.0,0],width=4.8,size=27)
        self.play(FadeOut(string),FadeOut(force),FadeIn(cut),Create(guide),FadeTransform(before,after),run_time=0.7)
        trail = TracedPath(ball.get_center,stroke_color=BALL,stroke_width=4)
        self.add(trail)
        ghost = Dot(p0,radius=0.11,color=BALL,fill_opacity=0.25)
        flight = ValueTracker(0)
        omega = TAU/6
        ghost.add_updater(lambda m:m.move_to(center+point(cut_angle+omega*flight.get_value(),radius)))
        self.add(ghost)
        flight_time = flight_distance/(omega*radius)
        self.play(ball.animate.move_to(endpoint),velocity.animate.shift(flight_distance*tangent),
                  flight.animate.set_value(flight_time),run_time=flight_time,rate_func=linear)
        misconception = label("Straight along the tangent,\nnot radially outward.",29,VEL,width=5.3).move_to([3.4,-1.28,0])
        assumption = label("Ideal horizontal motion; other forces ignored",20,MUTED,width=8).move_to([0,-2.55,0])
        self.play(Write(misconception),FadeIn(assumption),run_time=1.3)

    def scene_force_law(self):
        title = label("F = mv² / r",46,FORCE).move_to([-3.7,1.78,0])
        defs = label("m: mass   v: speed   r: radius",21,MUTED,width=5.8).move_to([-3.7,2.48,0])
        fixed = label("Fixed: m = 1 kg, r = 2 m",25,width=5.4).move_to([-3.6,-2.18,0])
        axes = Axes(x_range=[0,6,2],y_range=[0,20,4],x_length=5.2,y_length=3.6,
                    tips=False,axis_config={"color":MUTED,"stroke_width":2}).move_to([3.1,-0.05,0])
        labels = VGroup(label("Speed v (m/s)",24).next_to(axes.x_axis,DOWN,buff=0.3),
                        label("Force F (N)",24).rotate(PI/2).next_to(axes.y_axis,LEFT,buff=0.6))
        ticks = VGroup(*[label(str(v),19,MUTED).next_to(axes.c2p(v,0),DOWN,buff=0.13) for v in (0,2,4,6)],
                       *[label(str(v),19,MUTED).next_to(axes.c2p(0,v),LEFT,buff=0.13) for v in (4,8,12,16,20)])
        graph = axes.plot(lambda v:v*v/2,x_range=[0,6],color=FORCE)
        speed = ValueTracker(2)
        phase = ValueTracker(0)
        phase.add_updater(lambda m,dt:m.increment_value(speed.get_value()/2*dt))
        center = np.array([-3.7,0.15,0.0])
        orbit = Circle(radius=0.7,color=MUTED,stroke_opacity=0.45).move_to(center)
        orbit_ball = always_redraw(lambda: Dot(center+point(phase.get_value(),0.7),radius=0.10,color=BALL))
        orbit_force = always_redraw(lambda: arrow(orbit_ball.get_center(),
                         orbit_ball.get_center()-point(phase.get_value(),0.055*speed.get_value()**2/2),FORCE))
        dot = always_redraw(lambda: Dot(axes.c2p(speed.get_value(),speed.get_value()**2/2),radius=0.09,color=PSEUDO))
        guides = always_redraw(lambda: VGroup(
            DashedLine(axes.c2p(speed.get_value(),0),dot.get_center(),color=PSEUDO,stroke_opacity=0.45),
            DashedLine(axes.c2p(0,speed.get_value()**2/2),dot.get_center(),color=PSEUDO,stroke_opacity=0.45)))
        readout = always_redraw(lambda: label(f"v = {speed.get_value():.1f} m/s    F = {speed.get_value()**2/2:.1f} N",25,PSEUDO,width=5.7).move_to([3.1,2.45,0]))
        self.play(Write(title),FadeIn(defs),FadeIn(fixed),Create(axes),FadeIn(labels),FadeIn(ticks),run_time=1.5)
        self.play(Create(graph),run_time=1.2)
        self.add(phase,orbit,orbit_ball,orbit_force,guides,dot,readout)
        self.wait(1.2)
        self.play(speed.animate.set_value(4),run_time=2.5,rate_func=linear)
        comparison = label("2× speed → 4× force",29,PSEUDO,width=5.7).move_to([-3.6,-1.38,0])
        self.play(FadeIn(comparison),run_time=0.6)
        self.wait(1.1)
        self.play(speed.animate.set_value(6),run_time=2.5,rate_func=linear)
        next_comparison = label("3× speed → 9× force",29,PSEUDO,width=5.7).move_to(comparison)
        self.play(Transform(comparison,next_comparison),run_time=0.7)

    def scene_frames(self):
        left,right = np.array([-3.3,0.3,0.0]),np.array([3.3,0.3,0.0])
        radius = 1.05
        phase = ValueTracker(0)
        time = ValueTracker(0)
        panels = VGroup(*[RoundedRectangle(width=6.0,height=4.65,corner_radius=0.15,
                       fill_color=PANEL,fill_opacity=0.55,stroke_color=MUTED,stroke_opacity=0.2).move_to(c+[0,-0.2,0]) for c in (left,right)])
        titles = VGroup(label("FROM OUTSIDE",28,VEL).move_to(left+[0,2.02,0]),
                        label("ROTATING WITH THE BALL",25,PSEUDO,width=5.4).move_to(right+[0,2.02,0]))
        tracks = VGroup(*[Circle(radius=radius,color=MUTED,stroke_opacity=0.3).move_to(c) for c in (left,right)])
        world_left = VGroup(*[Dot(left+point(a,1.4),radius=0.035,color=MUTED) for a in (0,PI/2,PI,3*PI/2)])
        world_right = always_redraw(lambda: VGroup(*[Dot(right+point(a-phase.get_value()-time.get_value(),1.4),radius=0.035,color=MUTED) for a in (0,PI/2,PI,3*PI/2)]))
        lball = Dot(left+point(0,radius),radius=0.11,color=BALL)
        lball.add_updater(lambda m:m.move_to(left+point(phase.get_value(),radius)))
        rball = Dot(right+point(0,radius),radius=0.11,color=BALL)
        lforce = always_redraw(lambda: arrow(lball.get_center(),lball.get_center()-point(phase.get_value(),0.85),FORCE))
        rforce = arrow(rball.get_center(),rball.get_center()+0.85*LEFT,FORCE)
        pseudo = arrow(rball.get_center(),rball.get_center()+0.85*RIGHT,PSEUDO,dashed=True)
        descriptions = VGroup(label("Real inward force",25,FORCE).move_to(left+[0,-1.55,0]),
                              label("Stationary here: forces balance",23,width=5.5).move_to(right+[0,-1.55,0]))
        self.play(FadeIn(panels),FadeIn(titles),Create(tracks),FadeIn(descriptions),run_time=1)
        self.add(world_left,world_right,lball,rball,lforce,rforce,pseudo)
        self.play(phase.animate.set_value(TAU),run_time=4,rate_func=linear)
        equation = label("F_centrifugal = mω²r",28,PSEUDO).move_to(right+[0,-2.03,0])
        self.play(FadeIn(equation),run_time=0.6)
        self.wait(1.1)
        for obj in (lball,lforce): obj.clear_updaters(recursive=True)
        self.play(FadeOut(lforce),FadeOut(rforce),FadeOut(pseudo),FadeOut(descriptions),FadeOut(equation),run_time=0.55)
        cut = VGroup(label("STRING CUT",23,PSEUDO).move_to(left+[0,-1.55,0]),
                     label("Same release, same ball",23,PSEUDO).move_to(right+[0,-2.03,0]))
        self.play(FadeIn(cut),run_time=0.55)
        self.change_caption("After release: straight outside, curved in the rotating view.")
        def inertial(t): return np.array([radius,radius*t,0.0])
        lball.add_updater(lambda m:m.move_to(left+inertial(time.get_value())))
        rball.add_updater(lambda m:m.move_to(right+rotation(-time.get_value(),inertial(time.get_value()))))
        lt = TracedPath(lball.get_center,stroke_color=VEL,stroke_width=4)
        rt = TracedPath(rball.get_center,stroke_color=PSEUDO,stroke_width=4)
        self.add(lt,rt)
        self.play(time.animate.set_value(1.6),run_time=4.2,rate_func=linear)
        explanation = label("Relative motion requires centrifugal and Coriolis pseudo-forces.",22,PSEUDO,width=12.3).move_to([0,-2.57,0])
        self.play(FadeIn(explanation),run_time=0.7)

    def scene_car(self):
        center = np.array([-3.4,0.7,0.0])
        radius = 1.8
        phase = ValueTracker(-PI/2)
        contact_mode = [False]
        theta_contact = 0.50
        initial = center+point(-PI/2,radius)
        contact_position = initial+radius*theta_contact*RIGHT
        contact_car = center+point(-PI/2+theta_contact,radius)
        local_offset = rotation(-theta_contact,contact_position-contact_car)
        road = Arc(radius=radius,start_angle=-PI/2,angle=PI/2,arc_center=center,color=PANEL,stroke_width=90)
        lane = DashedVMobject(Arc(radius=radius,start_angle=-PI/2,angle=PI/2,arc_center=center,color=MUTED,stroke_width=2),num_dashes=16)
        def make_car():
            car = VGroup(RoundedRectangle(width=0.95,height=0.6,corner_radius=0.1,
                        fill_color=BALL,fill_opacity=0.3,stroke_color=BALL,stroke_width=3),
                        Rectangle(width=0.22,height=0.43,fill_color=MUTED,fill_opacity=0.6,stroke_width=0).shift(0.15*RIGHT))
            car.rotate(phase.get_value()+PI/2)
            return car.move_to(center+point(phase.get_value(),radius))
        car = always_redraw(make_car)
        def passenger_position():
            theta = phase.get_value()+PI/2
            if not contact_mode[0]: return car.get_center()
            if theta <= theta_contact: return initial+radius*theta*RIGHT
            return car.get_center()+rotation(theta,local_offset)
        person = always_redraw(lambda: Dot(passenger_position(),radius=0.085,color=INK))
        contact = always_redraw(lambda: arrow(person.get_center(),person.get_center()-point(phase.get_value(),0.9),FORCE).set_opacity(1 if phase.get_value()+PI/2>=theta_contact else 0))
        tangent = DashedLine(initial,initial+3.15*RIGHT,color=VEL,stroke_opacity=0.7)
        ghost = Dot(initial,radius=0.09,color=VEL,fill_opacity=0.6)
        no_contact = label("Without inward contact",22,VEL,width=4.7).move_to([-2.85,-2.1,0])
        real = self.card("The car turns left.\nThe road pushes it inward.",[3.4,1.45,0],width=5.0,size=28)
        passenger = self.card("Seat, belt or door pushes\nthe passenger inward.",[3.4,-0.12,0],width=5.0,color=FORCE,size=28)
        frame_title = label("Rotating viewpoint",23,PSEUDO).move_to([3.4,-1.25,0])
        frame_person = Dot([3.4,-1.88,0],radius=0.09,color=INK)
        frame = VGroup(frame_title,frame_person,
            arrow(frame_person.get_center(),frame_person.get_center()+0.95*LEFT,FORCE),
            arrow(frame_person.get_center(),frame_person.get_center()+0.95*RIGHT,PSEUDO,dashed=True),
            label("Outward centrifugal pseudo-force",20,PSEUDO,width=5.2).move_to([3.4,-2.52,0]))
        self.play(Create(road),Create(lane),FadeIn(real),run_time=1)
        self.add(car,person)
        self.play(Create(tangent),FadeIn(ghost),FadeIn(no_contact),run_time=0.7)
        self.play(phase.animate.set_value(0),ghost.animate.move_to(initial+3.15*RIGHT),run_time=4.5,rate_func=linear)
        self.play(FadeOut(ghost),FadeOut(no_contact),FadeOut(tangent),run_time=0.6)
        self.play(phase.animate.set_value(-PI/2),run_time=0.7)
        contact_mode[0] = True
        self.add(contact)
        self.play(FadeIn(passenger),phase.animate.set_value(0),run_time=4.5,rate_func=linear)
        self.play(FadeIn(frame),run_time=0.8)

    def scene_summary(self):
        left_title = label("CENTRIPETAL",34,FORCE).move_to([-3.35,2.12,0])
        right_title = label("CENTRIFUGAL",34,PSEUDO).move_to([3.35,2.12,0])
        left = ["Inward net force", "Supplied by real interactions", "Explains circular acceleration"]
        right = ["Outward pseudo-force", "Introduced in a rotating frame", "Useful for the rotating observer"]
        cards = []
        for i,(a,b) in enumerate(zip(left,right)):
            y=1.15-i*1.05
            cards.extend([self.card(a,[-3.35,y,0],width=5.7,color=FORCE,size=25),
                          self.card(b,[3.35,y,0],width=5.7,color=PSEUDO,size=25)])
        self.play(Write(left_title),Write(right_title),run_time=1)
        for i in range(0,6,2): self.play(FadeIn(cards[i],shift=0.15*UP),FadeIn(cards[i+1],shift=0.15*UP),run_time=0.8)
        diagrams = []
        for x in (-3.35,3.35):
            center = np.array([x,-2.14,0.0])
            dot = Dot(center+0.48*RIGHT,radius=0.08,color=BALL)
            diagram = VGroup(Circle(radius=0.48,color=MUTED,stroke_opacity=0.4).move_to(center),dot,
                             arrow(dot.get_center(),dot.get_center()+0.7*LEFT,FORCE))
            if x>0: diagram.add(arrow(dot.get_center(),dot.get_center()+0.7*RIGHT,PSEUDO,dashed=True))
            diagrams.append(diagram)
        self.play(FadeIn(diagrams[0]),FadeIn(diagrams[1]),run_time=1.4)
        self.play(Indicate(left_title,color=FORCE),Indicate(right_title,color=PSEUDO),run_time=1)
