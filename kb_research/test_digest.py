import unittest

import digest as d

PAGE = ('We are now familiar with the concepts of work and kinetic energy to prove the work-energy theorem for a '
        'variable force.\n(5.8a)\nExample 5.6 A block of mass m = 1 kg, moving on a horizontal surface')
PAGES = [{'page': 7, 'text': PAGE}]


class CalculationTests(unittest.TestCase):
    def test_wrong_midpoint_sum_is_caught(self):
        content = ('For F = 2x N from 0 to 3 m, a midpoint sum with dx = 1 m gives 2(0.5)(1) + 2(1.5)(1) + 2(2.5)(1) '
                   '= 10 J; the exact integral is 9 J.')
        errors = d.calculation_errors({'content': content, 'calculations': [
            {'expr': '2*0.5*1 + 2*1.5*1 + 2*2.5*1', 'value': 10}]})
        self.assertTrue(any('= 9, not 10' in e for e in errors), errors)

    def test_unlisted_result_and_givens(self):
        self.assertEqual(d.computed_results('m = 5 kg and v = 2 m/s, so K = 0.5 × 5 × 2^2 = 10 J'), [10.0])
        errors = d.calculation_errors({'content': 'W = 10 × 4 × 0.5 = 20 J', 'calculations': []})
        self.assertTrue(any('20' in e for e in errors))
        ok = {'content': 'W = 10 × 4 × 0.5 = 20 J', 'calculations': [{'expr': '10*4*0.5', 'value': 20}]}
        self.assertEqual(d.calculation_errors(ok), [])

    def test_expression_start_is_not_a_result_and_trig_in_degrees(self):
        content = 'The power is $P = F v \\cos(90^\\circ) = 10 \\times 5 \\times 0 = 0$ W.'
        self.assertEqual(d.computed_results(content), [0.0])
        self.assertEqual(d.calculation_errors({'content': content, 'calculations': [
            {'expr': '10 * 5 * cos(90)', 'value': 0}]}), [])

    def test_symbols_and_coefficients_are_not_results(self):
        for text in ('with $m_2 = 2m_1$, the neutron', '$v_{1i}^2 = v_{1f}^2 + 2 v$', 'where x2 = 4 m',
                     'so $\\theta_2 = 37^\\circ$'):
            self.assertEqual(d.computed_results(text), [], text)
        self.assertEqual(d.computed_results('$\\theta_1 = 90^\\circ - 37^\\circ = 53^\\circ$'), [])
        self.assertEqual(d.computed_results('K = 0.5 × 2 × 3² = 9 J and (2 + 3) = 5'), [9.0, 5.0])

    def test_evaluate_is_arithmetic_only(self):
        self.assertAlmostEqual(d.evaluate('2 - 0.5*ln(20.1)'), 0.4999, places=3)
        self.assertAlmostEqual(d.evaluate('sqrt(2*0.5/1)'), 1.0)
        with self.assertRaises(ValueError):
            d.evaluate('__import__("os")')


