"""The solving rule (user, 2026-10-23).

1. Two students solve the question independently: the film engine's planner (Haiku) and reviewer (Luna).
2. Both reach the official answer: Opus is only the reviewer. It sees the two solutions blind (shuffled, authors
   hidden), checks every step and picks the one to teach from.
3. They disagree, or agree on a wrong answer: Opus solves it itself (it sees their attempts, marked unverified, not
   the key). Opus right: its solution is the one. Opus wrong: the question stops here and needs human review.
Code, not a model, decides what is right: bank.marked compares each answer with the official key.
"""
from __future__ import annotations

import json
import random

from . import bank
from .models import ask

STUDENTS = ('haiku', 'luna')
TEACHER = 'opus'
TYPES = {
    'single': 'Exactly one option (A)-(D) is correct. Answer with that one letter.',
    'multiple': 'One or more options (A)-(D) are correct, and one wrong pick loses marks: judge each option on its '
                'own, true or false with a reason. Answer with all the correct letters, e.g. "AC".',
    'numerical': 'The answer is a number. Give it to two decimal places (or an integer if it is one), no units.',
    'match': 'Match List-I to List-II; exactly one of the options (A)-(D) gives the correct matching. Work out each '
             'entry of List-I, then answer with that one letter.',
}
SOLUTION_SHAPE = (
    'Return {"answer": "<letters or number>", "options": {"A": {"correct": true|false, "why": "..."}, ...} '
    '(omit for numerical), "steps": [{"n": 1, "title": "short", "working": "the reasoning and equations of this '
    'step, in plain text with Unicode maths", "result": "what this step establishes"}], "ideas": ["each physics '
    'principle or law the solution uses"], "check": "one independent sanity check of the result (limits, units, '
    'a special case)"}. Steps are the order a teacher would explain them; each does one thing.')


def question_prompt(q):
    parts = [f'This is JEE Advanced {q["year"]} Paper {q["paper"]}, {q["subject"].upper()} part, question Q.{q["number"]}. '
             f'The images are the question paper pages; they may also show neighbouring questions: use only '
             f'Q.{q["number"]} of the {q["subject"]} part. The text below was extracted from the PDF and may garble '
             f'fractions, subscripts and figures; trust the images.',
             f'Question type: {TYPES.get(q["type"], q["type"])}']
    if q.get('stem'):
        parts.append('Paragraph this question belongs to (extracted text):\n' + q['stem'])
    parts.append('Extracted question text:\n' + q['text'])
    return '\n\n'.join(parts)


def student(q, who):
    task = ('You are a top JEE Advanced student. Solve this question fully and carefully.\n\n' + question_prompt(q) +
            '\n\n' + SOLUTION_SHAPE)
    return ask(who, task, q.get('pages', []), name=f'{q["id"]}-solve')


def review(q, solutions):
    """Both students are right: Opus reviews them blind and picks the one to teach from."""
    order = list(solutions)
    random.Random(q['id']).shuffle(order)
    labelled = {f'S{i + 1}': solutions[who] for i, who in enumerate(order)}
    task = (f'You are an experienced JEE {q["subject"]} teacher. Two students solved the question below independently and '
            f'both reached the official answer ({q["answer"]["raw"]}). A right answer can still hide a wrong step. '
            'Check every step of each solution, then choose the one a student should be taught from: correct at '
            'every step, the governing idea named before the algebra, no gaps, no detours.\n\n' + question_prompt(q) +
            '\n\nSOLUTIONS:\n' + json.dumps(labelled, ensure_ascii=False) +
            '\n\nReturn {"better": "S1"|"S2", "step_errors": {"S1": ["each wrong or unjustified step, with why"], '
            '"S2": [...]}, "why": "one or two sentences", "improvements": ["what the chosen solution should add or '
            'fix before it is taught"]}.')
    value, usage = ask(TEACHER, task, q.get('pages', []), name=f'{q["id"]}-review')
    value['chosen'] = dict(zip(labelled, order)).get(value.get('better'))
    value['labels'] = dict(zip(labelled, order))
    return value, usage


def teacher_solves(q, solutions):
    """The students disagree (or agree on a wrong answer): Opus solves it, seeing their attempts as unverified."""
    order = list(solutions)
    random.Random(q['id']).shuffle(order)
    attempts = {f'S{i + 1}': {'answer': solutions[who].get('answer'), 'steps': solutions[who].get('steps')}
                for i, who in enumerate(order)}
    task = (f'You are an experienced JEE {q["subject"]} teacher. Two students attempted the question below; their attempts '
            'are unverified and at least one is wrong (they may both be). Solve it yourself from first principles; '
            'use their attempts only to spot traps.\n\n' + question_prompt(q) + '\n\nATTEMPTS:\n' +
            json.dumps(attempts, ensure_ascii=False) + '\n\n' + SOLUTION_SHAPE +
            ' Also add "students": {"S1": "where this attempt went wrong, or right", "S2": "..."}.')
    value, usage = ask(TEACHER, task, q.get('pages', []), max_tokens=16000, name=f'{q["id"]}-teacher')
    value['labels'] = {f'S{i + 1}': who for i, who in enumerate(order)}
    return value, usage


def solve(q):
    """Run the rule on one question. Returns a record: status settled | needs_review, and the solution to teach."""
    record = {'id': q['id'], 'type': q['type'], 'key': q['answer']['raw'], 'students': {}, 'usage': {}}
    solutions = {}
    for who in STUDENTS:
        try:
            value, usage = student(q, who)
        except Exception as exc:  # noqa: BLE001 - a failed call is recorded and counts as a wrong answer
            value, usage = {'answer': None, 'error': str(exc)[:300]}, {}
        solutions[who] = value
        record['usage'][who] = usage
        record['students'][who] = {'answer': value.get('answer'), 'right': bank.marked(q['answer'], value.get('answer')),
                                   **({'error': value['error']} if 'error' in value else {})}
    right = [who for who in STUDENTS if record['students'][who]['right']]
    if len(right) == len(STUDENTS):
        verdict, usage = review(q, solutions)
        record['usage']['opus'] = usage
        record.update(route='review', status='settled', teacher=verdict,
                      solution=solutions[verdict['chosen']] if verdict.get('chosen') else solutions[STUDENTS[0]],
                      author=verdict.get('chosen') or STUDENTS[0])
        return record, solutions
    verdict, usage = teacher_solves(q, solutions)
    record['usage']['opus'] = usage
    ok = bank.marked(q['answer'], verdict.get('answer'))
    record.update(route='teacher_solves', teacher={'answer': verdict.get('answer'), 'right': ok,
                                                   'students': verdict.get('students'), 'labels': verdict['labels']},
                  status='settled' if ok else 'needs_review', author='opus' if ok else None,
                  solution=verdict if ok else None)
    return record, {**solutions, 'opus': verdict}
