"""Organic figures drawn by code (user, 2026-10-21): curly-arrow mechanisms, Newman and sawhorse projections, chairs.

What students get wrong is what code works out:
- mechanism: the planner writes each stage's species as SMILES with numbered atoms ([CH3:1][CH2:2][Br:3]) and the
  curly arrows between them by those numbers. Code pushes the electrons itself (bond orders and formal charges) and
  the result must be the next stage the planner wrote, so an arrow on screen always makes what the film shows.
- newman / sawhorse: the planner gives the groups and the dihedral angle; code draws the projection and names the
  conformation (staggered, eclipsed, anti, gauche), so a stated name must agree with the angle.
- chair: substituents by carbon and axial/equatorial, drawn from a real 3D chair; a ring flip is computed (axial and
  equatorial swap, up stays up), never written by the planner.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .chem import ACCENT, INK, MUTED, BLUE, _line_arrow, _panel, formula_text, labelled, svg, text

STAGES = (2, 4)
GROUP = re.compile(r'^(?:[A-Z][a-z]?\d*|\(|\)|\d)+$')        # H, CH3, C2H5, OH, Cl, COOH, CH(CH3)2 ...


# ------------------------------------------------------------------ mechanisms
def _mapped(smiles):
    """A species with every atom's hydrogens fixed (no implicit-H drift when bonds change); map number -> index."""
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    params = Chem.SmilesParserParams()
    params.removeHs = False                                  # an [H:5] the arrows move stays an atom
    mol = Chem.MolFromSmiles(str(smiles or ''), params)
    if mol is None:
        raise ValueError(f'"{smiles}" is not valid SMILES')
    for atom in mol.GetAtoms():
        atom.SetNumExplicitHs(atom.GetTotalNumHs())
        atom.SetNoImplicit(True)
    return mol


def _canonical(mol):
    from rdkit import Chem
    copy = Chem.Mol(mol)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
    copy = Chem.RemoveHs(copy, sanitize=False)
    Chem.SanitizeMol(copy)
    return Chem.MolToSmiles(copy)


def _combined(species):
    from rdkit import Chem
    mols = [_mapped(s) for s in species]
    whole = mols[0]
    for mol in mols[1:]:
        whole = Chem.CombineMols(whole, mol)
    return mols, Chem.RWMol(whole)


def _lone_electrons(atom):
    from rdkit import Chem
    outer = Chem.GetPeriodicTable().GetNOuterElecs(atom.GetAtomicNum())
    return outer - atom.GetFormalCharge() - atom.GetTotalValence()


def _ends(arrow):
    a, b = arrow.get('from'), arrow.get('to')
    ok = lambda v: isinstance(v, list) and 1 <= len(v) <= 2 and all(isinstance(n, int) for n in v)  # noqa: E731
    return (a, b) if ok(a) and ok(b) else (None, None)


def push(species, arrows):
    """The species the arrows make, as sorted canonical SMILES (see pushed)."""
    from rdkit import Chem
    mol = pushed(species, arrows)
    return sorted(_canonical(frag) for frag in Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False))


