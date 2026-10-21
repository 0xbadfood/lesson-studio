"""Trusted molecule helpers for LLM-coded scenes (copied into the render sandbox with scene_kit, chem_kit and the
figure_library package).

Every structure comes from RDKit: the coder names WHAT to show (a SMILES or a known name, which atoms an arrow joins,
which group to light up) and the kit computes the layout, bonds, charges, lone pairs, stereo labels and geometry.
Mechanisms are checked by pushing the electrons (figure_library.organic) before anything is drawn, and stage-to-stage
morphs follow every atom, so a coded scene cannot draw a carbon with five bonds or an arrow that makes the wrong
product. Scenes are 2D (m.Scene): 3D molecules are projected and redrawn as they turn.
"""
import math

import manim as m
import numpy as np

from scene_kit import WHITE, GREY, AMBER, CYAN, GREEN, RED, VIOLET, FONT
from figure_library import chem as _chem, organic as _organic

PINK, ORANGE, H_GREY = '#F7B0C8', '#F0965A', '#C9D3E3'
COLOUR = {'C': WHITE, 'H': H_GREY, 'O': RED, 'N': CYAN, 'F': GREEN, 'Cl': GREEN, 'Br': ORANGE, 'I': VIOLET,
          'S': AMBER, 'P': ORANGE, 'B': PINK, 'Be': PINK, 'Si': AMBER, 'Xe': CYAN, 'Na': VIOLET, 'K': VIOLET,
          'Mg': GREEN, 'Ca': GREEN, 'Al': PINK, 'Li': VIOLET}
BALL = {'H': .5, 'C': .78, 'N': .74, 'O': .72, 'F': .68, 'Cl': .92, 'Br': 1.0, 'I': 1.12, 'S': .95, 'P': .95,
        'B': .75, 'Be': .7, 'Si': .95, 'Xe': 1.05}
# NCERT atomic masses (Class 11, Some Basic Concepts), for molar masses on screen
MASS = {'H': 1, 'C': 12, 'N': 14, 'O': 16, 'F': 19, 'Na': 23, 'Mg': 24, 'Al': 27, 'Si': 28, 'P': 31, 'S': 32,
        'Cl': 35.5, 'K': 39, 'Ca': 40, 'Fe': 56, 'Cu': 63.5, 'Zn': 65.4, 'Br': 80, 'Ag': 108, 'I': 127, 'B': 11,
        'Be': 9, 'Li': 7, 'Xe': 131.3}
SUB = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
SUP = str.maketrans('0123456789+-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻')
RDKIT_BOND = 1.5
SMALL = 6

# Known molecules (Class 6-12): name -> SMILES. Tests check every entry against its molecular formula.
NAMES = {
    # hydrocarbons
    'methane': 'C', 'ethane': 'CC', 'propane': 'CCC', 'butane': 'CCCC', '2-methylpropane': 'CC(C)C',
    'isobutane': 'CC(C)C', 'pentane': 'CCCCC', '2-methylbutane': 'CCC(C)C', '2,2-dimethylpropane': 'CC(C)(C)C',
    'neopentane': 'CC(C)(C)C', 'hexane': 'CCCCCC', 'cyclopropane': 'C1CC1', 'cyclobutane': 'C1CCC1',
    'cyclopentane': 'C1CCCC1', 'cyclohexane': 'C1CCCCC1', 'ethene': 'C=C', 'ethylene': 'C=C', 'propene': 'CC=C',
    'but-1-ene': 'C=CCC', 'but-2-ene': 'CC=CC', 'cis-but-2-ene': 'C/C=C\\C', 'trans-but-2-ene': 'C/C=C/C',
    'buta-1,3-diene': 'C=CC=C', 'ethyne': 'C#C', 'acetylene': 'C#C', 'propyne': 'CC#C', 'benzene': 'c1ccccc1',
    'toluene': 'Cc1ccccc1', 'methylbenzene': 'Cc1ccccc1', 'o-xylene': 'Cc1ccccc1C', 'styrene': 'C=Cc1ccccc1',
    'naphthalene': 'c1ccc2ccccc2c1',
    # haloalkanes and haloarenes
    'chloromethane': 'CCl', 'dichloromethane': 'ClCCl', 'chloroform': 'ClC(Cl)Cl', 'trichloromethane': 'ClC(Cl)Cl',
    'carbon tetrachloride': 'ClC(Cl)(Cl)Cl', 'tetrachloromethane': 'ClC(Cl)(Cl)Cl', 'iodomethane': 'CI',
    'bromoethane': 'CCBr', 'chloroethane': 'CCCl', '2-bromopropane': 'CC(C)Br', '1-bromopropane': 'CCCBr',
    '2-bromobutane': 'CCC(C)Br', '2-bromo-2-methylpropane': 'CC(C)(C)Br', 'tert-butyl bromide': 'CC(C)(C)Br',
    '2-chloro-2-methylpropane': 'CC(C)(C)Cl', 'chlorobenzene': 'Clc1ccccc1', 'bromobenzene': 'Brc1ccccc1',
    'vinyl chloride': 'C=CCl', 'chloroethene': 'C=CCl', 'freon-12': 'FC(F)(Cl)Cl', 'dichlorodifluoromethane': 'FC(F)(Cl)Cl',
    # alcohols, phenols, ethers
    'methanol': 'CO', 'ethanol': 'CCO', 'propan-1-ol': 'CCCO', 'propan-2-ol': 'CC(C)O', 'butan-1-ol': 'CCCCO',
    'butan-2-ol': 'CCC(C)O', '2-methylpropan-2-ol': 'CC(C)(C)O', 'tert-butyl alcohol': 'CC(C)(C)O',
    'ethane-1,2-diol': 'OCCO', 'ethylene glycol': 'OCCO', 'glycerol': 'OCC(O)CO', 'propane-1,2,3-triol': 'OCC(O)CO',
    'cyclohexanol': 'OC1CCCCC1', 'phenol': 'Oc1ccccc1', 'benzyl alcohol': 'OCc1ccccc1', 'methoxymethane': 'COC',
    'dimethyl ether': 'COC', 'ethoxyethane': 'CCOCC', 'diethyl ether': 'CCOCC', 'methoxybenzene': 'COc1ccccc1',
    'anisole': 'COc1ccccc1',
    # aldehydes, ketones, acids and derivatives
    'methanal': 'C=O', 'formaldehyde': 'C=O', 'ethanal': 'CC=O', 'acetaldehyde': 'CC=O', 'propanal': 'CCC=O',
    'benzaldehyde': 'O=Cc1ccccc1', 'propanone': 'CC(C)=O', 'acetone': 'CC(C)=O', 'butanone': 'CCC(C)=O',
    'acetophenone': 'CC(=O)c1ccccc1', 'benzophenone': 'O=C(c1ccccc1)c1ccccc1', 'methanoic acid': 'OC=O',
    'formic acid': 'OC=O', 'ethanoic acid': 'CC(=O)O', 'acetic acid': 'CC(=O)O', 'propanoic acid': 'CCC(=O)O',
    'benzoic acid': 'O=C(O)c1ccccc1', 'oxalic acid': 'OC(=O)C(=O)O', 'acetate': 'CC(=O)[O-]',
    'ethanoate': 'CC(=O)[O-]', 'ethyl ethanoate': 'CCOC(C)=O', 'ethyl acetate': 'CCOC(C)=O',
    'methyl ethanoate': 'COC(C)=O', 'ethanoyl chloride': 'CC(Cl)=O', 'acetyl chloride': 'CC(Cl)=O',
    'ethanoic anhydride': 'CC(=O)OC(C)=O', 'acetic anhydride': 'CC(=O)OC(C)=O', 'ethanamide': 'CC(N)=O',
    'acetamide': 'CC(N)=O', 'urea': 'NC(N)=O', 'salicylic acid': 'O=C(O)c1ccccc1O',
    'aspirin': 'CC(=O)Oc1ccccc1C(=O)O', 'paracetamol': 'CC(=O)Nc1ccc(O)cc1',
    # nitrogen compounds
    'methanamine': 'CN', 'methylamine': 'CN', 'ethanamine': 'CCN', 'ethylamine': 'CCN', 'dimethylamine': 'CNC',
    'trimethylamine': 'CN(C)C', 'aniline': 'Nc1ccccc1', 'benzenamine': 'Nc1ccccc1', 'nitrobenzene': 'O=[N+]([O-])c1ccccc1',
    'nitromethane': 'C[N+](=O)[O-]', 'ethanenitrile': 'CC#N', 'acetonitrile': 'CC#N', 'benzonitrile': 'N#Cc1ccccc1',
    # biomolecules (no stereo here; use fischer() or haworth() for D/L and alpha/beta)
    'glycine': 'NCC(=O)O', 'alanine': 'CC(N)C(=O)O', 'l-alanine': 'C[C@H](N)C(=O)O', 'lactic acid': 'CC(O)C(=O)O',
    'glucose': 'OCC(O)C(O)C(O)C(O)C=O', 'fructose': 'OCC(O)C(O)C(O)C(=O)CO',
    # ions, intermediates and inorganic molecules
    'hydroxide': '[OH-]', 'hydronium': '[OH3+]', 'ammonium': '[NH4+]', 'methoxide': 'C[O-]', 'ethoxide': 'CC[O-]',
    'methyl cation': '[CH3+]', 'tert-butyl cation': 'C[C+](C)C', 'water': 'O', 'ammonia': 'N', 'hydrogen': '[H][H]',
    'oxygen': 'O=O', 'nitrogen': 'N#N', 'chlorine': 'ClCl', 'bromine': 'BrBr', 'hydrogen chloride': 'Cl',
    'hydrogen bromide': 'Br', 'hydrogen sulfide': 'S', 'carbon dioxide': 'O=C=O', 'carbon monoxide': '[C-]#[O+]',
    'sulfur dioxide': 'O=S=O', 'sulfuric acid': 'OS(=O)(=O)O', 'nitric acid': 'O[N+](=O)[O-]',
    'phosphine': 'P', 'boron trifluoride': 'FB(F)F', 'beryllium chloride': 'Cl[Be]Cl',
    'phosphorus pentachloride': 'ClP(Cl)(Cl)(Cl)Cl', 'sulfur hexafluoride': 'FS(F)(F)(F)(F)F',
    'sulfur tetrafluoride': 'F[S](F)(F)F', 'chlorine trifluoride': 'F[Cl](F)F', 'xenon difluoride': 'F[Xe]F',
    'xenon tetrafluoride': 'F[Xe](F)(F)F', 'bromine pentafluoride': 'F[Br](F)(F)(F)F',
}


