"""Trusted chemistry helpers for LLM-coded scenes (copied into the render sandbox next to scene_kit).

The coder says WHAT to show (which levels, which jump); these helpers compute every number and draw the exact
shape, so energies, wavelengths and colours on screen are right by construction. Numbers follow NCERT Class 11
(Structure of Atom): R_H = 109677 cm^-1, E_n = -2.18e-18 / n^2 J, r_n = 52.9 n^2 pm.
"""
import math

import manim as m
import numpy as np

from scene_kit import WHITE, GREY, AMBER, CYAN, text

RYDBERG_CM = 109677.0           # cm^-1, NCERT value
E1_JOULE = -2.18e-18            # J, energy of the hydrogen ground state (NCERT)
BOHR_PM = 52.9                  # pm, radius of the first orbit
NUCLEUS = '#FF727C'
ELECTRON = '#49D6F5'


# ------------------------------------------------------------------ numbers
def energy_joule(n):
    """Energy of hydrogen's level n: -2.18e-18 / n^2 J."""
    return E1_JOULE / n ** 2


def radius_pm(n):
    return BOHR_PM * n ** 2


def wavenumber_cm(upper, lower):
    """Wavenumber of the line for a jump from level `upper` down to `lower` (cm^-1)."""
    if not upper > lower >= 1:
        raise ValueError('An emission line needs upper > lower >= 1')
    return RYDBERG_CM * (1 / lower ** 2 - 1 / upper ** 2)


def wavelength_nm(upper, lower):
    return 1e7 / wavenumber_cm(upper, lower)


SERIES = {1: 'Lyman', 2: 'Balmer', 3: 'Paschen', 4: 'Brackett', 5: 'Pfund'}


def series_name(lower):
    return SERIES.get(lower, f'n = {lower} series')


def region(nm):
    return 'ultraviolet' if nm < 380 else 'visible' if nm <= 750 else 'infrared'


