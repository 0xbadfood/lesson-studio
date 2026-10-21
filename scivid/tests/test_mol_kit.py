import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent)]                      # the sandbox imports the kits as top-level modules

import mol_kit as k  # noqa: E402
from scene_check import validate_code  # noqa: E402

# name -> molecular formula (Hill order, as RDKit writes it), typed independently of the SMILES in NAMES
FORMULAS = {
    'methane': 'CH4', 'ethane': 'C2H6', 'propane': 'C3H8', 'butane': 'C4H10', '2-methylpropane': 'C4H10',
    'pentane': 'C5H12', '2,2-dimethylpropane': 'C5H12', 'hexane': 'C6H14', 'cyclohexane': 'C6H12',
    'ethene': 'C2H4', 'propene': 'C3H6', 'buta-1,3-diene': 'C4H6', 'ethyne': 'C2H2', 'propyne': 'C3H4',
    'benzene': 'C6H6', 'toluene': 'C7H8', 'styrene': 'C8H8', 'naphthalene': 'C10H8', 'o-xylene': 'C8H10',
    'chloromethane': 'CH3Cl', 'dichloromethane': 'CH2Cl2', 'chloroform': 'CHCl3', 'carbon tetrachloride': 'CCl4',
    'iodomethane': 'CH3I', 'bromoethane': 'C2H5Br', '2-bromopropane': 'C3H7Br', 'tert-butyl bromide': 'C4H9Br',
    'chlorobenzene': 'C6H5Cl', 'vinyl chloride': 'C2H3Cl', 'freon-12': 'CCl2F2',
    'methanol': 'CH4O', 'ethanol': 'C2H6O', 'propan-2-ol': 'C3H8O', '2-methylpropan-2-ol': 'C4H10O',
    'ethane-1,2-diol': 'C2H6O2', 'glycerol': 'C3H8O3', 'phenol': 'C6H6O', 'cyclohexanol': 'C6H12O',
    'dimethyl ether': 'C2H6O', 'diethyl ether': 'C4H10O', 'anisole': 'C7H8O',
    'formaldehyde': 'CH2O', 'acetaldehyde': 'C2H4O', 'benzaldehyde': 'C7H6O', 'acetone': 'C3H6O',
    'butanone': 'C4H8O', 'acetophenone': 'C8H8O', 'benzophenone': 'C13H10O', 'formic acid': 'CH2O2',
    'acetic acid': 'C2H4O2', 'benzoic acid': 'C7H6O2', 'oxalic acid': 'C2H2O4', 'acetate': 'C2H3O2-',
    'ethyl acetate': 'C4H8O2', 'acetyl chloride': 'C2H3ClO', 'acetic anhydride': 'C4H6O3', 'acetamide': 'C2H5NO',
    'urea': 'CH4N2O', 'salicylic acid': 'C7H6O3', 'aspirin': 'C9H8O4', 'paracetamol': 'C8H9NO2',
    'methylamine': 'CH5N', 'dimethylamine': 'C2H7N', 'trimethylamine': 'C3H9N', 'aniline': 'C6H7N',
    'nitrobenzene': 'C6H5NO2', 'nitromethane': 'CH3NO2', 'acetonitrile': 'C2H3N', 'benzonitrile': 'C7H5N',
    'glycine': 'C2H5NO2', 'alanine': 'C3H7NO2', 'lactic acid': 'C3H6O3', 'glucose': 'C6H12O6',
    'fructose': 'C6H12O6', 'hydroxide': 'HO-', 'hydronium': 'H3O+', 'ammonium': 'H4N+', 'tert-butyl cation': 'C4H9+',
    'water': 'H2O', 'ammonia': 'H3N', 'carbon dioxide': 'CO2', 'carbon monoxide': 'CO', 'sulfur dioxide': 'O2S',
    'sulfuric acid': 'H2O4S', 'nitric acid': 'HNO3', 'hydrogen chloride': 'HCl', 'boron trifluoride': 'BF3',
    'beryllium chloride': 'BeCl2', 'phosphorus pentachloride': 'Cl5P', 'sulfur hexafluoride': 'F6S',
    'sulfur tetrafluoride': 'F4S', 'chlorine trifluoride': 'ClF3', 'xenon difluoride': 'F2Xe',
    'xenon tetrafluoride': 'F4Xe', 'bromine pentafluoride': 'BrF5',
}
SN2 = [{'species': ['[OH-:1]', '[CH3:2][Br:3]'], 'arrows': [{'from': [1], 'to': [1, 2]}, {'from': [2, 3], 'to': [3]}]},
       {'species': ['[OH:1][CH3:2]', '[Br-:3]']}]