# ------------------------------------------------------------------ text and parsing
def formula_text(value):
    """'CH3' -> 'CH₃', 'SO4 2-' -> 'SO₄²⁻': digits after a letter or ')' are subscripts, a trailing charge is raised."""
    out, value = [], str(value).strip()
    charge = ''
    if value and value[-1] in '+-':
        k = len(value) - 1
        while k > 0 and (value[k - 1].isdigit() or value[k - 1] == ' '):
            k -= 1
        if k > 0 and value[k - 1] not in '+-':
            charge, value = value[k:].replace(' ', ''), value[:k].rstrip()
    for i, ch in enumerate(value):
        out.append(ch.translate(SUB) if ch.isdigit() and i and (value[i - 1].isalpha() or value[i - 1] in ')₀₁₂₃₄₅₆₇₈₉')
                   else ch)
    return ''.join(out) + charge.translate(SUP)


def _smiles(spec):
    key = str(spec).strip()
    return NAMES.get(key.lower(), key)


def _parse(spec, as_written=False):
    """RDKit molecule for a SMILES or a known name; atom numbers ([C:1]) and explicit [H:n] atoms kept, hydrogens
    fixed per atom. as_written keeps Kekule bonds exactly as written (resonance structures). Hypervalent central
    atoms (ClF3, XeF4) are accepted."""
    from rdkit import Chem
    smiles = _smiles(spec)
    if as_written:
        mol = _chem._kekule(smiles)
    else:
        try:
            mol = _organic._mapped(smiles)
        except ValueError:
            mol = Chem.MolFromSmiles(smiles, sanitize=False)
            if mol is None:
                raise ValueError(f'"{spec}" is neither a known molecule name nor valid SMILES')
            mol.UpdatePropertyCache(strict=False)
            Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
    for atom in mol.GetAtoms():
        atom.SetNumExplicitHs(atom.GetTotalNumHs())
        atom.SetNoImplicit(True)
    mol.UpdatePropertyCache(strict=False)
    return mol


def formula(spec):
    """Molecular formula computed by RDKit, e.g. 'C₂H₆O'."""
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    return formula_text(CalcMolFormula(_parse(spec)))


def molar_mass(spec):
    """Molar mass in g/mol from NCERT's atomic masses (C 12, H 1, O 16, Cl 35.5 ...)."""
    from rdkit import Chem
    mol = Chem.AddHs(_parse(spec))
    return round(sum(MASS[a.GetSymbol()] for a in mol.GetAtoms()), 2)


def _layout(mol):
    from rdkit.Chem import rdDepictor
    rdDepictor.SetPreferCoordGen(True)                  # CoordGen lays out rings and chains more cleanly; the
    try:                                                # setting is process-wide, so put it back after each layout
        rdDepictor.Compute2DCoords(mol)
    finally:
        rdDepictor.SetPreferCoordGen(False)
    conf = mol.GetConformer()
    xy = np.array([[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y] for i in range(mol.GetNumAtoms())])
    if not np.isfinite(xy).all():                       # CoordGen gives NaN for some tiny molecules (H2)
        rdDepictor.Compute2DCoords(mol)
        conf = mol.GetConformer()
        xy = np.array([[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y] for i in range(mol.GetNumAtoms())])
    lengths = [np.linalg.norm(xy[b.GetBeginAtomIdx()] - xy[b.GetEndAtomIdx()]) for b in mol.GetBonds()]
    if lengths:                                         # CoordGen draws bonds at 1.0, RDKit's own at 1.5: normalise
        xy = xy * RDKIT_BOND / float(np.median(lengths))
        _set_coords(mol, xy)
    return xy


def _set_coords(mol, xy):
    from rdkit.Chem import rdDepictor
    from rdkit import Geometry
    if not mol.GetNumConformers():
        rdDepictor.Compute2DCoords(mol)
    conf = mol.GetConformer()
    for i, (x, y) in enumerate(xy):
        conf.SetAtomPosition(i, Geometry.Point3D(float(x), float(y), 0.0))


def _v(x, y):
    return np.array([x, y, 0.0])


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


