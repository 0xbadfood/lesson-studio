"""Book extras: a multi-part figure's crop must hold every part its words name."""
import sys
import re
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
        # words placed along each line in proportion to their characters: runs of spaces become wide gaps
        out = []
        for l in self.extract_text_lines():
            per = (l['x1'] - l['x0']) / len(l['text'])
            for m in re.finditer(r'\S+', l['text']):
                out.append({'x0': l['x0'] + m.start() * per, 'x1': l['x0'] + m.end() * per, 'top': l['top'], 'bottom': l['bottom'],
                            'text': m.group()})
        return out

    def extract_text_lines(self):
        return [{'x0': 78, 'top': 527, 'x1': 396, 'bottom': 537, 'text': 'when placed inside the coil (Fig. 12.11). The magnet'}]


class WidenTests(unittest.TestCase):
    def test_a_shaded_band_does_not_pull_body_text_into_a_crop(self):
        # 2026-10-29, jesc1-12 Fig. 12.11: the QUESTIONS box's gradient strips each touched the figure's box
        box = book_extras.widen(FakePage(), (421, 511, 552, 579), set())
        self.assertEqual([round(v) for v in box], [421, 511, 552, 579])

    def test_a_paragraphs_last_line_is_not_taken_into_a_crop(self):
        # 2026-10-30, keph1-06 Fig. 6.21(a): the model's box began on "magnetic field.", a paragraph's short last line
        page = FakePage()
        page.rects = []
        page.images = [{'x0': 364, 'top': 560, 'x1': 561, 'bottom': 706}]
        page.extract_text_lines = lambda: [
            {'x0': 356, 'top': 562, 'x1': 584, 'bottom': 572, 'text': "a couple acting on the needle due to the earth's"},
            {'x0': 356, 'top': 574, 'x1': 427, 'bottom': 584, 'text': 'magnetic field.'},
            {'x0': 400, 'top': 640, 'x1': 430, 'bottom': 650, 'text': 'lid'}]
        box = book_extras.widen(page, (380, 575, 578, 703), set())
        self.assertGreater(box[1], 584 + book_extras.PAD)  # the tail is cut off, padding and all
        self.assertLessEqual(box[1], 600)               # the drawing below it stays
        self.assertGreaterEqual(box[3], 703)

    def test_part_labels_across_a_figure_stay(self):
        # 2026-10-30: a first try at trimming cut iesc1-05 Fig. 5.23's "(a) (b) (c)" and lebo1-04 Fig. 4.17's labels
        page = FakePage()
        page.rects = []
        page.extract_text_lines = lambda: [
            {'x0': 110, 'top': 585, 'x1': 540, 'bottom': 597, 'text': '(a)              (b)              (c)'},
            {'x0': 90, 'top': 600, 'x1': 520, 'bottom': 612, 'text': 'Tall stature              Short stature and feminine'}]
        box = book_extras.widen(page, (80, 400, 560, 615), set())
        self.assertEqual([round(v) for v in box], [80, 400, 560, 615])

    def test_the_next_columns_text_beside_a_figure_stays_out_of_the_trim(self):
        # 2026-10-30, kemh1-09 Fig. 9.18: a body line in the next column, overlapping the box's edge, cut off the x-axis
        page = FakePage()
        page.rects = []
        page.extract_text_lines = lambda: [
            {'x0': 20, 'top': 590, 'x1': 300, 'bottom': 602, 'text': 'the line meets the axis at a point we call the intercept'}]
        box = book_extras.widen(page, (280, 400, 560, 615), set())
        self.assertEqual([round(v) for v in box], [280, 400, 560, 615])

    def test_a_charts_months_and_an_axis_numbers_stay(self):
        # 2026-10-30: a third try cut a climate chart's month row and the lanthanide plot's atomic numbers
        page = FakePage()
        page.rects = []
        page.extract_text_lines = lambda: [
            {'x0': 90, 'top': 590, 'x1': 540, 'bottom': 602, 'text': 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'},
            {'x0': 90, 'top': 603, 'x1': 540, 'bottom': 614, 'text': '57 59 61 63 65 67 69 71 Atomic number'}]
        box = book_extras.widen(page, (80, 400, 560, 615), set())
        self.assertEqual([round(v) for v in box], [80, 400, 560, 615])

    def test_a_label_merged_with_the_next_columns_text_stays(self):
        # 2026-10-30, leph2-06 Fig. 14.12: the diode's "p n" labels and the next column's body text read as one line
        page = FakePage()
        page.rects = []
        page.extract_text_lines = lambda: [
            {'x0': 153, 'top': 573, 'x1': 540, 'bottom': 585, 'text': 'p                n                bias). The equilibrium barrier potential'}]
        box = book_extras.widen(page, (76, 465, 252, 600), set())
        self.assertEqual([round(v) for v in box], [76, 465, 252, 600])


if __name__ == '__main__':
    unittest.main()
