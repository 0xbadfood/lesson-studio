import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from history_studio import activity


def project_with(events, extra=None):
    """A film project folder whose event log holds (time, stage, state, detail) rows."""
    folder = Path(tempfile.mkdtemp())
    db = sqlite3.connect(folder / 'jobs.sqlite3')
    db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, time REAL, stage TEXT, state TEXT, detail TEXT)')
    db.executemany('INSERT INTO events (time, stage, state, detail) VALUES (?, ?, ?, ?)',
                   [(t, s, st, json.dumps(d)) for t, s, st, d in events])
    db.commit()
    for path, value in (extra or {}).items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(json.dumps(value))
    return folder


class ActivityTests(unittest.TestCase):
    def test_only_the_latest_attempt_is_shown(self):
        project = project_with([(1, 'pipeline:research', 'running', {}),
                                (2, 'pipeline:evidence', 'failed', {'error': 'old failure'}),
                                (10, 'pipeline:research', 'running', {}),
                                (11, 'pipeline:research', 'succeeded', {})])
        a = activity.activity(project, now=20)
        self.assertEqual([(s['key'], s['state']) for s in a['steps']], [('research', 'succeeded')])
        self.assertFalse(a['running'])

    def test_planning_rounds_reviews_and_repairs(self):
        project = project_with([
            (0, 'pipeline:research', 'running', {}), (1, 'pipeline:narration', 'running', {}),
            (2, 'script-300-draft-2dd4228f-0', 'running', {'role': 'planner'}),
            (5, 'script-300-draft-2dd4228f-0', 'succeeded', {'usage': {'cost': 0.004, 'prompt_tokens': 10}}),
            (6, 'script-300-review-2dd4228f-0', 'running', {'role': 'reviewer'}),
            (9, 'script-300-review-2dd4228f-0', 'succeeded', {'usage': {'input_tokens': 100, 'output_tokens': 20}}),
            (10, 'script-300', 'targeted_repair', {'attempt': 1, 'units': ['P08']}),
            (11, 'script-300-draft-2dd4228f-1', 'running', {})],
            {'planning/script-300/2dd4228ff3fe67db/review-0.json': {
                'score': 74, 'pass': False, 'issues': [{'severity': 'major', 'problem': 'P08 omits the signed change'}]}})
        a = activity.activity(project, now=30)
        loop = a['work']['planning'][0]
        self.assertEqual((loop['label'], loop['rounds'], loop['score'], loop['state']),
                         ('Writing the narration', 2, 74, 'working'))
        self.assertEqual(loop['repairs'], [['P08']])
        self.assertIn('omits', loop['majors'][0])
        self.assertEqual(a['models'], {'calls': 2, 'planner_usd': 0.004, 'reviewer_tokens': 120})
        self.assertIn('fixing P08', a['log'][1]['text'])

    def test_animations_pictures_and_clips(self):
        project = project_with([
            (0, 'pipeline:research', 'running', {}), (1, 'pipeline:scenes', 'running', {}),
            (2, 'animations', 'progress', {'message': 'Chapter s07: coding the scene (routine coder, attempt 1)'}),
            (5, 'animations', 'progress', {'message': 'Chapter s07: rendering attempt 2'}),
            (8, 'animations', 'progress', {'message': 'Chapter s07: finished, passed review after 2 attempt(s)'}),
            (9, 'pipeline:scenes', 'succeeded', {}), (10, 'pipeline:images', 'running', {}),
            (11, 'images', 'planned', {'planned_images': 2, 'accepted_images': 0}),
            (12, 'A001', 'rejected', {'attempt': 1, 'visual_message': 'Lines of light', 'issues': ['a blurry haze']}),
            (13, 'A002', 'accepted', {'attempt': 1, 'visual_message': 'The staircase'}),
            (14, 'action-clips', 'running', {'clips': 1}),
            (20, 'action-clips', 'rendered', {'scene': 'S05', 'worker': 'amdserver', 'seconds': 300})],
            {'film-300/storyboard.json': {'scenes': [{'id': 'S07', 'kind': 'animation',
                                                      'animation': {'title': 'The ball hops down one step'}}]}})
        a = activity.activity(project, now=25)
        beat = a['work']['animations'][0]
        self.assertEqual((beat['id'], beat['state'], beat['attempts'], beat['title'], beat['seconds']),
                         ('s07', 'done', 2, 'The ball hops down one step', 6))
        pictures = {p['id']: p for p in a['work']['pictures']['items']}
        self.assertEqual((pictures['A001']['state'], pictures['A001']['issue']), ('retrying', 'a blurry haze'))
        self.assertEqual(pictures['A002']['state'], 'accepted')
        self.assertEqual(a['work']['clips']['made'][0]['scene'], 'S05')
        self.assertTrue(a['running'])


if __name__ == '__main__':
    unittest.main()
