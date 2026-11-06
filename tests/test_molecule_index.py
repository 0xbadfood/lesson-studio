import unittest

from kb_research import molecule_index as mi


class Parse(unittest.TestCase):
    def test_noble_gas_compounds_parse_and_other_valence_errors_do_not(self):
        # 2026-11-06, Chemical Bonding: RDKit has no valence for krypton, so KrF2 could never pass and the run stopped
        kr = mi.parse('F[Kr]F')
        self.assertEqual(mi.structure_formula(kr), ({'F': 2, 'Kr': 1}, 0))
        self.assertEqual(mi.book_formula('KrF2'), mi.structure_formula(kr))
        self.assertIsNotNone(mi.parse('F[Xe](F)(F)F'))
        self.assertIsNone(mi.parse('F[I](F)(F)(F)(F)F'))
        self.assertIsNone(mi.parse('C(C)(C)(C)(C)C'))

    def test_errors_accept_krypton_difluoride(self):
        result = {'molecules': [{'name': 'krypton difluoride', 'formula': 'KrF2', 'smiles': 'F[Kr]F', 'kind': 'molecule',
                                 'blocks': ['B1']}]}
        self.assertEqual(mi.errors(result, {'B1'}), [])


if __name__ == '__main__':
    unittest.main()
