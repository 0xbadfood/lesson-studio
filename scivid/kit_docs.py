"""The coder's instructions for each subject kit. Kept apart from the kits, which import manim: a film worker reads
these without manim installed."""

CHEM = '''CHEMISTRY KIT (exact numbers and shapes; use it instead of computing or drawing these yourself):
from chem_kit import bohr_atom, orbiting, electron, nucleus, photon, energy_ladder, transition_arrow, line_label, \
spectrum_bar, wavelength_nm, wavelength_colour, energy_joule, radius_pm, series_name, region
- bohr_atom(levels=4, center=(x,y,0), scale=.45, law='n', electrons={1:1}) -> VGroup; .orbits[n], .radius(n),
  .center, .electrons. law='n' is not to scale (say so); law='n2' is to scale (r ~ n^2) but needs a small scale.
- orbiting(dot, center, radius, period=4): keeps a dot circling (updater); dot.clear_updaters() before a jump.
- photon(start, direction, nm, length=1.6): wave packet coloured by wavelength; m.Create it or shift it.
- energy_ladder(levels=(1..6), x0, x1, bottom, top) -> VGroup with .y(n), .lines[n]: heights proportional to E_n,
  labels n and E_n in 10^-19 J. transition_arrow(ladder, upper, lower): arrow coloured by the emitted line.
- wavelength_nm(upper, lower) (NCERT R_H = 109677 cm^-1), line_label(upper, lower) -> '656 nm',
  energy_joule(n) = -2.18e-18/n^2 J, radius_pm(n) = 52.9 n^2, series_name(lower) ('Balmer'), region(nm).
- spectrum_bar([(3,2),(4,2),...], x0, x1, y): line spectrum strip with lines at the computed wavelengths.
Every number on screen must come from these functions (format it to the precision the narration speaks).'''

MOL = '''MOLECULE KIT (every structure from RDKit; never draw a molecule, bond, lone pair or arrow yourself):
from mol_kit import Molecule, Mechanism, Resonance, reaction, Molecule3D, vsepr, Newman, Sawhorse, Chair, \\
Fischer, Haworth, curly_arrow, formula, molar_mass, formula_text
- Molecule(spec, center=(x,y,0), bond=None, carbons='auto', hydrogens=False, lone_pairs=False, aromatic='kekule'|
  'circle', angle=0) -> VGroup. spec: a SMILES or a known name ('ethanol', 'acetic acid', 'benzene', 'aspirin',
  'tert-butyl bromide', 'ammonia' ...). Small acyclic molecules write their carbons (CH3-CH2-OH), others are
  skeletal; hydrogens=True draws every H; lone_pairs=True draws each atom's computed lone pairs; wedges and dashes
  come from stereo SMILES (C[C@H](O)CC). Number atoms you refer to ([CH3:1][CH2:2][OH:3]) and use those numbers:
  .point(n), .atom(n) (label or None), .bond(a, b), .bond_point(a, b), .lone_pair_point(n), .lone_pairs(n),
  .lone_pair_count(n), .highlight('hydroxyl'|'carbonyl'|'aldehyde'|'ketone'|'carboxylic acid'|'carboxylate'|
  'ester'|'ether'|'amine'|'amide'|'halide'|'alkene'|'alkyne'|'benzene ring'|'nitrile'|'nitro') -> glow VGroup to
  add behind, .stereo() -> {n: 'R'/'S', (a, b): 'E'/'Z'} and .stereo_labels() -> VGroup, .mirror(center) -> the
  enantiomer, .formula() -> 'C₂H₆O'. formula(spec), molar_mass(spec) (NCERT masses), formula_text('H2SO4').
- Mechanism(stages, center, width=11.5, scale=1.4): stages = [{'species': ['[OH-:1]', '[CH3:2][Br:3]'], 'arrows':
  [{'from': [1], 'to': [1, 2]}, {'from': [2, 3], 'to': [3]}], 'label': 'slow'}, ..., {'species': [products]}].
  from [a] = a lone pair on a; from [a, b] = the bond a-b; to [a, x] = a new or stronger bond; to [b] = a lone pair
  on b. Keep atom numbers across stages and every species (spectators too); write a moving H as [H:5]. The kit
  pushes the electrons and raises if a stage does not make the next. Show: self.play(m.FadeIn(mech.stage(0)));
  self.play(m.Create(mech.arrows(0))); mech.play_step(self, 0, run_time=2) morphs stage 0 into stage 1 (atoms
  move, broken bonds fade, new bonds grow, arrows fade); mech.label(k) -> Text of stage k's label or None.
- Resonance([smiles, ...], center, scale=1.2): same atoms in the same order, only double bonds and charges moved
  (checked). .form(k) -> Molecule; .row(width, center) -> forms side by side with double-headed arrows;
  .play_to(self, a, b, run_time) morphs form a (on screen) into form b.
- reaction(reactants, products, conditions='', below='', center, width, balanced=False) -> VGroup row of
  structures with + and an arrow (balanced=True: code checks atoms).
- Molecule3D(spec, center, size=1.4, model='ball_and_stick'|'framework'|'space_filling', labels=True, angle=25,
  tilt=15) -> a projected 3D model that turns: self.play(mol.angle.animate.set_value(360), run_time=6,
  rate_func=m.linear). Morph between the three models with self.play(mol.model.animate.set_value(2)) (0 framework:
  bonds only; 1 ball-and-stick; 2 space-filling: van der Waals spheres to scale, about twice as wide as the
  ball-and-stick, so give it room or a smaller size); mol.model_name() -> 'space-filling model' at a whole value.
  Central-atom molecules
  (CH4, NH3, H2O, BF3, BeCl2, CO2, SO2, PCl5, SF4, ClF3, XeF2, SF6, BrF5, XeF4, NH4+, H3O+) use ideal VSEPR
  geometry with lone-pair lobes; others RDKit's 3D structure. .caption() -> 'NH₃: trigonal pyramidal'.
  vsepr(spec) -> {'shape', 'bond_pairs', 'lone_pairs', 'domains', 'angle'} (computed; NCERT angles for a molecule
  like NH3 107° or H2O 104.5° must come from the evidence, not from 'angle', which is the ideal domain angle).
- Newman(front, back, dihedral, center, size) / Sawhorse(...): turn with self.play(n.dihedral.animate.set_value(
  180)); the caption names the conformation from the angle (anti, gauche, eclipsed, staggered); n.conformation().
- Chair([{'carbon': 1, 'position': 'equatorial', 'group': 'CH3'}], center, size): ring flip with
  self.play(c.flip.animate.set_value(1)) (axial <-> equatorial computed); c.positions(), c.caption().
- Fischer(name='D-glucose' | 'D-fructose' | 'D-ribose' | '2-deoxy-D-ribose' | 'D-galactose' | 'D-mannose' |
  'D-glyceraldehyde' | 'L-alanine' | 'L-serine' ... or top=, rows=[(left, right) | 'C=O'], bottom=, labels=True for
  R/S): .configuration ('D'/'L'), .cip ({carbon: 'R'/'S'}) computed. Haworth(sugar='glucose'|'galactose'|'mannose'|
  'fructose'|'ribose'|'deoxyribose', anomer='alpha'|'beta', center, size): derived from the Fischer projection; .cip.
- curly_arrow(start, end, bend=1) for an extra electron-pair arrow between kit points (Molecule.point etc.).
Objects that turn (Molecule3D, Newman, Sawhorse, Chair) redraw themselves; add them once, then animate their
trackers. Every name, shape, label and number on a structure must come from these objects. Make the structure the
main thing on screen: large and central in the body area (a scene that fills less than 15% of it is sent back).'''
