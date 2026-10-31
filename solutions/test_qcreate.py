import unittest

import qcreate
import qfigure

GOOD = {
    'stem': 'A block slides down a height [[h]] ...', 'unwrap': 'u', 'decoy': 'd', 'key': 'A', 'params': {'g': 10, 'h': 5}, 'params_alt': {'g': 9.8, 'h': 2},
    'options': {'A': {'text': '√(2gh)', 'expr': 'sqrt(2*g*h)'}, 'B': {'text': '√(gh)', 'expr': 'sqrt(g*h)'}, 'C': {'text': '√(3gh)', 'expr': 'sqrt(3*g*h)'}, 'D': {'text': '√(gh/2)', 'expr': 'sqrt(g*h/2)'}},
    'mistakes': {'B': 'x', 'C': 'y', 'D': 'z'}, 'concepts': [{'name': 'a'}, {'name': 'b'}, {'name': 'c'}],
    'python': "from math import sqrt\ndef correct(P): return sqrt(2*P['g']*P['h'])\ndef wrong(P): return {'B': sqrt(P['g']*P['h']), 'C': sqrt(3*P['g']*P['h']), 'D': sqrt(P['g']*P['h']/2)}\ndef checks(P): return {'height positive': P['h'] > 0}\n",
}


class Code(unittest.TestCase):
    def test_a_sound_question_passes_and_runs_in_the_sandbox(self):
        errors, numbers = qcreate.code_errors(GOOD, {'a', 'b', 'c'})
        self.assertEqual(errors, [])
        self.assertAlmostEqual(numbers['params']['correct'], 10)

    def test_a_key_the_physics_does_not_give_is_refused(self):
        errors, _ = qcreate.code_errors({**GOOD, 'key': 'B', 'mistakes': {'A': 'x', 'C': 'y', 'D': 'z'}}, {'a', 'b', 'c'})
        self.assertTrue(any('key B' in e for e in errors), errors)

    def test_a_wrong_option_must_come_from_its_mistake(self):
        python = GOOD['python'].replace("'C': sqrt(3*P['g']*P['h'])", "'C': 1.0")
        errors, _ = qcreate.code_errors({**GOOD, 'python': python}, {'a', 'b', 'c'})
        self.assertTrue(any('option C' in e for e in errors), errors)

    def test_a_false_assumption_and_too_few_concepts_are_refused(self):
        python = GOOD['python'].replace("P['h'] > 0", "P['h'] < 0")
        errors, _ = qcreate.code_errors({**GOOD, 'python': python}, {'a', 'b', 'c'})
        self.assertTrue(any('check height positive' in e for e in errors), errors)
        errors, _ = qcreate.code_errors({**GOOD, 'concepts': GOOD['concepts'][:2]}, {'a', 'b', 'c'})
        self.assertTrue(any('at least 3' in e for e in errors), errors)

    def test_arithmetic_on_a_filled_value_is_refused(self):
        errors, _ = qcreate.code_errors({**GOOD, 'stem': 'natural length [[h]]/4'}, {'a', 'b', 'c'})
        self.assertTrue(any('arithmetic' in e for e in errors), errors)

    def test_the_sandbox_has_no_network(self):
        python = "import socket\ndef correct(P):\n    socket.create_connection(('1.1.1.1', 53), 2)\n    return 0\ndef wrong(P): return {}\ndef checks(P): return {}\n"
        _, err = qcreate.run_python({**GOOD, 'python': python})
        self.assertIn('failed', err)

    def test_a_reply_with_words_and_braces_still_reads(self):
        self.assertEqual(qcreate.parse('Using {v} here. {"working": "x", "choice": "B"}', 'choice')['choice'], 'B')
        self.assertEqual(qcreate.parse('{"a": {"choice": 1}} then {"choice": "C"}', 'choice')['choice'], 'C')
        with self.assertRaises(ValueError):
            qcreate.parse('no answer {here}', 'choice')

    def test_the_haiku_gauge_has_a_price(self):
        self.assertAlmostEqual(qcreate.cost('claude-haiku-5-5', {'input_tokens': 1_000_000, 'output_tokens': 1_000_000}), 0.6)

    def test_cost_counts_every_token_kind(self):
        self.assertAlmostEqual(qcreate.cost('claude-opus-5-5', {'input_tokens': 1_000_000, 'output_tokens': 1_000_000}), 24.0)
        self.assertAlmostEqual(qcreate.cost('claude-sonnet-5-5', {'cache_read_input_tokens': 1_000_000}), 0.2)

    def test_what_cannot_be_confirmed_is_discarded(self):
        self.assertEqual(qcreate.settle(10.0, None, 10.0), 'accepted')
        self.assertEqual(qcreate.settle(12.0, 10.0, 10.0), 'accepted_hard')
        self.assertEqual(qcreate.settle(12.0, 12.0, 10.0), 'discarded_key_disputed')
        self.assertEqual(qcreate.settle(12.0, 14.0, 10.0), 'discarded_unclear')
        self.assertEqual(qcreate.settle(None, None, 10.0), 'discarded_unclear')

    def test_fable_has_a_price(self):
        self.assertAlmostEqual(qcreate.cost('claude-fable-5-1', {'input_tokens': 1_000_000, 'output_tokens': 1_000_000}), 60.0)


class Figure(unittest.TestCase):
    def test_a_block_rests_on_its_incline_and_a_string_ends_on_it(self):
        fig = {'parts': [{'type': 'incline', 'id': 'w', 'at': [10, 10], 'angle': 30, 'length': 50, 'fixed': True},
                         {'type': 'block', 'id': 'b', 'w': 8, 'h': 5, 'on': 'w', 's': 0.5, 'label': 'm'},
                         {'type': 'pulley', 'id': 'p', 'r': 3, 'at': 'w.top'},
                         {'type': 'string', 'from': 'b.right', 'to': [55, 15], 'over': ['p'], 'side': ['top']}]}
        f = qfigure.Figure(fig)
        svg = f.svg()
        self.assertEqual(f.errors, [])
        self.assertIn('<polygon', svg)
        b = next(p for p in f.parts if p.get('id') == 'b')
        w = next(p for p in f.parts if p.get('id') == 'w')
        # the block's underside is on the slope: its bottom anchor lies on the line from foot to top
        q = f.anchor(b, 'bottom', 'b.bottom')
        foot, top = w['_foot'], w['_top']
        cross = (top[0] - foot[0]) * (q[1] - foot[1]) - (top[1] - foot[1]) * (q[0] - foot[0])
        self.assertAlmostEqual(cross, 0, places=6)

    def test_a_part_the_kit_lacks_names_the_kit(self):
        _, errors = qfigure.render({'parts': [{'type': 'gear'}]})
        self.assertIn('missing_parts', errors[0])

    def test_off_frame_and_overlapping_labels_are_refused(self):
        _, errors = qfigure.render({'width': 50, 'height': 30, 'parts': [{'type': 'label', 'at': [80, 10], 'text': 'x'}]})
        self.assertTrue(any('outside' in e for e in errors), errors)
        _, errors = qfigure.render({'parts': [{'type': 'label', 'at': [20, 10], 'text': 'mass'}, {'type': 'label', 'at': [21, 10], 'text': 'mass'}]})
        self.assertTrue(any('overlap' in e for e in errors), errors)

    def test_values_fill_the_figure_and_the_stem(self):
        self.assertEqual(qcreate.fill({'angle': '[[t]]', 'text': 'θ = [[t]]°'}, {'t': 30}), {'angle': 30, 'text': 'θ = 30°'})


if __name__ == '__main__':
    unittest.main()