def pushed(species, arrows):
    """Apply curly and fish-hook arrows to a stage: returns the resulting molecule (atoms keep their indices in the
    stage's species, combined in order, so each atom can be followed) or raises ValueError with what is wrong,
    phrased for the planner. An arrow moves an electron pair ("electrons": 2, the default curly arrow) or one
    electron ("electrons": 1, a fish-hook arrow, for radical steps):
      from [a]     a lone pair (or, for one electron, the unpaired electron) on atom a
      from [a, b]  the bond a-b
      to [a, x]    a new or stronger bond a-x          to [b]  an unshared electron (pair) on b
    Code keeps the books in electrons: bond orders change in half-steps that must add up to whole bonds (a bond
    broken by fish-hooks needs both of its electrons moved), formal charges follow from each atom's unshared
    electrons and bonds (charge = valence electrons - unshared - bonds), and one-electron moves set the radicals."""
    from rdkit import Chem
    _, mol = _combined(species)
    index = {a.GetAtomMapNum(): a.GetIdx() for a in mol.GetAtoms() if a.GetAtomMapNum()}
    if len(index) != sum(1 for a in mol.GetAtoms() if a.GetAtomMapNum()):
        raise ValueError('every atom number must be used once in a stage')
    shared, unshared, unpaired = Counter(), Counter(), Counter()   # electrons gained (+) or given (-)
    key = lambda x, y: (min(x, y), max(x, y))  # noqa: E731
    for n, arrow in enumerate(arrows, 1):
        src, dst = _ends(arrow)
        if src is None:
            raise ValueError(f'arrow {n}: give "from" and "to" as lists of 1 or 2 atom numbers')
        e = arrow.get('electrons', 2)
        if e not in (1, 2):
            raise ValueError(f'arrow {n}: "electrons" is 2 (a curly arrow, the default) or 1 (a fish-hook arrow)')
        missing = [m for m in src + dst if m not in index]
        if missing:
            raise ValueError(f'arrow {n}: atom numbers {missing} are not in this stage\'s SMILES (write them as [C:1])')
        s, d = [index[m] for m in src], [index[m] for m in dst]
        if len(s) == 1:
            atom = mol.GetAtomWithIdx(s[0])
            radicals = atom.GetNumRadicalElectrons() + unpaired[s[0]]
            if e == 2 and _lone_electrons(atom) + unshared[s[0]] - radicals < 2:
                raise ValueError(f'arrow {n}: atom {src[0]} has no lone pair to give')
            if e == 1 and radicals < 1:
                raise ValueError(f'arrow {n}: atom {src[0]} has no unpaired electron; a fish-hook arrow from an atom '
                                 'starts at a radical')
            if len(d) != 2 or s[0] not in d:
                raise ValueError(f'arrow {n}: electrons on {src[0]} go to a bond from it, "to": [{src[0]}, x]')
            unshared[s[0]] -= e
            unpaired[s[0]] -= e == 1
        else:
            bond = mol.GetBondBetweenAtoms(*s)
            held = (round(bond.GetBondTypeAsDouble()) * 2 if bond else 0) + shared[key(*s)]
            if held < e:
                raise ValueError(f'arrow {n}: there is no bond (or no electrons left in it) between atoms '
                                 f'{src[0]} and {src[1]}')
            if len(d) == 1 and d[0] not in s:
                raise ValueError(f'arrow {n}: a bond\'s electrons go to one of its own atoms ({src}) or to a bond '
                                 'from one of them')
            if len(d) == 2 and not set(d) & set(s):
                raise ValueError(f'arrow {n}: a bond\'s electrons go to a bond that shares an atom with it')
            shared[key(*s)] -= e
        if len(d) == 1:
            unshared[d[0]] += e
            unpaired[d[0]] += e == 1
        else:
            if d[0] == d[1]:
                raise ValueError(f'arrow {n}: a bond needs two different atoms')
            shared[key(*d)] += e
    bonds = Counter()
    for (a, b), change in shared.items():
        if change % 2:
            raise ValueError(f'the bond between atoms {_number(mol, a)} and {_number(mol, b)} is left with half an '
                             'electron pair: a bond broken by fish-hook arrows needs both of its electrons moved, and '
                             'a new bond needs two')
        if change:
            _change_bond(mol, a, b, change // 2)
            bonds[a] += change // 2
            bonds[b] += change // 2
    for i in set(unshared) | set(bonds) | set(unpaired):
        atom = mol.GetAtomWithIdx(i)
        atom.SetFormalCharge(atom.GetFormalCharge() - unshared[i] - bonds[i])
        radicals = atom.GetNumRadicalElectrons() + unpaired[i]
        if radicals < 0:
            raise ValueError(f'atom {_number(mol, i)} would have fewer than no unpaired electrons')
        atom.SetNumRadicalElectrons(radicals)
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:                                        # noqa: BLE001 - an impossible structure
        raise ValueError(f'the arrows give an impossible structure ({str(exc).splitlines()[0][:90]}); is an arrow '
                         'missing, such as the leaving group taking its bond?')
    return mol.GetMol()


def _number(mol, i):
    return mol.GetAtomWithIdx(i).GetAtomMapNum() or i


def _change_bond(mol, a, b, step):
    from rdkit import Chem
    orders = [None, Chem.BondType.SINGLE, Chem.BondType.DOUBLE, Chem.BondType.TRIPLE]
    bond = mol.GetBondBetweenAtoms(a, b)
    order = (round(bond.GetBondTypeAsDouble()) if bond else 0) + step
    if not 0 <= order <= 3:
        raise ValueError('a bond cannot go above triple')
    if bond:
        mol.RemoveBond(a, b)
    if order:
        mol.AddBond(a, b, orders[order])


def mechanism_errors(spec):
    stages = spec.get('stages')
    if not isinstance(stages, list) or not STAGES[0] <= len(stages) <= STAGES[1]:
        return [f'mechanism: give {STAGES[0]}-{STAGES[1]} "stages", each {{species:[SMILES], arrows:[...]}}; the last '
                'is the products, without arrows']
    errors = []
    for n, stage in enumerate(stages, 1):
        species = stage.get('species') if isinstance(stage, dict) else None
        if not isinstance(species, list) or not 1 <= len(species) <= 3:
            errors.append(f'mechanism stage {n}: give 1-3 species as SMILES')
            continue
        arrows = stage.get('arrows') or []
        if n < len(stages) and not 1 <= len(arrows) <= 4:
            errors.append(f'mechanism stage {n}: give 1-4 curly arrows to the next stage')
        if n == len(stages) and arrows:
            errors.append('mechanism: the last stage is the products and has no arrows')
        if len(stage.get('label') or '') > 30:
            errors.append(f'mechanism stage {n}: "label" is at most 30 characters')
        try:
            for smiles in species:
                _mapped(smiles)
        except ValueError as exc:
            errors.append(f'mechanism stage {n}: {exc}')
            continue
        if n == len(stages) or errors:
            continue
        try:
            made = push(species, arrows)
            following = sorted(_canonical(_mapped(s)) for s in stages[n]['species'])
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f'mechanism stage {n}: {exc}')
            continue
        if made != following:
            errors.append(f'mechanism stage {n}: these arrows make {made}, but stage {n + 1} shows {following}; fix '
                          'the arrows or the next stage (keep every species, spectator ions too)')
    return errors


