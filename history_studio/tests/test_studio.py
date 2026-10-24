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
        self.jobs[job_id].update(status='queued', error=None)
        return self.jobs[job_id]

    def cancel(self, job_id):
        if self.jobs[job_id]['status'] not in ('queued', 'running'):
            raise ValueError('not active')
        self.jobs[job_id].update(status='interrupted', error="Cancelled at the user's request.")
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
        self.assertTrue(catalog.SHORTEST <= record['seconds'] and record['seconds'] % 15 == 0)
        self.assertFalse(catalog.filmable(DIGEST, DIGEST['concepts'][1]))

    def test_length_matches_the_measured_films(self):
        # Unification of Italy (2026-10-15): 561 book words, one accepted addition, 305 s of narration.
        italy = {**DIGEST, 'blocks': [{**DIGEST['blocks'][0], 'text': 'word ' * 561}]}
        self.assertEqual(catalog.film_seconds(italy, {'id': 'C1', 'blocks': ['B1']}), 300)

    def test_long_concepts_run_as_long_as_their_coverage_needs(self):
        big = {**DIGEST, 'blocks': [{**DIGEST['blocks'][0], 'text': 'word ' * 1500}]}
        self.assertEqual(catalog.film_seconds(big, {'id': 'C1', 'blocks': ['B1']}), 735)     # about 12 min, no cap

    def test_objective_terms_bring_their_book_text_from_elsewhere_in_the_chapter(self):
        # Unification of Germany (2026-10-17): the objective names the Zollverein, whose block belongs to another
        # concept; without it the evidence review rejected every candidate.
        digest = {**DIGEST, 'blocks': [
            {'id': 'B1', 'type': 'event', 'title': 'Formation of the Zollverein', 'date': '1834', 'pages': [10],
             'text': 'In 1834, a customs union or zollverein was formed at the initiative of Prussia.'},
            {'id': 'B2', 'type': 'event', 'title': 'Proclamation of the German Empire', 'pages': [20],
             'text': 'In January 1871 William I was proclaimed German Emperor at Versailles.'},
            {'id': 'B3', 'type': 'exercise', 'title': 'Zollverein question', 'text': 'What was the Zollverein?'}]}
        germany = {'id': 'C8', 'name': 'The Unification of Germany', 'blocks': ['B2'], 'aliases': ['Zollverein', 'Bismarck'],
                   'objectives': ['Trace German unification from the Zollverein to the German Empire.']}
        self.assertEqual(catalog.teaching_ids(digest, germany), ['B1', 'B2'])            # book order, no questions
        self.assertIn('customs union', catalog.book_text(digest, germany))
        self.assertIn('Event: Formation of the Zollverein (1834)', ' '.join(k['point'] for k in catalog.coverage(digest, germany)))
        named = {**germany, 'blocks': ['B1', 'B2']}
        self.assertEqual(catalog.teaching_ids(digest, named), ['B1', 'B2'])              # nothing added twice
        unnamed = {**germany, 'objectives': ['Explain the proclamation.']}
        self.assertEqual(catalog.teaching_ids(digest, unnamed), ['B2'])                  # only terms objectives name

    def test_key_terms_bring_their_meaning_into_the_book_text(self):
        # Human Evolution (2026-10-17): 'Fossil' had only a meaning, so the book text showed a bare heading while
        # coverage asked for the definition, and the evidence review rejected every candidate.
        digest = {**DIGEST, 'blocks': [{'id': 'B1', 'type': 'key_term', 'title': 'Fossil', 'term': 'Fossil', 'pages': [6],
                                        'meaning': 'The preserved remains of plants, animals, or humans.'}]}
        concept = {'id': 'C2', 'name': 'Human Evolution', 'blocks': ['B1']}
        self.assertIn('[Key term, p.6] Fossil\nThe preserved remains', catalog.book_text(digest, concept))


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

    def test_a_film_started_by_mistake_can_be_stopped_and_made_again_with_its_narrator(self):
        studio.voices = lambda: [{'id': 'kane', 'label': 'Kane (studio narrator)', 'reference_audio': '/r/kane.wav'},
                                 {'id': 'in-abc', 'label': 'Clear Anchor (female, V1)', 'reference_audio': '/r/abc.wav'}]
        self.client.post('/api/login', json={'code': self.access.code})
        film = self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1', 'voice': 'in-abc'}).json()['film']
        stopped = self.client.post(f'/api/films/{film}/cancel').json()
        self.assertEqual(stopped['status'], 'stopped')
        self.assertEqual(self.client.post(f'/api/films/{film}/cancel').status_code, 409)      # already stopped
        again = self.client.post('/api/films', json={'chapter': stopped['chapter_id'], 'concept': stopped['concept_id']}).json()
        self.assertEqual((again['film'], len(self.queue.jobs), self.queue.jobs['job1']['status']), (film, 1, 'queued'))
        self.assertEqual(self.client.get(f'/api/films/{film}').json()['status'], 'waiting')
        # the book text changed since (a digest or catalog fix): the saved run would plan from the old text, so start anew
        self.client.post(f'/api/films/{film}/cancel')
        changed = json.loads(json.dumps(DIGEST)); changed['blocks'][0]['text'] += ' He reached Dandi on 6 April.'
        (catalog.DIGESTS / 'jess3-02' / 'digest.json').write_text(json.dumps(changed))
        fresh = self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1'}).json()['film']
        self.assertNotEqual(fresh, film)
        self.assertEqual((len(self.queue.jobs), self.queue.jobs['job2']['request']['voice_id']),
                         (2, self.queue.jobs['job1']['request']['voice_id']))                    # same narrator
        self.assertIn('6 April', self.queue.jobs['job2']['request']['curriculum']['sources']['results'][0]['raw_content'])

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