# ------------------------------------------------------------------ 2D molecules
class Molecule(m.VGroup):
    """A molecule drawn from RDKit's 2D layout.

    spec: SMILES or a known name (NAMES). bond: bond length in scene units. carbons: 'auto' (written CH3, CH2 when
    the molecule is small, else skeletal), 'all' or 'none'. hydrogens=True draws every H (full structural formula).
    lone_pairs=True draws each atom's computed lone pairs. aromatic: 'kekule' or 'circle'. angle rotates the layout
    (degrees). Atoms are addressed by their SMILES number ([C:1] -> 1), or by index when unnumbered."""

    def __init__(self, spec, center=(0, 0, 0), bond=None, carbons='auto', hydrogens=False, lone_pairs=False,
                 aromatic='kekule', angle=0, flip=False, coords=None, as_written=False, mol=None, text_size=None):
        super().__init__()
        from rdkit import Chem
        self.spec = str(spec)
        mol = Chem.Mol(mol) if mol is not None else _parse(spec, as_written)
        if hydrogens:
            mol = Chem.AddHs(mol)
        written = carbons == 'all' or hydrogens or (carbons == 'auto' and mol.GetNumHeavyAtoms() <= SMALL
                                                     and not mol.GetRingInfo().NumRings())
        if bond is None:                               # written carbons (CH3-CH2-OH) need room between labels
            bond = 1.15 if written else .75
        self.text_size = text_size or (26 if written else 30) * (bond / (1.15 if written else .75))
        self.mol, self.bond_length = mol, bond
        xy = np.array(coords, dtype=float) if coords is not None else _layout(mol)
        if coords is not None:
            _set_coords(mol, xy)
        xy = xy - xy.mean(axis=0) if len(xy) else xy
        if flip:
            xy[:, 0] *= -1
        if angle:
            a = math.radians(angle)
            xy = xy @ np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
        self.coords = xy
        if coords is None and (flip or angle):
            _set_coords(mol, xy)
        scale = bond / RDKIT_BOND
        center = np.array(center, dtype=float)
        points = [center + _v(*(p * scale)) for p in xy]
        show_carbons = written
        self.numbers = {a.GetAtomMapNum(): a.GetIdx() for a in mol.GetAtoms() if a.GetAtomMapNum()}
        self.anchors = m.VGroup(*[m.Dot(p, radius=.01).set_opacity(0) for p in points])
        self.labels, self.bond_mobs = {}, {}
        draw = Chem.Mol(mol)
        if aromatic == 'kekule' and not as_written:
            try:
                Chem.Kekulize(draw, clearAromaticFlags=True)
            except Exception:                                   # noqa: BLE001 - keep aromatic bonds as written
                pass
        wedges = self._wedges(draw)
        labels = m.VGroup()
        for atom in mol.GetAtoms():
            label = self._label(atom, points, show_carbons, hydrogens)
            if label is not None:
                self.labels[atom.GetIdx()] = label
                labels.add(label)
        bonds = m.VGroup()
        rings = draw.GetRingInfo()
        for b in draw.GetBonds():
            i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
            ring = None
            if b.IsInRing():
                members = min((r for r in rings.AtomRings() if i in r and j in r), key=len)
                ring = np.mean([points[k] for k in members], axis=0)
            order = (1 if aromatic == 'circle' else 1.5) if b.GetIsAromatic() else b.GetBondTypeAsDouble()
            mob = self._bond(points[i], points[j], order, self.labels.get(i), self.labels.get(j), ring,
                             wedges.get(b.GetIdx()))
            self.bond_mobs[frozenset((i, j))] = mob
            bonds.add(mob)
        if aromatic == 'circle':
            for r in rings.AtomRings():
                if all(draw.GetAtomWithIdx(k).GetIsAromatic() for k in r) or all(
                        mol.GetAtomWithIdx(k).GetIsAromatic() for k in r):
                    c = np.mean([points[k] for k in r], axis=0)
                    radius = min(np.linalg.norm(points[k] - c) for k in r) * .62
                    bonds.add(m.Circle(radius=radius, color=WHITE, stroke_width=3).move_to(c))
        self.bonds_group, self.labels_group = bonds, labels
        self.add(self.anchors, bonds, labels)
        if lone_pairs:
            self.lone_pair_group = m.VGroup(*[self.lone_pairs(a.GetIdx(), index=True) for a in mol.GetAtoms()
                                              if self._pairs(a.GetIdx())])
            self.add(self.lone_pair_group)

    # -- addressing
    def index(self, n, index=False):
        if index:
            return n
        if self.numbers:
            if n not in self.numbers:
                raise ValueError(f'atom number {n} is not in {self.spec}; number atoms in the SMILES as [C:{n}]')
            return self.numbers[n]
        if not 0 <= n < self.mol.GetNumAtoms():
            raise ValueError(f'{self.spec} has atoms 0-{self.mol.GetNumAtoms() - 1} (unnumbered SMILES: by index)')
        return n

    def point(self, n, index=False):
        """Scene position of atom n (moves with the molecule)."""
        return self.anchors[self.index(n, index)].get_center()

    def atom(self, n, index=False):
        """The atom's label, or None for an unwritten skeletal carbon."""
        return self.labels.get(self.index(n, index))

    def bond(self, a, b, index=False):
        key = frozenset((self.index(a, index), self.index(b, index)))
        if key not in self.bond_mobs:
            raise ValueError(f'atoms {a} and {b} are not bonded in {self.spec}')
        return self.bond_mobs[key]

    def bond_point(self, a, b, index=False):
        return (self.point(a, index) + self.point(b, index)) / 2

    def free_direction(self, n, index=False):
        """Unit vector off atom n, away from its bonds (where lone pairs and labels go)."""
        i = self.index(n, index)
        p = self.point(i, True)
        atom = self.mol.GetAtomWithIdx(i)
        v = np.zeros(3)
        for nb in atom.GetNeighbors():
            v += _unit(p - self.point(nb.GetIdx(), True))
        if np.linalg.norm(v) < 1e-6:
            return _v(0, 1)
        return _unit(v)

    def lone_pair_point(self, n, index=False):
        return self.point(n, index) + self.free_direction(n, index) * self._scale() * .42

    def _scale(self):
        """The current length, in scene units, of a bond RDKit draws at standard length (follows m.scale)."""
        for key in self.bond_mobs:
            i, j = tuple(key)
            drawn = np.linalg.norm(self.coords[i] - self.coords[j]) / RDKIT_BOND
            if drawn > 1e-6:
                return np.linalg.norm(self.point(i, True) - self.point(j, True)) / drawn
        return self.bond_length

    # -- chemistry computed by RDKit
    def _pairs(self, i):
        atom = self.mol.GetAtomWithIdx(i)
        if atom.GetAtomicNum() == 1:
            return 0
        if atom.GetAtomicNum() == 6 and atom.GetFormalCharge() >= 0:
            return 0
        return max(0, _organic._lone_electrons(atom) // 2)

    def lone_pair_count(self, n, index=False):
        return self._pairs(self.index(n, index))

    def lone_pairs(self, n, index=False, color=CYAN):
        """The computed lone pairs of atom n as pairs of dots, in the largest gaps between its bonds."""
        i = self.index(n, index)
        count = self._pairs(i)
        group = m.VGroup()
        if not count:
            return group
        p = self.point(i, True)
        atom = self.mol.GetAtomWithIdx(i)
        taken = [math.atan2(*(self.point(nb.GetIdx(), True) - p)[1::-1]) for nb in atom.GetNeighbors()]
        label = self.labels.get(i)
        if label is not None and atom.GetTotalNumHs():                # the written H sits on one side
            taken.append(math.pi if label.get_center()[0] < p[0] - .05 else 0.0)
        r = .34 * self.text_size / 26
        for _ in range(count):
            best = max((math.radians(d) for d in range(0, 360, 15)),
                       key=lambda a: min([abs(math.remainder(a - t, 2 * math.pi)) for t in taken] or [math.pi]))
            taken.append(best)
            u, w = _v(math.cos(best), math.sin(best)), _v(-math.sin(best), math.cos(best))
            for s in (-1, 1):
                group.add(m.Dot(p + u * r + w * s * .07, radius=.035, color=color))
        return group

    def highlight(self, group, color=AMBER, opacity=.35):
        """A glow behind a functional group (hydroxyl, carbonyl, aldehyde, ketone, carboxylic acid, carboxylate,
        ester, ether, amine, amide, halide, alkene, alkyne, benzene ring, nitrile, nitro). Only the group's atoms
        light up; a group the molecule lacks raises."""
        if group not in _chem.GROUPS:
            raise ValueError(f'highlight: group must be one of {list(_chem.GROUPS)}')
        atoms = _chem._group_atoms(self.mol, group)
        if not atoms:
            raise ValueError(f'{self.spec} has no {group} group')
        glow = m.VGroup()
        for a in atoms:
            glow.add(m.Circle(radius=self.bond_length * .32, stroke_width=0, fill_color=color,
                              fill_opacity=opacity).move_to(self.point(a, True)))
        for key in self.bond_mobs:
            i, j = tuple(key)
            if i in atoms and j in atoms:
                glow.add(m.Line(self.point(i, True), self.point(j, True), color=color, stroke_width=26,
                                stroke_opacity=opacity))
        return glow.set_z_index(-1)

    def stereo(self):
        """CIP labels computed by RDKit: {atom number (or index): 'R'/'S'} and {(a, b): 'E'/'Z'} for double bonds."""
        from rdkit import Chem
        from rdkit.Chem import rdCIPLabeler
        mol = Chem.Mol(self.mol)
        Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
        rdCIPLabeler.AssignCIPLabels(mol)
        back = {v: k for k, v in self.numbers.items()}
        name = lambda i: back.get(i, i)  # noqa: E731
        out = {name(a.GetIdx()): a.GetProp('_CIPCode') for a in mol.GetAtoms() if a.HasProp('_CIPCode')}
        for b in mol.GetBonds():
            if b.HasProp('_CIPCode'):
                out[(name(b.GetBeginAtomIdx()), name(b.GetEndAtomIdx()))] = b.GetProp('_CIPCode')
        return out

    def stereo_labels(self, size=22, color=AMBER):
        """'(R)'/'(S)' beside each stereocentre and '(E)'/'(Z)' beside each stereo double bond, computed."""
        group = m.VGroup()
        for key, code in self.stereo().items():
            if isinstance(key, tuple):
                p = self.bond_point(*key, index=not self.numbers)
                group.add(m.Text(f'({code})', font=FONT, font_size=size, color=color).next_to(p, m.UP, buff=.25))
            else:
                p = self.point(key, index=not self.numbers)
                d = self.free_direction(key, index=not self.numbers)
                group.add(m.Text(f'({code})', font=FONT, font_size=size, color=color).move_to(
                    p + d * self.bond_length * .75))
        return group

    def mirror(self, center=None, **kwargs):
        """The mirror image (enantiomer): reflected drawing and inverted stereocentres, so stereo() is right too."""
        from rdkit import Chem
        mol = Chem.Mol(self.mol)
        for atom in mol.GetAtoms():
            tag = atom.GetChiralTag()
            if tag == Chem.ChiralType.CHI_TETRAHEDRAL_CW:
                atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
            elif tag == Chem.ChiralType.CHI_TETRAHEDRAL_CCW:
                atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CW)
        xy = self.coords.copy()
        xy[:, 0] *= -1
        c = self.get_center() if center is None else center
        return Molecule(self.spec, center=c, bond=self.bond_length, coords=xy, mol=mol, **kwargs)

    def formula(self):
        from rdkit.Chem.rdMolDescriptors import CalcMolFormula
        return formula_text(CalcMolFormula(self.mol))

    # -- drawing
    def _wedges(self, draw):
        from rdkit import Chem
        if not any(a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED for a in draw.GetAtoms()):
            return {}
        _set_coords(draw, self.coords)
        Chem.AssignStereochemistry(draw, cleanIt=True, force=True)
        Chem.WedgeMolBonds(draw, draw.GetConformer())
        out = {}
        for b in draw.GetBonds():
            d = b.GetBondDir()
            if d == Chem.BondDir.BEGINWEDGE:
                out[b.GetIdx()] = 'wedge'
            elif d == Chem.BondDir.BEGINDASH:
                out[b.GetIdx()] = 'dash'
        return out

    def _label(self, atom, points, show_carbons, hydrogens):
        sym, i = atom.GetSymbol(), atom.GetIdx()
        q = atom.GetFormalCharge()
        if sym == 'C' and not (show_carbons or q or atom.GetDegree() == 0):
            return None
        h = 0 if hydrogens else atom.GetTotalNumHs()
        hpart = ('H' + (str(h).translate(SUB) if h > 1 else '')) if h else ''
        charge = '' if not q else (('' if abs(q) == 1 else str(abs(q))) + ('+' if q > 0 else '-')).translate(SUP)
        p = points[i]
        dx = sum((points[nb.GetIdx()] - p)[0] for nb in atom.GetNeighbors())
        if atom.GetDegree():
            h_first = bool(hpart) and dx > .05
        else:                                          # a lone hydride: H2O, H2S, HCl but NH3, CH4
            h_first = bool(hpart) and sym in ('O', 'S', 'F', 'Cl', 'Br', 'I')
        words = (hpart + sym if h_first else sym + hpart) + charge
        size = self.text_size
        label = m.Text(words, font=FONT, font_size=size, color=COLOUR.get(sym, WHITE))
        start = len(hpart) if h_first else 0
        core = m.VGroup(*label[start:start + len(sym)])
        label.shift(p - core.get_center())
        return label

    @staticmethod
    def _exit(p, u, label, pad=.07):
        """Distance from p along u to the edge of the label's box, plus a little air."""
        if label is None:
            return 0.0
        c, half = label.get_center(), np.array([label.width / 2, label.height / 2])
        best = np.inf
        for axis in (0, 1):
            if abs(u[axis]) > 1e-6:
                for edge in (c[axis] - half[axis], c[axis] + half[axis]):
                    t = (edge - p[axis]) / u[axis]
                    if t > 0:
                        best = min(best, t)
        return (0.0 if best == np.inf else best) + pad

    def _bond(self, p1, p2, order, label1, label2, ring, wedge, color=WHITE):
        u = _unit(p2 - p1)
        length = np.linalg.norm(p2 - p1)
        g1, g2 = self._exit(p1, u, label1), self._exit(p2, -u, label2)
        if g1 + g2 > length * .8:                      # crowded: keep at least a short visible bond
            g1, g2 = g1 * length * .8 / (g1 + g2), g2 * length * .8 / (g1 + g2)
        a = p1 + u * g1
        b = p2 - u * g2
        n = _v(-u[1], u[0])
        width = 4
        line = lambda s, e: m.Line(s, e, color=color, stroke_width=width)  # noqa: E731
        d = self.bond_length * .1
        if wedge == 'wedge':
            w = self.bond_length * .1
            return m.VGroup(m.Polygon(a, b + n * w, b - n * w, color=color, fill_color=color, fill_opacity=1,
                                      stroke_width=1))
        if wedge == 'dash':
            group = m.VGroup()
            for k in range(1, 8):
                t = k / 7
                c = a + (b - a) * t
                w = self.bond_length * .1 * t
                group.add(m.Line(c - n * w, c + n * w, color=color, stroke_width=width * .7))
            return group
        if order == 1:
            return m.VGroup(line(a, b))
        if order == 3:
            return m.VGroup(line(a, b), line(a + n * d * 1.3, b + n * d * 1.3), line(a - n * d * 1.3, b - n * d * 1.3))
        if ring is not None:                          # main line plus a shorter inner line toward the ring centre
            side = 1 if np.dot(ring - (a + b) / 2, n) > 0 else -1
            trim = (b - a) * .15
            inner = line(a + trim + n * side * d * 1.6, b - trim + n * side * d * 1.6)
            if order == 1.5:
                inner = m.DashedLine(inner.get_start(), inner.get_end(), color=color, stroke_width=width)
            return m.VGroup(line(a, b), inner)
        return m.VGroup(line(a + n * d, b + n * d), line(a - n * d, b - n * d))


