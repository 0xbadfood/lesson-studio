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

    def test_highlight_lights_only_the_group(self):
        mol = chem._mol('CCC(=O)OC')                               # methyl propanoate: C(=O)O, not the carbons
        self.assertEqual([mol.GetAtomWithIdx(i).GetSymbol() for i in chem._group_atoms(mol, 'ester')], ['C', 'O', 'O'])
        self.assertEqual(chem.figure_errors({'type': 'molecule', 'smiles': 'CCO', 'highlight': 'hydroxyl'}), [])
        self.assertIn('no ketone', chem.figure_errors({'type': 'molecule', 'smiles': 'CCO', 'highlight': 'ketone'})[0])
        self.assertIn('must be one of', chem.figure_errors({'type': 'molecule', 'smiles': 'CCO', 'highlight': 'x'})[0])

    def test_reaction_checks_structures_and_balance(self):
        sn2 = {'type': 'reaction', 'reactants': [{'smiles': 'CCBr', 'formula': 'C2H5Br'}, {'smiles': '[OH-]'}],
               'products': [{'smiles': 'CCO'}, {'smiles': '[Br-]'}], 'conditions': 'aqueous KOH', 'balanced': True}
        self.assertEqual(chem.figure_errors(sn2), [])
        self.assertIn('atoms differ', chem.figure_errors({**sn2, 'products': [{'smiles': 'CCO'}]})[0])
        self.assertIn('not C2H5Br', chem.figure_errors({**sn2, 'reactants': [{'smiles': 'CCCl', 'formula': 'C2H5Br'}]})[0])
        self.assertTrue(chem.figure_errors({**sn2, 'conditions': 'x' * 41}))

    def test_resonance_structures_only_move_bonds_and_charges(self):
        self.assertEqual(chem.figure_errors({'type': 'resonance', 'structures': ['C1=CC=CC=C1', 'C1C=CC=CC=1']}), [])
        self.assertEqual(chem.figure_errors({'type': 'resonance', 'structures': ['CC(=O)[O-]', 'CC([O-])=O']}), [])
        protonated = chem.figure_errors({'type': 'resonance', 'structures': ['CC(=O)[O-]', 'CC(=O)O']})
        self.assertTrue(any('total charge' in e for e in protonated))
        moved = chem.figure_errors({'type': 'resonance', 'structures': ['C=CC=O', 'C=COC']})
        self.assertTrue(any('same atoms in the same order' in e for e in moved))
        self.assertIn('written the same', chem.figure_errors({'type': 'resonance', 'structures': ['C=CC=O'] * 2})[0])

    def test_formula_counts_are_subscripts(self):
        drawn = chem.formula_text(0, 0, 'conc. H2SO4 at 25 C')
        self.assertEqual(drawn.count("dy='6.5'"), 2)               # the 2 and the 4, not the 25

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
                 {'type': 'spectrum', 'kind': 'hydrogen'}, {'type': 'spectrum', 'kind': 'electromagnetic'},
                 {'type': 'molecule', 'smiles': 'CC(=O)OC', 'highlight': 'ester'},
                 {'type': 'reaction', 'reactants': ['C=C', '[H][H]'], 'products': ['CC'], 'conditions': 'Ni, heat'},
                 {'type': 'resonance', 'structures': ['C=CC=O', '[CH2+]C=C[O-]']}]
        specs += [{'type': 'orbital', 'orbital': o} for o in chem.ORBITALS]
        for spec in specs:
            self.assertIn('<svg', chem.draw(spec), spec)


if __name__ == '__main__':
    unittest.main()
