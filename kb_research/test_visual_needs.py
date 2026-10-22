import unittest

import visual_needs as v

BLOCKS = [{'block': 'B22', 'type': 'figure'}, {'block': 'B13', 'type': 'table'}, {'block': 'B5', 'type': 'figure'}]


def need(**change):
    n = {'id': 'N1', 'name': 'Human heart, section', 'kind': 'structure', 'shows': 'the four chambers and the valves',
         'parts': ['right atrium'], 'stages': [], 'motions': ['highlight', 'labels'], 'concepts': ['C6'],
         'blocks': ['B22'], 'figure_ref': 'Fig. 15.2', 'beyond_book': False}
    n.update(change)
    return n


GOOD = {'figures': [{'block': 'B22', 'role': 'teaching', 'need': 'N1'}, {'block': 'B13', 'role': 'data_table', 'need': None},
                    {'block': 'B5', 'role': 'illustration', 'need': None}],
        'needs': [need(), need(id='N2', name='Cardiac conduction', kind='flow', blocks=[], figure_ref='', beyond_book=True,
                                motions=['flow', 'highlight'])]}


class NeedTests(unittest.TestCase):
    def test_a_good_answer_passes(self):
        self.assertEqual(v.need_errors(GOOD, BLOCKS, {'C6'}), [])

    def test_every_block_once_and_the_vocabulary(self):
        missing = {**GOOD, 'figures': GOOD['figures'][:2]}
        self.assertIn('missing [\'B5\']', ' '.join(v.need_errors(missing, BLOCKS, {'C6'})))
        bad = {**GOOD, 'needs': [need(kind='picture', motions=['spin'])] + GOOD['needs'][1:]}
        problems = ' '.join(v.need_errors(bad, BLOCKS, {'C6'}))
        self.assertIn('kind must be', problems)
        self.assertIn('motions from', problems)
        wrong_blocks = {**GOOD, 'needs': [need(blocks=[])] + GOOD['needs'][1:]}
        self.assertIn('exactly the teaching blocks', ' '.join(v.need_errors(wrong_blocks, BLOCKS, {'C6'})))
        three_extra = {**GOOD, 'needs': GOOD['needs'] + [need(id=f'N{k}', blocks=[], figure_ref='', beyond_book=True)
                                                         for k in (3, 4)]}
        self.assertIn('at most 2 beyond_book', ' '.join(v.need_errors(three_extra, BLOCKS, {'C6'})))


if __name__ == '__main__':
    unittest.main()
