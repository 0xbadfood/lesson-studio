import manim as m
import numpy as np
import math
import json
import pathlib

BG_COLOR = '#0B1220'
CYAN = '#49D6F5'
VELOCITY_GREEN = '#71E3A2'
FORCE_RED = '#FF727C'
AMBER = '#FFC768'
TEXT_COLOR = '#EDF3FF'


def circle_point(theta, radius):
    return radius * np.array([math.cos(theta), math.sin(theta), 0.0])

def tangent_velocity(theta, radius, omega):
    return omega * radius * np.array([-math.sin(theta), math.cos(theta), 0.0])

def free_flight(t, theta, radius, omega):
    return circle_point(theta, radius) + t * tangent_velocity(theta, radius, omega)

def rotating_flight(t, theta, radius, omega):
    angle = -omega * t
    rot = np.array([
        [math.cos(angle), -math.sin(angle), 0.0],
        [math.sin(angle), math.cos(angle), 0.0],
        [0.0, 0.0, 1.0]
    ])
    return rot @ free_flight(t, theta, radius, omega)

def force_magnitude(mass, speed, radius):
    return mass * speed**2 / radius

def txt(text, size=28, color=TEXT_COLOR, max_width=11):
    if len(text) > 70:
        words = text.split()
        lines = []
        current = ""
        for w in words:
            if len(current) + len(w) + 1 > 70:
                lines.append(current)
                current = w
            else:
                current = (current + " " + w).strip()
        if current:
            lines.append(current)
        text = "\n".join(lines)
    
    t = m.Text(text, font="DejaVu Sans", font_size=size, color=color)
    if t.width > max_width:
        t.scale(max_width / t.width)
    return t

def vec(start, end, color=CYAN):
    s = np.array(start)
    e = np.array(end)
    if np.linalg.norm(e - s) < 1e-6:
        return m.Arrow(s, s + np.array([0.01, 0.01, 0]), buff=0.04, stroke_width=4, color=color)
    return m.Arrow(s, e, buff=0.04, stroke_width=4, color=color)