CHEM = {'source': {'id': 'kech1-02', 'class': 11, 'subject': 'chemistry', 'book': 'kech1', 'chapter': 2,
                   'book_title': 'Chemistry Part I', 'title': 'Structure of Atom', 'pdf': '/books/kech102.pdf'},
        'blocks': [{'id': 'B1', 'type': 'fact', 'title': 'Scattering experiment', 'pages': [6],
                    'text': ' '.join(['Alpha particles were directed at a thin gold foil.'] * 40)},
                   {'id': 'B2', 'type': 'equation', 'title': 'Mass number', 'latex': 'A = Z + n', 'ref': ['Eq. 2.4'],
                    'pages': [7], 'text': 'Mass number is the sum of protons and neutrons.'},
                   {'id': 'B3', 'type': 'definition', 'title': 'Isotopes', 'pages': [7],
                    'text': 'Atoms with the same atomic number but different mass number.'},
                   {'id': 'B4', 'type': 'worked_example', 'title': 'Problem 2.1', 'pages': [8],
                    'problem': 'Find the neutrons in Br-80', 'given': ['Z = 35', 'A = 80'],
                    'steps': [{'latex': 'n = A - Z = 45'}], 'answer': '45 neutrons', 'text': 'Find the neutrons'}],
        'concepts': [{'id': 'C1', 'name': "Rutherford's Nuclear Model", 'summary': 'Gold foil and the nucleus.',
                      'blocks': ['B1', 'B2', 'B3', 'B4'], 'objectives': ['Explain the scattering experiment.']}],
        'gaps': [], 'additions': []}


class ChemistryStudioTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup); root = Path(folder.name)
        for d in (DIGEST, CHEM):
            (root / 'digests' / d['source']['id']).mkdir(parents=True)
            (root / 'digests' / d['source']['id'] / 'digest.json').write_text(json.dumps(d))
        self.addCleanup(setattr, catalog, 'DIGESTS', catalog.DIGESTS)
        catalog.DIGESTS = root / 'digests'
        self.queue = FakeQueue(root)
        self.access = studio.Access(root / 'chem-data')
        self.addCleanup(setattr, studio, 'voices', studio.voices)
        studio.voices = lambda: [{'id': 'kane', 'label': 'Kane (studio narrator)', 'reference_audio': '/r/kane.wav',
                                  'reference_transcript': 'hello'}]
        self.client = TestClient(studio.build(self.queue, self.access, root / 'chem-data',
                                              catalog.PROFILES['chemistry']))

    def test_only_chemistry_is_offered_and_the_page_is_named_for_it(self):
        page = self.client.get('/').text
        self.assertIn('<title>Chemistry Studio</title>', page)
        self.assertIn('"subject": "chemistry"', page)
        self.client.post('/api/login', json={'code': self.access.code})
        subjects = [s['id'] for c in self.client.get('/api/catalog').json()['classes'] for s in c['subjects']]
        self.assertEqual(subjects, ['chemistry'])

    def test_a_chemistry_film_carries_its_equations_and_figures(self):
        self.client.post('/api/login', json={'code': self.access.code})
        self.client.post('/api/films', json={'chapter': 'kech1-02', 'concept': 'C1'})
        job = self.queue.jobs['job1']
        record = job['request']['curriculum']['record']
        points = [k['point'] for k in record['coverage']]
        self.assertIn('Equation Eq. 2.4: Mass number - A = Z + n', points)
        self.assertTrue(any(p.startswith('Definition: Isotopes') for p in points))
        self.assertIn('figures', record)
        self.assertEqual(record['figures']['code_root'], str(catalog.ROOT))
        book = job['request']['curriculum']['sources']['results'][0]['raw_content']
        self.assertIn('[Equation: A = Z + n]', book)
        self.assertIn('Working: n = A - Z = 45 Answer: 45 neutrons', book)
        self.assertEqual(self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1'}).status_code,
                         404)                                      # history is not this studio's

    def test_history_films_get_no_figures(self):
        record = catalog.film_request(DIGEST, DIGEST['concepts'][0])['record']
        self.assertNotIn('figures', record)


IDEAS = [{'id': f'I{n}', 'title': f'Idea number {n} made simple', 'why': 'Students mix up the two pictures.',
          'understanding': 'Mass number counts protons and neutrons together.', 'questions': ['Q one?', 'Q two?'],
          'minutes': 3 + n / 2, 'research': 'simple analogy for mass number and isotopes'} for n in (1, 2, 3)]