class PageTests(unittest.TestCase):
    def block(self, **over):
        base = {'type': 'derivation', 'section': '5.6', 'title': 'WE theorem', 'ref': ['Eq. 5.8a'],
                'steps': [{'latex': 'K_f - K_i = \\int F\\,dx', 'reason': ''}],
                'quote': 'to prove the work-energy theorem for a variable force'}
        return {**base, **over}

    def test_valid_page(self):
        example = {'type': 'worked_example', 'section': '5.6', 'title': 'Example 5.6', 'ref': ['Example 5.6'],
                   'continues': True, 'quote': 'A block of mass m = 1 kg, moving on a horizontal surface'}
        required = d.inventory(PAGE, 5)
        self.assertEqual(required, {'example': ['5.6'], 'eq': ['5.8a']})
        self.assertEqual(d.page_errors({'blocks': [self.block(), example]}, 7, PAGES, 5, required), [])

    def test_missing_numbered_items_bad_quote_and_latex(self):
        required = d.inventory(PAGE, 5)
        bad = self.block(ref=[], steps=[{'latex': '\\frac{1}{2'}], quote='energy is never conserved in this chapter')
        worse = self.block(title='other', quote='momentum is conserved in every collision here')
        errors = ' '.join(d.page_errors({'blocks': [bad, worse]}, 7, PAGES, 5, required))
        for text in ('Example 5.6 is on this page', 'unbalanced', 'is not in the page text'):
            self.assertIn(text, errors)

    def test_lettered_subsection_is_its_section(self):
        block = {**self.block(), 'section': '5.2(d)'}
        self.assertEqual(d.page_errors({'blocks': [block]}, 7, PAGES, 5, {}), [])
        self.assertEqual(block['section'], '5.2')
        for lettered in ('5.2B', '5.2 (B)'):                # iesc1:09 page 9 wrote "9.4.1B" three times
            block = {**self.block(), 'section': lettered}
            self.assertEqual(d.page_errors({'blocks': [block]}, 7, PAGES, 5, {}), [], lettered)
            self.assertEqual(block['section'], '5.2')

    def test_one_missed_quote_is_flagged_not_fatal(self):
        miss = self.block(title='other', quote='momentum is conserved in every collision here')
        self.assertEqual(d.page_errors({'blocks': [self.block(), miss]}, 7, PAGES, 5, {}), [])
        self.assertFalse(miss['quote_found'])

    def test_join_blocks_across_pages(self):
        p1 = {'blocks': [{'type': 'worked_example', 'title': 'Ex', 'problem': 'A block', 'continues': True,
                          'steps': [{'latex': 'a'}]}]}
        p2 = {'blocks': [{'type': 'worked_example', 'title': 'Ex', 'continued': True, 'steps': [{'latex': 'b'}],
                          'answer': '1 J'}, {'type': 'fact', 'title': 'F'}]}
        blocks = d.join_blocks([(6, p1), (7, p2)])
        self.assertEqual([b['id'] for b in blocks], ['B1', 'B2'])
        self.assertEqual(blocks[0]['pages'], [6, 7])
        self.assertEqual([s['latex'] for s in blocks[0]['steps']], ['a', 'b'])
        self.assertEqual(blocks[0]['answer'], '1 J')
        self.assertNotIn('continues', blocks[0])

    def test_outline_ignores_numbered_exercises(self):
        pages = [{'page': 1, 'text': '5.1 INTRODUCTION\ntext'}, {'page': 2, 'text': '5.2 WORK\ntext'},
                 {'page': 3, 'text': 'more'}, {'page': 4, 'text': 'EXERCISES\n5.1\nThe sign of work\n5.12 A rain drop'}]
        self.assertEqual([s['id'] for s in d.make_outline(pages, 5, [])], ['5.1', '5.2'])

    def test_missing_exercise_numbers(self):
        per_page = [(18, {'blocks': [{'type': 'exercise', 'ref': ['Exercise 5.1']},
                                     {'type': 'exercise', 'ref': ['Exercise 5.2']}]}),
                    (19, {'blocks': [{'type': 'exercise', 'ref': ['Exercise 5.4']}]})]
        self.assertEqual(d.missing_exercises(per_page), {18: ['5.3']})


class GapTests(unittest.TestCase):
    def test_context_gaps_go_to_research(self):
        group, blocks = [{'id': 'C1'}], [{'id': 'B1'}]
        gap = {'concept': 'C1', 'blocks': ['B1'], 'type': 'context', 'missing': 'm', 'resolve': 'knowledge'}
        self.assertIn('resolve "research"', ' '.join(d.gap_errors({'gaps': [gap]}, group, blocks)))
        gap.update(resolve='research', research_question='What power does a typical car engine deliver in kW?')
        self.assertEqual(d.gap_errors({'gaps': [gap]}, group, blocks), [])


class AuditTests(unittest.TestCase):
    def test_apply_audit(self):
        concepts = [{'id': 'C1', 'summary': 'wrong'}]
        gaps = [{'id': 'G1', 'concept': 'C1'}, {'id': 'G2', 'concept': 'C1'}]
        additions = [{'id': 'A1', 'gap': 'G1', 'status': 'accepted'}, {'id': 'A2', 'gap': 'G2', 'status': 'accepted'}]
        findings = [{'target': 'C1', 'problem': 'contradicts_book', 'severity': 'error', 'fix': 'right'},
                    {'target': 'A1', 'problem': 'wrong_number', 'severity': 'error'},
                    {'target': 'G2', 'problem': 'not_a_gap', 'severity': 'error'}]
        self.assertEqual(d.apply_audit(findings, concepts, gaps, additions), {'G2'})
        self.assertEqual(concepts[0]['summary'], 'right')
        self.assertEqual([(a['id'], a['status']) for a in additions], [('A1', 'needs_review')])
        self.assertEqual([g['id'] for g in gaps], ['G1'])
        self.assertEqual(d.audit_errors({'findings': [{'target': 'C9', 'problem': 'x', 'severity': 'e'}]},
                                        {'C1'}).__len__(), 3)


class GuardTests(unittest.TestCase):
    def test_shape_errors_become_rejections(self):
        class Fake:
            def call(self, name, prompt, validate=None, **kw):
                return validate({'additions': [{'gap': 'G1', 'calculations': ['2*3']}]})
        client = d.guarded(Fake())
        with self.assertRaises(ValueError):
            client.call('x', 'p', validate=lambda r: d.calculation_errors(r['additions'][0]))


