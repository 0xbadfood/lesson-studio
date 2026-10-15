"""History Studio: concept films from textbook digests, made by the film queue; access by code."""
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from history_studio import app as studio
from history_studio import catalog


class FakeQueue:
    def __init__(self, root):
        self.root, self.jobs = Path(root), {}

    def submit(self, request, key):
        job_id = f'job{len(self.jobs) + 1}'
        project = self.root / job_id
        project.mkdir()
        (project / 'curriculum.json').write_text(json.dumps(request['curriculum']['record']))
        (project / 'curriculum-sources.json').write_text(json.dumps(request['curriculum']['sources']))
        self.jobs[job_id] = {'id': job_id, 'status': 'queued', 'project': str(project), 'created': len(self.jobs),
                             'request': request}
        return self.jobs[job_id]

    def get(self, job_id):
        return self.jobs[job_id]

    def resume(self, job_id):
        self.jobs[job_id]['status'] = 'queued'
        return self.jobs[job_id]

    def list(self):
        return list(self.jobs.values())


DIGEST = {'source': {'id': 'jess3-02', 'class': 10, 'subject': 'history', 'book': 'jess3', 'chapter': 2,
                     'book_title': 'India And The Contemporary World Ii', 'title': 'Nationalism in India',
                     'pdf': '/books/jess302.pdf'},
          'blocks': [{'id': 'B1', 'type': 'event', 'title': 'The Salt March', 'date': '12 March 1930', 'pages': [11],
                      'text': ' '.join(['Gandhi walked to Dandi with his followers.'] * 60)},
                     {'id': 'B2', 'type': 'key_term', 'term': 'Satyagraha', 'meaning': 'the power of truth',
                      'pages': [12], 'text': 'Satyagraha emphasised the power of truth.'},
                     {'id': 'B3', 'type': 'exercise', 'text': 'Why was salt chosen?', 'pages': [22]}],
          'concepts': [{'id': 'C1', 'name': 'The Salt March', 'summary': 'Why salt.', 'blocks': ['B1', 'B2', 'B3'],
                        'objectives': ['Explain why salt was chosen.']},
                       {'id': 'C2', 'name': 'Chapter Review and Assessment', 'blocks': ['B3']}],
          'gaps': [{'id': 'G1', 'concept': 'C1'}],
          'additions': [{'gap': 'G1', 'title': 'Route', 'content': 'Sabarmati to Dandi, about 387 km.',
                         'status': 'accepted', 'sources': [{'url': 'https://example.org/dandi', 'tier': 'reference'}]}]}


class CatalogTests(unittest.TestCase):
    def test_request_is_rooted_in_the_book_and_sized_by_coverage(self):
        concept = DIGEST['concepts'][0]
        built = catalog.film_request(DIGEST, concept)
        record, sources = built['record'], built['sources']['results']
        self.assertEqual([c['point'][:20] for c in record['coverage']],
                         ['Objective: Explain w', 'Event: The Salt Marc', 'Key term: Satyagraha'])
        self.assertTrue(sources[0]['url'].endswith('/jess302.pdf') and sources[0]['complete'])
        self.assertNotIn('Why was salt chosen', sources[0]['raw_content'])          # questions are not narrated
        self.assertEqual(sources[1]['url'], 'https://example.org/dandi')
        self.assertTrue(catalog.SHORTEST <= record['seconds'] <= catalog.LONGEST and record['seconds'] % 15 == 0)
        self.assertFalse(catalog.filmable(DIGEST, DIGEST['concepts'][1]))

    def test_length_matches_the_measured_films(self):
        # Unification of Italy (2026-10-15): 561 book words, one accepted addition, 305 s of narration.
        italy = {**DIGEST, 'blocks': [{**DIGEST['blocks'][0], 'text': 'word ' * 561}]}
        self.assertEqual(catalog.film_seconds(italy, {'id': 'C1', 'blocks': ['B1']}), 300)

    def test_long_concepts_stop_at_six_minutes(self):
        big = {**DIGEST, 'blocks': [{**DIGEST['blocks'][0], 'text': 'word ' * 4000}]}
        self.assertEqual(catalog.film_seconds(big, {'id': 'C1', 'blocks': ['B1']}), catalog.LONGEST)


class AppTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup); root = Path(folder.name)
        (root / 'digests' / 'jess3-02').mkdir(parents=True)
        (root / 'digests' / 'jess3-02' / 'digest.json').write_text(json.dumps(DIGEST))
        self.old = catalog.DIGESTS
        catalog.DIGESTS = root / 'digests'
        self.addCleanup(setattr, catalog, 'DIGESTS', self.old)
        self.queue = FakeQueue(root)
        self.access = studio.Access(root / 'data')
        self.addCleanup(setattr, studio, 'voices', studio.voices)
        studio.voices = lambda: [{'id': 'kane', 'label': 'Kane (studio narrator)', 'reference_audio': '/r/kane.wav',
                                  'reference_transcript': 'hello'}]
        self.client = TestClient(studio.build(self.queue, self.access, root / 'data'))

    def test_everything_needs_the_access_code(self):
        self.assertEqual(self.client.get('/api/catalog').status_code, 401)
        self.assertEqual(self.client.post('/api/login', json={'code': 'wrong'}).status_code, 403)
        self.assertEqual(self.client.post('/api/login', json={'code': self.access.code.upper()}).status_code, 200)
        self.assertEqual(self.client.get('/api/catalog').status_code, 200)

    def test_one_film_per_concept_and_progress_shows_the_book(self):
        self.client.post('/api/login', json={'code': self.access.code})
        catalog_ = self.client.get('/api/catalog').json()
        chapter = catalog_['classes'][0]['subjects'][0]['chapters'][0]
        self.assertEqual(chapter['book'], 'India and the Contemporary World II')
        self.assertEqual([c['id'] for c in chapter['concepts']], ['C1'])           # the review set is not offered
        film = self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1'}).json()['film']
        again = self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1'}).json()['film']
        self.assertEqual(film, again)
        self.assertEqual(len(self.queue.jobs), 1)
        request = self.queue.jobs['job1']['request']
        self.assertEqual((request['generation_mode'], request['voice_id']), ('short', 'kane'))
        progress = self.client.get(f'/api/films/{film}').json()
        self.assertEqual((progress['status'], progress['concept'], progress['chapter_id']),
                         ('waiting', 'The Salt March', 'jess3-02'))
        self.assertTrue(progress['passages'][0].startswith('Gandhi walked to Dandi'))
        self.queue.jobs['job1']['status'] = 'failed'              # a failed film is made again from its saved run
        again = self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1'}).json()['film']
        self.assertEqual((again, len(self.queue.jobs), self.queue.jobs['job1']['status']), (film, 1, 'queued'))

    def test_chosen_narrator_reaches_the_film_request(self):
        studio.voices = lambda: [{'id': 'kane', 'label': 'Kane (studio narrator)', 'reference_audio': '/r/kane.wav'},
                                 {'id': 'in-abc', 'label': 'Clear Anchor (female, V1)', 'reference_audio': '/r/abc.wav',
                                  'reference_transcript': 'A quiet morning.', 'gender': 'female'}]
        self.client.post('/api/login', json={'code': self.access.code})
        self.assertEqual(self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1', 'voice': 'nobody'}).status_code, 404)
        self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1', 'voice': 'in-abc'})
        request = self.queue.jobs['job1']['request']
        self.assertEqual((request['voice_id'], request['reference_audio'], request['narrator_label']),
                         ('in-abc', '/r/abc.wav', 'Clear Anchor'))
        self.queue.jobs['job1']['status'] = 'failed'              # another narrator after a failure: a new recording
        self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1', 'voice': 'kane'})
        self.assertEqual((len(self.queue.jobs), self.queue.jobs['job2']['request']['voice_id']), (2, 'kane'))

    def test_media_only_from_the_films_own_folder(self):
        self.client.post('/api/login', json={'code': self.access.code})
        film = self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1'}).json()['film']
        project = Path(self.queue.jobs['job1']['project'])
        (project / 'images' / 'abcdef12').mkdir(parents=True)
        outside = project.parent / 'secret.png'; outside.write_bytes(b'x')
        (project / 'images' / 'abcdef12' / 'selected.json').write_text(json.dumps({'file': str(outside)}))
        self.assertEqual(self.client.get(f'/media/{film}/scene/abcdef12').status_code, 404)
        inside = project / 'images' / 'abcdef12' / 'a.png'; inside.write_bytes(b'png')
        (project / 'images' / 'abcdef12' / 'selected.json').write_text(json.dumps({'file': str(inside)}))
        self.assertEqual(self.client.get(f'/media/{film}/scene/abcdef12').content, b'png')
        self.assertEqual(self.client.get(f'/media/{film}/scene/..%2f..').status_code, 404)


if __name__ == '__main__':
    unittest.main()
