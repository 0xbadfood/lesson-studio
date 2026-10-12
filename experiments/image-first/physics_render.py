"""Generality test: two new subjects animated from image-derived geometry + physics.

Orbit: stone follows the measured (magenta) circle, string drawn from the path centre,
       velocity tangent / centripetal inward arrows, then release -> straight tangent line.
Ramp:  ball rolls without slipping along the measured contact path, offset by its measured
       radius; speed from energy conservation (solid sphere, v^2 = 10/7 g dh).
No coordinates are hand-entered; scale assumptions are stated in the report.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import manim as m

ROOT = Path(__file__).resolve().parent
BG_ORBIT, BG_RAMP = 'r4-orbit-bg', 'r5-ramp-bg'


def latest(name):
    return sorted((ROOT / 'images').glob(name + '-*.png'), key=lambda p: p.stat().st_mtime)[-1]


class Frame:
    def __init__(self, w, h):
        self.w, self.h, self.s = w, h, 14.222222 / w

    def pt(self, x, y):
        return np.array([(x - self.w / 2) * self.s, (self.h / 2 - y) * self.s, 0.0])

    def place(self, mob, bbox, rot=0.0, pivot=None, shift=(0, 0)):
        x0, y0, x1, y1 = bbox
        c = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]], float)
        pivot = np.array(pivot if pivot is not None else [(x0 + x1) / 2, (y0 + y1) / 2])
        cs, sn = math.cos(rot), math.sin(rot)
        r = c - pivot
        moved = np.c_[cs * r[:, 0] - sn * r[:, 1], sn * r[:, 0] + cs * r[:, 1]] + pivot + np.array(shift)
        mob.points = np.array([self.pt(*p) for p in moved])


def free_corner(mob, paths, frame, margin=.35):
    """Put a text block in the first frame corner whose box avoids every planned motion path."""
    for corner in (m.UL, m.UR, m.DL, m.DR):
        mob.to_corner(corner, buff=.4)
        lo, hi = mob.get_corner(m.DL) - margin, mob.get_corner(m.UR) + margin
        hit = any(lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1] for path in paths for p in path)
        if not hit:
            return corner
    raise ValueError('No free corner for the legend; the layout needs another region')


def cut(name, part):
    rgba = np.array(Image.open(ROOT / 'grounding' / f'{name}-{part}.png').convert('RGBA'))
    ys, xs = np.nonzero(rgba[..., 3] > 127)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    return rgba[y0:y1, x0:x1], [int(x0), int(y0), int(x1), int(y1)]


def flatten_page(rgb, tol=28):
    """Edits add grain/ghosts to flat page areas: snap near-page pixels to the page colour."""
    border = np.concatenate([rgb[:12].reshape(-1, 3), rgb[-12:].reshape(-1, 3)])
    page = np.median(border, axis=0)
    near = np.abs(rgb.astype(int) - page).max(2) < tol
    out = rgb.copy()
    out[near] = page.astype(np.uint8)
    return out, float(near.mean())


def background(name, size):
    img = np.array(Image.open(latest(name)).convert('RGB').resize(size))
    flat, share = flatten_page(img)
    background.page_share = share
    return m.ImageMobject(flat)


class OrbitScene(m.Scene):
    def construct(self):
        geo = json.loads((ROOT / 'paths/r2-orbit.json').read_text())
        W, H = geo['size']
        F = Frame(W, H)
        cx, cy = geo['circle']['center_px']
        R = geo['circle']['radius_px']
        bg = background(BG_ORBIT, (W, H))
        F.place(bg, [0, 0, W, H])
        self.add(bg)
        stone_img, sb = cut('orbit', 'stone')
        sc = np.array([(sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2])
        phi0 = math.atan2(sc[1] - cy, sc[0] - cx)
        stone = m.ImageMobject(stone_img)
        omega = -2 * math.pi / 2.4  # one turn per 2.4 s, counter-clockwise on screen (image angle decreasing)
        t_release = 7.2 + (math.atan2(0, 1) - 0)  # release after three turns
        clock = m.ValueTracker(0)
        self.add(clock)

        def state(t):
            if t <= t_release:
                phi = phi0 + omega * t
                p = np.array([cx + R * math.cos(phi), cy + R * math.sin(phi)])
                v = R * omega * np.array([-math.sin(phi), math.cos(phi)])
                return p, v, True
            phi = phi0 + omega * t_release
            p0 = np.array([cx + R * math.cos(phi), cy + R * math.sin(phi)])
            v = R * omega * np.array([-math.sin(phi), math.cos(phi)])
            return p0 + v * (t - t_release), v, False

        stone.add_updater(lambda mob: F.place(mob, sb, shift=state(clock.get_value())[0] - sc))
        string = m.always_redraw(lambda: m.Line(F.pt(cx, cy), F.pt(*state(clock.get_value())[0]),
                                                color='#7A5C3E', stroke_width=3)
                                 if state(clock.get_value())[2] else m.VGroup())

        def arrows():
            t = clock.get_value()
            p, v, held = state(t)
            g = m.VGroup()
            unit = v / np.linalg.norm(v)
            g.add(m.Arrow(F.pt(*p), F.pt(*(p + unit * 170)), buff=0, color='#16A34A', stroke_width=6))
            if held:
                inward = np.array([cx, cy]) - p
                inward /= np.linalg.norm(inward)
                g.add(m.Arrow(F.pt(*p), F.pt(*(p + inward * 130)), buff=0, color='#DC2626', stroke_width=6))
            return g
        trail = m.always_redraw(lambda: m.DashedLine(F.pt(*state(t_release)[0]), F.pt(*state(max(t_release, clock.get_value()))[0]),
                                                     color='#16A34A', stroke_width=3)
                                if clock.get_value() > t_release else m.VGroup())
        legend = m.VGroup(m.Text('velocity (tangent)', font='DejaVu Sans', font_size=24, color='#16A34A'),
                          m.Text('pull of the string (inward)', font='DejaVu Sans', font_size=24, color='#DC2626')
                          ).arrange(m.DOWN, aligned_edge=m.LEFT)
        planned = [[F.pt(*state(t)[0]) for t in np.linspace(0, 10.5, 400)]]
        legend_corner = free_corner(legend, planned, F)
        self.add(trail, string, stone, m.always_redraw(arrows), legend)
        self.play(clock.animate.set_value(10.5), run_time=10.5, rate_func=m.linear)
        report = {'circle_px': geo['circle'], 'grip_vs_path_centre_px': None, 'release_time_s': t_release, 'legend_corner': str(legend_corner),
                  'assumptions': ['uniform circular motion, 2.4 s per turn', 'string drawn from the measured path centre',
                                  'after release: straight line at release velocity (no gravity, top view)']}
        (ROOT / 'renders' / 'orbit-report.json').write_text(json.dumps(report, indent=2))


class RampScene(m.Scene):
    def construct(self):
        geo = json.loads((ROOT / 'paths/r2-ramp.json').read_text())
        W, H = geo['size']
        F = Frame(W, H)
        bg = background(BG_RAMP, (W, H))
        F.place(bg, [0, 0, W, H])
        self.add(bg)
        ball_img, bb = cut('ramp', 'ball')
        bc = np.array([(bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2])
        r = ((bb[2] - bb[0]) + (bb[3] - bb[1])) / 4
        # Contact path -> centre path: densify, smooth, offset by r along the normal facing the ball.
        pts = np.array(geo['polyline']['points_px'], float)
        seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        s_dense = np.linspace(0, seg[-1], 1200)
        dense = np.c_[np.interp(s_dense, seg, pts[:, 0]), np.interp(s_dense, seg, pts[:, 1])]
        k = 25
        dense = np.array([dense[max(0, i - k):i + k + 1].mean(0) for i in range(len(dense))])
        tang = np.gradient(dense, axis=0)
        tang /= np.linalg.norm(tang, axis=1)[:, None]
        normal = np.c_[tang[:, 1], -tang[:, 0]]
        if np.dot(bc - dense[0], normal[0]) < 0:
            normal = -normal
        centre = dense + normal * r
        cs = np.r_[0, np.cumsum(np.linalg.norm(np.diff(centre, axis=0), axis=1))]
        # Rolling solid sphere, energy conservation; scale: ramp span ~ 3 m (stated assumption).
        px_per_m = (centre[:, 0].max() - centre[:, 0].min()) / 3.0
        g = 9.81 * px_per_m
        y0 = centre[0, 1]
        v0 = 0.25 * px_per_m
        dt, t, s, direction, track = 1 / 240, 0.0, 0.0, 1, []
        while t < 12:
            y = np.interp(s, cs, centre[:, 1])
            v2 = v0 ** 2 + (10 / 7) * g * (y - y0)
            v = math.sqrt(max(v2, 0.0))
            if v2 <= 0 and t > .5:
                direction *= -1  # turning point: rolls back
                v = 1e-3
            s = min(max(s + direction * v * dt, 0.0), cs[-1])
            if s in (0.0, cs[-1]):
                direction *= -1
            t += dt
            track.append((t, s))
        track = np.array(track)
        clock = m.ValueTracker(0)
        self.add(clock)
        ball = m.ImageMobject(ball_img)

        def pose(t):
            s = float(np.interp(t, track[:, 0], track[:, 1]))
            p = np.array([np.interp(s, cs, centre[:, 0]), np.interp(s, cs, centre[:, 1])])
            return p, s / r  # rolling without slipping: angle = s / r (clockwise when moving right)

        start_shift = centre[0] - bc
        ball.add_updater(lambda mob: F.place(mob, bb, rot=pose(clock.get_value())[1], pivot=bc,
                                             shift=pose(clock.get_value())[0] - bc))

        def speed_bar():
            t = clock.get_value()
            s = float(np.interp(t, track[:, 0], track[:, 1]))
            y = np.interp(s, cs, centre[:, 1])
            v = math.sqrt(max(0, v0 ** 2 + (10 / 7) * g * (y - y0))) / px_per_m
            label = m.Text(f'speed {v:4.1f} m/s', font='DejaVu Sans', font_size=28, color='#1F2A37')
            return label.to_corner(m.UR, buff=.5)
        self.add(ball, m.always_redraw(speed_bar))
        self.play(clock.animate.set_value(11), run_time=11, rate_func=m.linear)
        report = {'ball_radius_px': r, 'start_offset_px': start_shift.tolist(), 'px_per_m': px_per_m,
                  'max_speed_mps': float(math.sqrt((10 / 7) * 9.81 * (centre[:, 1].max() - y0) / px_per_m)),
                  'assumptions': ['ramp span 3 m', 'solid sphere rolling without slipping, no friction loss',
                                  'contact path offset by measured ball radius']}
        (ROOT / 'renders' / 'ramp-report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    which = sys.argv[1]
    q = sys.argv[2] if len(sys.argv) > 2 else 'low'
    h, w, fps = (480, 854, 15) if q == 'low' else (720, 1280, 30)
    (ROOT / 'renders').mkdir(exist_ok=True)
    with m.tempconfig({'pixel_height': h, 'pixel_width': w, 'frame_rate': fps, 'media_dir': str(ROOT / 'media'),
                       'output_file': which, 'disable_caching': True, 'verbosity': 'WARNING',
                       'background_color': '#FDFAF2'}):
        scene = {'orbit': OrbitScene, 'ramp': RampScene}[which]()
        scene.render()
        print(scene.renderer.file_writer.movie_file_path)
