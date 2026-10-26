"""Book extras: a multi-part figure's crop must hold every part its words name."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import book_extras  # noqa: E402


class FakeModel:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def call(self, name, prompt, **kw):
        self.calls.append((name, prompt))
        return self.answers.pop(0)


class PanelTests(unittest.TestCase):
    def test_names_parts_from_the_figure_words(self):
        block = {'caption': 'Fig. 2.10', 'shows': 'Graph (a) is an x-t plot; (b) a v-t plot; (c) speed; (d) path length.'}
        self.assertEqual(book_extras.panels_named(block), ['a', 'b', 'c', 'd'])
        self.assertEqual(book_extras.panels_named({'caption': 'Fig. 3.1 (a) only'}), [])

    def test_crop_missing_parts_is_recut_then_marked(self):
        block = {'id': 'B82', 'shows': '(a) x-t (b) v-t (c) speed (d) path', 'pages': [13]}
        entry = {'ref': 'Fig. 2.10', 'image': 'figures/Fig._2.10.png', 'caption': 'Fig. 2.10'}
        recuts = []
        real = book_extras.cut_figure
        book_extras.cut_figure = lambda *a, **k: recuts.append(a[-1] if len(a) > 7 else k.get('hint')) or True
        try:
            model = FakeModel([{'visible': ['c', 'd']}, {'visible': ['c', '(d)']}])
            book_extras.check_panels(model, None, 'x.pdf', Path('/tmp'), block, entry, set(), log=lambda *_: None)
        finally:
            book_extras.cut_figure = real
        self.assertEqual(entry['panels_missing'], ['a', 'b'])
        self.assertTrue(entry['suspect'])
        self.assertIn('left out (a), (b)', recuts[0])

    def test_a_whole_crop_passes(self):
        entry = {'ref': 'Fig. 4.2', 'image': 'figures/Fig._4.2.png'}
        model = FakeModel([{'visible': ['a', 'b']}])
        book_extras.check_panels(model, None, 'x.pdf', Path('/tmp'), {'shows': '(a) and (b)'}, entry, set(), log=lambda *_: None)
        self.assertEqual(entry['panels_missing'], [])
        self.assertFalse(entry.get('suspect'))


if __name__ == '__main__':
    unittest.main()
