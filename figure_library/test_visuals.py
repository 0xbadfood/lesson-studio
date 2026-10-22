import tempfile
import unittest
from pathlib import Path

from figure_library import visuals


def member(key, chapter, concepts, name='Human heart, section', ref='Fig. 15.2', book='kebo1', subject='biology'):
    return {'key': key, 'chapter': chapter, 'class': 11, 'concepts': concepts, 'figure_ref': ref, 'beyond_book': False,
            'name': name, 'book': book, 'subject': subject}


class RegistryTests(unittest.TestCase):
    def test_merge_places_every_need_once_with_a_known_asset(self):
        keys = ['kebo1-15:N2', 'jesc1-05:N4']
        good = {'groups': [{'name': 'Human heart, section', 'kind': 'structure', 'members': keys,
                            'asset': 'biology:heart-section'}]}
        known = visuals.assets('biology')
        self.assertEqual(visuals.merge_errors(good, keys, known), [])
        self.assertIn('missing', visuals.merge_errors({'groups': [{**good['groups'][0], 'members': keys[:1]}]}, keys, known)[0])
        self.assertIn('asset must be', visuals.merge_errors(
            {'groups': [{**good['groups'][0], 'asset': 'biology:kidney'}]}, keys, known)[0])

    def test_a_library_svg_that_cites_the_book_figure_is_matched_by_code(self):
        self.assertEqual(visuals.cited_by_library(member('kebo1-15:N2', 'kebo1-15', ['C6'])), ['biology:heart-section'])
        self.assertEqual(visuals.cited_by_library(member('kebo1-15:N9', 'kebo1-15', ['C5'], ref='')), [])
        # Fig. 15.4 is cited by two SVGs: the closest name wins; the model's choice only breaks a tie
        cited = visuals.cited_by_library(member('kebo1-15:N4', 'kebo1-15', ['C9'], ref='Fig. 15.4'))
        self.assertIn('biology:double-circulation', cited)
        titles = visuals.assets('biology')
        self.assertEqual(visuals.choose_asset('human double circulation', cited, None, titles), 'biology:double-circulation')
        self.assertEqual(visuals.choose_asset('human double circulation', cited, 'biology:blood-vessels', titles),
                         'biology:double-circulation')
        self.assertEqual(visuals.choose_asset('x', cited, 'biology:blood-vessels', titles), 'biology:blood-vessels')

    def test_store_and_search(self):
        entries = [{'name': 'Human heart, section', 'kind': 'structure', 'subject': 'biology',
                    'shows': 'the four chambers and valves', 'parts': ['right atrium', 'aorta'], 'stages': [],
                    'motions': ['highlight', 'labels'], 'status': 'have', 'asset': 'biology:heart-section',
                    'commons': [], 'members': [member('kebo1-15:N2', 'kebo1-15', ['C6', 'C10']),
                                               member('jesc1-05:N4', 'jesc1-05', ['C3'], book='jesc1')]},
                   {'name': 'Cathode ray tube', 'kind': 'apparatus', 'subject': 'chemistry', 'shows': 'a discharge tube',
                    'parts': ['cathode', 'anode'], 'stages': [], 'motions': ['flow'], 'status': 'to_build',
                    'asset': None, 'commons': [], 'members': [member('kech1-02:N1', 'kech1-02', ['C1'],
                                                                     name='Cathode ray tube', subject='chemistry')]}]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'v.sqlite3'
            visuals.store(entries, db)
            self.assertEqual([e['name'] for e in visuals.search('heart chambers', db=db)], ['Human heart, section'])
            self.assertEqual(visuals.search('heart', db=db)[0]['reuse'], 2)
            self.assertEqual([e['name'] for e in visuals.search(concept='kebo1-15:C10', db=db)], ['Human heart, section'])
            self.assertEqual([e['name'] for e in visuals.search(status='to_build', db=db)], ['Cathode ray tube'])
            self.assertIn('to build: Cathode ray tube', visuals.report(db))


    def test_a_concept_finds_drawn_diagrams_from_other_chapters(self):
        # Mitosis (Ch 10) needs centromeres; the chromosome-structure SVG belongs to the Cell chapter (Ch 8)
        def entry(name, parts, asset, chapter, concepts, status='have'):
            return {'name': name, 'kind': 'structure', 'subject': 'biology', 'shows': name, 'parts': parts,
                    'stages': [], 'motions': ['labels'], 'status': status, 'asset': asset, 'commons': [],
                    'members': [member(f'{chapter}:N1', chapter, concepts, name=name, ref='')]}
        entries = [entry('Mitosis stages', ['chromosomes', 'spindle fibers', 'centromeres'], 'biology:mitosis-stages',
                         'kebo1-10', ['C2']),
                   entry('Chromosome with kinetochore', ['centromere', 'kinetochore', 'sister chromatids', 'chromosome'],
                         'biology:chromosome-structure', 'kebo1-08', ['C16']),
                   entry('Plasma membrane', ['phospholipid', 'protein'], 'biology:plasma-membrane-fluid-mosaic',
                         'kebo1-08', ['C5'])]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'v.sqlite3'
            visuals.store(entries, db)
            self.assertEqual(visuals.related_assets('kebo1-10', 'C2', db=db),
                             ['biology:mitosis-stages', 'biology:chromosome-structure'])
            self.assertEqual(visuals.related_assets('kebo1-10', 'C9', db=db), [])
        self.assertEqual(visuals.related_assets('kebo1-10', 'C2', db=Path('/nowhere.sqlite3')), [])


if __name__ == '__main__':
    unittest.main()