def curly_arrow(start, end, bend=1, color=AMBER, width=4):
    """A curly (electron-pair) arrow from start to end, bowed up the screen (bend=-1: down); full head."""
    p0, p1 = np.array(start, dtype=float), np.array(end, dtype=float)
    d = p1 - p0
    length = np.linalg.norm(d)
    if length < .05:
        raise ValueError('curly arrow endpoints are too close')
    nrm = _v(-d[1], d[0]) / length
    if nrm[1] < 0:
        nrm = -nrm
    lift = max(.45, .45 * length) * bend
    c0, c1 = p0 + d * .15 + nrm * lift, p0 + d * .85 + nrm * lift
    path = m.CubicBezier(p0, c0, c1, p1, color=color, stroke_width=width)
    t = _unit(p1 - c1)
    side = _v(-t[1], t[0])
    head = m.Polygon(p1, p1 - t * .2 + side * .1, p1 - t * .2 - side * .1, color=color, fill_color=color,
                     fill_opacity=1, stroke_width=1)
    return m.VGroup(path, head)


def _row(items, center, width, gap=.45):
    """Arrange molecules and text left to right, centred; shrink to the width."""
    group = m.VGroup(*items)
    group.arrange(m.RIGHT, buff=gap)
    for item in items:
        item.set_y(0)
    group.move_to(center)
    if group.width > width:
        group.scale(width / group.width)
    return group


def _written(specs):
    """One figure writes all its carbons (CH3-CH2-OH) or none: all when every molecule is small and has no ring."""
    mols = [_parse(x) for x in specs]
    return 'all' if all(mm.GetNumHeavyAtoms() <= SMALL and not mm.GetRingInfo().NumRings() for mm in mols) else 'none'


def _plus(size=40):
    return m.Text('+', font=FONT, font_size=size, color=WHITE)


def reaction(reactants, products, conditions='', below='', center=(0, -.2, 0), width=12, bond=None, balanced=False):
    """Reactants -> products as structures, checked (SMILES validity, optional atom balance) by figure_library.
    Conditions over the arrow (formula subscripts applied). Returns a VGroup with .reactants, .products, .arrow."""
    spec = {'type': 'reaction', 'reactants': [{'smiles': _smiles(r)} for r in reactants],
            'products': [{'smiles': _smiles(p)} for p in products], 'conditions': conditions, 'below': below,
            'balanced': balanced}
    errors = _chem.figure_errors(spec)
    if errors:
        raise ValueError('; '.join(errors))
    carbons = _written(list(reactants) + list(products))
    left = [Molecule(r, bond=bond, carbons=carbons) for r in reactants]
    right = [Molecule(p, bond=bond, carbons=carbons) for p in products]
    over = m.Text(formula_text(conditions), font=FONT, font_size=24, color=AMBER) if conditions else None
    under = m.Text(formula_text(below), font=FONT, font_size=22, color=GREY) if below else None
    length = max(1.6, (max(over.width if over else 0, under.width if under else 0)) + .4)
    arrow = m.Arrow(_v(-length / 2, 0), _v(length / 2, 0), buff=0, color=WHITE, stroke_width=5)
    items = []
    for k, mol in enumerate(left):
        items += ([_plus()] if k else []) + [mol]
    items.append(arrow)
    for k, mol in enumerate(right):
        items += ([_plus()] if k else []) + [mol]
    group = _row(items, center, width)
    if over:
        over.scale(arrow.width / length if arrow.width < length else 1).next_to(arrow, m.UP, buff=.12)
        group.add(over)
    if under:
        under.scale(arrow.width / length if arrow.width < length else 1).next_to(arrow, m.DOWN, buff=.12)
        group.add(under)
    group.reactants, group.products, group.arrow = left, right, arrow
    return group


# ------------------------------------------------------------------ mechanisms and resonance (morphs)
def _procrustes(target, source):
    """Rotation (reflection allowed) of centred source points that best matches centred target points."""
    t = target - target.mean(axis=0)
    s = source - source.mean(axis=0)
    if len(s) < 2 or np.linalg.norm(t) < 1e-6:
        return np.eye(2)
    u, _, vt = np.linalg.svd(s.T @ t)
    return u @ vt


def _links(species, arrows, following):
    """For every atom of every next-stage species: (source species, source atom index) in this stage."""
    from rdkit import Chem
    mols = [_organic._mapped(s) for s in species]
    offsets = np.cumsum([0] + [mm.GetNumAtoms() for mm in mols])
    where = lambda g: (int(np.searchsorted(offsets, g, side='right') - 1),  # noqa: E731
                       int(g - offsets[np.searchsorted(offsets, g, side='right') - 1]))
    result = _organic.pushed(species, arrows)
    frags, mapping = [], []
    pieces = Chem.GetMolFrags(result, asMols=True, sanitizeFrags=False, frags=frags, fragsMolAtomMapping=mapping)
    used, links = set(), []
    for smiles in following:
        target = _organic._mapped(smiles)
        key = _organic._canonical(target)
        for f, piece in enumerate(pieces):
            if f in used or _organic._canonical(piece) != key:
                continue
            link = _match(target, piece, mapping[f])
            if link is None:
                continue
            used.add(f)
            links.append({j: where(g) for j, g in link.items()})
            break
        else:
            raise ValueError(f'could not follow the atoms into {smiles}')
    return links


def _strip_h(mol):
    """The molecule without hydrogen atoms, and the original index of each atom kept."""
    from rdkit import Chem
    keep = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() != 1]
    rw = Chem.RWMol(mol)
    for i in sorted((a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1), reverse=True):
        rw.RemoveAtom(i)
    return rw.GetMol(), keep


def _match(target, piece, mapping):
    """Target atom index -> combined stage index, preferring matches that keep the atom numbers."""
    from rdkit import Chem
    for heavy_only in (False, True):
        t, p, t_idx, p_idx = target, piece, list(range(target.GetNumAtoms())), list(range(piece.GetNumAtoms()))
        if heavy_only:
            (t, t_idx), (p, p_idx) = _strip_h(target), _strip_h(piece)
        if t.GetNumAtoms() != p.GetNumAtoms():
            continue
        matches = t.GetSubstructMatches(p, uniquify=False, maxMatches=500, useChirality=False)
        if not matches:
            continue
        maps_t = [target.GetAtomWithIdx(k).GetAtomMapNum() for k in t_idx]
        maps_p = [piece.GetAtomWithIdx(k).GetAtomMapNum() for k in p_idx]
        best = max(matches, key=lambda mt: sum(1 for qi, ti in enumerate(mt) if maps_p[qi] and maps_p[qi] == maps_t[ti]))
        return {t_idx[ti]: mapping[p_idx[qi]] for qi, ti in enumerate(best)}
    return None


class _Stage:
    def __init__(self, molecules, center, width, scale=1.0):
        self.molecules = molecules
        items, self.pluses = [], m.VGroup()
        for k, mol in enumerate(molecules):
            if k:
                plus = _plus()
                self.pluses.add(plus)
                items.append(plus)
            items.append(mol)
        group = m.VGroup(*items).arrange(m.RIGHT, buff=.45)
        for item in items:
            item.set_y(0)
        group.scale(scale)
        self.group = _row(items, center, width)


def _morph(scene, a, b, links, extra_out=(), run_time=2.0):
    """Animate stage a into stage b: every atom label and kept bond moves to its new place, broken bonds fade,
    new bonds grow. links[t][j] = (s, i): atom j of b's species t came from atom i of a's species s."""
    anims, kept_labels, kept_bonds = [], set(), set()
    for t, mb in enumerate(b.molecules):
        link = links[t]
        for j, lb in mb.labels.items():
            s, i = link.get(j, (None, None))
            la = a.molecules[s].labels.get(i) if s is not None else None
            if la is not None:
                anims.append(m.ReplacementTransform(la, lb))
                kept_labels.add((s, i))
            else:
                anims.append(m.FadeIn(lb))
        for key, bmob in mb.bond_mobs.items():
            j1, j2 = tuple(key)
            (s1, i1), (s2, i2) = link.get(j1, (None, 0)), link.get(j2, (None, 1))
            amob = a.molecules[s1].bond_mobs.get(frozenset((i1, i2))) if s1 is not None and s1 == s2 else None
            if amob is not None:
                anims.append(m.ReplacementTransform(amob, bmob))
                kept_bonds.add((s1, frozenset((i1, i2))))
            else:
                anims.append(m.Create(bmob))
        if hasattr(mb, 'lone_pair_group'):
            anims.append(m.FadeIn(mb.lone_pair_group))
    for s, ma in enumerate(a.molecules):
        anims += [m.FadeOut(lab) for i, lab in ma.labels.items() if (s, i) not in kept_labels]
        anims += [m.FadeOut(bm) for key, bm in ma.bond_mobs.items() if (s, key) not in kept_bonds]
        if hasattr(ma, 'lone_pair_group'):
            anims.append(m.FadeOut(ma.lone_pair_group))
    anims += [m.FadeOut(p) for p in a.pluses] + [m.FadeIn(p) for p in b.pluses]
    anims += [m.FadeOut(x) for x in extra_out]
    scene.play(*anims, run_time=run_time)
    family = set()
    for g in [a.group, b.group, *extra_out]:
        family.update(g.get_family())
    for mob in list(scene.mobjects):
        if mob in family:
            scene.remove(mob)
    scene.add(b.group)


