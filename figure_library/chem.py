"""Chemistry figures drawn by code, so every symbol, number and electron on them is exact.

The planner names WHAT to show (an equation, a molecule, an element's orbital boxes); code works out everything that
can be wrong: electron configurations (Aufbau order with the known exceptions), shells, Hund's rule, energy levels
(E_n = -2.18e-18 J / n^2), line wavelengths. Figures are SVG in the film's palette, on a transparent background, so
the renderer can place them on its board.

  spec = {"type": "orbital_boxes", "element": "N"}
  errors = figure_errors(spec)          # [] or what to fix, phrased for the planner
  svg = draw(spec)                      # SVG text
  png(spec, path, width=1600)           # PNG file

Types: equation, molecule (optionally with a functional group highlighted), reaction (structures either side of an
arrow), resonance (2-4 resonance structures on one layout), bohr, orbital_boxes, energy_levels, orbital, spectrum (and
"library" for a Commons figure, resolved by figure_library.pick); organic.py adds mechanism (curly arrows, checked by
pushing the electrons), newman, sawhorse and chair.
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
            group = spec.get('highlight')
            if group and group not in GROUPS:
                errors.append(f'molecule: "highlight" must be one of {list(GROUPS)}')
            elif group and not _group_atoms(mol, group):
                errors.append(f'molecule: {spec["smiles"]} has no {group} group to highlight')
    elif kind == 'reaction':
        errors += reaction_errors(spec)
    elif kind == 'resonance':
        errors += resonance_errors(spec)
    elif kind in organic.ERRORS:
        errors += organic.ERRORS[kind](spec)
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


def formula_text(x, y, words, size=26, fill=INK):
    """Centred text whose formula counts are subscripts: digits right after a letter or ')' (conc. H2SO4,
    Ca(OH)2); other digits (such as 25 in '25 °C') stay as written."""
    small, spans = round(size * .7), []
    for part in re.split(r'((?<=[A-Za-z)])\d+)', str(words)):
        if part and part.isdigit() and spans and re.search(r'[A-Za-z)]$', spans[-1][1]):
            spans.append(('sub', part))
        elif part:
            spans.append(('base', part))
    out = []
    for kind, part in spans:
        if kind == 'sub':
            out.append(f"<tspan font-size='{small}' dy='{size * .25:.1f}'>{html.escape(part)}</tspan>"
                       f"<tspan font-size='{size}' dy='{-size * .25:.1f}'></tspan>")
        else:
            out.append(f"<tspan font-size='{size}'>{html.escape(part)}</tspan>")
    # cairosvg misplaces tspans under text-anchor='middle': start at x minus half the width (DejaVu Sans ~0.6 em)
    width = sum(len(p) * (small if k == 'sub' else size) for k, p in spans) * .6
    return f"<text x='{x - width / 2:.1f}' y='{y:.1f}' {FONT} fill='{fill}' text-anchor='start'>{''.join(out)}</text>"


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


PALETTE = {0: (0.97, 0.95, 0.91), 6: (0.97, 0.95, 0.91), 1: (0.97, 0.95, 0.91), 7: (0.49, 0.78, 0.84),
           8: (0.95, 0.45, 0.40), 9: (0.6, 0.9, 0.5), 16: (0.95, 0.72, 0.37), 17: (0.6, 0.9, 0.5),
           35: (0.85, 0.55, 0.35), 53: (0.75, 0.55, 0.85)}
HIGHLIGHT = (0.95, 0.72, 0.37, 0.45)       # ACCENT, half see-through, behind the group's atoms and bonds
# Functional groups a molecule figure may highlight (Class 11-12 organic). Code finds them; a group the molecule
# does not have is an error, so the highlight can never point at the wrong atoms.
GROUPS = {'hydroxyl': '[#6][OX2H:1]', 'carbonyl': '[CX3:1]=[OX1:1]', 'aldehyde': '[CX3H1:1]=[O:1]',
          'ketone': '[#6][CX3:1](=[O:1])[#6]', 'carboxylic acid': '[CX3:1](=[O:1])[OX2H1:1]',
          'carboxylate': '[CX3:1](=[O:1])[O-:1]', 'ester': '[#6][CX3:1](=[O:1])[OX2:1][#6]',
          'ether': '[#6;!$(C=O)][OD2:1][#6;!$(C=O)]', 'amine': '[NX3;!$(N-C=O);!$(N=*);!$([N+]):1]',
          'amide': '[NX3:1][CX3:1]=[O:1]', 'halide': '[#6][F,Cl,Br,I:1]', 'alkene': '[CX3:1]=[CX3:1]',
          'alkyne': '[CX2:1]#[CX2:1]', 'benzene ring': '[c:1]1[c:1][c:1][c:1][c:1][c:1]1',
          'nitrile': '[CX2:1]#[NX1:1]', 'nitro': '[N+:1](=[O:1])[O-:1]'}
# Atoms marked :1 are the group; unmarked atoms are context the match needs (the carbons either side of an ester
# oxygen) and stay unlit.
BOND = 1.5                                 # RDKit's 2D bond length
BOND_PX = 64                               # drawn bond length, the same in every panel of a figure


def _drawer(width, height):
    from rdkit.Chem.Draw import rdMolDraw2D
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    options.clearBackground = False
    options.bondLineWidth = 3
    options.minFontSize = 30
    options.setAtomPalette(PALETTE)
    return drawer


def _group_atoms(mol, group):
    from rdkit import Chem
    pattern = Chem.MolFromSmarts(GROUPS[group])
    lit = [q.GetIdx() for q in pattern.GetAtoms() if q.GetAtomMapNum() == 1]
    return sorted({match[i] for match in mol.GetSubstructMatches(pattern) for i in lit})


def draw_molecule(spec, width=900, height=640):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = _mol(spec['smiles'])
    if spec.get('hydrogens'):
        mol = Chem.AddHs(mol)
    AllChem.Compute2DCoords(mol)
    drawer = _drawer(width, height)
    drawer.drawOptions().highlightRadius = .32
    drawer.drawOptions().highlightBondWidthMultiplier = 8
    atoms = _group_atoms(mol, spec['highlight']) if spec.get('highlight') else []
    if atoms:
        bonds = [b.GetIdx() for b in mol.GetBonds() if b.GetBeginAtomIdx() in atoms and b.GetEndAtomIdx() in atoms]
        drawer.DrawMolecule(mol, highlightAtoms=atoms, highlightBonds=bonds,
                            highlightAtomColors={a: HIGHLIGHT for a in atoms},
                            highlightBondColors={b: HIGHLIGHT for b in bonds})
    else:
        drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


# ------------------------------------------------------------------ several structures in one figure
def _kekule(smiles):
    """A molecule exactly as written: bonds and charges kept, no aromatic perception (a Kekule benzene stays one
    Kekule form), so each resonance structure draws as the planner wrote it."""
    from rdkit import Chem
    mol = Chem.MolFromSmiles(str(smiles or ''), sanitize=False)
    if mol is None:
        raise ValueError(f'"{smiles}" is not valid SMILES')
    try:
        Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_SETAROMATICITY)
    except Exception as exc:                                       # noqa: BLE001 - valence errors etc.
        raise ValueError(f'"{smiles}" is not a valid structure ({str(exc).splitlines()[0][:80]})')
    return mol


def _extent(mol):
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    return max(xs) - min(xs), max(ys) - min(ys)


SMALL = 6               # figures whose molecules are all this small show their carbons (CH3-CH2-OH, as NCERT writes
                        # them), not bare lines; one figure labels all its molecules or none


def _label_carbons(mol):
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        h, q = atom.GetTotalNumHs(), atom.GetFormalCharge()
        label = 'C' + ('H' if h else '') + (f'<sub>{h}</sub>' if h > 1 else '')
        label += {1: '<sup>+</sup>', -1: '<sup>-</sup>'}.get(q, '')
        atom.SetProp('atomLabel', label)


def labelled(mols):
    return max(m.GetNumHeavyAtoms() for m in mols) <= SMALL


def _panel(mol, x, y, pad=60, labels=False):
    """One structure at the shared bond length, as a nested SVG at (x, y); returns (svg, width, height, atom
    positions in the outer figure's pixels)."""
    if labels:
        _label_carbons(mol)
    w, h = _extent(mol)
    width, height = round(w / BOND * BOND_PX + 2 * pad), round(h / BOND * BOND_PX + 2 * pad)
    drawer = _drawer(width, height)
    drawer.drawOptions().fixedBondLength = BOND_PX
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    body = re.sub(r'^<\?xml[^>]*>\s*', '', drawer.GetDrawingText())
    coords = [(x + p.x, y + p.y) for p in (drawer.GetDrawCoords(i) for i in range(mol.GetNumAtoms()))]
    return body.replace('<svg ', f"<svg x='{x:.1f}' y='{y:.1f}' ", 1), width, height, coords


def _line_arrow(x0, x1, y, both=False):
    head = 16
    parts = [f"<line x1='{x0:.1f}' y1='{y:.1f}' x2='{x1:.1f}' y2='{y:.1f}' stroke='{INK}' stroke-width='4'/>",
             f"<path d='M{x1:.1f},{y:.1f} l{-head},{-head * .6:.1f} l0,{head * 1.2:.1f} z' fill='{INK}'/>"]
    if both:
        parts.append(f"<path d='M{x0:.1f},{y:.1f} l{head},{-head * .6:.1f} l0,{head * 1.2:.1f} z' fill='{INK}'/>")
    return ''.join(parts)


def _row(items, height_min=280, gap=28):
    """Lay out [('mol', mol) | ('plus',) | ('arrow', over, under) | ('resonance',)] left to right, centred on one
    line."""
    panels, labels = [], labelled([item[1] for item in items if item[0] == 'mol'])
    for item in items:
        if item[0] == 'mol':
            _, w, h, _ = _panel(item[1], 0, 0, labels=labels)
            panels.append((item, w, h))
        elif item[0] == 'arrow':
            label = max(len(item[1] or ''), len(item[2] or ''))
            panels.append((item, max(150, 17 * label + 50), 0))
        else:
            panels.append((item, 70 if item[0] == 'plus' else 130, 0))
    height = max([height_min] + [h for _, _, h in panels]) + 80
    width = sum(w for _, w, _ in panels) + gap * (len(panels) + 1)
    mid, x, body = height / 2, gap, []
    for item, w, h in panels:
        if item[0] == 'mol':
            body.append(_panel(item[1], x, mid - h / 2, labels=labels)[0])
        elif item[0] == 'plus':
            body.append(text(x + w / 2, mid + 14, '+', size=44))
        elif item[0] == 'arrow':
            body.append(_line_arrow(x + 10, x + w - 10, mid))
            if item[1]:
                body.append(formula_text(x + w / 2, mid - 18, item[1], size=26, fill=ACCENT))
            if item[2]:
                body.append(formula_text(x + w / 2, mid + 40, item[2], size=24, fill=MUTED))
        else:
            body.append(_line_arrow(x + 15, x + w - 15, mid, both=True))
        x += w + gap
    return svg(round(width), round(height), ''.join(body))


def _species(item):
    return item.get('smiles') if isinstance(item, dict) else item


def _counts(mols):
    from collections import Counter
    from rdkit import Chem
    total = Counter()
    for mol in mols:
        for atom in Chem.AddHs(mol).GetAtoms():
            total[atom.GetSymbol()] += 1
    return total


def reaction_errors(spec):
    errors, sides = [], {}
    for side in ('reactants', 'products'):
        items = spec.get(side)
        if not isinstance(items, list) or not 1 <= len(items) <= 3:
            errors.append(f'reaction: give 1-3 {side}, each {{smiles, formula}}')
            continue
        mols = []
        for item in items:
            try:
                mol = _mol(_species(item))
            except ValueError as exc:
                errors.append(f'reaction {side}: {exc}')
                continue
            stated = item.get('formula') if isinstance(item, dict) else None
            if stated and _formula(mol) != re.sub(r'\s', '', str(stated)):
                errors.append(f'reaction {side}: SMILES {_species(item)} is {_formula(mol)}, not {stated}; fix the SMILES')
            mols.append(mol)
        sides[side] = mols
    for key in ('conditions', 'below'):
        if len(str(spec.get(key) or '')) > 40:
            errors.append(f'reaction: "{key}" is short text over or under the arrow, at most 40 characters')
    if spec.get('balanced') and not errors and _counts(sides['reactants']) != _counts(sides['products']):
        errors.append(f'reaction: marked balanced but atoms differ: reactants {dict(_counts(sides["reactants"]))}, '
                      f'products {dict(_counts(sides["products"]))}')
    return errors


def draw_reaction(spec):
    from rdkit.Chem import AllChem
    items = []
    for side in ('reactants', 'products'):
        for n, item in enumerate(spec[side]):
            if n:
                items.append(('plus',))
            mol = _mol(_species(item))
            AllChem.Compute2DCoords(mol)
            items.append(('mol', mol))
        if side == 'reactants':
            items.append(('arrow', spec.get('conditions'), spec.get('below')))
    return _row(items)


def _skeleton(mol):
    return ([a.GetSymbol() for a in mol.GetAtoms()],
            sorted(tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()))) for b in mol.GetBonds()))