def _bezier(p0, p1, bow, single=False):
    """A curly arrow from p0 to p1, bowed to one side (screen up for bow > 0), with a full (electron pair) head, or
    a half head (a fish-hook: one electron) when single."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1
    nx, ny = dy / length, -dx / length                     # a normal; pick the one pointing up the screen
    if ny > 0:
        nx, ny = -nx, -ny
    lift = max(40, .45 * length) * bow
    c0 = (x0 + dx * .15 + nx * lift, y0 + dy * .15 + ny * lift)
    c1 = (x0 + dx * .85 + nx * lift, y0 + dy * .85 + ny * lift)
    tx, ty = x1 - c1[0], y1 - c1[1]
    t = math.hypot(tx, ty) or 1
    tx, ty = tx / t, ty / t
    head, half = 18, 9
    left = (x1 - tx * head - ty * half, y1 - ty * head + tx * half)
    right = (x1 - tx * head + ty * half, y1 - ty * head - tx * half)
    return (f"<path d='M{x0:.1f},{y0:.1f} C{c0[0]:.1f},{c0[1]:.1f} {c1[0]:.1f},{c1[1]:.1f} {x1:.1f},{y1:.1f}' "
            f"fill='none' stroke='{ACCENT}' stroke-width='3.5'/>"
            f"<path d='M{x1:.1f},{y1:.1f} L{left[0]:.1f},{left[1]:.1f} "
            + (f"L{x1 - tx * head:.1f},{y1 - ty * head:.1f}" if single else f"L{right[0]:.1f},{right[1]:.1f}")
            + f" z' fill='{ACCENT}'/>")


def _toward(p, q, px):
    """The point px pixels from p toward q."""
    d = math.hypot(q[0] - p[0], q[1] - p[1]) or 1
    return p[0] + (q[0] - p[0]) * px / d, p[1] + (q[1] - p[1]) * px / d


def _away(mol, i, pos, px=28):
    """A point px pixels off atom i, away from its bonds (where a lone pair sits)."""
    atom = mol.GetAtomWithIdx(i)
    vx = vy = 0.0
    for nb in atom.GetNeighbors():
        q = pos[nb.GetIdx()]
        vx, vy = vx + pos[i][0] - q[0], vy + pos[i][1] - q[1]
    norm = math.hypot(vx, vy)
    if not norm:
        return pos[i][0], pos[i][1] - px
    return pos[i][0] + vx / norm * px, pos[i][1] + vy / norm * px


def draw_mechanism(spec):
    """Stages left to right (two per row), species joined by +, a reaction arrow between stages, and each stage's
    curly arrows drawn over its species."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    stages, rows = spec['stages'], []
    labels = labelled([_mapped(s) for stage in stages for s in stage['species']])
    for start in range(0, len(stages), 2):
        rows.append(list(range(start, min(start + 2, len(stages)))))
    gap, top, parts, row_svgs, widths, y = 28, 110, [], [], [], 0
    for r, row in enumerate(rows):
        x, body, heights, placed = gap, [], [], []
        if r:                                              # a row that continues the sequence starts with its arrow
            label = stages[row[0]].get('label') or ''
            body.append(('arrow', x, label))
            x += max(130, 15 * len(label) + 40) + gap
        for k, n in enumerate(row):
            stage = stages[n]
            mols = []
            for s, smiles in enumerate(stage['species']):
                if s:
                    body.append(('plus', x))
                    x += 70 + gap
                mol = Chem.Mol(_mapped(smiles))
                numbers = [a.GetAtomMapNum() for a in mol.GetAtoms()]
                for atom in mol.GetAtoms():
                    atom.SetAtomMapNum(0)
                AllChem.Compute2DCoords(mol)
                _, w, h, _ = _panel(mol, 0, 0, labels=labels)
                body.append(('mol', x, mol, w, h))
                mols.append((mol, numbers, len(body) - 1))
                heights.append(h)
                x += w + gap
            placed.append((n, mols))
            if k < len(row) - 1 or n < len(stages) - 1:
                if k < len(row) - 1:
                    label = stages[n + 1].get('label') or ''
                    body.append(('arrow', x, label))
                    x += max(130, 15 * len(label) + 40) + gap
        height = max(heights) + top + 40
        mid = top + max(heights) / 2
        svg_parts, positions = [], {}
        for item in body:
            if item[0] == 'mol':
                _, px, mol, w, h = item
                panel, _, _, coords = _panel(mol, px, y + mid - h / 2, labels=labels)
                svg_parts.append(panel)
                positions[id(mol)] = coords
            elif item[0] == 'plus':
                svg_parts.append(text(item[1] + 35, y + mid + 14, '+', size=44))
            else:
                label = item[2] if len(item) > 2 else ''
                w = max(130, 15 * len(label) + 40)
                svg_parts.append(_line_arrow(item[1] + 10, item[1] + w - 10, y + mid))
                if label:
                    svg_parts.append(formula_text(item[1] + w / 2, y + mid - 18, label, size=24, fill=MUTED))
        for n, mols in placed:
            where = {}
            for mol, numbers, _ in mols:
                for i, num in enumerate(numbers):
                    if num:
                        where[num] = (mol, i, positions[id(mol)])
            for arrow in stages[n].get('arrows') or []:
                svg_parts.append(_curly(arrow, where))
        parts.append(''.join(svg_parts))
        widths.append(x)
        y += height
    return svg(round(max(widths) + gap), round(y), ''.join(parts))


