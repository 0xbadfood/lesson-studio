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
        self.assertEqual(book_extras.panels_named({'type': 'figure', 'ref': ['Fig. 9.7 (a)'], 'caption': 'Fig. 9.7 (a) and (b)'}), [])

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


class FakePage:
    """A page with a figure and, below-left of it, a box shaded as hundreds of 1-pt strips."""
    width, height = 595, 842
    curves, lines, images = [], [], []

    def __init__(self):
        self.rects = [{'x0': 430, 'top': 515, 'x1': 545, 'bottom': 575}]
        self.rects += [{'x0': 311, 'top': 525 + i * .05, 'x1': 541, 'bottom': 525.5 + i * .05} for i in range(200)]

    def extract_words(self):
        return []

    def extract_text_lines(self):
        return [{'x0': 78, 'top': 527, 'x1': 396, 'bottom': 537, 'text': 'when placed inside the coil (Fig. 12.11). The magnet'}]


class WidenTests(unittest.TestCase):
    def test_a_shaded_band_does_not_pull_body_text_into_a_crop(self):
        # 2026-10-29, jesc1-12 Fig. 12.11: the QUESTIONS box's gradient strips each touched the figure's box
        box = book_extras.widen(FakePage(), (421, 511, 552, 579), set())
        self.assertEqual([round(v) for v in box], [421, 511, 552, 579])


if __name__ == '__main__':
    unittest.main()
