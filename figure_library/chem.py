"""Chemistry figures drawn by code, so every symbol, number and electron on them is exact.

The planner names WHAT to show (an equation, a molecule, an element's orbital boxes); code works out everything that
can be wrong: electron configurations (Aufbau order with the known exceptions), shells, Hund's rule, energy levels
(E_n = -2.18e-18 J / n^2), line wavelengths. Figures are SVG in the film's palette, on a transparent background, so
the renderer can place them on its board.

  spec = {"type": "orbital_boxes", "element": "N"}
  errors = figure_errors(spec)          # [] or what to fix, phrased for the planner
  svg = draw(spec)                      # SVG text
  png(spec, path, width=1600)           # PNG file

Types: equation, molecule, bohr, orbital_boxes, energy_levels, orbital, spectrum (and "library" for a Commons figure,
resolved by figure_library.pick).
"""
from __future__ import annotations

import html
import math
import re
import subprocess
import tempfile
from pathlib import Path

INK, ACCENT, MUTED, BLUE = '#f7f3e9', '#f3b85e', '#9fb9bd', '#7cc6d6'
FONT = "font-family='DejaVu Sans, sans-serif'"

SYMBOLS = ('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr '
           'Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb '
           'Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf '
           'Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og').split()
Z = {s: n for n, s in enumerate(SYMBOLS, 1)}
# Madelung order, and the ground states that break it (the ones NCERT and the board ask about first: Cr, Cu)
ORDER = '1s 2s 2p 3s 3p 4s 3d 4p 5s 4d 5p 6s 4f 5d 6p 7s 5f 6d 7p'.split()
CAPACITY = {'s': 2, 'p': 6, 'd': 10, 'f': 14}
EXCEPTIONS = {'Cr': '[Ar] 3d5 4s1', 'Cu': '[Ar] 3d10 4s1', 'Nb': '[Kr] 4d4 5s1', 'Mo': '[Kr] 4d5 5s1',
              'Ru': '[Kr] 4d7 5s1', 'Rh': '[Kr] 4d8 5s1', 'Pd': '[Kr] 4d10', 'Ag': '[Kr] 4d10 5s1',
              'La': '[Xe] 5d1 6s2', 'Ce': '[Xe] 4f1 5d1 6s2', 'Gd': '[Xe] 4f7 5d1 6s2', 'Pt': '[Xe] 4f14 5d9 6s1',
              'Au': '[Xe] 4f14 5d10 6s1'}
NOBLE = {'He': 2, 'Ne': 10, 'Ar': 18, 'Kr': 36, 'Xe': 54, 'Rn': 86}
RYDBERG_J = 2.18e-18                       # NCERT's value for the hydrogen energy levels
SERIES = {1: 'Lyman', 2: 'Balmer', 3: 'Paschen', 4: 'Brackett', 5: 'Pfund'}
FORBIDDEN_TEX = re.compile(r'\\(input|include|openin|openout|write|immediate|catcode|def|let|csname|read|usepackage|'
                           r'documentclass|special|loop|newcommand|renewcommand)\b')


# ------------------------------------------------------------------ configurations
def parse_config(text):
    """'[Ar] 3d5 4s1' or '1s2 2s2 2p3' -> {'1s': 2, ...}, noble-gas cores expanded."""
    out = {}
    for core in re.findall(r'\[(\w+)\]', text):
        out.update(configuration(core))
    for n, l, count in re.findall(r'(\d)([spdf])\^?\{?(\d+)\}?', re.sub(r'\[\w+\]', '', text)):
        out[f'{n}{l}'] = int(count)
    return out


def configuration(symbol):
    """Ground-state electron configuration of a neutral atom, subshell -> electrons, in filling order."""
    if symbol in EXCEPTIONS:
        return parse_config(EXCEPTIONS[symbol])
    left, out = Z[symbol], {}
    for sub in ORDER:
        if not left:
            break
        out[sub] = min(left, CAPACITY[sub[-1]])
        left -= out[sub]
    return out


def config_text(config):
    """Written the NCERT way, by shell: 1s2 2s2 2p6 3s2 3p6 3d5 4s1."""
    subs = sorted(config, key=lambda s: (int(s[0]), 'spdf'.index(s[1])))
    return ' '.join(f'{s}{config[s]}' for s in subs if config[s])


def shells(config):
    out = {}
    for sub, count in config.items():
        out[int(sub[0])] = out.get(int(sub[0]), 0) + count
    return [out.get(n, 0) for n in range(1, max(out) + 1)]