def _curly(arrow, where):
    src, dst = arrow['from'], arrow['to']
    pos = lambda num: where[num][2][where[num][1]]          # noqa: E731
    if len(src) == 1:
        mol, i, coords = where[src[0]]
        start = _away(mol, i, coords)
    else:
        a, b = pos(src[0]), pos(src[1])
        start = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if len(dst) == 1:
        mol, i, coords = where[dst[0]]
        end = _away(mol, i, coords, px=30)
    else:
        a, b = pos(dst[0]), pos(dst[1])
        shared = set(src) & set(dst)
        mol0, i0, _ = where[dst[0]]
        mol1, i1, _ = where[dst[1]]
        existing = mol0 is mol1 and mol0.GetBondBetweenAtoms(i0, i1) is not None
        if existing:
            end = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        else:                                               # a new bond: point at the atom the electrons reach
            far = dst[1] if dst[0] in shared else dst[0]
            near = dst[0] if far == dst[1] else dst[1]
            end = _toward(pos(far), pos(near), 30)
    return _bezier(start, end, 1, single=arrow.get('electrons', 2) == 1)


# ------------------------------------------------------------------ Newman and sawhorse projections
def _conformation(dihedral):
    d = dihedral % 360
    if d % 120 == 60:
        return 'staggered'
    if d % 120 == 0:
        return 'eclipsed'
    return 'skew'


NAMES = {'anti': {180}, 'gauche': {60, 300}, 'fully eclipsed': {0}, 'staggered': {60, 180, 300},
         'eclipsed': {0, 120, 240}}


