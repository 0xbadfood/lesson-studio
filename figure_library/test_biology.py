import tempfile
import unittest
from pathlib import Path

from figure_library import biology

HEART = {'type': 'biology', 'id': 'heart-section', 'highlight': 'part-left-ventricle',
         'labels': ['part-aorta', 'part-right-atrium', 'part-left-ventricle']}


class BiologyTests(unittest.TestCase):
    def test_a_chapter_gets_the_diagrams_its_book_cites(self):
        ids = {c['id'] for c in biology.candidates('kebo1-15', 11)}
        self.assertEqual(ids, {'heart-section', 'double-circulation', 'blood-vessels'})
        heart = next(c for c in biology.candidates('kebo1-15', 11) if c['id'] == 'heart-section')
        self.assertEqual(heart['parts']['part-left-ventricle'], 'Left ventricle')
        stages = next(c for c in biology.candidates('kebo1-10', 11) if c['id'] == 'meiosis-stages')['stages']
        self.assertIn('stage-metaphase-i', [s['id'] for s in stages])

    def test_code_checks_ids_parts_stages_and_level(self):
        self.assertEqual(biology.figure_errors(HEART), [])
        self.assertIn('not in the library', biology.figure_errors({**HEART, 'id': 'kidney'})[0])
        self.assertIn('not labelled parts', biology.figure_errors({**HEART, 'labels': ['part-valve-x']})[0])
        self.assertIn('at most 5', biology.figure_errors({**HEART, 'labels': ['part-aorta'] * 6})[0])
        self.assertIn('stage must be', biology.figure_errors({'id': 'meiosis-stages', 'stage': 'stage-x'})[0])
        self.assertEqual(biology.figure_errors({'id': 'meiosis-stages', 'stage': 'stage-metaphase-i'}), [])
        # the class level: Class 7 sees "Upper right chamber", and level-3 parts are not offered
        self.assertEqual(biology.label({'label': 'Right atrium', 'label_by_level': {'1': 'Upper right chamber'}}, 1),
                         'Upper right chamber')

    def test_the_drawing_has_its_labels_and_no_css_variables(self):
        svg = biology.draw(HEART)
        self.assertNotIn('var(', svg)
        self.assertEqual(svg.count("r='5'"), 3)                                      # three labels, a dot each
        self.assertIn("opacity=\"0.28\"", svg)                                     # the rest dims
        with tempfile.TemporaryDirectory() as tmp:
            biology.png(HEART, Path(tmp) / 'h.png')
            self.assertGreater((Path(tmp) / 'h.png').stat().st_size, 10000)


if __name__ == '__main__':
    unittest.main()
