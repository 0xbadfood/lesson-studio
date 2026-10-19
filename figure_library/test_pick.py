import unittest

from figure_library import pick, vet


def record(id, name, description='', labels=(), verdict=None):
    out = {'id': id, 'name': name, 'description': description, 'labels': list(labels), 'categories': [],
           'credit': f'{name}.svg by X, CC0, via Wikimedia Commons'}
    if verdict is not None:
        out['vet'] = verdict
    return out


GOOD = {'usable': True, 'shows': 'Rutherford gold foil experiment: alpha particles scattered by gold foil'}
INDEX = [record('a', 'Rutherford gold foil experiment', 'Alpha particles and gold foil', ['gold foil'], GOOD),
         record('b', 'Gold foil logo', 'A logo', verdict={'usable': False, 'shows': 'A logo'}),
         record('c', 'Cathode ray tube diagram', 'Diagram of a CRT', ['Anode', 'Kathode']),
         record('d', 'Cathode ray tube diagram-ar', 'رسم', ['أنود'])]


class PickTests(unittest.TestCase):
    def test_matching_vetted_figures(self):
        found = pick.candidates("Rutherford's nuclear model: alpha particle scattering by gold foil", index=INDEX)
        self.assertEqual([f['id'] for f in found], ['a'])
        self.assertEqual(found[0]['description'], GOOD['shows'])

    def test_unvetted_figures_need_english_labels(self):
        found = pick.candidates('cathode ray tube discharge', index=INDEX)
        self.assertEqual([f['id'] for f in found], ['c'])

    def test_vetted_figures_with_foreign_svg_text_are_left_out(self):
        blank = record('e', 'Cathode ray tube diagram-te', 'CRT', ['రుణధ్రువం'], {**GOOD, 'shows': 'A cathode ray tube'})
        self.assertEqual(pick.candidates('cathode ray tube', index=[blank]), [])

    def test_weak_matches_are_left_out(self):
        self.assertEqual(pick.candidates('quantum numbers of orbitals', index=INDEX), [])


class VerdictTests(unittest.TestCase):
    def verdict(self, **over):
        return {'shows': 'A distillation set-up', 'kind': 'diagram', 'labels': 'english', 'clean': True,
                'correct': True, 'usable': True, 'reason': '', **over}

    def test_usable_never_looser_than_the_findings(self):
        self.assertTrue(vet.decide(self.verdict()))
        self.assertFalse(vet.decide(self.verdict(kind='logo')))
        self.assertFalse(vet.decide(self.verdict(labels='other language')))
        self.assertFalse(vet.decide(self.verdict(correct=False)))

    def test_shape(self):
        self.assertEqual(vet.verdict_errors(self.verdict()), [])
        self.assertTrue(vet.verdict_errors(self.verdict(kind='cartoon', clean='yes')))


if __name__ == '__main__':
    unittest.main()