class ConceptTests(unittest.TestCase):
    blocks = [{'id': f'B{n}', 'type': 'fact'} for n in range(1, 5)]
    outline = [{'id': '5.1'}, {'id': '5.2'}]

    def concept(self, n, blocks, **over):
        return {'id': f'C{n}', 'name': f'c{n}', 'sections': ['5.1'], 'depth': 'stated', 'difficulty': 'core',
                'blocks': blocks, **over}

    def test_every_block_covered(self):
        concepts = [self.concept(1, ['B1']), self.concept(2, ['B2']), self.concept(3, ['B9'], sections=['7.1'])]
        errors = ' '.join(d.concept_errors({'concepts': concepts}, self.blocks, self.outline))
        for text in ('not covered: [\'B3\', \'B4\']', 'unknown: [\'B9\']', 'C3: sections'):
            self.assertIn(text, errors)
        concepts = [self.concept(1, ['B1', 'B4']), self.concept(2, ['B2']), self.concept(3, ['B3'])]
        self.assertEqual(d.concept_errors({'concepts': concepts}, self.blocks, self.outline), [])

    def test_an_invented_block_id_is_dropped(self):
        concepts = [{'id': 'C1', 'name': 'a', 'blocks': ['B1', 'B2', 'B99'], 'depth': 'stated', 'difficulty': 'core',
                     'sections': ['5.1']}]
        errors = ' '.join(d.concept_errors({'concepts': concepts}, self.blocks, self.outline, tolerate=1))
        self.assertNotIn('unknown', errors)
        self.assertEqual(concepts[0]['blocks'], ['B1', 'B2'])

    def test_a_few_uncovered_blocks_are_tolerated_then_assigned(self):
        concepts = [self.concept(1, ['B1']), self.concept(2, ['B2']), self.concept(3, ['B3'])]
        self.assertEqual(d.concept_errors({'concepts': concepts}, self.blocks, self.outline, tolerate=0.25), [])
        left = d.uncovered(concepts, self.blocks)
        self.assertEqual([b['id'] for b in left], ['B4'])
        self.assertTrue(d.assign_errors({'assign': {'B4': ['C9']}}, left, concepts, 4))
        self.assertEqual(d.assign_errors({'assign': {'B4': ['C2']}}, left, concepts, 4), [])


class BalancedTest(unittest.TestCase):
    def test_arrows_are_not_delimiters(self):
        self.assertTrue(d.balanced(r'^{1}_{0}\text{n} + ^{235}_{92}\text{U} \rightarrow ^{236}_{92}\text{U}'))
        self.assertTrue(d.balanced(r'A \leftarrow B \Leftrightarrow C \leftrightarrow D'))
        self.assertTrue(d.balanced(r'\left( \frac{a}{b} \right)'))
        self.assertFalse(d.balanced(r'\left( \frac{a}{b}'))
        self.assertFalse(d.balanced(r'\frac{a}{b'))


class ReplyRepairTest(unittest.TestCase):
    def test_latex_value_missing_its_opening_quote(self):
        from scivid.llm import parse_json
        reply = '{"blocks": [{"latex": \\\\text{2-bromobutane} \\\\rightarrow x", "ref": []}]}'
        self.assertEqual(parse_json(reply)['blocks'][0]['ref'], [])


class TextLayerTest(unittest.TestCase):
    def test_quotes_are_found_in_rejected_ocr(self):
        pages = [{'page': 10, 'text': 'a l s s p p iupac', 'ocr_text': 'The name of such branched chain alkyl group is '
                  'placed in parenthesis while naming the compound.'}]
        self.assertEqual(d.kb.find_quote('such branched chain alkyl group is placed in parenthesis', pages, [10]), 10)

    def test_textless_pages_use_ocr(self):
        real = d.ocr_text
        d.ocr_text = lambda pdf, page, folder: 'The law of areas can be understood as a consequence ' * 5
        try:
            pages = d.with_text_layer('x.pdf', [{'page': 1, 'text': '45'}, {'page': 2, 'text': 'word ' * 40}], None)
        finally:
            d.ocr_text = real
        self.assertTrue(pages[0]['ocr'])
        self.assertIn('law of areas', pages[0]['text'])
        self.assertNotIn('ocr', pages[1])

    def test_formula_pages_take_ocr_prose_despite_its_fragments(self):
        real = d.ocr_text
        d.ocr_text = lambda pdf, page, folder: ('In cyclic compounds the bond-line formulas may be given ' * 6 +
                                                'H,C C H CH, ' * 20)
        try:
            pages = d.with_text_layer('x.pdf', [{'page': 4, 'text': 'solution c c ho ch ch ch ch hoch b e e ' * 2}], None)
        finally:
            d.ocr_text = real
        self.assertTrue(pages[0].get('ocr'))


