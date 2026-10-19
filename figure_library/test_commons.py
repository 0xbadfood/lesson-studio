import unittest

from figure_library import commons as c


class LicenceTests(unittest.TestCase):
    def test_usable_with_a_credit(self):
        for name in ('Public domain', 'PD-self', 'CC0', 'CC BY 4.0', 'CC BY 3.0', 'CC-BY 2.5'):
            self.assertTrue(c.allowed(name), name)

    def test_share_alike_and_others_are_not(self):
        for name in ('CC BY-SA 3.0', 'CC BY-SA 4.0', 'CC BY-SA 2.0 uk', 'GFDL', 'LGPL', 'CC BY-NC 4.0', '', None):
            self.assertFalse(c.allowed(name), name)


class RecordTests(unittest.TestCase):
    def page(self, licence='CC BY 4.0', mime='image/svg+xml', size=20_000):
        return {'title': 'File:Cathode ray tube.svg', 'imageinfo': [{
            'mime': mime, 'size': size, 'url': 'https://upload.wikimedia.org/x.svg', 'width': 800, 'height': 400,
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Cathode_ray_tube.svg',
            'extmetadata': {'LicenseShortName': {'value': licence},
                            'Artist': {'value': '<a href="/wiki/User:Kd">Kd</a>'},
                            'ImageDescription': {'value': 'A <b>cathode</b> ray tube &amp; screen'},
                            'Categories': {'value': 'Cathode ray tubes|SVG physics'}}}]}

    def test_a_usable_file_gets_its_credit(self):
        record = c.record_for(self.page(), 'search: cathode ray tube')
        self.assertEqual(record['author'], 'Kd')
        self.assertEqual(record['description'], 'A cathode ray tube & screen')
        self.assertEqual(record['credit'], 'Cathode ray tube.svg by Kd, CC BY 4.0, via Wikimedia Commons')
        self.assertEqual(record['categories'], ['Cathode ray tubes', 'SVG physics'])

    def test_unusable_files_are_left(self):
        self.assertIsNone(c.record_for(self.page(licence='CC BY-SA 4.0'), 'x'))
        self.assertIsNone(c.record_for(self.page(mime='image/png'), 'x'))
        self.assertIsNone(c.record_for(self.page(size=9_000_000), 'x'))


class LabelTests(unittest.TestCase):
    def test_printed_words(self):
        svg = (b'<svg xmlns="http://www.w3.org/2000/svg"><text>Anode</text><text><tspan>Gold</tspan> '
               b'<tspan>foil</tspan></text><path d="M0 0"/></svg>')
        self.assertEqual(c.labels(svg), ['Anode', 'Gold foil'])

    def test_broken_svg(self):
        self.assertEqual(c.labels(b'<svg'), [])


if __name__ == '__main__':
    unittest.main()
