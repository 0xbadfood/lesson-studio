import unittest

from figure_library import chem


class ConfigurationTests(unittest.TestCase):
    def test_aufbau_and_the_exceptions(self):
        self.assertEqual(chem.config_text(chem.configuration('N')), '1s2 2s2 2p3')
        self.assertEqual(chem.config_text(chem.configuration('Fe')), '1s2 2s2 2p6 3s2 3p6 3d6 4s2')
        self.assertEqual(chem.config_text(chem.configuration('Cr')), '1s2 2s2 2p6 3s2 3p6 3d5 4s1')
        self.assertEqual(chem.config_text(chem.configuration('Cu')), '1s2 2s2 2p6 3s2 3p6 3d10 4s1')
        self.assertEqual(chem.shells(chem.configuration('K')), [2, 8, 8, 1])

    def test_written_configurations(self):
        self.assertEqual(chem.parse_config('[Ne] 3s2 3p4'), {**chem.configuration('Ne'), '3s': 2, '3p': 4})
        self.assertEqual(chem.parse_config('1s^2 2s^{2} 2p^3'), {'1s': 2, '2s': 2, '2p': 3})

    def test_hund_fills_singly_first(self):
        self.assertEqual(chem.hund(3, 3), [1, 1, 1])
        self.assertEqual(chem.hund(4, 3), [2, 1, 1])
        self.assertEqual(chem.hund(10, 5), [2, 2, 2, 2, 2])


class SpectrumTests(unittest.TestCase):
    def test_balmer_lines(self):
        self.assertEqual([round(chem.wavelength_nm(n, 2)) for n in (3, 4, 5, 6)], [656, 486, 434, 410])


class SpecTests(unittest.TestCase):
    def test_molecule_formula_must_match(self):
        self.assertEqual(chem.figure_errors({'type': 'molecule', 'smiles': 'CC(=O)O', 'formula': 'C2H4O2'}), [])
        self.assertIn('C2H6O', chem.figure_errors({'type': 'molecule', 'smiles': 'CCO', 'formula': 'C2H4O2'})[0])
        self.assertTrue(chem.figure_errors({'type': 'molecule', 'smiles': 'C(('}))

    def test_latex_is_maths_only(self):
        self.assertTrue(chem.figure_errors({'type': 'equation', 'latex': r'\input{/etc/passwd}'}))
        self.assertEqual(chem.figure_errors({'type': 'equation', 'latex': r'\ce{H2 + Cl2 -> 2HCl}'}), [])

    def test_bad_specs_are_explained(self):
        self.assertTrue(chem.figure_errors({'type': 'orbital_boxes', 'config': '2p9'}))
        self.assertTrue(chem.figure_errors({'type': 'energy_levels', 'transitions': [[3, 3]]}))
        self.assertTrue(chem.figure_errors({'type': 'orbital', 'orbital': 'f'}))
        self.assertTrue(chem.figure_errors({'type': 'hologram'}))

    def test_every_type_draws(self):
        specs = [{'type': 'equation', 'latex': r'\ce{2H2 + O2 -> 2H2O}'},
                 {'type': 'molecule', 'smiles': 'O'}, {'type': 'bohr', 'element': 'Na'},
                 {'type': 'orbital_boxes', 'element': 'Cr', 'valence_only': True},
                 {'type': 'energy_levels', 'transitions': [[3, 2], [1, 4]]},
                 {'type': 'spectrum', 'kind': 'hydrogen'}, {'type': 'spectrum', 'kind': 'electromagnetic'}]
        specs += [{'type': 'orbital', 'orbital': o} for o in chem.ORBITALS]
        for spec in specs:
            self.assertIn('<svg', chem.draw(spec), spec)


if __name__ == '__main__':
    unittest.main()