def resonance_errors(spec):
    structures = spec.get('structures')
    if not isinstance(structures, list) or not 2 <= len(structures) <= 4:
        return ['resonance: give 2-4 "structures" as SMILES']
    mols, errors = [], []
    for smiles in structures:
        try:
            mols.append(_kekule(smiles))
        except ValueError as exc:
            errors.append(f'resonance: {exc}')
    if errors:
        return errors
    if any(_skeleton(m) != _skeleton(mols[0]) for m in mols[1:]):
        errors.append('resonance: write every structure with the same atoms in the same order and the same '
                      'connections; only double bonds and charges move between resonance structures')
    if len({_formula(m) for m in mols}) > 1:
        errors.append(f'resonance: the structures have different formulas {[_formula(m) for m in mols]}')
    charges = {sum(a.GetFormalCharge() for a in m.GetAtoms()) for m in mols}
    if len(charges) > 1:
        errors.append(f'resonance: the total charge must be the same in every structure (found {sorted(charges)})')
    if len(set(structures)) < len(structures):
        errors.append('resonance: two structures are written the same; each must move a bond or a charge')
    return errors


def draw_resonance(spec):
    """Every structure on the first one's 2D layout (same atom order), so only the bonds and charges change."""
    from rdkit.Chem import AllChem
    mols = [_kekule(s) for s in spec['structures']]
    AllChem.Compute2DCoords(mols[0])
    layout = mols[0].GetConformer()
    items = []
    for n, mol in enumerate(mols):
        if n:
            AllChem.Compute2DCoords(mol)
            conf = mol.GetConformer()
            for i in range(mol.GetNumAtoms()):
                conf.SetAtomPosition(i, layout.GetAtomPosition(i))
            items.append(('resonance',))
        items.append(('mol', mol))
    return _row(items)


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
        'energy_levels': draw_energy_levels, 'orbital': draw_orbital, 'spectrum': draw_spectrum,
        'reaction': draw_reaction, 'resonance': draw_resonance}


def draw(spec):
    errors = figure_errors(spec)
    if errors:
        raise ValueError('; '.join(errors))
    return DRAW[spec['type']](spec)


def png(spec, path, width=1600):
    import cairosvg
    cairosvg.svg2png(bytestring=draw(spec).encode(), write_to=str(path), output_width=width)
    return Path(path)


from . import organic  # noqa: E402 - organic figures use the helpers above
DRAW.update(organic.DRAW)
