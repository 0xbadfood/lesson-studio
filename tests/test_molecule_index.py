import unittest

from kb_research import molecule_index as mi


class Parse(unittest.TestCase):
    def test_noble_gas_compounds_parse_and_other_valence_errors_do_not(self):
        # 2026-11-06, Chemical Bonding: RDKit has no valence for krypton, so KrF2 could never pass and the run stopped
        kr = mi.parse('F[Kr]F')
        self.assertEqual(mi.structure_formula(kr), ({'F': 2, 'Kr': 1}, 0))
        self.assertEqual(mi.book_formula('KrF2'), mi.structure_formula(kr))
        self.assertIsNotNone(mi.parse('F[Xe](F)(F)F'))
        self.assertIsNone(mi.parse('C(C)(C)(C)(C)C'))

    def test_expanded_octets_parse_by_electron_count(self):
        # 2026-11-06, Chemical Bonding: RDKit's valence table refuses ClF3, BrF5 and IF7, which the book draws
        for smiles, formula in (('FCl(F)F', 'ClF3'), ('FBr(F)(F)(F)F', 'BrF5'), ('F[I](F)(F)(F)(F)(F)F', 'IF7'),
                                ('O=[Cl]=O', 'ClO2')):
            mol = mi.parse(smiles)
            self.assertIsNotNone(mol, smiles)
            self.assertEqual(mi.structure_formula(mol), mi.book_formula(formula), smiles)
        self.assertIsNone(mi.parse('F[Cl](F)(F)(F)(F)(F)(F)F'))    # eight bonds need more than chlorine's seven
        self.assertIsNone(mi.parse('FCl(F)FC(C)(C)(C)C'))          # the carbon is still checked by RDKit
        self.assertIsNone(mi.parse('[Ne][Ne]'))                    # period 2: no expanded octet

    def test_deuterium_counts_as_d(self):
        # 2026-11-06, Hydrogen: D2, HD and ND3 were set aside, counted as H2 and NH3
        for smiles, formula in (('[2H][2H]', 'D2'), ('[2H][H]', 'HD'), ('[2H]N([2H])[2H]', 'ND3'), ('[2H]N', 'NH2D'),
                                ('[3H][H]', 'HT')):
            self.assertEqual(mi.structure_formula(mi.parse(smiles)), mi.book_formula(formula), smiles)

    def test_errors_accept_krypton_difluoride(self):
        result = {'molecules': [{'name': 'krypton difluoride', 'formula': 'KrF2', 'smiles': 'F[Kr]F', 'kind': 'molecule',
                                 'blocks': ['B1']}]}
        self.assertEqual(mi.errors(result, {'B1'}), [])

    def test_a_species_still_wrong_on_the_last_try_is_set_aside_not_fatal(self):
        # 2026-11-06, Chemical Bonding: He2 and Ne2 (bond order zero) cannot be SMILES, and stopped the whole run
        result = {'molecules': [{'name': 'Ne2', 'formula': 'Ne2', 'smiles': '[Ne][Ne]', 'kind': 'molecule', 'blocks': ['B1']},
                                {'name': 'water', 'formula': 'H2O', 'smiles': 'O', 'kind': 'molecule', 'blocks': ['B1']}]}
        self.assertTrue(mi.errors(result, {'B1'}))
        rejected = []
        kept = mi.keep_good(result, {'B1'}, rejected)
        self.assertEqual([m['name'] for m in kept['molecules']], ['water'])
        self.assertEqual(rejected[0]['name'], 'Ne2')
        self.assertIn('does not parse', rejected[0]['problems'][0])


if __name__ == '__main__':
    unittest.main()
