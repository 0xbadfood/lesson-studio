"""Humanities digests (NCERT Class 10 History pilot, 2026-10-14): the book numbers its own sections (1, 2.1),
labels figures "Fig. 3", primary sources "Source A" and boxes "Box 1"; the nightly job borrows the amdserver only
while no film job needs it."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import digest as d
import nightly_digest as nightly

PAGE = ('1 The French Revolution and the Idea of the Nation\nThe first clear expression of nationalism came with the '
        'French Revolution in 1789.\nFig. 2 — The cover of a German almanac\nSource A\nErnst Renan, What is a '
        'Nation?\nBox 1\n2.1 The Aristocracy and the New Middle Class\n1. Write a note on:\n1848 was a year')
HISTORY = {'id': 'jess3:01', 'subject': 'history', 'chapter': 1}


class HumanitiesTests(unittest.TestCase):
    def test_own_section_numbers_and_labels(self):
        self.assertIsNone(d.numbering(HISTORY))
        self.assertEqual(d.numbering({'subject': 'physics', 'chapter': 5}), 5)
        self.assertEqual([h[0] for h in d.headings(PAGE, None)], ['1', '2.1'])   # not "1. Write", not "1848"
        self.assertEqual(d.inventory(PAGE, None), {'fig': ['2'], 'source': ['A'], 'box': ['1']})

    def test_mislabelled_heading_does_not_replace_the_printed_title(self):
        pages = [{'page': 9, 'text': '2.3 Swaraj in the Plantations\nWorkers too had their own understanding'},
                 {'page': 10, 'text': '3 Towards Civil Disobedience\nIn February 1922'}]
        read = [(10, {'headings': [{'id': '2.3', 'title': 'Towards Civil Disobedience'},
                                   {'id': '3', 'title': 'Towards Civil Disobedience'}]})]
        self.assertEqual([(s['id'], s['title']) for s in d.make_outline(pages, None, read)],
                         [('2.3', 'Swaraj in the Plantations'), ('3', 'Towards Civil Disobedience')])

    def test_page_check_wants_the_source_box_and_humanities_types(self):
        pages = [{'page': 4, 'text': PAGE}]
        fact = {'type': 'fact', 'section': '1', 'title': 'Nationalism', 'quote': 'The first clear expression of '
                'nationalism came with the French Revolution', 'text': 'x'}
        errors = ' '.join(d.page_errors({'blocks': [fact, {**fact, 'type': 'equation', 'section': '1.9.9.9'}]}, 4,
                                        pages, None, {'source': ['A']}))
        self.assertIn('Source A is on this page', errors)
        self.assertIn('type must be one of', errors)
        self.assertIn('section must be a section number like 2 or 2.1', errors)
        source = {**fact, 'type': 'source', 'ref': ['Source A'], 'section': '2.1'}
        self.assertEqual(d.page_errors({'blocks': [fact, source]}, 4, pages, None, {'source': ['A']}), [])

    def test_fact_gaps_need_research(self):
        group, blocks = [{'id': 'C1'}], [{'id': 'B1'}]
        gap = {'concept': 'C1', 'blocks': ['B1'], 'type': 'person', 'resolve': 'knowledge'}
        self.assertIn('resolve "research"', ' '.join(d.gap_errors({'gaps': [gap]}, group, blocks, True)))
        self.assertIn('type must be one of', ' '.join(d.gap_errors({'gaps': [gap]}, group, blocks)))   # science


class NightlyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup); self.root = Path(folder.name)

    def test_film_busy_reads_the_queue(self):
        db = self.root / 'queue.sqlite3'
        with sqlite3.connect(db) as c:
            c.execute('create table jobs (id text, status text)')
            c.execute("insert into jobs values ('a', 'succeeded')")
        self.assertFalse(nightly.film_busy(db))
        with sqlite3.connect(db) as c:
            c.execute("insert into jobs values ('b', 'queued')")
        self.assertTrue(nightly.film_busy(db))
        self.assertFalse(nightly.film_busy(self.root / 'missing.sqlite3'))

    def test_wanted_skips_built_chapters_and_comments(self):
        queue = self.root / 'q.txt'
        queue.write_text('# pilot\njess3:01\njess3:02  # second\n\n')
        (self.root / 'jess3-01').mkdir(); (self.root / 'jess3-01' / 'digest.json').write_text('{}')
        self.assertEqual(nightly.wanted(queue, self.root), ['jess3:02'])

    def test_borrow_marker_survives_a_restart(self):
        from unittest.mock import patch
        marker, calls = self.root / 'amd-borrowed', []
        amd = nightly.Amd(print, marker)
        statuses = iter([{'mode': 'image', 'services': {'llm': 'down'}},
                         {'mode': 'llm', 'services': {'llm': 'up'}}])
        with patch.object(nightly, 'http', lambda url, method='GET', timeout=10: calls.append(url) or {}), \
                patch.object(nightly.Amd, 'status', lambda self: next(statuses)), patch.object(nightly.time, 'sleep'):
            self.assertTrue(amd.borrow())
            self.assertTrue(nightly.Amd(print, marker).switched)          # a restarted job knows it holds it
            nightly.Amd(print, marker).give_back()
        self.assertFalse(marker.exists())
        self.assertEqual([u.rsplit('/', 2)[-1] for u in calls], ['llm', 'image'])

    def test_empty_calculation_entry_is_ignored(self):
        self.assertEqual(d.calculation_errors({'content': 'Gandhi reached Dandi in April 1930.',
                                               'calculations': [{'expr': None, 'value': None}]}), [])


class GarbledTextLayerTests(unittest.TestCase):
    def test_damaged_text_layers_are_caught_and_clean_prose_is_not(self):
        from digest import garbled
        damaged = ("he vast plains of the n ab toda divided between ndia and a istan and indh now in a istan are watered b "
                   "the nd s iver and its tributaries his made those plains fertile and, therefore, favo rable to agric lt re "
                   "little f rther east, a few millenni ms ago, another river, the arasvat , sed to ow from the foothills")
        clean = ("The vast plains of the Punjab (today divided between India and Pakistan) and Sindh (now in Pakistan) are "
                 "watered by the Indus River and its tributaries. This made those plains fertile and, therefore, favourable "
                 "to agriculture. A little further east, a few millenniums ago, another river, the Sarasvati, used to flow.")
        self.assertTrue(garbled(damaged))
        self.assertFalse(garbled(clean))
        self.assertFalse(garbled("too short to judge"))


class SettleFactGapsTests(unittest.TestCase):
    def test_extra_fact_gaps_are_settled_by_code_not_left_to_fail_the_chapter(self):
        q = 'When and where was this person born exactly'
        result = {'gaps': [
            {'concept': 'C1', 'type': 'person', 'resolve': 'research', 'research_question': q, 'priority': 'low'},
            {'concept': 'C1', 'type': 'person', 'resolve': 'research', 'research_question': q, 'priority': 'high'},
            {'concept': 'C2', 'type': 'chronology', 'resolve': 'research', 'research_question': q, 'priority': 'medium'},
            {'concept': 'C2', 'type': 'person', 'resolve': 'knowledge', 'priority': 'high'},
            {'concept': 'C2', 'type': 'term', 'resolve': 'knowledge', 'priority': 'low'}]}
        d.settle_fact_gaps(result, humanities_mode=True)
        kinds = [(g['type'], g['priority']) for g in result['gaps']]
        self.assertEqual(kinds, [('person', 'high'), ('chronology', 'medium'), ('term', 'low')])
        self.assertEqual(sum(g['resolve'] == 'research' for g in result['gaps']), 2)
        group = [{'id': 'C1'}, {'id': 'C2'}]
        self.assertFalse([e for e in d.gap_errors(result, group, [], humanities_mode=True) if 'research' in e])


if __name__ == '__main__':
    unittest.main()
