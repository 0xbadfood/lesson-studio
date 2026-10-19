import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))      # the sandbox imports the kits as top-level modules

import chem_kit  # noqa: E402
from scene_check import validate_code  # noqa: E402


class ChemKitTests(unittest.TestCase):
    def test_hydrogen_numbers_follow_ncert(self):
        self.assertAlmostEqual(chem_kit.wavelength_nm(3, 2), 656.3, delta=.2)        # H-alpha, Balmer
        self.assertAlmostEqual(chem_kit.wavelength_nm(2, 1), 121.6, delta=.2)        # Lyman-alpha
        self.assertAlmostEqual(chem_kit.energy_joule(2) / 1e-19, -5.45, places=2)
        self.assertEqual(chem_kit.radius_pm(2), 211.6)
        self.assertEqual(chem_kit.series_name(2), 'Balmer')
        self.assertEqual(chem_kit.region(chem_kit.wavelength_nm(2, 1)), 'ultraviolet')
        with self.assertRaises(ValueError):
            chem_kit.wavelength_nm(2, 3)

    def test_line_colours_follow_the_wavelength(self):
        red, cyan = chem_kit.wavelength_colour(656.3), chem_kit.wavelength_colour(486.1)
        self.assertGreater(int(red[1:3], 16), int(red[5:7], 16))                     # more red than blue
        self.assertGreater(int(cyan[5:7], 16), int(cyan[1:3], 16))

    def test_ladder_labels_never_crowd(self):
        ladder = chem_kit.energy_ladder(levels=(1, 2, 3, 4, 5, 6), bottom=-2.4, top=2.4)
        tags = sorted(t.get_center()[1] for t in ladder if getattr(t, 'tex_string', '').startswith('n='))
        self.assertTrue(all(b - a >= .34 for a, b in zip(tags, tags[1:])), tags)

    def test_scenes_may_import_the_kit(self):
        code = ('import manim as m\nimport numpy as np\nimport math\nfrom scene_kit import begin, at, finish\n'
                'from chem_kit import bohr_atom\n\nclass ChapterScene(m.Scene):\n    def construct(self):\n'
                '        begin(self, "Atom")\n        at(self, 1)\n        self.add(bohr_atom())\n        finish(self, 3)\n')
        validate_code(code)


if __name__ == '__main__':
    unittest.main()
