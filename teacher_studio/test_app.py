import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from PIL import Image

from teacher_studio import app


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.studio = app.Studio(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_consent_no_voice(self):
        with self.assertRaises(HTTPException):
            self.studio.record_voice(b'x' * 2000, False, 'Asha')
        self.assertIsNone(self.studio.voice())

    def test_a_noisy_take_changes_nothing_and_asks_again(self):
        report = {'ok': False, 'problems': ['noise'], 'measures': {}}
        with mock.patch.object(app.rendition, 'prepare_voice', return_value=report), mock.patch.object(app.rendition, 'load_config', return_value={}):
            self.assertFalse(self.studio.record_voice(b'x' * 2000, True, 'Asha')['ok'])
        self.assertIsNone(self.studio.voice())

    def test_a_good_take_records_consent_and_replaces_by_setting_aside(self):
        def good(take, trial, config):
            Path(trial).mkdir()
            (Path(trial) / 'voice.wav').write_bytes(b'v' + Path(take).name.encode())
            return {'ok': True, 'problems': [], 'measures': {'snr_db': 40}}
        with mock.patch.object(app.rendition, 'prepare_voice', side_effect=good), mock.patch.object(app.rendition, 'load_config', return_value={}):
            self.studio.record_voice(b'x' * 2000, True, ' Asha  Rao ')
            voice = self.studio.voice()
            self.assertEqual(voice['name'], 'Asha Rao')
            self.assertEqual(voice['consent_text'], app.CONSENT)
            self.assertTrue(voice['live_recording'])
            with mock.patch.object(app.time, 'strftime', return_value='later'):
                self.studio.record_voice(b'y' * 2000, True, 'Asha Rao')
        self.assertTrue((Path(self.tmp.name) / 'voice.old-later' / 'consent.json').exists())

    def test_a_film_needs_a_voice(self):
        with self.assertRaises(HTTPException):
            self.studio.enqueue('C7')

    def test_a_logo_must_be_an_image_and_small(self):
        with self.assertRaises(HTTPException):
            self.studio.set_logo(b'<svg onload="x()"></svg>')
        out = io.BytesIO()
        Image.new('RGB', (900, 900), 'red').save(out, 'PNG')
        self.studio.set_logo(out.getvalue())
        self.assertEqual(Image.open(Path(self.tmp.name) / 'logo.png').size, (256, 256))

    def test_a_changed_voice_does_not_narrate_a_waiting_film(self):
        self.assertEqual(self.studio.run_job({'id': 'x', 'voice_sha': 'old'})['state'], 'failed')

    def test_a_bundle_set_aside_is_not_a_film(self):
        root = Path(self.tmp.name) / 'bundles'
        for name in ('C2', 'C10', 'C7.old-20261101-1330'):
            (root / name).mkdir(parents=True)
            (root / name / 'bundle.json').write_text('{"title": "T: x"}')
            (root / name / 'master.json').write_text('{"seconds": 60}')
        self.assertEqual([f['id'] for f in app.film_list(root)], ['C2', 'C10'])

    def test_sessions_are_signed(self):
        good = mock.Mock(cookies={app.COOKIE: self.studio.token()})
        self.assertTrue(self.studio.signed_in(good))
        self.assertFalse(self.studio.signed_in(mock.Mock(cookies={app.COOKIE: '123.forged'})))


if __name__ == '__main__':
    unittest.main()