class Mechanism:
    """A curly-arrow mechanism, one stage on screen at a time.

    stages: [{'species': ['[OH-:1]', '[CH3:2][Br:3]'], 'arrows': [{'from': [1], 'to': [1, 2]},
              {'from': [2, 3], 'to': [3]}], 'label': 'slow'}, ..., {'species': [products]}].
    from [a]: a lone pair on atom a; from [a, b]: the bond a-b; to [a, x]: a new or stronger bond; to [b]: a lone
    pair on b. Code pushes the electrons and each stage must be exactly the next (else ValueError, before drawing).
    stage(k) -> VGroup to show; arrows(k) -> VGroup of curly arrows; play_step(scene, k) morphs stage k into k+1
    (fading stage k's arrows); label(k) -> Text of stage k's arrow label or None."""

    def __init__(self, stages, center=(0, -.3, 0), width=11.5, bond=None, carbons='auto', lone_pairs=False, scale=1.4):
        errors = _organic.mechanism_errors({'stages': stages})
        if errors:
            raise ValueError('; '.join(errors))
        self.spec = stages
        if carbons == 'auto':
            carbons = _written([s for st in stages for s in st['species']])
        self.links, self.stages = [], []
        previous = None
        for k, stage in enumerate(stages):
            mols = []
            if k:
                links = _links(stages[k - 1]['species'], stages[k - 1]['arrows'], stage['species'])
                self.links.append(links)
            for t, smiles in enumerate(stage['species']):
                coords = None
                if previous is not None:
                    probe = _organic._mapped(smiles)
                    source = _layout(probe)
                    link = self.links[-1][t]
                    known = [j for j in range(probe.GetNumAtoms()) if j in link]
                    target = np.array([previous.molecules[link[j][0]].point(link[j][1], True)[:2] for j in known])
                    if len(known) >= 2:
                        coords = (source - source.mean(axis=0)) @ _procrustes(target, source[known])
                mols.append(Molecule(smiles, bond=bond, carbons=carbons, lone_pairs=lone_pairs, coords=coords))
            previous = _Stage(mols, center, width, scale)
            self.stages.append(previous)
        self.arrow_groups = [self._arrows(k) for k in range(len(stages))]

    def _arrows(self, k):
        stage, group = self.stages[k], m.VGroup()
        where = {}
        for mol in stage.molecules:
            for num, i in mol.numbers.items():
                where[num] = (mol, i)
        for arrow in self.spec[k].get('arrows') or []:
            src, dst = arrow['from'], arrow['to']
            if len(src) == 1:
                mol, i = where[src[0]]
                start = mol.lone_pair_point(i, True)
            else:
                start = (where[src[0]][0].point(where[src[0]][1], True) + where[src[1]][0].point(where[src[1]][1], True)) / 2
            if len(dst) == 1:
                mol, i = where[dst[0]]
                end = mol.lone_pair_point(i, True)
            else:
                (m0, i0), (m1, i1) = where[dst[0]], where[dst[1]]
                p0, p1 = m0.point(i0, True), m1.point(i1, True)
                if m0 is m1 and m0.mol.GetBondBetweenAtoms(i0, i1) is not None:
                    end = (p0 + p1) / 2
                else:
                    far = p1 if dst[0] in src else p0
                    near = p0 if dst[0] in src else p1
                    end = far + _unit(near - far) * stage.molecules[0].text_size / 26 * .45
            group.add(curly_arrow(start, end))
        return group

    def stage(self, k):
        return self.stages[k].group

    def arrows(self, k):
        return self.arrow_groups[k]

    def label(self, k, size=26):
        text = self.spec[k].get('label')
        return m.Text(text, font=FONT, font_size=size, color=GREY) if text else None

    def play_step(self, scene, k, run_time=2.0):
        """Morph stage k (on screen) into stage k+1; stage k's curly arrows fade as the bonds move."""
        _morph(scene, self.stages[k], self.stages[k + 1], self.links[k], [self.arrow_groups[k]], run_time)


class Resonance:
    """Resonance structures on one shared layout (same atoms in the same order; only double bonds and charges move),
    checked by figure_library. form(k) -> Molecule; row() -> all forms side by side with double-headed arrows;
    play_to(scene, a, b) morphs form a (on screen) into form b in place."""

    def __init__(self, structures, center=(0, -.2, 0), bond=None, carbons='auto', lone_pairs=False, scale=1.2):
        errors = _chem.figure_errors({'type': 'resonance', 'structures': [_smiles(s) for s in structures]})
        if errors:
            raise ValueError('; '.join(errors))
        first = _parse(structures[0], as_written=True)
        coords = _layout(first)
        if carbons == 'auto':
            carbons = _written([first_smiles for first_smiles in [_smiles(structures[0])]])
        self.center, self.bond = center, bond
        self.forms = [Molecule(s, center=center, bond=bond, carbons=carbons, lone_pairs=lone_pairs, coords=coords,
                               as_written=True) for s in structures]
        self.stages = [_Stage([f], center, 99, scale) for f in self.forms]

    def form(self, k):
        return self.forms[k]

    def row(self, width=12, center=None):
        items = []
        for k, f in enumerate(self.forms):
            copy = f.copy()
            if k:
                items.append(m.DoubleArrow(_v(-.6, 0), _v(.6, 0), buff=0, color=WHITE, stroke_width=4))
            items.append(copy)
        return _row(items, self.center if center is None else center, width)

    def play_to(self, scene, a, b, run_time=1.5):
        n = self.forms[a].mol.GetNumAtoms()
        _morph(scene, self.stages[a], self.stages[b], [{j: (0, j) for j in range(n)}], [], run_time)


def _redraw(mob, parts):
    """Replace a turning object's drawing in place. Manim draws the parts that existed when an animation began, so
    swapping in new parts each frame leaves the first picture behind; become() keeps the same parts and moves them."""
    if not mob.submobjects:
        mob.add(*parts)
    else:
        mob.become(m.VGroup(*parts))


# ------------------------------------------------------------------ 3D (projected) and VSEPR
VSEPR = {(2, 0): 'linear', (3, 0): 'trigonal planar', (3, 1): 'bent', (4, 0): 'tetrahedral',
         (4, 1): 'trigonal pyramidal', (4, 2): 'bent', (5, 0): 'trigonal bipyramidal', (5, 1): 'see-saw',
         (5, 2): 'T-shaped', (5, 3): 'linear', (6, 0): 'octahedral', (6, 1): 'square pyramidal',
         (6, 2): 'square planar'}
IDEAL_ANGLE = {2: '180°', 3: '120°', 4: '109.5°', 5: '90° and 120°', 6: '90°'}


def _slots(n):
    """Electron-domain directions for n domains; lone pairs take the first slots (VSEPR: equatorial in a trigonal
    bipyramid, trans in an octahedron, the top of a tetrahedron)."""
    r = math.sqrt(8 / 9)
    if n == 2:
        return [(1, 0, 0), (-1, 0, 0)]
    if n == 3:
        return [(0, 1, 0), (math.cos(math.radians(210)), math.sin(math.radians(210)), 0),
                (math.cos(math.radians(330)), math.sin(math.radians(330)), 0)]
    if n == 4:
        return [(0, 1, 0)] + [(r * math.cos(math.radians(a)), -1 / 3, r * math.sin(math.radians(a)))
                              for a in (90, 210, 330)]
    if n == 5:
        return [(math.cos(math.radians(a)), 0, math.sin(math.radians(a))) for a in (90, 210, 330)] + \
            [(0, 1, 0), (0, -1, 0)]
    if n == 6:
        return [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]
    raise ValueError('VSEPR covers 2-6 electron domains')


