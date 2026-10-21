import unittest

from history_studio import questions

POINTS = [f'P{n:02d}' for n in range(1, 17)]
KINDS = list(questions.KINDS)


def blueprint(points=None):
    points = points or [['P01'], ['P03'], ['P05'], ['P07'], ['P09'], ['P11'], ['P13'], ['P15']]
    return {'ideas': [{'id': f'B{n}', 'idea': 'what the student must understand here', 'points': p,
                       'kind': KINDS[n - 1], 'targets': 'the weak spot this exposes'}
                      for n, p in enumerate(points, 1)]}


class BlueprintTests(unittest.TestCase):
    def test_a_broad_blueprint_passes(self):
        self.assertEqual(questions.blueprint_errors(blueprint(), POINTS), [])

    def test_the_set_must_be_spread_across_the_film(self):
        # Hydrocarbons experiment: seven of eight free questions tested one idea (the peroxide effect)
        narrow = blueprint([['P15'], ['P15'], ['P15'], ['P16'], ['P14'], ['P13'], ['P14'], ['P13']])
        problems = ' '.join(questions.blueprint_errors(narrow, POINTS))
        self.assertIn('more than two ideas', problems)
        self.assertIn('too narrow a part of the film', problems)
        repeated = blueprint()
        repeated['ideas'][1]['kind'] = repeated['ideas'][0]['kind']
        self.assertIn('each kind of question once', ' '.join(questions.blueprint_errors(repeated, POINTS)))
        self.assertIn('narration point ids', ' '.join(questions.blueprint_errors(blueprint([['P99']] * 8), POINTS)))


class QuestionTests(unittest.TestCase):
    def question(self, n=1, **change):
        q = {'id': f'Q{n}', 'blueprint': f'B{n}', 'kind': KINDS[n - 1],
             'stem': 'Propene reacts with HBr without peroxide; which product forms?',
             'options': ['A. 1-bromopropane', 'B. 2-bromopropane', 'C. propane', 'D. no reaction'], 'answer': 'B',
             'explanation': 'The more stable secondary carbocation forms, so bromide adds to the middle carbon.',
             'targets': 'applying the rule backwards', 'difficulty': 'easy',
             'structures': [{'name': '2-bromopropane', 'smiles': 'CC(C)Br', 'formula': 'C3H7Br'}],
             'reaction': {'reactants': ['CC=C', 'Br'], 'products': ['CC(C)Br']}}
        q.update(change)
        return q

    def test_code_checks_chemistry_and_answers(self):
        plan = {'ideas': [blueprint()['ideas'][0]]}
        self.assertEqual(questions.question_errors({'questions': [self.question()]}, plan, True), [])
        wrong_formula = self.question(structures=[{'name': '2-bromopropane', 'smiles': 'CCBr', 'formula': 'C3H7Br'}])
        self.assertIn('not C3H7Br', ' '.join(questions.question_errors({'questions': [wrong_formula]}, plan, True)))
        unbalanced = self.question(reaction={'reactants': ['CC=C'], 'products': ['CC(C)Br']})
        self.assertIn('atoms differ', ' '.join(questions.question_errors({'questions': [unbalanced]}, plan, True)))
        self.assertIn('one option letter', ' '.join(questions.question_errors(
            {'questions': [self.question(answer='E')]}, plan, True)))
        self.assertEqual(questions.question_errors({'questions': [unbalanced]}, plan, False), [])   # not chemistry

    def test_options_are_shuffled_and_the_answer_follows(self):
        q = self.question()
        shuffled = questions.shuffle(q)
        right = next(o for o in shuffled['options'] if o.startswith(shuffled['answer'] + '.'))
        self.assertTrue(right.endswith('2-bromopropane') and not right.endswith('1-bromopropane'))
        self.assertEqual([o[:2] for o in shuffled['options']], ['A.', 'B.', 'C.', 'D.'])
        self.assertEqual(questions.shuffle(q), shuffled)                           # the same order every time


if __name__ == '__main__':
    unittest.main()