def hund(count, boxes):
    """Arrows per box: singly first, all up, then pair (Hund's rule and the Pauli principle)."""
    return [(1 if count > i else 0) + (1 if count > i + boxes else 0) for i in range(boxes)]


# ------------------------------------------------------------------ validation
def figure_errors(spec):
    kind = spec.get('type')
    errors = []
    if kind == 'equation':
        tex = str(spec.get('latex', ''))
        if not tex.strip() or len(tex) > 400:
            errors.append('equation: give "latex" (use \\ce{...} for chemical equations), at most 400 characters')
        if FORBIDDEN_TEX.search(tex):
            errors.append('equation: only maths and \\ce{} are allowed in "latex"')
    elif kind == 'molecule':
        try:
            mol = _mol(spec.get('smiles', ''))
        except ValueError as exc:
            errors.append(f'molecule: {exc}')
        else:
            stated = spec.get('formula')
            if stated and _formula(mol) != re.sub(r'\s', '', str(stated)):
                errors.append(f'molecule: SMILES {spec["smiles"]} is {_formula(mol)}, not {stated}; fix the SMILES')
    elif kind in ('bohr', 'orbital_boxes'):
        if spec.get('element') not in Z and not spec.get('config'):
            errors.append(f'{kind}: give "element" as a symbol such as "Na"')
        if kind == 'orbital_boxes' and spec.get('config'):
            try:
                config = parse_config(spec['config'])
            except KeyError as exc:
                errors.append(f'orbital_boxes: unknown core {exc}')
            else:
                bad = [s for s, n in config.items() if n > CAPACITY[s[-1]]]
                if bad or not config:
                    errors.append(f'orbital_boxes: "config" must be like "1s2 2s2 2p3" (too many electrons in {bad})')
    elif kind == 'energy_levels':
        transitions = spec.get('transitions') or []
        if not all(isinstance(t, list) and len(t) == 2 and all(isinstance(n, int) and 1 <= n <= 7 for n in t)
                   and t[0] != t[1] for t in transitions):
            errors.append('energy_levels: "transitions" is a list of [from_n, to_n] pairs with 1 <= n <= 7')
    elif kind == 'orbital':
        if spec.get('orbital') not in ORBITALS:
            errors.append(f'orbital: "orbital" must be one of {list(ORBITALS)}')
    elif kind == 'spectrum':
        if spec.get('kind') not in ('electromagnetic', 'hydrogen', 'continuous'):
            errors.append('spectrum: "kind" must be electromagnetic, hydrogen or continuous')
    else:
        errors.append(f'figure type must be one of {list(DRAW)} or library')
    return errors


# ------------------------------------------------------------------ drawing helpers
def svg(width, height, body):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
            f"viewBox='0 0 {width} {height}'>{body}</svg>")


def text(x, y, words, size=28, fill=INK, anchor='middle', weight='normal'):
    return (f"<text x='{x:.1f}' y='{y:.1f}' {FONT} font-size='{size}' fill='{fill}' text-anchor='{anchor}' "
            f"font-weight='{weight}'>{html.escape(str(words))}</text>")


def sup_text(x, y, pieces, size=30, fill=INK, anchor='start'):
    """Text with superscripts: pieces are (base, superscript) pairs, e.g. [('1s', '2'), (' 2s', '2')]. Absolute sizes
    and dy shifts (cairosvg draws a percentage font-size or baseline-shift wrongly)."""
    small, spans = round(size * .62), []
    for base, sup in pieces:
        spans.append(f"<tspan font-size='{size}'>{html.escape(base)}</tspan>")
        if sup:
            spans.append(f"<tspan font-size='{small}' dy='{-size * .42:.1f}'>{html.escape(str(sup))}</tspan>"
                         f"<tspan font-size='{size}' dy='{size * .42:.1f}'></tspan>")
    return (f"<text x='{x:.1f}' y='{y:.1f}' {FONT} fill='{fill}' text-anchor='{anchor}'>{''.join(spans)}</text>")


def config_pieces(config):
    subs = sorted((s for s in config if config[s]), key=lambda s: (int(s[0]), 'spdf'.index(s[1])))
    return [((' ' if i else '') + s, config[s]) for i, s in enumerate(subs)]