def vsepr(spec):
    """VSEPR for a central-atom molecule: {'central', 'bond_pairs', 'lone_pairs', 'domains', 'shape', 'angle'}.
    Multiple bonds count as one domain; lone pairs are computed from the central atom's electrons."""
    mol = _parse(spec)
    centre = max(mol.GetAtoms(), key=lambda a: a.GetDegree() + a.GetTotalNumHs())
    others = [a for a in mol.GetAtoms() if a.GetIdx() != centre.GetIdx()]
    if any(a.GetDegree() != 1 for a in others):
        raise ValueError(f'{spec}: VSEPR needs one central atom with every other atom bonded only to it')
    bonded = centre.GetDegree() + centre.GetTotalNumHs()
    lone = max(0, _organic._lone_electrons(centre) // 2)
    domains = bonded + lone
    if (domains, lone) not in VSEPR:
        raise ValueError(f'{spec}: {domains} domains with {lone} lone pairs is outside Class 11 VSEPR')
    return {'central': centre.GetSymbol(), 'bond_pairs': bonded, 'lone_pairs': lone, 'domains': domains,
            'shape': VSEPR[(domains, lone)], 'angle': IDEAL_ANGLE[domains]}


def _geometry(spec, hydrogens=True, ideal=None):
    """(elements, coords n x 3 centred, bonds [(i, j, order)], lone-pair directions [(atom, unit vector)])."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = _parse(spec)
    shape = None
    if ideal is None:
        try:
            shape = vsepr(spec)
        except ValueError:
            shape = None
    elif ideal:
        shape = vsepr(spec)
    if shape:
        mol = Chem.AddHs(mol, explicitOnly=False)
        centre = max(mol.GetAtoms(), key=lambda a: a.GetDegree()).GetIdx()
        slots = [np.array(s, dtype=float) for s in _slots(shape['domains'])]
        lone_dirs = slots[:shape['lone_pairs']]
        coords = np.zeros((mol.GetNumAtoms(), 3))
        free = iter(slots[shape['lone_pairs']:])
        for nb in mol.GetAtomWithIdx(centre).GetNeighbors():
            length = .75 if nb.GetAtomicNum() == 1 else 1.0
            coords[nb.GetIdx()] = next(free) * length
        lone = [(centre, d) for d in lone_dirs]
    else:
        mol = Chem.AddHs(mol) if hydrogens else mol
        if AllChem.EmbedMolecule(mol, randomSeed=11) != 0:
            raise ValueError(f'{spec}: RDKit could not build 3D coordinates')
        try:
            AllChem.MMFFOptimizeMolecule(mol)
        except Exception:                                          # noqa: BLE001 - keep the embedded geometry
            pass
        conf = mol.GetConformer()
        coords = np.array([list(conf.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]) / RDKIT_BOND
        lone = []
        for atom in mol.GetAtoms():
            pairs = 0 if atom.GetAtomicNum() in (1, 6) else max(0, _organic._lone_electrons(atom) // 2)
            if pairs and atom.GetDegree() and str(atom.GetHybridization()) == 'SP3':
                vecs = [_unit(coords[nb.GetIdx()] - coords[atom.GetIdx()]) for nb in atom.GetNeighbors()]
                s = -_unit(sum(vecs))
                if pairs == 1:
                    lone.append((atom.GetIdx(), s))
                elif pairs == 2 and len(vecs) == 2:
                    perp = _unit(np.cross(vecs[0], vecs[1]))
                    for sign in (1, -1):
                        lone.append((atom.GetIdx(), _unit(s * .58 + perp * sign * .82)))
        if not hydrogens:
            pass
    coords = coords - coords.mean(axis=0)
    elements = [a.GetSymbol() for a in mol.GetAtoms()]
    bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), b.GetBondTypeAsDouble()) for b in mol.GetBonds()]
    return elements, coords, bonds, lone


class Molecule3D(m.VGroup):
    """A ball-and-stick model, projected (scenes are 2D) and redrawn as it turns.

    Geometry: ideal VSEPR directions for a central-atom molecule (CH4, NH3, H2O, BF3, PCl5, SF6, XeF4 ...), with
    lone-pair lobes; otherwise RDKit's 3D structure (ETKDG + MMFF). Turn it with self.play(mol.angle.animate.
    set_value(...)) (degrees about the vertical axis); mol.tilt (degrees) leans it toward the viewer.
    shape is the VSEPR result or None."""

    def __init__(self, spec, center=(0, 0, 0), size=1.4, hydrogens=True, lone_pairs=True, labels=True, angle=25,
                 tilt=15, ideal=None):
        super().__init__()
        self.elements, self.xyz, self.bond_list, self.lone = _geometry(spec, hydrogens, ideal)
        try:
            self.shape = vsepr(spec) if ideal is not False else None
        except ValueError:
            self.shape = None
        self.center_point, self.size, self.show_lone, self.show_labels = np.array(center, float), size, lone_pairs, labels
        self.angle, self.tilt = m.ValueTracker(angle), m.ValueTracker(tilt)
        self._draw()
        self.add_updater(lambda mob: mob._draw())

    def _project(self, p):
        a, t = math.radians(self.angle.get_value()), math.radians(self.tilt.get_value())
        x, y, z = p
        x, z = x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)
        y, z = y * math.cos(t) - z * math.sin(t), y * math.sin(t) + z * math.cos(t)
        return self.center_point + _v(x, y) * self.size, z

    def _draw(self):
        projected = [self._project(p) for p in self.xyz]
        items = []
        for i, j, order in self.bond_list:
            (pi, zi), (pj, zj) = projected[i], projected[j]
            mid = (pi + pj) / 2
            u = _unit(pj - pi)
            n = _v(-u[1], u[0]) * .06 * self.size
            offsets = [0] if order < 1.5 else ([-.5, .5] if order < 2.5 else [-1, 0, 1])
            for o in offsets:
                for (s, e, el) in ((pi, mid, self.elements[i]), (mid, pj, self.elements[j])):
                    items.append(((zi + zj) / 2 - .05, m.Line(s + n * o, e + n * o, stroke_width=7,
                                                               color=COLOUR.get(el, WHITE))))
        if self.show_lone:
            for atom, d in self.lone:
                p, z = projected[atom]
                tip, _ = self._project(self.xyz[atom] + np.array(d) * .75)
                v = tip - p
                length = max(np.linalg.norm(v), .12 * self.size)
                lobe = m.Ellipse(width=length, height=.32 * self.size, stroke_width=1.5, color=CYAN,
                                 fill_color=CYAN, fill_opacity=.22)
                lobe.rotate(math.atan2(v[1], v[0])).move_to(p + v / 2)
                depth = self._project(self.xyz[atom] + np.array(d) * .5)[1]
                items.append((depth, lobe))
        for i, (p, z) in enumerate(projected):
            el = self.elements[i]
            r = BALL.get(el, .85) * .28 * self.size * (1 + .1 * z)
            ball = m.Circle(radius=r, stroke_width=2, stroke_color=GREY, fill_color=COLOUR.get(el, WHITE),
                            fill_opacity=1).move_to(p)
            shine = m.Circle(radius=r * .35, stroke_width=0, fill_color=WHITE, fill_opacity=.35).move_to(
                p + _v(-.3, .3) * r)
            parts = [ball, shine]
            if self.show_labels and el != 'H':
                parts.append(m.Text(el, font=FONT, font_size=max(14, 40 * r), color='#0B1220').move_to(p))
            items.append((z, m.VGroup(*parts)))
        items.sort(key=lambda it: it[0])
        _redraw(self, [mob for _, mob in items])

    def caption(self, size=26, color=GREY):
        """'NH₃: trigonal pyramidal' (VSEPR shape computed), or the formula."""
        from rdkit.Chem.rdMolDescriptors import CalcMolFormula
        words = formula_text(CalcMolFormula(_parse_elements(self.elements)))
        if self.shape:
            words += f': {self.shape["shape"]}'
        return m.Text(words, font=FONT, font_size=size, color=color)


def _parse_elements(elements):
    from rdkit import Chem
    mol = Chem.RWMol()
    for el in elements:
        mol.AddAtom(Chem.Atom(el))
    mol = mol.GetMol()
    mol.UpdatePropertyCache(strict=False)
    for a in mol.GetAtoms():
        a.SetNoImplicit(True)
    return mol


# ------------------------------------------------------------------ conformations
def _conformation_name(front, back, dihedral):
    d = round(dihedral) % 360
    if d % 60:
        return ''
    big = front[0] != 'H' and back[0] != 'H'
    if big:
        return {0: 'fully eclipsed', 60: 'gauche', 120: 'eclipsed', 180: 'anti', 240: 'eclipsed', 300: 'gauche'}[d]
    return 'staggered' if d % 120 == 60 else 'eclipsed'


class Newman(m.VGroup):
    """A Newman projection that can turn: self.play(n.dihedral.animate.set_value(180)). front/back: three groups
    each (formulas, e.g. ['CH3', 'H', 'H']); dihedral: degrees between the first front and first back group. The
    caption names the conformation (staggered, eclipsed; anti, gauche, fully eclipsed when the first groups are not
    H), computed from the angle; it is blank between named angles."""

    def __init__(self, front, back, dihedral=60, center=(0, 0, 0), size=1.0, caption=True, kind='newman'):
        super().__init__()
        for side, groups in (('front', front), ('back', back)):
            if len(groups) != 3:
                raise ValueError(f'Newman: give 3 {side} groups')
        self.front, self.back, self.kind = list(front), list(back), kind
        self.center_point, self.size, self.show_caption = np.array(center, float), size, caption
        self.dihedral = m.ValueTracker(dihedral)
        self._draw()
        self.add_updater(lambda mob: mob._draw())

    def conformation(self):
        return _conformation_name(self.front, self.back, self.dihedral.get_value())

    def _draw(self):
        c, s, d = self.center_point, self.size, self.dihedral.get_value()
        parts = []
        txt = lambda w, p, col: m.Text(formula_text(w), font=FONT, font_size=30 * s, color=col).move_to(p)  # noqa: E731
        if self.kind == 'newman':
            ring, bond = .75 * s, 1.45 * s
            parts.append(m.Circle(radius=ring, color=WHITE, stroke_width=4).move_to(c))
            eclipsed = round(d) % 120 == 0
            for k, g in enumerate(self.back):
                a = math.radians(90 - (d + 120 * k) - (8 if eclipsed else 0))
                u = _v(math.cos(a), math.sin(a))
                parts += [m.Line(c + u * ring, c + u * bond, color=CYAN, stroke_width=4), txt(g, c + u * (bond + .3 * s), CYAN)]
            for k, g in enumerate(self.front):
                a = math.radians(90 - 120 * k)
                u = _v(math.cos(a), math.sin(a))
                parts += [m.Line(c, c + u * (bond - .25 * s), color=WHITE, stroke_width=4),
                          txt(g, c + u * (bond + .05 * s), WHITE)]
            parts.append(m.Dot(c, radius=.05 * s, color=WHITE))
        else:                                                    # sawhorse: front lower left, back upper right
            f, b, bond = c + _v(-.55, -.45) * s, c + _v(.55, .45) * s, .9 * s
            parts.append(m.Line(f, b, color=WHITE, stroke_width=4))
            for centre, groups, offset, col in ((b, self.back, d, CYAN), (f, self.front, 0, WHITE)):
                for k, g in enumerate(groups):
                    a = math.radians(90 - (offset + 120 * k))
                    u = _v(math.cos(a), math.sin(a) * .8)
                    parts += [m.Line(centre, centre + u * bond, color=col, stroke_width=4),
                              txt(g, centre + u * (bond + .28 * s), col)]
        if self.show_caption and self.conformation():
            parts.append(m.Text(self.conformation(), font=FONT, font_size=26 * s, color=GREY).move_to(c + _v(0, -2.35 * s)))
        _redraw(self, parts)


def Sawhorse(front, back, dihedral=60, center=(0, 0, 0), size=1.0, caption=True):
    """The same conformation as a sawhorse projection (turns the same way: s.dihedral)."""
    return Newman(front, back, dihedral, center, size, caption, kind='sawhorse')


class Chair(m.VGroup):
    """Cyclohexane chair from a real 3D chair (three pairs of parallel bonds by construction). substituents:
    [{'carbon': 1-6, 'position': 'axial' | 'equatorial', 'group': 'CH3'}]. Animate the ring flip with
    self.play(c.flip.animate.set_value(1)): the ring inverts, every axial group becomes equatorial and back, and a
    group pointing up still points up. caption() names each group's position, computed for the current side."""

    def __init__(self, substituents, center=(0, 0, 0), size=1.0, numbers=False):
        super().__init__()
        errors = _organic.chair_errors({'substituents': substituents})
        if errors:
            raise ValueError('; '.join(errors))
        self.subs, self.center_point, self.size, self.show_numbers = substituents, np.array(center, float), size, numbers
        self.flip = m.ValueTracker(0)
        self._draw()
        self.add_updater(lambda mob: mob._draw())

    def positions(self):
        """The substituents as they are now (after a completed flip, axial and equatorial swapped)."""
        return self.subs if self.flip.get_value() < .5 else _organic.flipped(self.subs)

    @staticmethod
    def _frame(pucker):
        out = []
        for k in range(6):
            a = math.radians(60 * k)
            sign = 1 if k % 2 == 0 else -1
            out.append((np.array([math.cos(a), .25 * sign * pucker, math.sin(a)]), sign * pucker))
        return out

    def _dirs(self, k, pucker, position):
        p, s = self._frame(pucker)[k]
        up = 1 if s >= 0 else -1
        if position == 'axial':
            return np.array([0, .7 * up, 0])
        return np.array([p[0] * .7, -.15 * up, p[2] * .7])

    def _draw(self):
        t = self.flip.get_value()
        pucker = 1 - 2 * t
        frame = self._frame(pucker)
        proj = lambda p: self.center_point + _v(p[0], p[1] + p[2] * .3) * 1.5 * self.size  # noqa: E731
        parts = []
        for k in range(6):
            parts.append(m.Line(proj(frame[k][0]), proj(frame[(k + 1) % 6][0]), color=WHITE, stroke_width=4))
        if self.show_numbers:
            for k in range(6):
                p = frame[k][0]
                parts.append(m.Text(str(k + 1), font=FONT, font_size=18 * self.size, color=GREY).move_to(
                    proj(p * .78)))
        flipped = _organic.flipped(self.subs)
        for before, after in zip(self.subs, flipped):
            k = before['carbon'] - 1
            d0 = self._dirs(k, 1, before['position'])
            d1 = self._dirs(k, -1, after['position'])
            d = d0 * (1 - t) + d1 * t
            start = frame[k][0]
            end = start + d
            col = AMBER if before['group'] != 'H' else GREY
            parts.append(m.Line(proj(start), proj(end), color=col, stroke_width=4))
            tip = proj(end) + _unit(proj(end) - proj(start)) * .28 * self.size
            parts.append(m.Text(formula_text(before['group']), font=FONT, font_size=26 * self.size, color=col).move_to(tip))
        _redraw(self, parts)

    def caption(self, size=24):
        words = ', '.join(f'{formula_text(s["group"])} {s["position"]}' for s in self.positions() if s['group'] != 'H')
        return m.Text(words, font=FONT, font_size=size, color=GREY)