def projection_errors(spec):
    kind, errors = spec.get('type'), []
    for side in ('front', 'back'):
        groups = spec.get(side)
        if not isinstance(groups, list) or len(groups) != 3 or not all(
                isinstance(g, str) and len(g) <= 8 and GROUP.match(g) for g in groups):
            errors.append(f'{kind}: "{side}" is the 3 groups on the {side} carbon, as formulas like H, CH3, Cl, OH')
    dihedral = spec.get('dihedral')
    if not isinstance(dihedral, (int, float)) or isinstance(dihedral, bool):
        errors.append(f'{kind}: "dihedral" is the angle in degrees between the first front and first back group')
    elif spec.get('conformation'):
        name = str(spec['conformation']).lower()
        if name not in NAMES:
            errors.append(f'{kind}: "conformation" must be one of {list(NAMES)} (or leave it out; code names it)')
        elif round(dihedral) % 360 not in NAMES[name]:
            errors.append(f'{kind}: a dihedral of {dihedral} degrees is not {name} (that needs '
                          f'{sorted(NAMES[name])}); the first front and first back groups are the ones compared')
    return errors


def _caption(spec):
    d = round(spec['dihedral']) % 360
    name = str(spec.get('conformation') or _conformation(d))
    return f'{name}, dihedral {d}°' if spec.get('show_angle') else name


def draw_newman(spec, size=560):
    cx, cy, ring, bond = size / 2, size / 2 - 20, 95, 185
    d = spec['dihedral']
    eclipsed = round(d) % 120 == 0
    body = [f"<circle cx='{cx}' cy='{cy}' r='{ring}' fill='none' stroke='{INK}' stroke-width='4'/>"]
    for k, group in enumerate(spec['back']):              # back bonds start at the circle's edge
        angle = math.radians(90 - (d + 120 * k) - (10 if eclipsed else 0))
        ux, uy = math.cos(angle), -math.sin(angle)
        x0, y0, x1, y1 = cx + ux * ring, cy + uy * ring, cx + ux * bond, cy + uy * bond
        body.append(f"<line x1='{x0:.1f}' y1='{y0:.1f}' x2='{x1:.1f}' y2='{y1:.1f}' stroke='{BLUE}' stroke-width='4'/>")
        body.append(formula_text(cx + ux * (bond + 34), cy + uy * (bond + 34) + 10, group, size=28, fill=BLUE))
    for k, group in enumerate(spec['front']):             # front bonds meet at the centre
        angle = math.radians(90 - 120 * k)
        ux, uy = math.cos(angle), -math.sin(angle)
        x1, y1 = cx + ux * (bond - 30), cy + uy * (bond - 30)
        body.append(f"<line x1='{cx}' y1='{cy}' x2='{x1:.1f}' y2='{y1:.1f}' stroke='{INK}' stroke-width='4'/>")
        body.append(formula_text(cx + ux * (bond + 4), cy + uy * (bond + 4) + 10, group, size=28))
    body.append(f"<circle cx='{cx}' cy='{cy}' r='6' fill='{INK}'/>")
    body.append(text(cx, size + 10, _caption(spec), size=26, fill=MUTED))
    return svg(size, size + 30, ''.join(body))


def draw_sawhorse(spec, size=560):
    """The C-C bond seen obliquely: front carbon lower left, back carbon upper right; each carbon's three groups
    spread as in the Newman view, so the two drawings of one spec agree."""
    fx, fy, bx, by, bond = size * .38, size * .62, size * .62, size * .34, 120
    d = spec['dihedral']
    body = [f"<line x1='{fx:.1f}' y1='{fy:.1f}' x2='{bx:.1f}' y2='{by:.1f}' stroke='{INK}' stroke-width='4'/>"]
    for centre, groups, offset, colour in (((bx, by), spec['back'], d, BLUE), ((fx, fy), spec['front'], 0, INK)):
        for k, group in enumerate(groups):
            angle = math.radians(90 - (offset + 120 * k))
            ux, uy = math.cos(angle), -math.sin(angle) * .8
            x1, y1 = centre[0] + ux * bond, centre[1] + uy * bond
            body.append(f"<line x1='{centre[0]:.1f}' y1='{centre[1]:.1f}' x2='{x1:.1f}' y2='{y1:.1f}' "
                        f"stroke='{colour}' stroke-width='4'/>")
            body.append(formula_text(centre[0] + ux * (bond + 30), centre[1] + uy * (bond + 30) + 10, group,
                                     size=28, fill=colour))
    body.append(text(size / 2, size + 10, _caption(spec), size=26, fill=MUTED))
    return svg(size, size + 30, ''.join(body))