# ------------------------------------------------------------------ figures
def draw_equation(spec):
    tex = spec['latex']
    body = tex if tex.strip().startswith('$') else f'$\\displaystyle {tex}$'
    doc = ('\\documentclass[preview,border=4pt]{standalone}\\usepackage[version=4]{mhchem}\\usepackage{amsmath}'
           '\\usepackage{xcolor}\\begin{document}\\color[HTML]{F7F3E9}' + body + '\\end{document}')
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, 'eq.tex').write_text(doc)
        run = subprocess.run(['latex', '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', 'eq.tex'],
                             cwd=folder, capture_output=True, text=True, timeout=60)
        if run.returncode:
            problem = next((l for l in run.stdout.splitlines() if l.startswith('!')), 'LaTeX failed')
            raise ValueError(f'equation: {problem}')
        subprocess.run(['dvisvgm', '--no-fonts', '--exact-bbox', '-o', 'eq.svg', 'eq.dvi'], cwd=folder,
                       capture_output=True, check=True, timeout=60)
        return Path(folder, 'eq.svg').read_text()


def _mol(smiles):
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    mol = Chem.MolFromSmiles(str(smiles or ''))
    if mol is None:
        raise ValueError(f'"{smiles}" is not valid SMILES')
    return mol


def _formula(mol):
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    return CalcMolFormula(mol)


def draw_molecule(spec, width=900, height=640):
    from rdkit.Chem import AllChem
    from rdkit.Chem.Draw import rdMolDraw2D
    mol = _mol(spec['smiles'])
    AllChem.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    options.clearBackground = False
    options.bondLineWidth = 3
    options.minFontSize = 30
    options.setAtomPalette({0: (0.97, 0.95, 0.91), 6: (0.97, 0.95, 0.91), 1: (0.97, 0.95, 0.91),
                            7: (0.49, 0.78, 0.84), 8: (0.95, 0.45, 0.40), 9: (0.6, 0.9, 0.5),
                            16: (0.95, 0.72, 0.37), 17: (0.6, 0.9, 0.5)})
    if spec.get('hydrogens'):
        from rdkit import Chem
        mol = Chem.AddHs(mol)
        AllChem.Compute2DCoords(mol)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def draw_bohr(spec):
    config = parse_config(spec['config']) if spec.get('config') else configuration(spec['element'])
    counts = shells(config)
    size = 260 + 120 * len(counts)
    c = size / 2
    parts = [f"<circle cx='{c}' cy='{c}' r='46' fill='{ACCENT}'/>",
             text(c, c + 10, spec.get('element', ''), 30, '#082d34', weight='bold')]
    for i, count in enumerate(counts):
        r = 100 + 60 * i
        parts.append(f"<circle cx='{c}' cy='{c}' r='{r}' fill='none' stroke='{MUTED}' stroke-width='3'/>")
        for k in range(count):
            angle = 2 * math.pi * k / count - math.pi / 2
            parts.append(f"<circle cx='{c + r * math.cos(angle):.1f}' cy='{c + r * math.sin(angle):.1f}' r='11' "
                         f"fill='{BLUE}'/>")
        parts.append(text(c + r * .72, c - r * .72 - 14, f'{"KLMNOPQ"[i]} ({count})', 24, MUTED))
    return svg(size, size, ''.join(parts))


def draw_orbital_boxes(spec):
    config = parse_config(spec['config']) if spec.get('config') else configuration(spec['element'])
    subs = sorted((s for s in config if config[s]), key=lambda s: (int(s[0]), 'spdf'.index(s[1])))
    if spec.get('valence_only') and spec.get('element') in Z:
        core = max((n for n, z in NOBLE.items() if z < Z[spec['element']]), key=NOBLE.get, default=None)
        if core:
            core_subs = configuration(core)
            subs = [s for s in subs if s not in core_subs or config[s] != core_subs[s]]
    box, gap, x, parts = 64, 34, 30, []
    for sub in subs:
        n_boxes = CAPACITY[sub[-1]] // 2
        for i, arrows in enumerate(hund(config[sub], n_boxes)):
            left = x + i * box
            parts.append(f"<rect x='{left}' y='70' width='{box}' height='{box}' fill='none' stroke='{INK}' "
                         f"stroke-width='3'/>")
            if arrows >= 1:
                parts.append(_arrow(left + box * .36, 70 + box, up=True))
            if arrows == 2:
                parts.append(_arrow(left + box * .64, 70 + box, up=False))
        width = n_boxes * box
        parts.append(sup_text(x + width / 2 - 24, 70 + box + 46, [(sub, config[sub])], 30, ACCENT))
        x += width + gap
    title = spec.get('element', '')
    parts.insert(0, sup_text(30, 40, ([(f'{title}: ', '')] if title else []) + config_pieces(config), 30))
    return svg(max(x, 520), 70 + box + 70, ''.join(parts))