def wavelength_colour(nm):
    """The colour of light of this wavelength; ultraviolet and infrared get violet-grey and dull red marks."""
    if nm < 380:
        return '#9C8CD9'
    if nm > 750:
        return '#A0524F'
    stops = [(380, (0.38, 0.0, 0.62)), (440, (0.35, 0.2, 1.0)), (490, (0.0, 0.75, 1.0)), (510, (0.1, 1.0, 0.3)),
             (580, (1.0, 0.95, 0.0)), (645, (1.0, 0.25, 0.0)), (750, (0.75, 0.0, 0.0))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if a <= nm <= b:
            f = (nm - a) / (b - a)
            rgb = [ca[i] + f * (cb[i] - ca[i]) for i in range(3)]
            return '#' + ''.join(f'{round(255 * v):02X}' for v in rgb)
    return WHITE


# ------------------------------------------------------------------ shapes
def nucleus(center=(0, 0, 0), radius=.22, label='+'):
    """A nucleus: a filled disc with a sign or symbol on it."""
    disc = m.Circle(radius=radius, color=NUCLEUS, fill_color=NUCLEUS, fill_opacity=1, stroke_width=0)
    group = m.VGroup(disc)
    if label:
        mark = m.MathTex(label, color='#0B1220', font_size=max(18, int(radius * 120)))
        if mark.width > 1.5 * radius:
            mark.scale(1.5 * radius / mark.width)
        group.add(mark)
    return group.move_to(np.array(center, dtype=float))


def electron(point=(0, 0, 0), radius=.08):
    return m.Dot(np.array(point, dtype=float), radius=radius, color=ELECTRON)


def orbit_radius(n, scale=.45, law='n2', top=None):
    """Drawn radius of orbit n. law='n2' is to scale (r grows as n^2); law='n' keeps outer orbits on screen and
    must be called "not to scale" on screen or in the narration. With `top`, radii are scaled so orbit `top` uses
    the full `scale`*top (n) or `scale`*top^2 (n2) budget."""
    if law not in ('n', 'n2'):
        raise ValueError("law must be 'n' or 'n2'")
    return scale * (n * n if law == 'n2' else n)


def bohr_atom(levels=4, center=(0, 0, 0), scale=.45, law='n', electrons=None, label_orbits=True):
    """Hydrogen-like atom: nucleus and circular orbits n = 1..levels. Returns a VGroup with .orbits[n] (Circle),
    .radius(n), .center and .electrons (Dots placed on the orbits named in `electrons`, e.g. {1: 1})."""
    c = np.array(center, dtype=float)
    group = m.VGroup()
    group.add(nucleus(c, radius=.16))
    group.orbits, group.electrons, group.center = {}, [], c
    group.radius = lambda n: orbit_radius(n, scale, law)
    for n in range(1, levels + 1):
        ring = m.Circle(radius=group.radius(n), color=GREY, stroke_width=2).move_to(c).set_fill(opacity=0)
        group.orbits[n] = ring
        group.add(ring)
        if label_orbits:
            tag = m.MathTex(f'n={n}', color=GREY, font_size=24)
            tag.next_to(c + np.array([group.radius(n) * .7071, group.radius(n) * .7071, 0]), m.UR, buff=.04)
            group.add(tag)
    for n, count in (electrons or {}).items():
        for k in range(count):
            angle = 2 * math.pi * k / count + .4
            dot = electron(c + group.radius(n) * np.array([math.cos(angle), math.sin(angle), 0]))
            dot.level = n
            group.electrons.append(dot)
            group.add(dot)
    return group


def orbiting(dot, center, radius, period=4.0, phase=None):
    """Keep `dot` circling `center` at `radius` (counter-clockwise, `period` seconds a turn) via an updater.
    Remove it with dot.clear_updaters() before moving the dot elsewhere."""
    c = np.array(center, dtype=float)
    start = dot.get_center() - c
    angle = [math.atan2(start[1], start[0]) if phase is None else phase]

    def step(mob, dt):
        angle[0] += 2 * math.pi * dt / period
        mob.move_to(c + radius * np.array([math.cos(angle[0]), math.sin(angle[0]), 0]))
    dot.add_updater(step)
    return dot


def photon(start, direction=(1, 0, 0), nm=656.3, length=1.6, waves=5, amplitude=.12):
    """A light wave packet leaving `start` along `direction`, coloured by its wavelength (stroke only).
    Animate with m.Create(p) or move it with p.animate.shift(...)."""
    s = np.array(start, dtype=float)
    d = np.array(direction, dtype=float)
    d = d / np.linalg.norm(d)
    normal = np.array([-d[1], d[0], 0])
    ts = np.linspace(0, 1, 120)
    points = [s + d * length * t + normal * amplitude * math.sin(2 * math.pi * waves * t) * math.sin(math.pi * t)
              for t in ts]
    wave = m.VMobject(stroke_width=4, color=wavelength_colour(nm)).set_points_smoothly(points)
    return wave.set_fill(opacity=0)


def energy_ladder(levels=(1, 2, 3, 4, 5, 6), x0=-1.5, x1=1.5, bottom=-2.4, top=2.4, labels=True):
    """Hydrogen's energy levels drawn at heights proportional to E_n (n = 1 at `bottom`, zero energy at `top`).
    Returns a VGroup with .y(n), .lines[n] and .left/.right x positions; labels show n and E_n in 10^-19 J."""
    span = top - bottom
    y = lambda n: top - span * (energy_joule(n) / E1_JOULE)       # noqa: E731
    group = m.VGroup()
    group.lines, group.y, group.left, group.right = {}, y, x0, x1
    for n in levels:
        line = m.Line([x0, y(n), 0], [x1, y(n), 0], color=WHITE if n == 1 else GREY, stroke_width=3)
        group.lines[n] = line
        group.add(line)
    if labels:
        shown = []                    # upper levels crowd together: label one only where its row is clear
        for n in sorted(levels):
            if not shown or abs(y(n) - y(shown[-1])) >= .34:
                shown.append(n)
        for n in shown:
            group.add(m.MathTex(f'n={n}', color=GREY, font_size=24).next_to([x0, y(n), 0], m.LEFT, buff=.15))
            value = energy_joule(n) / 1e-19
            group.add(m.MathTex(f'{value:.2f}', color=GREY, font_size=22).next_to([x1, y(n), 0], m.RIGHT, buff=.15))
        group.add(text('energy / 10⁻¹⁹ J', 18, GREY, width=3).next_to([x1, top, 0], m.UP + m.RIGHT, buff=.1))
    return group


def transition_arrow(ladder, upper, lower, x=None):
    """A downward arrow on an energy_ladder for the jump upper -> lower, coloured by the emitted line."""
    if not upper > lower:
        raise ValueError('An emission arrow goes from a higher level to a lower one')
    x = (ladder.left + ladder.right) / 2 if x is None else x
    return m.Arrow([x, ladder.y(upper), 0], [x, ladder.y(lower), 0], buff=0, stroke_width=4,
                   color=wavelength_colour(wavelength_nm(upper, lower)), max_tip_length_to_length_ratio=.12)


def line_label(upper, lower, digits=0):
    """'656 nm' for the jump upper -> lower (computed), for a text() or tex() label."""
    return f'{wavelength_nm(upper, lower):.{digits}f} nm'


def spectrum_bar(lines, x0=-5, x1=5, y=-2.2, height=.5, nm_range=(380, 750), dark=True):
    """An emission (dark=True: bright lines on black) strip with lines at the wavelengths of the given jumps
    [(upper, lower), ...] that fall inside nm_range. Returns a VGroup with .x(nm)."""
    lo, hi = nm_range
    xf = lambda nm: x0 + (x1 - x0) * (nm - lo) / (hi - lo)        # noqa: E731
    group = m.VGroup(m.Rectangle(width=x1 - x0, height=height, stroke_width=1, stroke_color=GREY,
                                 fill_color='#000000' if dark else WHITE, fill_opacity=1).move_to([(x0 + x1) / 2, y, 0]))
    group.x = xf
    for upper, lower in lines:
        nm = wavelength_nm(upper, lower)
        if lo <= nm <= hi:
            group.add(m.Line([xf(nm), y - height / 2, 0], [xf(nm), y + height / 2, 0], stroke_width=5,
                             color=wavelength_colour(nm)))
    return group