# ------------------------------------------------------------------ chair cyclohexane
def chair_errors(spec):
    errors, seen = [], set()
    subs = spec.get('substituents')
    if not isinstance(subs, list) or not 1 <= len(subs) <= 6:
        return ['chair: give 1-6 "substituents", each {carbon:1-6, position:"axial"|"equatorial", group:"CH3"}']
    for s in subs:
        if not isinstance(s, dict) or s.get('carbon') not in range(1, 7) or s.get('position') not in (
                'axial', 'equatorial') or not (isinstance(s.get('group'), str) and GROUP.match(s['group'])):
            errors.append(f'chair: {s} needs carbon 1-6, position axial or equatorial, and group as a formula')
            continue
        key = (s['carbon'], s['position'])
        if key in seen:
            errors.append(f'chair: carbon {s["carbon"]} has two {s["position"]} groups')
        seen.add(key)
    return errors


def flipped(subs):
    """The ring flip: every axial group becomes equatorial and back; a group pointing up still points up."""
    return [{**s, 'position': 'equatorial' if s['position'] == 'axial' else 'axial'} for s in subs]


def _chair_points(flip=False):
    """Ring carbons 1-6 of a chair: on a circle (radius 1) in 3D, puckered +-0.25 alternately, seen from slightly
    above (back carbons higher on screen). This gives the textbook chair, its three pairs of parallel bonds by
    construction. For each carbon: screen point, whether it is puckered up, and the axial and equatorial bond
    directions on screen. A flipped chair is the mirror chair: carbons that were up are down."""
    scale, depth = 150, .3
    project = lambda x, y, z: (x * scale, -(y + z * depth) * scale)  # noqa: E731
    out = []
    for k in range(6):
        angle = math.radians(60 * k)
        x, z = math.cos(angle), math.sin(angle)
        up = (k % 2 == 0) != flip
        y = .25 if up else -.25
        sx, sy = project(x, y, z)
        ax = project(x, y + (.7 if up else -.7), z)
        eq = project(x * 1.7, y + (-.15 if up else .15), z * 1.7)
        out.append(((sx, sy), up, (ax[0] - sx, ax[1] - sy), (eq[0] - sx, eq[1] - sy)))
    return out


def _chair(subs, ox, oy, flip=False):
    points = _chair_points(flip)
    body = []
    for k in range(6):
        (x0, y0), (x1, y1) = points[k][0], points[(k + 1) % 6][0]
        body.append(f"<line x1='{ox + x0:.1f}' y1='{oy + y0:.1f}' x2='{ox + x1:.1f}' y2='{oy + y1:.1f}' "
                    f"stroke='{INK}' stroke-width='4' stroke-linecap='round'/>")
    for k, ((x, y), up, ax, eq) in enumerate(points):         # numbers inside the ring, off the bonds
        n = math.hypot(x, y) or 1
        body.append(text(ox + x - x / n * 26, oy + y - y / n * 18 + 6, str(k + 1), size=18, fill=MUTED))
    for s in subs:
        (x, y), up, ax, eq = points[s['carbon'] - 1]
        vx, vy = ax if s['position'] == 'axial' else eq
        colour = ACCENT if s['group'] != 'H' else MUTED
        x1, y1 = ox + x + vx, oy + y + vy
        body.append(f"<line x1='{ox + x:.1f}' y1='{oy + y:.1f}' x2='{x1:.1f}' y2='{y1:.1f}' stroke='{colour}' "
                    f"stroke-width='4'/>")
        n = math.hypot(vx, vy) or 1
        body.append(formula_text(x1 + vx / n * 28, y1 + vy / n * 28 + 9, s['group'], size=26, fill=colour))
    return ''.join(body)


def draw_chair(spec):
    subs = spec['substituents']
    label = lambda ss: ', '.join(f'{s["group"]} {s["position"]}' for s in ss if s['group'] != 'H')  # noqa: E731
    if not spec.get('flip'):
        return svg(620, 460, _chair(subs, 310, 200) + formula_text(310, 440, label(subs), size=24, fill=MUTED))
    other = flipped(subs)
    body = (_chair(subs, 330, 200) + formula_text(330, 440, label(subs), size=24, fill=MUTED)
            + _line_arrow(660, 800, 330, both=True) + text(730, 310, 'ring flip', size=22, fill=MUTED)
            + _chair(other, 1130, 200, flip=True) + formula_text(1130, 440, label(other), size=24, fill=MUTED))
    return svg(1460, 460, body)


ERRORS = {'mechanism': mechanism_errors, 'newman': projection_errors, 'sawhorse': projection_errors,
          'chair': chair_errors}
DRAW = {'mechanism': draw_mechanism, 'newman': draw_newman, 'sawhorse': draw_sawhorse, 'chair': draw_chair}