class ChemistryTests(unittest.TestCase):
    def test_known_names_have_the_right_formula(self):
        from rdkit.Chem.rdMolDescriptors import CalcMolFormula
        for name, formula in FORMULAS.items():
            self.assertEqual(CalcMolFormula(k._parse(name)), formula, name)
        self.assertEqual(k.formula('ethanol'), 'C₂H₆O')
        self.assertEqual(k.molar_mass('ethanol'), 46)
        self.assertEqual(k.molar_mass('chloromethane'), 50.5)                      # Cl 35.5 (NCERT)

    def test_fischer_stereo_matches_the_known_descriptors(self):
        self.assertEqual(k.Fischer('D-glucose').cip, {2: 'R', 3: 'S', 4: 'R', 5: 'R'})   # (2R,3S,4R,5R)
        self.assertEqual(k.Fischer('D-ribose').cip, {2: 'R', 3: 'R', 4: 'R'})
        self.assertEqual(k.Fischer('D-fructose').cip, {3: 'S', 4: 'R', 5: 'R'})
        self.assertEqual(k.Fischer('D-glyceraldehyde').cip, {2: 'R'})
        self.assertEqual((k.Fischer('L-alanine').cip, k.Fischer('L-alanine').configuration), ({2: 'S'}, 'L'))
        self.assertEqual(k.Fischer('L-cysteine').cip, {2: 'R'})                     # the CIP exception
        self.assertEqual(k.Fischer('D-glucose').configuration, 'D')

    def test_haworth_stereo_matches_the_known_descriptors(self):
        # beta-D-glucopyranose (2R,3R,4S,5S,6R)-oxane numbering = sugar C1..C5
        self.assertEqual(k.Haworth('glucose', 'beta').cip, {1: 'R', 2: 'R', 3: 'S', 4: 'S', 5: 'R'})
        self.assertEqual(k.Haworth('glucose', 'alpha').cip, {1: 'S', 2: 'R', 3: 'S', 4: 'S', 5: 'R'})
        self.assertEqual(k.Haworth('ribose', 'beta').cip, {1: 'R', 2: 'R', 3: 'S', 4: 'R'})
        self.assertEqual(k.Haworth('fructose', 'beta').cip, {2: 'R', 3: 'S', 4: 'S', 5: 'R'})

    def test_vsepr_shapes_are_computed(self):
        shapes = {'methane': 'tetrahedral', 'ammonia': 'trigonal pyramidal', 'water': 'bent',
                  'boron trifluoride': 'trigonal planar', 'beryllium chloride': 'linear', 'carbon dioxide': 'linear',
                  'sulfur dioxide': 'bent', 'phosphorus pentachloride': 'trigonal bipyramidal',
                  'sulfur tetrafluoride': 'see-saw', 'chlorine trifluoride': 'T-shaped', 'xenon difluoride': 'linear',
                  'sulfur hexafluoride': 'octahedral', 'bromine pentafluoride': 'square pyramidal',
                  'xenon tetrafluoride': 'square planar', 'ammonium': 'tetrahedral', 'hydronium': 'trigonal pyramidal'}
        for name, shape in shapes.items():
            self.assertEqual(k.vsepr(name)['shape'], shape, name)
        with self.assertRaises(ValueError):
            k.vsepr('ethanol')                                                       # no single central atom

    def test_mechanism_follows_every_atom(self):
        links = k._links(SN2[0]['species'], SN2[0]['arrows'], SN2[1]['species'])
        methanol = k._organic._mapped(SN2[1]['species'][0])
        numbers = {a.GetIdx(): a.GetAtomMapNum() for a in methanol.GetAtoms()}
        self.assertEqual({numbers[j]: s for j, (s, i) in links[0].items()}, {1: 0, 2: 1})   # O from OH-, C from CH3Br
        with self.assertRaises(ValueError):
            k.Mechanism([{**SN2[0], 'arrows': SN2[0]['arrows'][:1]}, SN2[1]])       # Br never leaves