class KeyIdeaTests(ChemistryStudioTests):
    """Key ideas, made simple (2026-10-20): a finished concept film offers short simplified films of its key ideas."""

    def finished_film(self):
        self.client.post('/api/login', json={'code': self.access.code})
        film = self.client.post('/api/films', json={'chapter': 'kech1-02', 'concept': 'C1', 'voice': 'kane'}).json()['film']
        self.queue.jobs['job1']['status'] = 'succeeded'
        return film, Path(self.queue.jobs['job1']['project'])

    def test_ideas_are_listed_and_each_becomes_its_own_short_film(self):
        film, project = self.finished_film()
        self.assertEqual(self.client.get(f'/api/films/{film}/ideas').json(), {'state': 'none', 'ideas': []})
        (project / 'key-ideas').mkdir()
        (project / 'key-ideas' / 'ideas.json').write_text(json.dumps(IDEAS))
        listed = self.client.get(f'/api/films/{film}/ideas').json()
        self.assertEqual((listed['state'], [i['id'] for i in listed['ideas']]), ('ready', ['I1', 'I2', 'I3']))
        made = self.client.post(f'/api/films/{film}/ideas/I2', json={}).json()['film']
        again = self.client.post(f'/api/films/{film}/ideas/I2', json={}).json()['film']
        self.assertEqual((made, len(self.queue.jobs)), (again, 2))
        request = self.queue.jobs['job2']['request']
        record = request['curriculum']['record']
        self.assertEqual((record['kind'], record['seconds'], record['coverage']), ('key_idea', 240, []))
        self.assertEqual(record['idea']['questions'], ['Q one?', 'Q two?'])
        self.assertEqual(record['research'], 'simple analogy for mass number and isotopes')
        self.assertIn('figures', record)                             # same exact chemistry as the concept film
        self.assertEqual(request['voice_id'], 'kane')               # the concept film's narrator
        self.assertTrue(request['subject'].startswith('Idea number 2 made simple (key idea of'))
        progress = self.client.get(f'/api/films/{made}').json()
        self.assertEqual((progress['kind'], progress['idea']['title'], progress['parent']),
                         ('key_idea', 'Idea number 2 made simple', film))
        listed = self.client.get(f'/api/films/{film}/ideas').json()['ideas']
        self.assertEqual([i['film'] for i in listed], [None, made, None])
        concepts = self.client.get('/api/catalog').json()['classes'][0]['subjects'][0]['chapters'][0]['concepts']
        self.assertEqual(next(c for c in concepts if c['id'] == 'C1')['film'], film)    # the concept keeps its film
        self.assertEqual(self.client.post(f'/api/films/{film}/ideas/I9', json={}).status_code, 404)
        path = next(Path(p) for p in [self.queue.root / 'chem-data' / 'films.json'] if Path(p).exists())
        saved = json.loads(path.read_text())
        old = saved.pop('kech1-02:C1:I2')                            # retire version 1 to make the idea again
        saved['kech1-02:C1:I2:v1'] = {**old, 'retired': True}
        path.write_text(json.dumps(saved))
        self.assertIsNone(self.client.get(f'/api/films/{film}/ideas').json()['ideas'][1]['film'])
        remade = self.client.post(f'/api/films/{film}/ideas/I2', json={}).json()['film']
        self.assertNotEqual(remade, made)
        self.assertEqual(self.client.get(f'/api/films/{made}').json()['idea']['title'], 'Idea number 2 made simple')
        self.assertEqual(self.client.get(f'/api/films/{made}/ideas').status_code, 409)  # no ideas of ideas

    def test_ideas_come_only_from_a_finished_film(self):
        self.client.post('/api/login', json={'code': self.access.code})
        film = self.client.post('/api/films', json={'chapter': 'kech1-02', 'concept': 'C1'}).json()['film']
        self.assertEqual(self.client.post(f'/api/films/{film}/ideas').status_code, 409)

    def test_the_planner_finds_ideas_once_and_they_are_checked(self):
        from history_studio import ideas
        self.assertIn('I1: minutes must be 3-5', ' '.join(ideas.errors({'ideas': [{**IDEAS[0], 'minutes': 9}] + IDEAS[1:]})))
        self.assertIn('Give 3-6 key ideas', ideas.errors({'ideas': IDEAS[:2]}))
        self.assertEqual(ideas.errors({'ideas': IDEAS}), [])
        _, project = self.finished_film()
        (project / 'film-90').mkdir()
        (project / 'film-90' / 'script.json').write_text(json.dumps({'points': [{'heading': 'H', 'narration': 'N'}]}))
        (project / 'evidence-final.json').write_text(json.dumps({'facts': [{'claim': 'A = Z + n'}]}))

        class Models:
            seen = []

            def loop(self, stage, task, context, validator):
                self.seen.append((stage, context))
                return {'ideas': [{**i, 'extra': 'dropped'} for i in IDEAS]}
        found = ideas.find(project, {'seconds': 90, 'concept': 'Isotopes', 'coverage': []}, Models())
        self.assertEqual(found, IDEAS)
        self.assertEqual(ideas.saved(project), IDEAS)
        self.assertEqual(Models.seen[0][1]['facts'], ['A = Z + n'])


class HistoryHasNoKeyIdeasTests(AppTests):
    def test_history_studio_offers_no_key_ideas(self):
        self.client.post('/api/login', json={'code': self.access.code})
        film = self.client.post('/api/films', json={'chapter': 'jess3-02', 'concept': 'C1'}).json()['film']
        self.assertEqual(self.client.get(f'/api/films/{film}/ideas').status_code, 404)


if __name__ == '__main__':
    unittest.main()


DIGEST = catalog.ROOT / 'textbook-digest' / 'keph1-02' / 'digest.json'


@unittest.skipUnless(DIGEST.exists() and (catalog.EXTRAS / 'extras.sqlite3').exists(), 'needs the Class 11 Physics digest')
class BookFigureTests(unittest.TestCase):
    def test_physics_films_get_the_figures_their_concept_teaches_from(self):
        digest = json.loads(DIGEST.read_text())
        concept = next(c for c in digest['concepts'] if c['id'] == 'C2')
        record = catalog.film_request(digest, concept, figures=catalog.PROFILES['physics']['figures'])['record']
        figures = record['figures']
        self.assertTrue(figures['book'])
        first = figures['library'][0]
        self.assertEqual((first['id'], first['credit']), ('Fig-2-1', 'NCERT Class 11 Physics, Fig. 2.1'))
        self.assertIn('tangent', first['description'])
        self.assertTrue(Path(first['file']).exists())
        self.assertTrue(all(f['description'] for f in figures['library']))