# ------------------------------------------------------------------ Fischer and Haworth projections
GROUP_SMILES = {'H': '[H]', 'OH': 'O', 'HO': 'O', 'NH2': 'N', 'H2N': 'N', 'CH3': 'C', 'H3C': 'C', 'CHO': 'C=O',
                'COOH': 'C(=O)O', 'HOOC': 'C(=O)O', 'CH2OH': 'CO', 'HOCH2': 'CO', 'Cl': 'Cl', 'Br': 'Br',
                'C2H5': 'CC', 'CN': 'C#N', 'SH': 'S', 'CH2SH': 'CS', 'CH2C6H5': 'Cc1ccccc1', 'C6H5': 'c1ccccc1',
                'CH(CH3)2': 'C(C)C', 'COO-': 'C(=O)[O-]', 'NH3+': '[NH3+]', 'C=O': None}
FISCHER = {
    'D-glyceraldehyde': ('CHO', [('H', 'OH')], 'CH2OH'), 'L-glyceraldehyde': ('CHO', [('HO', 'H')], 'CH2OH'),
    'D-glucose': ('CHO', [('H', 'OH'), ('HO', 'H'), ('H', 'OH'), ('H', 'OH')], 'CH2OH'),
    'D-galactose': ('CHO', [('H', 'OH'), ('HO', 'H'), ('HO', 'H'), ('H', 'OH')], 'CH2OH'),
    'D-mannose': ('CHO', [('HO', 'H'), ('HO', 'H'), ('H', 'OH'), ('H', 'OH')], 'CH2OH'),
    'D-fructose': ('CH2OH', ['C=O', ('HO', 'H'), ('H', 'OH'), ('H', 'OH')], 'CH2OH'),
    'D-ribose': ('CHO', [('H', 'OH'), ('H', 'OH'), ('H', 'OH')], 'CH2OH'),
    '2-deoxy-D-ribose': ('CHO', [('H', 'H'), ('H', 'OH'), ('H', 'OH')], 'CH2OH'),
    'L-alanine': ('COOH', [('H2N', 'H')], 'CH3'), 'D-alanine': ('COOH', [('H', 'NH2')], 'CH3'),
    'L-serine': ('COOH', [('H2N', 'H')], 'CH2OH'), 'L-cysteine': ('COOH', [('H2N', 'H')], 'CH2SH'),
    'L-phenylalanine': ('COOH', [('H2N', 'H')], 'CH2C6H5'), 'L-valine': ('COOH', [('H2N', 'H')], 'CH(CH3)2'),
    'D-lactic acid': ('COOH', [('H', 'OH')], 'CH3'), 'L-lactic acid': ('COOH', [('HO', 'H')], 'CH3'),
}


def _fragment(group):
    from rdkit import Chem
    if group not in GROUP_SMILES or GROUP_SMILES[group] is None:
        raise ValueError(f'group "{group}" is not one of {[g for g, s in GROUP_SMILES.items() if s]}')
    params = Chem.SmilesParserParams()
    params.removeHs = False
    return Chem.MolFromSmiles(GROUP_SMILES[group], params)


def _tag_from_local(mol, centre, neighbours):
    """The chiral tag of `centre` when its neighbours sit at the given 3D directions (others anywhere)."""
    from rdkit import Chem, Geometry
    probe = Chem.Mol(mol)
    conf = Chem.Conformer(probe.GetNumAtoms())
    for i in range(probe.GetNumAtoms()):
        conf.SetAtomPosition(i, Geometry.Point3D(10 + i, 10 + 2 * i, 10 + 3 * i))
    conf.SetAtomPosition(centre, Geometry.Point3D(0, 0, 0))
    for atom, d in neighbours.items():
        conf.SetAtomPosition(atom, Geometry.Point3D(*map(float, d)))
    conf.Set3D(True)
    probe.RemoveAllConformers()
    probe.AddConformer(conf, assignId=True)
    Chem.AssignStereochemistryFrom3D(probe, confId=conf.GetId(), replaceExistingTags=True)
    return probe.GetAtomWithIdx(centre).GetChiralTag()


def _finish(mol, tags):
    from rdkit import Chem
    from rdkit.Chem import rdCIPLabeler
    for i, tag in tags.items():
        mol.GetAtomWithIdx(i).SetChiralTag(tag)
    out = mol.GetMol()
    Chem.SanitizeMol(out)
    Chem.AssignStereochemistry(out, cleanIt=True, force=True)
    rdCIPLabeler.AssignCIPLabels(out)
    return out


def _fischer_mol(top, rows, bottom):
    """The molecule a Fischer projection shows (horizontal bonds toward the viewer, vertical away), with its
    stereocentres set from that geometry; returns (mol, chain carbon index per row)."""
    from rdkit import Chem
    mol = Chem.RWMol()
    chain = []
    for row in rows:
        c = mol.AddAtom(Chem.Atom(6))
        if chain:
            mol.AddBond(chain[-1], c, Chem.BondType.SINGLE)
        chain.append(c)
        if row == 'C=O':
            o = mol.AddAtom(Chem.Atom(8))
            mol.AddBond(c, o, Chem.BondType.DOUBLE)

    def attach(carbon, group):
        frag = _fragment(group)
        base = mol.GetNumAtoms()
        for a in frag.GetAtoms():
            new = Chem.Atom(a.GetAtomicNum())
            new.SetFormalCharge(a.GetFormalCharge())
            new.SetIsAromatic(a.GetIsAromatic())
            mol.AddAtom(new)
        for b in frag.GetBonds():
            mol.AddBond(base + b.GetBeginAtomIdx(), base + b.GetEndAtomIdx(), b.GetBondType())
        mol.AddBond(carbon, base, Chem.BondType.SINGLE)
        return base

    up = {0: attach(chain[0], top)}
    down = {len(rows) - 1: attach(chain[-1], bottom)}
    sides = {}
    for k, row in enumerate(rows):
        if row != 'C=O':
            sides[k] = (attach(chain[k], row[0]), attach(chain[k], row[1]))
    tmp = mol.GetMol()
    tmp.UpdatePropertyCache(strict=False)
    Chem.SanitizeMol(tmp)
    tags = {}
    for k, row in enumerate(rows):
        if row == 'C=O':
            continue
        above = chain[k - 1] if k else up[0]
        below = chain[k + 1] if k < len(rows) - 1 else down[len(rows) - 1]
        left, right = sides[k]
        tags[chain[k]] = _tag_from_local(tmp, chain[k], {above: (0, 1, -1), below: (0, -1, -1),
                                                          left: (-1, 0, 1), right: (1, 0, 1)})
    return _finish(mol, tags), chain