def _arrow(x, bottom, up=True):
    top, low = bottom - 52, bottom - 12
    tip, tail = (top, low) if up else (low, top)
    head = 10 if up else -10
    return (f"<line x1='{x}' y1='{tail}' x2='{x}' y2='{tip}' stroke='{BLUE}' stroke-width='4'/>"
            f"<polygon points='{x - 8},{tip + head} {x + 8},{tip + head} {x},{tip}' fill='{BLUE}'/>")


def level_energy(n):
    return -RYDBERG_J / n ** 2


def wavelength_nm(upper, lower):
    """Hydrogen line from n=upper to n=lower: 1/lambda = R_H (1/lower^2 - 1/upper^2), R_H = 109677 cm^-1."""
    wavenumber = 109677 * (1 / lower ** 2 - 1 / upper ** 2)     # cm^-1
    return 1e7 / wavenumber


def draw_energy_levels(spec, width=1000, height=720):
    top_n = max([7] + [max(t) for t in spec.get('transitions') or []])
    left, right, y0, y1 = 190, width - 60, 60, height - 60
    scale = lambda e: y0 + e / level_energy(1) * (y1 - y0)            # 0 J at the top, n = 1 at the bottom  # noqa: E731
    parts = [f"<line x1='{left}' y1='{y0}' x2='{right}' y2='{y0}' stroke='{MUTED}' stroke-dasharray='8 8' "
             "stroke-width='2'/>", text(left - 16, y0 + 8, 'n = ∞  (0 J)', 22, MUTED, 'end')]
    for n in range(1, top_n + 1):
        y = scale(level_energy(n))
        parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{right}' y2='{y:.1f}' stroke='{INK}' stroke-width='3'/>")
        if n <= 4:                                      # the upper levels crowd under n = infinity
            parts.append(text(left - 16, y + 8, f'n = {n}', 24, INK, 'end'))
    transitions = spec.get('transitions') or []
    for i, (a, b) in enumerate(transitions):
        x = left + 60 + i * min(90, (right - left - 120) / max(1, len(transitions)))
        ya, yb = scale(level_energy(a)), scale(level_energy(b))
        colour = ACCENT if a > b else BLUE              # emission amber, absorption blue
        head = 12 if yb > ya else -12
        parts.append(f"<line x1='{x:.1f}' y1='{ya:.1f}' x2='{x:.1f}' y2='{yb - head:.1f}' stroke='{colour}' "
                     "stroke-width='4'/>"
                     f"<polygon points='{x - 9:.1f},{yb - head:.1f} {x + 9:.1f},{yb - head:.1f} {x:.1f},{yb:.1f}' "
                     f"fill='{colour}'/>")
        if a > b and spec.get('wavelengths', True):
            parts.append(text(x, max(ya, yb) + 32 if yb > ya else min(ya, yb) - 12, f'{wavelength_nm(a, b):.0f} nm',
                              18, colour))
    lows = {min(t) for t in transitions if t[0] > t[1]}
    if len(lows) == 1 and spec.get('series_label', True):
        parts.append(text(right, y1 + 40, f'{SERIES.get(lows.pop(), "")} series'.strip(), 26, ACCENT, 'end'))
    return svg(width, height + 20, ''.join(parts))


ORBITALS = ('s', 'px', 'py', 'pz', 'dxy', 'dxz', 'dyz', 'dx2-y2', 'dz2')


def _lobe(cx, cy, angle, length=150, width=70, fill=BLUE, opacity=.85):
    """A teardrop lobe from the nucleus outwards at `angle` degrees."""
    return (f"<g transform='translate({cx},{cy}) rotate({angle})'><path d='M0,0 C{width},{-width * .6} "
            f"{length},{-width} {length},0 C{length},{width} {width},{width * .6} 0,0 Z' fill='{fill}' "
            f"fill-opacity='{opacity}' stroke='{INK}' stroke-width='2'/></g>")


