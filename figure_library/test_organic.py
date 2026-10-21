import unittest

from figure_library import chem, organic

SN2 = {'type': 'mechanism', 'stages': [
    {'species': ['[OH-:1]', '[CH3:2][Br:3]'], 'arrows': [{'from': [1], 'to': [1, 2]}, {'from': [2, 3], 'to': [3]}]},
    {'species': ['[OH:1][CH3:2]', '[Br-:3]']}]}
E2 = {'type': 'mechanism', 'stages': [
    {'species': ['[OH-:1]', '[H:2][CH2:3][CH2:4][Br:5]'],
     'arrows': [{'from': [1], 'to': [1, 2]}, {'from': [2, 3], 'to': [3, 4]}, {'from': [4, 5], 'to': [5]}]},
    {'species': ['[H:2][OH:1]', '[CH2:3]=[CH2:4]', '[Br-:5]']}]}


class MechanismTests(unittest.TestCase):
    def test_code_pushes_the_electrons(self):
        self.assertEqual(chem.figure_errors(SN2), [])
        self.assertEqual(chem.figure_errors(E2), [])
        self.assertEqual(organic.push(['[OH-:1]', '[CH3:2][Br:3]'], SN2['stages'][0]['arrows']), ['CO', '[Br-]'])

    def test_a_wrong_mechanism_is_caught(self):
        no_leaving = {'type': 'mechanism', 'stages': [{**SN2['stages'][0], 'arrows': SN2['stages'][0]['arrows'][:1]},
                                                     SN2['stages'][1]]}
        self.assertIn('impossible structure', chem.figure_errors(no_leaving)[0])      # a five-bonded carbon
        wrong_product = {'type': 'mechanism', 'stages': [SN2['stages'][0],
                                                        {'species': ['[OH:1][CH2:2]', '[Br-:3]']}]}
        self.assertIn('these arrows make', chem.figure_errors(wrong_product)[0])
        backwards = {'type': 'mechanism', 'stages': [{'species': SN2['stages'][0]['species'],
                                                     'arrows': [{'from': [2], 'to': [2, 1]}]}, SN2['stages'][1]]}
        self.assertIn('no lone pair', chem.figure_errors(backwards)[0])               # carbon has none to give
        self.assertIn('not in this stage', chem.figure_errors(
            {'type': 'mechanism', 'stages': [{'species': ['[OH-:1]', 'CBr'], 'arrows': [{'from': [1], 'to': [1, 2]}]},
                                             SN2['stages'][1]]})[0])

    def test_mechanisms_draw(self):
        self.assertEqual(chem.draw(SN2).count("stroke='#f3b85e'"), 2)               # two curly arrows


class ProjectionTests(unittest.TestCase):
    BUTANE = {'type': 'newman', 'front': ['CH3', 'H', 'H'], 'back': ['CH3', 'H', 'H'], 'dihedral': 180}

    def test_code_names_the_conformation(self):
        self.assertEqual(chem.figure_errors({**self.BUTANE, 'conformation': 'anti'}), [])
        self.assertIn('not anti', chem.figure_errors({**self.BUTANE, 'dihedral': 60, 'conformation': 'anti'})[0])
        self.assertEqual(chem.figure_errors({**self.BUTANE, 'dihedral': 60, 'conformation': 'gauche'}), [])
        self.assertEqual(organic._caption({**self.BUTANE, 'dihedral': 0}), 'eclipsed')
        self.assertIn('3 groups', chem.figure_errors({**self.BUTANE, 'front': ['CH3', 'H']})[0])
        for kind in ('newman', 'sawhorse'):
            self.assertIn('<svg', chem.draw({**self.BUTANE, 'type': kind}))

    def test_the_ring_flip_is_computed(self):
        subs = [{'carbon': 1, 'position': 'equatorial', 'group': 'CH3'}]
        self.assertEqual(organic.flipped(subs), [{'carbon': 1, 'position': 'axial', 'group': 'CH3'}])
        self.assertIn('two axial', chem.figure_errors({'type': 'chair', 'substituents': [
            {'carbon': 2, 'position': 'axial', 'group': 'CH3'}, {'carbon': 2, 'position': 'axial', 'group': 'Cl'}]})[0])
        self.assertIn('<svg', chem.draw({'type': 'chair', 'substituents': subs, 'flip': True}))

    def test_chair_bonds_come_in_parallel_pairs(self):
        points = [p[0] for p in organic._chair_points()]
        bond = lambda k: (points[(k + 1) % 6][0] - points[k][0], points[(k + 1) % 6][1] - points[k][1])  # noqa: E731
        for k in range(3):
            (ax, ay), (bx, by) = bond(k), bond(k + 3)
            self.assertAlmostEqual(ax * by - ay * bx, 0, places=6)


if __name__ == '__main__':
    unittest.main()