class Fischer(m.VGroup):
    """A Fischer projection. Either name= one of FISCHER (D-glucose, D-fructose, D-ribose, L-alanine ...) or top,
    rows [(left, right) | 'C=O'], bottom. Code builds the molecule from the projection's geometry and computes
    configuration ('D'/'L', from the lowest stereocentre's OH or NH2), cip ({carbon number: 'R'/'S'}, the top
    group is C1) and smiles."""

    def __init__(self, name=None, top=None, rows=None, bottom=None, center=(0, 0, 0), size=1.0, labels=False):
        super().__init__()
        if name is not None:
            if name not in FISCHER:
                raise ValueError(f'Fischer name must be one of {list(FISCHER)}')
            top, rows, bottom = FISCHER[name]
        self.name, self.top, self.rows, self.bottom = name, top, list(rows), bottom
        self.mol, chain = _fischer_mol(top, self.rows, bottom)
        from rdkit import Chem
        self.smiles = Chem.MolToSmiles(self.mol)
        self.cip = {k + 2: self.mol.GetAtomWithIdx(c).GetProp('_CIPCode')                # carbon numbers: top is C1
                    for k, c in enumerate(chain) if self.mol.GetAtomWithIdx(c).HasProp('_CIPCode')}
        self.configuration = None
        for row in reversed(self.rows):
            if row != 'C=O' and any(g in ('OH', 'HO', 'NH2', 'H2N') for g in row) and 'H' in row:
                self.configuration = 'D' if row[1] in ('OH', 'NH2') else 'L'
                break
        c, s = np.array(center, float), size
        gap = .9 * s
        top_y = c[1] + gap * (len(self.rows) + 1) / 2
        txt = lambda w, p, col=WHITE: m.Text(formula_text(w), font=FONT, font_size=30 * s, color=col).move_to(p)  # noqa: E731
        ys = [top_y - gap * (k + 1) for k in range(len(self.rows))]
        self.add(txt(top, c + _v(0, top_y - c[1] + .05)), txt(bottom, _v(c[0], ys[-1] - gap + .05, )))
        self.add(m.Line(_v(c[0], top_y - .25 * s), _v(c[0], ys[-1] - gap + .25 * s), color=WHITE, stroke_width=4))
        for k, (row, y) in enumerate(zip(self.rows, ys)):
            if row == 'C=O':
                self.add(m.Line(_v(c[0], y), _v(c[0] + .55 * s, y), color=WHITE, stroke_width=4).shift(_v(0, .05)),
                         m.Line(_v(c[0], y), _v(c[0] + .55 * s, y), color=WHITE, stroke_width=4).shift(_v(0, -.05)),
                         txt('O', _v(c[0] + .8 * s, y), RED))
                continue
            self.add(m.Line(_v(c[0] - .7 * s, y), _v(c[0] + .7 * s, y), color=WHITE, stroke_width=4))
            for g, x in ((row[0], c[0] - 1.05 * s), (row[1], c[0] + 1.05 * s)):
                self.add(txt(g, _v(x, y), RED if g in ('OH', 'HO') else CYAN if g in ('NH2', 'H2N') else WHITE))
            if labels and (k + 2) in self.cip:
                self.add(m.Text(f'({self.cip[k + 2]})', font=FONT, font_size=20 * s, color=AMBER).move_to(
                    _v(c[0] + .25 * s, y + .25 * s)))


HAWORTH = {'glucose': ('D-glucose', 'pyranose'), 'galactose': ('D-galactose', 'pyranose'),
           'mannose': ('D-mannose', 'pyranose'), 'fructose': ('D-fructose', 'furanose'),
           'ribose': ('D-ribose', 'furanose'), 'deoxyribose': ('2-deoxy-D-ribose', 'furanose')}


def _haworth_spec(sugar, anomer):
    """Ring carbons as (carbon number, up group, down group), anomeric carbon first, from the sugar's Fischer
    projection (D-series): a group on the right points down, on the left up; the ring closes through the last
    stereocentre's OH, whose carbon keeps the chain end (CH2OH) up; alpha puts the anomeric OH trans to that CH2OH
    (down), beta cis (up). Aldoses: the anomeric carbon is C1 (Fischer's top CHO); ketoses: C2 (the C=O row)."""
    name, ring = HAWORTH[sugar]
    top, rows, bottom = FISCHER[name]
    ketose = rows[0] == 'C=O'
    oh_up = anomer == 'beta'
    other = _plain(top) if ketose else 'H'
    members = [(2 if ketose else 1, 'OH' if oh_up else other, other if oh_up else 'OH')]
    middle = rows[1:-1] if ketose else rows[:-1]
    first_number = 3 if ketose else 2
    for k, (left, right) in enumerate(middle):
        members.append((first_number + k, _plain(left), _plain(right)))
    members.append((first_number + len(middle), _plain(bottom), 'H'))
    return members


def _plain(group):
    return {'HO': 'OH', 'H2N': 'NH2', 'HOCH2': 'CH2OH', 'H3C': 'CH3'}.get(group, group)


RING_TEMPLATE = {6: [(1.0, .35), (1.55, -.15), (.75, -.6), (-.75, -.6), (-1.55, -.15), (-1.0, .35)],
                 5: [(0, .45), (1.25, .0), (.7, -.6), (-.7, -.6), (-1.25, .0)]}   # ring O first, then clockwise


class Haworth(m.VGroup):
    """A Haworth projection of glucose, galactose, mannose (pyranose), fructose, ribose or deoxyribose (furanose),
    anomer 'alpha' or 'beta', derived from the sugar's Fischer projection (right -> down, left -> up). Code builds
    the ring molecule from the drawn up/down positions and computes cip ({carbon number: 'R'/'S'}) and smiles."""

    def __init__(self, sugar='glucose', anomer='beta', center=(0, 0, 0), size=1.0):
        super().__init__()
        if sugar not in HAWORTH:
            raise ValueError(f'Haworth sugar must be one of {list(HAWORTH)}')
        if anomer not in ('alpha', 'beta'):
            raise ValueError('anomer must be alpha or beta')
        self.sugar, self.anomer = sugar, anomer
        self.members = _haworth_spec(sugar, anomer)
        n = len(self.members) + 1
        template = RING_TEMPLATE[n]
        self.mol, ring = self._build(self.members, template)
        from rdkit import Chem
        self.smiles = Chem.MolToSmiles(self.mol)
        self.cip = {num: self.mol.GetAtomWithIdx(idx).GetProp('_CIPCode')
                    for (num, _, _), idx in zip(self.members, ring[1:]) if self.mol.GetAtomWithIdx(idx).HasProp('_CIPCode')}
        c, s = np.array(center, float), size
        pts = [c + _v(x, y) * 1.3 * s for x, y in template]
        for k in range(n):
            a, b = pts[k], pts[(k + 1) % n]
            front = a[1] < c[1] - .1 * s and b[1] < c[1] - .1 * s
            self.add(m.Line(a, b, color=WHITE, stroke_width=10 if front else 4))
        self.add(m.Text('O', font=FONT, font_size=30 * s, color=RED).move_to(pts[0]))
        for slot, (num, up, down) in enumerate(self.members, 1):
            p = pts[slot]
            for g, sign in ((up, 1), (down, -1)):
                end = p + _v(0, .65 * sign * s)
                col = RED if g == 'OH' else GREY if g == 'H' else WHITE
                self.add(m.Line(p, end, color=col, stroke_width=3))
                self.add(m.Text(formula_text(g), font=FONT, font_size=24 * s, color=col).move_to(
                    end + _v(0, .2 * sign * s)))

    @staticmethod
    def _build(members, template):
        """Ring O + ring carbons + substituents; each carbon's stereo from the drawing (x right, screen-up = back,
        +y = up), so the molecule is exactly what the projection shows."""
        from rdkit import Chem
        mol = Chem.RWMol()
        ring = [mol.AddAtom(Chem.Atom(8))] + [mol.AddAtom(Chem.Atom(6)) for _ in members]
        n = len(ring)
        for k in range(n):
            mol.AddBond(ring[k], ring[(k + 1) % n], Chem.BondType.SINGLE)
        placed = {}
        for slot, (_, up, down) in enumerate(members, 1):
            for where, g in (('up', up), ('down', down)):
                frag = _fragment(g)
                base = mol.GetNumAtoms()
                for a in frag.GetAtoms():
                    mol.AddAtom(Chem.Atom(a.GetAtomicNum()))
                for b in frag.GetBonds():
                    mol.AddBond(base + b.GetBeginAtomIdx(), base + b.GetEndAtomIdx(), b.GetBondType())
                mol.AddBond(ring[slot], base, Chem.BondType.SINGLE)
                placed[(slot, where)] = base
        tmp = mol.GetMol()
        tmp.UpdatePropertyCache(strict=False)
        Chem.SanitizeMol(tmp)
        space = lambda q: np.array([template[q % n][0], 0.0, -template[q % n][1]])  # noqa: E731
        tags = {}
        for slot in range(1, n):
            here = space(slot)
            near = {ring[(slot - 1) % n]: space(slot - 1) - here, ring[(slot + 1) % n]: space(slot + 1) - here,
                    placed[(slot, 'up')]: np.array([0, 1.0, 0]), placed[(slot, 'down')]: np.array([0, -1.0, 0])}
            tags[ring[slot]] = _tag_from_local(tmp, ring[slot], near)
        return _finish(mol, tags), ring