class DrawingTests(unittest.TestCase):
    def test_molecules_and_their_parts(self):
        ethanol = k.Molecule('[CH3:1][CH2:2][OH:3]')
        self.assertEqual(ethanol.lone_pair_count(3), 2)
        self.assertIsNotNone(ethanol.atom(3))
        self.assertEqual(len(ethanol.lone_pairs(3)), 4)                              # two pairs of dots
        self.assertTrue(len(ethanol.highlight('hydroxyl')))
        with self.assertRaises(ValueError):
            ethanol.highlight('ketone')
        with self.assertRaises(ValueError):
            ethanol.point(7)
        chiral = k.Molecule('C[C@H](O)CC')
        label = chiral.stereo()[1]
        self.assertIn(label, ('R', 'S'))
        self.assertEqual(chiral.mirror().stereo()[1], {'R': 'S', 'S': 'R'}[label])   # the enantiomer flips
        self.assertEqual(k.Molecule('cis-but-2-ene').stereo(), {(1, 2): 'Z'})

    def test_everything_builds(self):
        k.Mechanism(SN2)
        k.Resonance(['CC(=O)[O-]', 'CC([O-])=O']).row()
        k.reaction(['acetic acid', 'ethanol'], ['ethyl acetate', 'water'], conditions='conc. H2SO4', balanced=True)
        for name in ('methane', 'sulfur hexafluoride', 'ethanol'):
            k.Molecule3D(name)
        n = k.Newman(['CH3', 'H', 'H'], ['CH3', 'H', 'H'], 180)
        self.assertEqual(n.conformation(), 'anti')
        n.dihedral.set_value(60)
        self.assertEqual(n.conformation(), 'gauche')
        chair = k.Chair([{'carbon': 1, 'position': 'axial', 'group': 'CH3'}])
        chair.flip.set_value(1)
        self.assertEqual(chair.positions()[0]['position'], 'equatorial')
        k.Haworth('deoxyribose', 'beta')

    def test_three_molecular_models(self):
        mol = k.Molecule3D('methane', model='framework')
        self.assertEqual((mol.model_name(), mol._radius('C', 0)), ('framework model', 0))
        mol.model.set_value(1)
        ball = mol._radius('C', 0)
        mol.model.set_value(2)
        self.assertEqual(mol.model_name(), 'space-filling model')
        self.assertAlmostEqual(mol._radius('C', 0), k.VDW['C'] / k.RDKIT_BOND * mol.size)  # van der Waals, to scale
        self.assertGreater(mol._radius('C', 0), 2 * ball)
        mol.model.set_value(1.5)
        self.assertEqual(mol.model_name(), '')
        with self.assertRaises(ValueError):
            k.Molecule3D('methane', model='wireframe')
        self.assertFalse(k.Molecule3D('ethanol').show_lone)                       # lobes only for VSEPR shapes
        self.assertTrue(k.Molecule3D('water').show_lone)

    def test_a_scene_must_fill_the_frame(self):
        from scene_check import geometry_defects
        tiny = {'samples': [{'time': 1, 'labels': [], 'content': [-.6, -.4, .6, .3]}], 'duration': 5, 'elapsed': 5}
        full = {'samples': [{'time': 1, 'labels': [], 'content': [-4, -2, 4, 2]}], 'duration': 5, 'elapsed': 5}
        self.assertIn('fills only 1%', geometry_defects(tiny)[0])
        self.assertEqual(geometry_defects(full), [])

    def test_scenes_may_import_the_kit(self):
        code = ('import manim as m\nfrom scene_kit import begin, at, finish\nfrom mol_kit import Molecule\n\n\n'
                'class ChapterScene(m.Scene):\n    def construct(self):\n        begin(self, "Ethanol")\n'
                '        at(self, 0.5)\n        self.play(m.FadeIn(Molecule("ethanol")))\n        finish(self, 3)\n')
        validate_code(code)


if __name__ == '__main__':
    unittest.main()