def draw_orbital(spec, size=520):
    kind, c = spec['orbital'], size / 2
    axes = {'s': ('x', 'y'), 'px': ('x', 'y'), 'py': ('y', 'z'), 'pz': ('x', 'z'), 'dxy': ('x', 'y'),   # (across, up)
            'dxz': ('x', 'z'), 'dyz': ('y', 'z'), 'dx2-y2': ('x', 'y'), 'dz2': ('x', 'z')}[kind]
    parts = [f"<line x1='30' y1='{c}' x2='{size - 30}' y2='{c}' stroke='{MUTED}' stroke-width='2'/>",
             f"<line x1='{c}' y1='30' x2='{c}' y2='{size - 30}' stroke='{MUTED}' stroke-width='2'/>",
             text(size - 24, c - 12, axes[0], 26, MUTED), text(c + 20, 44, axes[1], 26, MUTED)]
    if kind == 's':
        parts.append(f"<circle cx='{c}' cy='{c}' r='150' fill='{BLUE}' fill-opacity='.8' stroke='{INK}' "
                     "stroke-width='2'/>")
    elif kind in ('px', 'py', 'pz'):
        along = -90 if kind == 'pz' else 0                      # pz lies along the vertical (z) axis
        parts += [_lobe(c, c, along, fill=ACCENT), _lobe(c, c, along + 180)]
    elif kind == 'dz2':
        parts += [_lobe(c, c, -90, 170, 70, ACCENT), _lobe(c, c, 90, 170, 70, ACCENT),   # lobes one phase, ring the other
                  f"<ellipse cx='{c}' cy='{c}' rx='105' ry='32' fill='{BLUE}' fill-opacity='.7' stroke='{INK}' "
                  "stroke-width='2'/>"]
    else:
        start = 0 if kind == 'dx2-y2' else 45
        parts += [_lobe(c, c, start + 90 * k, 160, 62, ACCENT if k % 2 == 0 else BLUE) for k in range(4)]
    parts.append(text(c, size - 6, f'{kind} orbital', 28, INK))
    return svg(size, size + 20, ''.join(parts))


def draw_spectrum(spec, width=1200, height=260):
    kind, parts = spec['kind'], []
    if kind == 'electromagnetic':
        bands = [('Gamma rays', 'γ'), ('X-rays', ''), ('Ultraviolet', ''), ('Visible', ''), ('Infrared', ''),
                 ('Microwaves', ''), ('Radio waves', '')]
        step = (width - 40) / len(bands)
        for i, (name, _) in enumerate(bands):
            fill = 'url(#rainbow)' if name == 'Visible' else ['#3c5f73', '#41687d', '#4a7487', '#000', '#7a5a52',
                                                                 '#6f5a3c', '#5b4f36'][i]
            parts.append(f"<rect x='{20 + i * step:.1f}' y='60' width='{step - 4:.1f}' height='90' fill='{fill}'/>")
            parts.append(text(20 + i * step + step / 2, 185, name, 22, INK))
        parts.append(text(20, 40, '← shorter wavelength, higher frequency and energy', 22, MUTED, 'start'))
        parts.append(text(width - 20, 40, 'longer wavelength →', 22, MUTED, 'end'))
    else:
        parts.append(f"<rect x='20' y='60' width='{width - 40}' height='110' "
                     f"fill='{'url(#rainbow)' if kind == 'continuous' else '#05161a'}'/>")
        if kind == 'hydrogen':                          # Balmer lines, wavelengths from the Rydberg formula
            lo, hi = 380, 700
            for upper, colour in ((3, '#ff3b30'), (4, '#30c8ff'), (5, '#6a5cff'), (6, '#8f3bff')):
                nm = wavelength_nm(upper, 2)
                x = 20 + (nm - lo) / (hi - lo) * (width - 40)
                parts.append(f"<rect x='{x - 3:.1f}' y='60' width='6' height='110' fill='{colour}'/>")
                parts.append(text(x, 200, f'{nm:.0f} nm', 22, INK))
            parts.append(text(width / 2, 245, 'Hydrogen emission spectrum, visible (Balmer) lines', 24, MUTED))
    rainbow = ("<defs><linearGradient id='rainbow'>" + ''.join(
        f"<stop offset='{o}' stop-color='{c}'/>" for o, c in ((0, '#7f00ff'), (.17, '#3b4bff'), (.33, '#00b7ff'),
                                                             (.5, '#21d64b'), (.67, '#ffe600'), (.83, '#ff8a00'),
                                                             (1, '#ff1a1a'))) + "</linearGradient></defs>")
    return svg(width, height, rainbow + ''.join(parts))


DRAW = {'equation': draw_equation, 'molecule': draw_molecule, 'bohr': draw_bohr, 'orbital_boxes': draw_orbital_boxes,
        'energy_levels': draw_energy_levels, 'orbital': draw_orbital, 'spectrum': draw_spectrum}


def draw(spec):
    errors = figure_errors(spec)
    if errors:
        raise ValueError('; '.join(errors))
    return DRAW[spec['type']](spec)


def png(spec, path, width=1600):
    import cairosvg
    cairosvg.svg2png(bytestring=draw(spec).encode(), write_to=str(path), output_width=width)
    return Path(path)
