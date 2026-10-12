import unittest

import textbook_kb as kb

PAGES = [{'page': 1, 'text': 'The work-energy theorem\nstates that the change in kinetic\nenergy of a particle is equal '
                             'to the work done on it by the net force.'},
         {'page': 2, 'text': 'Power is defined as the time rate at which work is done or energy is transferred.'}]


def item(n, **over):
    base = {'id': f'T{n}', 'kind': 'law', 'title': 't', 'statement': 's', 'depth': 'stated', 'pages': [1],
            'quote': 'change in kinetic energy of a particle'}
    return {**base, **over}


def brief(**over):
    base = {'scope': 'x', 'objectives': [{'id': 'O1', 'text': 'o', 'covers': ['T1']}],
            'teaches': [item(n) for n in range(1, 6)], 'order': ['T1', 'T2']}
    return {**base, **over}


class QuoteTests(unittest.TestCase):
    def test_quote_across_line_breaks_and_case(self):
        self.assertTrue(kb.quoted('The Work-Energy theorem states that', PAGES[0]['text']))

    def test_quote_split_by_the_other_column(self):
        page = 'In general, the collision is two-\n\n(5.30)\n\nExample 5.12 Consider ... dimensional, where the'
        self.assertTrue(kb.quoted('In general, the collision is two-dimensional, where the', page))

    def test_sentence_end_printed_before_its_start(self):
        page = 'dimensional, where the initial velocities lie in a plane. Example 5.11 ... In general, the collision is two-'
        self.assertTrue(kb.quoted('In general, the collision is two-dimensional, where the initial velocities lie', page))

    def test_quote_words_must_be_in_order_and_close(self):
        self.assertFalse(kb.quoted('equal to the work-energy theorem', PAGES[0]['text']))
        self.assertFalse(kb.quoted('theorem states power', PAGES[0]['text'] + ' x' * 200 + ' power'))
        self.assertFalse(kb.quoted('kinetic energy', PAGES[0]['text']))   # too short to prove anything


class FindQuoteTests(unittest.TestCase):
    pages = [{'page': 1, 'text': 'Collisions can be two-'}, {'page': 2, 'text': 'dimensional, where the velocities lie '
             'in a plane.'}, {'page': 3, 'text': 'Example 5.2 Find the work done by the force on the block.'}]

    def test_neighbour_page_and_page_break(self):
        self.assertEqual(kb.find_quote('Find the work done by the force', self.pages, [2]), 3)
        self.assertEqual(kb.find_quote('can be two-dimensional, where the velocities', self.pages, [2]), 2)
        self.assertIsNone(kb.find_quote('Find the work done by the force', self.pages, [1]))

    def test_brief_records_the_real_page(self):
        b = brief(teaches=[item(1, pages=[2], quote='Find the work done by the force')] + [item(n) for n in range(2, 6)])
        pages = PAGES + [{'page': 3, 'text': 'Example 5.2 Find the work done by the force on the block.'}]
        self.assertEqual(kb.brief_errors(b, pages), [])
        self.assertEqual(b['teaches'][0]['pages'], [2, 3])


class BriefTests(unittest.TestCase):
    def test_valid_brief(self):
        self.assertEqual(kb.brief_errors(brief(), PAGES), [])

    def test_wrong_page_and_invented_quote(self):
        teaches = [item(1, quote='momentum is conserved in every collision')] + [item(n) for n in range(2, 5)] + [item(5, quote='energy is never conserved here')]
        errors = kb.brief_errors(brief(teaches=teaches), PAGES)
        self.assertTrue(any(e.startswith('T1: the quote') for e in errors))
        self.assertTrue(any(e.startswith('T5: the quote') for e in errors))

    def test_unknown_page_kind_and_ids(self):
        teaches = [item(1, pages=[9], kind='story')] + [item(n) for n in range(3, 7)]
        errors = ' '.join(kb.brief_errors(brief(teaches=teaches, order=['T99']), PAGES))
        for text in ('pages must be page numbers', 'kind must be', 'T1, T2', 'unknown ids'):
            self.assertIn(text, errors)


class GapTests(unittest.TestCase):
    def test_gap_checks(self):
        b = brief()
        gaps = [{'id': 'G1', 'type': 'intuition', 'about': ['T1'], 'missing': 'm', 'resolve': 'knowledge'},
                {'id': 'G2', 'type': 'context', 'about': ['T2'], 'missing': 'm', 'resolve': 'research',
                 'research_question': 'What is the power output of a typical human cyclist in watts?'},
                {'id': 'G3', 'type': 'vibes', 'about': ['T42'], 'missing': 'm', 'resolve': 'research'}]
        errors = ' '.join(kb.gap_errors({'gaps': gaps}, b))
        self.assertIn('G3: type must be', errors)
        self.assertIn('G3: "about"', errors)
        self.assertIn('G3: a research gap needs', errors)
        self.assertNotIn('G1', errors)
        self.assertNotIn('G2', errors)

    def test_research_cap(self):
        gaps = [{'id': f'G{n}', 'type': 'context', 'about': ['T1'], 'missing': 'm', 'resolve': 'research',
                 'research_question': 'a specific searchable question here'} for n in range(1, kb.MAX_RESEARCH + 2)]
        self.assertIn('at most', ' '.join(kb.gap_errors({'gaps': gaps}, brief())))


class AugmentTests(unittest.TestCase):
    gaps = [{'id': 'G1'}, {'id': 'G2'}]
    research = {'G2': {'fetched': ['https://nasa.gov/a']}}
    text = ' '.join(['word'] * 30)

    def test_web_sources_must_be_fetched(self):
        items = [{'gap': 'G1', 'level': 'within', 'provenance': 'standard_knowledge', 'content': self.text},
                 {'gap': 'G2', 'level': 'extension', 'provenance': 'web', 'content': self.text,
                  'sources': ['https://NASA.gov/a/', 'https://blog.example/x']}]
        errors = ' '.join(kb.augment_errors({'augmentations': items}, self.gaps, self.research))
        self.assertIn('G2: web sources', errors)
        self.assertIn('blog.example', errors)
        items[1]['sources'] = ['https://NASA.gov/a/']
        self.assertEqual(kb.augment_errors({'augmentations': items}, self.gaps, self.research), [])

    def test_every_gap_once_and_no_sources_on_knowledge(self):
        items = [{'gap': 'G1', 'level': 'within', 'provenance': 'standard_knowledge', 'content': self.text,
                  'sources': ['https://nasa.gov/a']}]
        errors = ' '.join(kb.augment_errors({'augmentations': items}, self.gaps, self.research))
        self.assertIn('exactly one augmentation per gap', errors)
        self.assertIn('standard_knowledge has no sources', errors)


if __name__ == '__main__':
    unittest.main()