class ChapterContextTest(unittest.TestCase):
    concepts = [{'id': 'C1'}]

    def test_context_blocks_may_stay_unassigned(self):
        left = [{'id': 'B1', 'type': 'fact'}, {'id': 'B3', 'type': 'figure'}, {'id': 'B9', 'type': 'box'}]
        self.assertEqual(d.assign_errors({'assign': {'B1': [], 'B3': [], 'B9': []}}, left, self.concepts, 177), [])

    def test_teaching_blocks_must_be_assigned(self):
        left = [{'id': 'B5', 'type': 'worked_example'}]
        self.assertTrue(d.assign_errors({'assign': {'B5': []}}, left, self.concepts, 177))

    def test_a_survey_chapter_keeps_its_chapter_wide_pieces(self):
        left = [{'id': f'B{n}', 'type': t} for n, t in enumerate(['source', 'fact', 'figure', 'map', 'map', 'box'])]
        self.assertEqual(d.assign_errors({'assign': {b['id']: [] for b in left}}, left, self.concepts, 140), [])

    def test_reference_tables_after_a_chapter_may_stay_unassigned(self):
        left = [{'id': f'B{n}', 'type': 'table'} for n in range(372, 376)]
        self.assertEqual(d.assign_errors({'assign': {b['id']: [] for b in left}}, left, self.concepts, 375), [])

    def test_a_section_no_concept_teaches_is_context(self):
        concepts = [{'id': 'C1', 'sections': ['8.2']}]
        left = [{'id': 'B5', 'type': 'equation', 'section': '8.1'}]
        self.assertEqual(d.assign_errors({'assign': {'B5': []}}, left, concepts, 282), [])
        left = [{'id': 'B9', 'type': 'equation', 'section': '8.2'}]
        self.assertTrue(d.assign_errors({'assign': {'B9': []}}, left, concepts, 282))

    def test_too_many_unassigned(self):
        left = [{'id': f'B{n}', 'type': 'fact'} for n in range(10)]
        self.assertTrue(d.assign_errors({'assign': {b['id']: [] for b in left}}, left, self.concepts, 100))


class MathQuoteTest(unittest.TestCase):
    def test_latex_quotes_are_unverifiable_not_wrong(self):
        self.assertTrue(d.mathy(r'Note that \int \sqrt{x^2 + 2x + 5} dx = \int \sqrt{(x+1)^2 + 4} dx'))
        self.assertFalse(d.mathy('The law of areas can be understood as a consequence'))
        self.assertFalse(d.mathy('Let the speed of the planet at the perihelion be v_p and the distance be r_p'))


class RealPowerTest(unittest.TestCase):
    def test_odd_roots_of_negatives_are_real(self):
        self.assertAlmostEqual(d.evaluate('12*(-1)**(4/3) - 6*(-1)**(1/3)'), 18)
        self.assertAlmostEqual(d.evaluate('(-8)**(1/3)'), -2)
        self.assertAlmostEqual(d.evaluate('2**0.5'), 2 ** 0.5)

    def test_even_roots_of_negatives_are_errors_not_crashes(self):
        with self.assertRaises(ValueError):
            d.evaluate('(-4)**0.5')
        errors = d.calculation_errors({'calculations': [{'expr': '(-4)**0.5', 'value': 2}], 'content': ''})
        self.assertIn('cannot be evaluated', errors[0])

    def test_an_exact_result_too_big_for_a_float_is_an_error_not_a_crash(self):
        errors = d.calculation_errors({'calculations': [{'expr': '10**400', 'value': 1}], 'content': ''})
        self.assertIn('cannot be evaluated', errors[0])


    def test_science_allows_more_gaps_per_concept_than_history(self):
        gap = {'concept': 'C1', 'blocks': ['B1'], 'type': 'intuition', 'resolve': 'knowledge'}
        group, blocks = [{'id': 'C1'}], [{'id': 'B1'}]
        self.assertEqual(d.gap_errors({'gaps': [dict(gap)] * 5}, group, blocks), [])
        self.assertIn('keep the 5', ' '.join(d.gap_errors({'gaps': [dict(gap)] * 6}, group, blocks)))
        history = {**gap, 'type': 'term'}
        self.assertIn('keep the 3', ' '.join(d.gap_errors({'gaps': [history] * 4}, group, blocks,
                                                          humanities_mode=True)))

    def test_science_keeps_three_research_gaps_per_group(self):
        research = [{'concept': 'C1', 'type': 'context', 'resolve': 'research', 'priority': p,
                     'research_question': 'how much ammonia does India make each year'} for p in ('high',) * 4]
        self.assertEqual(len(d.settle_fact_gaps({'gaps': research})['gaps']), 3)
        self.assertEqual(len(d.settle_fact_gaps({'gaps': [dict(g) for g in research]}, humanities_mode=True)['gaps']), 2)


if __name__ == '__main__':
    unittest.main()