class QwenForces(m.Scene):
    def construct(self):
        self.camera.background_color = BG_COLOR
        self.caption = None
        
        scene_ids = [
            "hook",
            "circular_motion",
            "release",
            "force_law",
            "frames",
            "car",
            "summary"
        ]
        
        scene_methods = [
            self.scene_hook,
            self.scene_circular_motion,
            self.scene_release,
            self.scene_force_law,
            self.scene_frames,
            self.scene_car,
            self.scene_summary
        ]
        
        timings = []
        for scene_id, method in zip(scene_ids, scene_methods):
            start_time = self.time
            method()
            end_time = self.time
            timings.append({
                "id": scene_id,
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time
            })

        out_path = pathlib.Path(__file__).parent / "artifacts" / "qwen-coded-scene-timings.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(timings, f, indent=2)

    def start_scene(self, title, caption):
        start = self.time
        title_mob = txt(title, size=36, color=CYAN, max_width=12)
        title_mob.move_to([0, 3.2, 0])
        self.play(m.FadeIn(title_mob), run_time=0.5)
        
        cap_mob = txt(caption, size=24, color=TEXT_COLOR, max_width=11)
        cap_mob.move_to([0, -3.2, 0])
        self.play(m.FadeIn(cap_mob), run_time=0.5)
        self.caption = cap_mob
        
        return start

    def change_caption(self, text):
        new_cap = txt(text, size=24, color=TEXT_COLOR, max_width=11)
        new_cap.move_to([0, -3.2, 0])
        self.play(m.FadeOut(self.caption), m.FadeIn(new_cap), run_time=0.5)
        self.caption = new_cap

    def end_scene(self, start, target):
        elapsed = self.time - start
        remaining = target - elapsed
        pad = max(0, remaining - 0.7)
        if pad > 0:
            self.wait(pad)
        
        mobs_to_fade = list(self.mobjects)
        for mob in mobs_to_fade:
            mob.clear_updaters(recursive=True)
            
        if mobs_to_fade:
            self.play(*[m.FadeOut(mob) for mob in mobs_to_fade], run_time=0.7)

    def scene_hook(self):
        start = self.start_scene("Why Does It Fly Out?", "When the string breaks, the ball flies straight, not outward. Why?")

        center = np.array([0.0, 0.25, 0.0])
        radius = 1.35
        omega = 2 * math.pi / 5.0

        circle = m.Circle(radius=radius, color="#334155", stroke_width=2).move_to(center)
        self.play(m.Create(circle), run_time=0.5)

        vt = m.ValueTracker(0.0)

        def get_dot():
            t = vt.get_value()
            theta = -math.pi / 2 + omega * t
            return m.Dot(center + circle_point(theta, radius), color=CYAN, radius=0.08)

        def get_string():
            t = vt.get_value()
            theta = -math.pi / 2 + omega * t
            return m.Line(center, center + circle_point(theta, radius), color="#8899AA", stroke_width=2)

        def get_force_arrow():
            t = vt.get_value()
            theta = -math.pi / 2 + omega * t
            pos = center + circle_point(theta, radius)
            return vec(pos, pos + (center - pos) * (0.5 / radius), color=FORCE_RED)

        def get_vel_arrow():
            t = vt.get_value()
            theta = -math.pi / 2 + omega * t
            pos = center + circle_point(theta, radius)
            return vec(pos, pos + tangent_velocity(theta, radius, omega) * 0.25, color=VELOCITY_GREEN)

        dot = m.always_redraw(get_dot)
        string = m.always_redraw(get_string)
        force_arrow = m.always_redraw(get_force_arrow)
        vel_arrow = m.always_redraw(get_vel_arrow)

        self.play(m.FadeIn(dot), m.FadeIn(string), m.FadeIn(force_arrow), m.FadeIn(vel_arrow), run_time=0.5)
        trail = m.TracedPath(dot.get_center, stroke_color=CYAN, stroke_width=2, stroke_opacity=0.4)
        self.add(trail)

        legend = txt("Net Force", size=24, color=FORCE_RED)
        legend.move_to([0.0, -2.25, 0.0])
        self.play(m.FadeIn(legend), run_time=0.3)

        self.play(vt.animate.set_value(5.0), run_time=5.0, rate_func=m.linear)

        self.change_caption("The string snaps. The ball flies off in a straight line.")

        string.clear_updaters(recursive=True)
        force_arrow.clear_updaters(recursive=True)
        self.play(m.FadeOut(string), m.FadeOut(force_arrow), run_time=0.5)

        dot.clear_updaters(recursive=True)
        vel_arrow.clear_updaters(recursive=True)
        self.remove(dot, vel_arrow)

        release_pos = center + circle_point(3 * math.pi / 2, radius)
        release_vel = tangent_velocity(3 * math.pi / 2, radius, omega)

        ghost_vt = m.ValueTracker(0.0)

        def get_ghost():
            t = ghost_vt.get_value()
            theta = 3 * math.pi / 2 + omega * t
            return m.Dot(center + circle_point(theta, radius), color="#445566", radius=0.06)

        ghost_dot = m.always_redraw(get_ghost)
        self.play(m.FadeIn(ghost_dot), run_time=0.2)

        flight_vt = m.ValueTracker(0.0)

        def get_flight_dot():
            t = flight_vt.get_value()
            return m.Dot(release_pos + t * release_vel, color=CYAN, radius=0.08)

        def get_flight_arrow():
            t = flight_vt.get_value()
            pos = release_pos + t * release_vel
            return vec(pos, pos + release_vel * 0.25, color=VELOCITY_GREEN)

        flight_dot = m.always_redraw(get_flight_dot)
        flight_arrow = m.always_redraw(get_flight_arrow)

        self.play(m.FadeIn(flight_dot), m.FadeIn(flight_arrow), run_time=0.2)
        flight_trail = m.TracedPath(flight_dot.get_center, stroke_color=CYAN, stroke_width=2, stroke_opacity=0.4)
        self.add(flight_trail)

        self.play(flight_vt.animate.set_value(1.2), ghost_vt.animate.set_value(1.2), run_time=1.2, rate_func=m.linear)

        self.end_scene(start, 12.0)

    def scene_circular_motion(self):
        start = self.start_scene(
            "Velocity and Acceleration Directions",
            "Velocity is tangent. Net force and acceleration point inward."
        )

        center = np.array([-3.0, 0.0, 0.0])
        radius = 1.4
        omega = 1.5

        circle = m.Circle(radius=radius, color=CYAN, stroke_width=2).move_to(center)
        center_dot = m.Dot(center, color=TEXT_COLOR, radius=0.05)
        radius_label = txt("radius r", size=22, color=TEXT_COLOR)
        radius_label.move_to(center + np.array([0.0, -1.9, 0.0]))

        origin = np.array([3.0, -1.0, 0.0])
        v1 = tangent_velocity(-0.32, 1.1, 1.0)
        v2 = tangent_velocity(0.32, 1.1, 1.0)
        v1_tip = origin + v1
        v2_tip = origin + v2

        v1_arrow = vec(origin, v1_tip, VELOCITY_GREEN)
        v2_arrow = vec(origin, v2_tip, VELOCITY_GREEN)
        delta_v_arrow = vec(v1_tip, v2_tip, FORCE_RED)

        delta_v_label = txt("Δv points inward", size=22, color=FORCE_RED)
        delta_v_label.move_to([3.0, 0.6, 0.0])
        diagram_label = txt("Near the right side of the circle", size=20, color=TEXT_COLOR)
        diagram_label.move_to([3.0, -2.2, 0.0])

        legend_group = m.VGroup(
            txt("Velocity (tangent)", size=20, color=VELOCITY_GREEN),
            txt("Net Force (inward)", size=20, color=FORCE_RED)
        ).arrange(m.DOWN, aligned_edge=m.LEFT, buff=0.2)
        legend_group.move_to([3.0, 2.0, 0.0])

        self.play(
            m.Create(circle),
            m.FadeIn(center_dot),
            m.FadeIn(radius_label),
            run_time=1.0
        )
        self.play(
            m.FadeIn(v1_arrow),
            m.FadeIn(v2_arrow),
            m.FadeIn(delta_v_arrow),
            m.FadeIn(delta_v_label),
            m.FadeIn(diagram_label),
            m.FadeIn(legend_group),
            run_time=1.0
        )

        angle = m.ValueTracker(0.0)

        def dynamic_group():
            theta = angle.get_value()
            pos = center + circle_point(theta, radius)
            tangent = np.array([-math.sin(theta), math.cos(theta), 0.0])
            inward = -circle_point(theta, radius) / radius
            ball = m.Dot(pos, color=CYAN, radius=0.1)
            string = m.Line(center, pos, color=TEXT_COLOR, stroke_width=2, stroke_opacity=0.55)
            v_arrow = vec(pos, pos + tangent * 0.8, VELOCITY_GREEN)
            f_arrow = vec(pos, pos + inward * 0.8, FORCE_RED)
            return m.VGroup(string, ball, v_arrow, f_arrow)

        moving = m.always_redraw(dynamic_group)
        self.add(moving)
        self.play(angle.animate.set_value(4.0 * math.pi), run_time=8.0, rate_func=m.linear)

        self.wait(0.7)
        self.end_scene(start, 15.0)

    def scene_release(self):
        start = self.start_scene("Tangent Release Path", "No outward force. The ball follows the tangent at constant speed.")

        center = np.array([-2.7, 0.0, 0.0])
        r = 1.3
        omega = 2.0 * math.pi / 5.0

        circle = m.Circle(radius=r, color=CYAN, stroke_width=2).move_to(center)
        self.play(m.Create(circle), run_time=0.5)

        ball = m.Dot(radius=0.1, color=CYAN)
        ghost = m.Dot(radius=0.1, color=CYAN)
        ghost.set_opacity(0.4)

        phase = m.ValueTracker(-2.0 * math.pi)
        flight_t = m.ValueTracker(0.0)

        def get_ball_pos():
            return center + circle_point(phase.get_value(), r)

        def get_ghost_pos():
            return center + circle_point(omega * flight_t.get_value(), r)

        def get_string():
            return m.Line(center, get_ball_pos(), color=TEXT_COLOR, stroke_width=2)

        def get_force():
            return vec(get_ball_pos(), center, color=FORCE_RED)

        def get_vel():
            v = 0.65 * tangent_velocity(phase.get_value(), 1.0, 1.0)
            return vec(get_ball_pos(), get_ball_pos() + v, color=VELOCITY_GREEN)

        ball.move_to(get_ball_pos())
        ghost.move_to(get_ghost_pos())
        ball.add_updater(lambda mob: mob.move_to(get_ball_pos()))
        ghost.add_updater(lambda mob: mob.move_to(get_ghost_pos()))

        string = m.always_redraw(get_string)
        force = m.always_redraw(get_force)
        vel = m.always_redraw(get_vel)

        self.add(ball, ghost, string, force, vel)
        self.play(phase.animate.set_value(0.0), run_time=5.0, rate_func=m.linear)

        ball.clear_updaters(recursive=True)
        ghost.clear_updaters(recursive=True)
        string.clear_updaters(recursive=True)
        force.clear_updaters(recursive=True)
        vel.clear_updaters(recursive=True)

        self.play(m.FadeOut(string), m.FadeOut(force), m.FadeOut(vel), run_time=0.5)

        p0 = center + np.array([r, 0.0, 0.0])
        release_mark = m.Circle(radius=0.15, color=AMBER, stroke_width=2).move_to(p0)
        self.play(m.Create(release_mark), run_time=0.5)

        flight_time = 1.4 / (omega * r)

        def get_flight_ball_pos():
            return center + free_flight(flight_t.get_value(), 0.0, r, omega)

        def get_flight_vel():
            pos = get_flight_ball_pos()
            return vec(pos, pos + np.array([0.0, 0.65, 0.0]), color=VELOCITY_GREEN)

        ball.move_to(get_flight_ball_pos())
        ghost.move_to(get_ghost_pos())
        ball.add_updater(lambda mob: mob.move_to(get_flight_ball_pos()))
        ghost.add_updater(lambda mob: mob.move_to(get_ghost_pos()))
        flight_vel = m.always_redraw(get_flight_vel)
        self.add(flight_vel)

        self.play(flight_t.animate.set_value(flight_time), run_time=flight_time, rate_func=m.linear)

        ball.clear_updaters(recursive=True)
        ghost.clear_updaters(recursive=True)
        flight_vel.clear_updaters(recursive=True)

        text_mob = txt("Without inward force,\nthe ball follows\nthe tangent.", size=28, color=TEXT_COLOR, max_width=5.2)
        text_mob.move_to([3.0, 0.0, 0.0])
        self.play(m.FadeIn(text_mob), run_time=0.5)

        self.wait(1.0)
        self.end_scene(start, 14.0)

    def scene_force_law(self):
        start = self.start_scene(
            "Force Depends on Speed Squared",
            "Doubling speed quadruples the required inward force. F = m*v^2/r."
        )

        circle_center = np.array([-3.0, 0.0, 0.0])
        circle_radius = 0.8
        graph_center = np.array([2.6, 0.0, 0.0])
        mass = 1.0
        phys_radius = 2.0
        g_x_len = 4.4
        g_y_len = 3.0
        g_x_max = 6.0
        g_y_max = 20.0

        def graph_xy(v, f):
            x = graph_center[0] - g_x_len / 2.0 + (v / g_x_max) * g_x_len
            y = graph_center[1] - g_y_len / 2.0 + (f / g_y_max) * g_y_len
            return np.array([x, y, 0.0])

        circle = m.Circle(radius=circle_radius, color=CYAN, stroke_width=2).move_to(circle_center)
        x_axis = m.Line(
            graph_center + np.array([-g_x_len / 2.0, -g_y_len / 2.0, 0.0]),
            graph_center + np.array([g_x_len / 2.0, -g_y_len / 2.0, 0.0]),
            color=TEXT_COLOR,
            stroke_width=2,
        )
        y_axis = m.Line(
            graph_center + np.array([-g_x_len / 2.0, -g_y_len / 2.0, 0.0]),
            graph_center + np.array([-g_x_len / 2.0, g_y_len / 2.0, 0.0]),
            color=TEXT_COLOR,
            stroke_width=2,
        )
        x_label = txt("Speed (m/s)", size=20, color=TEXT_COLOR, max_width=3.2).move_to([2.6, -2.10, 0.0])
        y_label = txt("Force (N)", size=20, color=TEXT_COLOR, max_width=2.2).next_to(y_axis, m.UP, buff=0.18).shift(m.LEFT * 0.35)

        ticks = m.VGroup()
        for v_val in [2, 4, 6]:
            x_pos = graph_center[0] - g_x_len / 2.0 + (v_val / g_x_max) * g_x_len
            tick = m.Line(
                np.array([x_pos, graph_center[1] - g_y_len / 2.0, 0.0]),
                np.array([x_pos, graph_center[1] - g_y_len / 2.0 - 0.1, 0.0]),
                color=TEXT_COLOR,
                stroke_width=2,
            )
            label = txt(str(v_val), size=18, color=TEXT_COLOR, max_width=0.6).next_to(tick, m.DOWN, buff=0.05)
            ticks.add(m.VGroup(tick, label))
        for f_val in [5, 10, 15, 20]:
            y_pos = graph_center[1] - g_y_len / 2.0 + (f_val / g_y_max) * g_y_len
            tick = m.Line(
                np.array([graph_center[0] - g_x_len / 2.0, y_pos, 0.0]),
                np.array([graph_center[0] - g_x_len / 2.0 - 0.1, y_pos, 0.0]),
                color=TEXT_COLOR,
                stroke_width=2,
            )
            label = txt(str(f_val), size=18, color=TEXT_COLOR, max_width=0.8).next_to(tick, m.LEFT, buff=0.05)
            ticks.add(m.VGroup(tick, label))

        curve = m.ParametricFunction(
            lambda v: graph_xy(v, force_magnitude(mass, v, phys_radius)),
            t_range=[0.0, g_x_max],
            color=FORCE_RED,
            stroke_width=3,
        )
        data_points = m.VGroup(*[m.Dot(radius=0.06, color=FORCE_RED).move_to(graph_xy(v, force_magnitude(mass, v, phys_radius))) for v in [2, 4, 6]])

        speed_tracker = m.ValueTracker(2.0)
        phase_tracker = m.ValueTracker(0.0)
        phase_tracker.add_updater(lambda mob, dt: mob.increment_value(speed_tracker.get_value() / phys_radius * dt))

        def ball_pos():
            phase = phase_tracker.get_value()
            return circle_center + circle_radius * np.array([math.cos(phase), math.sin(phase), 0.0])

        def force_arrow_mob():
            pos = ball_pos()
            f_mag = force_magnitude(mass, speed_tracker.get_value(), phys_radius)
            radial = (pos - circle_center) / np.linalg.norm(pos - circle_center)
            end = pos - radial * (0.04 * f_mag)
            return m.Arrow(pos, end, buff=0.01, stroke_width=4, color=FORCE_RED)

        def graph_dot_mob():
            v = speed_tracker.get_value()
            return m.Dot(radius=0.06, color=FORCE_RED).move_to(graph_xy(v, force_magnitude(mass, v, phys_radius)))

        def readout_mob():
            v = speed_tracker.get_value()
            f = force_magnitude(mass, v, phys_radius)
            return txt(f"v={v:.1f} m/s  F={f:.1f} N", size=20, color=VELOCITY_GREEN, max_width=4.2).move_to([2.6, 2.35, 0.0])

        ball = m.always_redraw(lambda: m.Dot(radius=0.12, color=CYAN).move_to(ball_pos()))
        force_arrow = m.always_redraw(force_arrow_mob)
        graph_dot = m.always_redraw(graph_dot_mob)
        readout = m.always_redraw(readout_mob)
        formula = txt("F = mv²/r", size=24, color=TEXT_COLOR, max_width=3.2).move_to([-3.0, 1.8, 0.0])
        params = txt("m=1 kg, r=2 m", size=20, color=TEXT_COLOR, max_width=3.2).move_to([-3.0, -1.2, 0.0])

        self.add(phase_tracker, speed_tracker, ball, force_arrow, graph_dot, readout)
        self.play(
            m.Create(circle),
            m.Create(x_axis),
            m.Create(y_axis),
            m.Create(ticks),
            m.FadeIn(x_label),
            m.FadeIn(y_label),
            m.FadeIn(formula),
            m.FadeIn(params),
            run_time=1.5,
        )
        self.play(m.Create(curve), m.FadeIn(data_points), run_time=1.5)

        self.play(speed_tracker.animate.set_value(4.0), run_time=2.0, rate_func=m.linear)
        self.change_caption("2× speed -> 4× force")
        self.wait(1.0)

        self.play(speed_tracker.animate.set_value(6.0), run_time=2.0, rate_func=m.linear)
        self.change_caption("3× speed -> 9× force")
        self.wait(1.0)

        self.wait(1.0)
        self.end_scene(start, 20.0)

    def scene_frames(self):
        start = self.start_scene(
            "Inertial vs Rotating Frames",
            "In a rotating frame, a fictitious outward force balances the inward force."
        )

        left_c = np.array([-3.0, 0.0, 0.0])
        right_c = np.array([3.0, 0.0, 0.0])
        r = 0.9
        omega = 1.0
        p0 = np.array([r, 0.0, 0.0])

        head_l = txt("From outside", size=24, color=CYAN, max_width=5).move_to([left_c[0], 2.15, 0.0])
        head_r = txt("Rotating viewpoint", size=24, color=CYAN, max_width=5).move_to([right_c[0], 2.15, 0.0])
        circ_l = m.Circle(radius=r, color="#334155", stroke_width=2).move_to(left_c)
        circ_r = m.Circle(radius=r, color="#334155", stroke_width=2).move_to(right_c)

        dot_l = m.Dot(radius=0.08, color=CYAN).move_to(left_c + p0)
        dot_r = m.Dot(radius=0.08, color=CYAN).move_to(right_c + p0)

        f_in_r = vec(right_c + p0, right_c, color=FORCE_RED)
        f_out_r = m.DashedVMobject(vec(right_c + p0, right_c + 2.0 * p0, color=AMBER), num_dashes=8)
        lab_f_in = txt("F_net", size=20, color=FORCE_RED, max_width=2).next_to(f_in_r, m.DOWN, buff=0.12)
        lab_f_out = txt("F_cf", size=20, color=AMBER, max_width=2).next_to(f_out_r, m.RIGHT, buff=0.12)

        self.play(
            m.FadeIn(head_l), m.FadeIn(head_r),
            m.Create(circ_l), m.Create(circ_r),
            m.FadeIn(dot_l), m.FadeIn(dot_r),
            m.Create(f_in_r), m.Create(f_out_r),
            m.FadeIn(lab_f_in), m.FadeIn(lab_f_out),
            run_time=1.2
        )

        t_orbit = m.ValueTracker(0.0)

        def make_inward_arrow():
            pos = left_c + circle_point(t_orbit.get_value(), r)
            return vec(pos, left_c, color=FORCE_RED)

        f_in_l = m.always_redraw(make_inward_arrow)
        self.add(f_in_l)

        def update_left_dot(mob):
            mob.move_to(left_c + circle_point(t_orbit.get_value(), r))

        dot_l.add_updater(update_left_dot)
        self.play(t_orbit.animate.set_value(2.0 * math.pi), run_time=2.0 * math.pi, rate_func=m.linear)

        dot_l.clear_updaters(recursive=True)
        f_in_l.clear_updaters(recursive=True)

        self.play(
            m.FadeOut(f_in_l), m.FadeOut(f_in_r), m.FadeOut(f_out_r),
            m.FadeOut(lab_f_in), m.FadeOut(lab_f_out),
            run_time=0.5
        )
        self.change_caption("After release: straight outside, curved in the rotating view.")

        cor_note = txt(
            "Coriolis force also acts in the rotating frame",
            size=18, color=AMBER, max_width=10
        ).move_to([0.0, -2.35, 0.0])
        self.play(m.FadeIn(cor_note), run_time=0.5)

        t_flight = m.ValueTracker(0.0)
        trail_l = m.TracedPath(dot_l.get_center, stroke_color=CYAN, stroke_width=3, stroke_opacity=0.9)
        trail_r = m.TracedPath(dot_r.get_center, stroke_color=AMBER, stroke_width=3, stroke_opacity=0.9)

        def update_left_flight(mob):
            mob.move_to(left_c + free_flight(t_flight.get_value(), 0.0, r, omega))

        def update_right_flight(mob):
            mob.move_to(right_c + rotating_flight(t_flight.get_value(), 0.0, r, omega))

        dot_l.add_updater(update_left_flight)
        dot_r.add_updater(update_right_flight)
        self.add(trail_l, trail_r)

        self.play(t_flight.animate.set_value(1.5), run_time=1.5, rate_func=m.linear)

        dot_l.clear_updaters(recursive=True)
        dot_r.clear_updaters(recursive=True)
        self.end_scene(start, 22)

    def scene_car(self):
        start = self.start_scene("Left-Turning Car Physics", "Friction turns the car. The door pushes the passenger inward.")

        center = np.array([-3.0, 0.5, 0.0])
        radius = 1.6
        start_theta = -math.pi / 2.0
        end_theta = 0.0
        omega = (end_theta - start_theta) / 3.5

        road = m.Arc(radius=radius, start_angle=start_theta, angle=end_theta - start_theta, arc_center=center, color="#445566", stroke_width=12)
        lane = m.Arc(radius=radius - 0.22, start_angle=start_theta, angle=end_theta - start_theta, arc_center=center, color="#2E3D52", stroke_width=2)
        self.play(m.Create(road), m.Create(lane), run_time=0.8)

        phase = m.ValueTracker(start_theta)
        flight = m.ValueTracker(0.0)

        def car_center():
            return center + circle_point(phase.get_value(), radius)

        def make_car():
            body = m.RoundedRectangle(width=0.8, height=0.5, corner_radius=0.1, color=CYAN, fill_opacity=0.22, stroke_width=2)
            body.rotate(phase.get_value() + math.pi / 2.0)
            body.move_to(car_center())
            return body

        car = m.always_redraw(make_car)
        passenger = m.Dot(radius=0.08, color=TEXT_COLOR)
        passenger.add_updater(lambda mob: mob.move_to(car_center()))
        self.play(m.FadeIn(car), m.FadeIn(passenger), run_time=0.5)

        def make_friction():
            pos = car_center()
            inward = center - pos
            if np.linalg.norm(inward) < 1e-6:
                inward = np.array([0.0, 1.0, 0.0])
            inward = inward / np.linalg.norm(inward)
            return vec(pos, pos + 0.55 * inward, color=FORCE_RED)

        friction = m.always_redraw(make_friction)
        self.play(m.FadeIn(friction), run_time=0.5)

        ghost = m.Dot(radius=0.08, color=VELOCITY_GREEN)
        ghost.move_to(center + circle_point(start_theta, radius))
        ghost.add_updater(lambda mob: mob.move_to(center + free_flight(flight.get_value(), start_theta, radius, omega)))
        ghost_label = txt("Without inward contact", size=20, color=VELOCITY_GREEN, max_width=5.2)
        ghost_label.move_to([-3.0, -2.25, 0.0])
        self.play(m.FadeIn(ghost), m.FadeIn(ghost_label), run_time=0.5)

        self.play(phase.animate.set_value(end_theta), flight.animate.set_value(3.5), run_time=3.5, rate_func=m.linear)
        self.wait(0.6)

        for mob in (car, passenger, friction, ghost):
            mob.clear_updaters(recursive=True)
        self.play(m.FadeOut(ghost), m.FadeOut(ghost_label), m.FadeOut(friction), run_time=0.6)

        phase.set_value(start_theta)
        passenger.move_to(car_center())
        car.become(make_car())
        car.add_updater(lambda mob: mob.become(make_car()))
        passenger.add_updater(lambda mob: mob.move_to(car_center()))

        def make_contact():
            pos = car_center()
            inward = center - pos
            if np.linalg.norm(inward) < 1e-6:
                inward = np.array([0.0, 1.0, 0.0])
            inward = inward / np.linalg.norm(inward)
            return vec(pos, pos + 0.55 * inward, color=FORCE_RED)

        contact = m.always_redraw(make_contact)
        self.play(m.FadeIn(contact), run_time=0.5)
        self.play(phase.animate.set_value(end_theta), run_time=3.5, rate_func=m.linear)
        self.wait(0.6)

        text1 = txt("Road friction turns the car", size=24, color=TEXT_COLOR, max_width=5.2)
        text1.move_to([3.0, 1.55, 0.0])
        text2 = txt("Seat, belt or door turns the passenger", size=24, color=TEXT_COLOR, max_width=5.2)
        text2.move_to([3.0, 0.55, 0.0])
        self.play(m.FadeIn(text1), m.FadeIn(text2), run_time=0.8)

        rot_center = np.array([3.0, -1.55, 0.0])
        rot_radius = 0.72
        rot_pos = rot_center + np.array([rot_radius, 0.0, 0.0])
        rot_car = m.RoundedRectangle(width=0.52, height=0.34, corner_radius=0.06, color=CYAN, fill_opacity=0.22, stroke_width=2)
        rot_car.rotate(math.pi / 2.0)
        rot_car.move_to(rot_pos)
        rot_passenger = m.Dot(radius=0.06, color=TEXT_COLOR)
        rot_passenger.move_to(rot_pos)
        rot_radius_line = m.Line(rot_center, rot_pos, color="#445566", stroke_width=2)
        rot_center_mark = m.Dot(radius=0.035, color="#8FA3BF")
        rot_center_mark.move_to(rot_center)
        rot_contact = vec(rot_pos, rot_pos + np.array([-0.45, 0.0, 0.0]), color=FORCE_RED)
        rot_pseudo = m.DashedVMobject(vec(rot_pos, rot_pos + np.array([0.45, 0.0, 0.0]), color=AMBER), num_dashes=8)
        rot_label = txt("Rotating view", size=20, color=TEXT_COLOR, max_width=5.2)
        rot_label.move_to([3.0, -2.35, 0.0])
        self.play(
            m.FadeIn(rot_car),
            m.FadeIn(rot_passenger),
            m.FadeIn(rot_radius_line),
            m.FadeIn(rot_center_mark),
            m.FadeIn(rot_contact),
            m.FadeIn(rot_pseudo),
            m.FadeIn(rot_label),
            run_time=0.8
        )

        self.wait(1.2)
        self.end_scene(start, 18)

    def scene_summary(self):
        start = self.start_scene(
            "Real vs Fictitious Forces",
            "Centripetal is a real net force. Centrifugal is a frame-dependent effect."
        )

        left_center = np.array([-3.0, 0.0, 0.0])
        right_center = np.array([3.0, 0.0, 0.0])
        radius = 0.9

        left_circle = m.Circle(radius=radius, color=CYAN, stroke_width=2).move_to(left_center)
        right_circle = m.Circle(radius=radius, color=CYAN, stroke_width=2).move_to(right_center)

        left_ball_pos = left_center + np.array([radius, 0.0, 0.0])
        right_ball_pos = right_center + np.array([radius, 0.0, 0.0])
        left_ball = m.Dot(left_ball_pos, radius=0.08, color=CYAN)
        right_ball = m.Dot(right_ball_pos, radius=0.08, color=CYAN)

        left_force = m.Arrow(
            left_ball_pos,
            left_center,
            buff=0.05,
            stroke_width=4,
            color=FORCE_RED
        )
        right_inward = m.Arrow(
            right_ball_pos,
            right_center,
            buff=0.05,
            stroke_width=4,
            color=FORCE_RED
        )
        right_outward = m.DashedVMobject(
            m.Arrow(
                right_ball_pos,
                right_ball_pos + np.array([radius, 0.0, 0.0]),
                buff=0.05,
                stroke_width=4,
                color=AMBER
            ),
            num_dashes=8
        )

        left_title = txt("CENTRIPETAL", size=24, color=CYAN, max_width=4).move_to([left_center[0], 2.2, 0])
        right_title = txt("CENTRIFUGAL", size=24, color=AMBER, max_width=4).move_to([right_center[0], 2.2, 0])

        left_label1 = txt("Inward net force", size=20, color=TEXT_COLOR, max_width=4).move_to([left_center[0], -1.8, 0])
        left_label2 = txt("Supplied by real interactions", size=18, color=TEXT_COLOR, max_width=4).move_to([left_center[0], -2.2, 0])
        right_label1 = txt("Outward pseudo-force", size=20, color=TEXT_COLOR, max_width=4).move_to([right_center[0], -1.8, 0])
        right_label2 = txt("Used in a rotating frame", size=18, color=TEXT_COLOR, max_width=4).move_to([right_center[0], -2.2, 0])

        self.play(
            m.Create(left_circle),
            m.Create(right_circle),
            m.FadeIn(left_ball),
            m.FadeIn(right_ball),
            run_time=1.5
        )

        self.play(
            m.Create(left_force),
            m.Create(right_inward),
            m.Create(right_outward),
            run_time=1.5
        )

        self.play(
            m.Write(left_title),
            m.Write(right_title),
            run_time=1.0
        )

        self.play(
            m.Write(left_label1),
            m.Write(left_label2),
            m.Write(right_label1),
            m.Write(right_label2),
            run_time=1.5
        )

        left_pulse = m.Circle(radius=0.18, color=CYAN, stroke_width=2).move_to(left_ball_pos)
        right_pulse = m.Circle(radius=0.18, color=CYAN, stroke_width=2).move_to(right_ball_pos)
        self.play(
            m.FadeIn(left_pulse, scale=0.5),
            m.FadeIn(right_pulse, scale=0.5),
            run_time=0.75
        )
        self.play(
            m.FadeOut(left_pulse),
            m.FadeOut(right_pulse),
            run_time=0.75
        )

        self.wait(1.0)
        self.end_scene(start, 15.0)
