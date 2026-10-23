"""The solving rule (user, 2026-10-23; calls trimmed the same day).

1. Two students solve the question independently: the film engine's planner (Haiku) and reviewer (Luna).
2. With an official key, code (bank.marked) decides who is right:
   - both right: Opus reviews them blind (shuffled, authors hidden), picks one and returns it improved, in one call.
     The clips are planned by the team: the chosen author drafts, the other student reviews, Opus settles.
   - one right: that student's solution is the one, no Opus; that student alone plans the clips.
   - both wrong: Opus solves it (it sees their attempts, not the key). Right: Opus alone plans the clips. Wrong:
     the question stops here and needs human review.
3. Without a key (older years whose official key is not found), agreement stands in for it and the best status is
   'unverified', never 'settled': the students agree and Opus's review agrees too, or they disagree and Opus's own
   answer matches one of them. Anything else needs human review.
record['planner'] is 'team' or the one model that plans the clips (clips.plan).
"""
from __future__ import annotations

import json
import random
import re

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
    'step, in plain text with Unicode maths (√, ², θ, ω, ×); never LaTeX or backslashes", "result": "what this step establishes"}], "ideas": ["each physics '
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


def same(a, b):
    """Two answers agree: the same option letters, or numbers within 1%."""
    if a is None or b is None:
        return False
    try:
        x, y = float(str(a).strip('[] ')), float(str(b).strip('[] '))
        return abs(x - y) <= 0.01 * max(abs(x), abs(y), 1e-9)
    except ValueError:
        return sorted(set(re.sub(r'[^A-D]', '', str(a).upper()))) == sorted(set(re.sub(r'[^A-D]', '', str(b).upper())))


def review(q, solutions):
    """Both students are right (or, without a key, agree): Opus reviews them blind, picks one and returns it improved."""
    order = list(solutions)
    random.Random(q['id']).shuffle(order)
    labelled = {f'S{i + 1}': solutions[who] for i, who in enumerate(order)}
    known = (f'both reached the official answer ({q["answer"]["raw"]}). A right answer can still hide a wrong step.'
             if q.get('answer') else 'both reached the same answer; there is no official key, so check the answer '
             'itself too.')
    task = (f'You are an experienced JEE {q["subject"]} teacher. Two students solved the question below independently and '
            + known + ' Check every step of each solution, then choose the one a student should be taught from: '
            'correct at every step, the governing idea named before the algebra, no gaps, no detours. Then improve '
            'the chosen solution: fix any wrong or unjustified step and fill gaps, keeping its approach.\n\n' +
            question_prompt(q) + '\n\nSOLUTIONS:\n' + json.dumps(labelled, ensure_ascii=False) +
            '\n\nReturn {"better": "S1"|"S2", "step_errors": {"S1": ["each wrong or unjustified step, with why"], '
            '"S2": [...]}, "why": "one or two sentences", "improvements": ["what you changed"], "agree": true|false '
            '(is their common answer right?), "solution": the improved chosen solution in this shape: ' +
            SOLUTION_SHAPE.removeprefix('Return ') + '}.')
    value, usage = ask(TEACHER, task, q.get('pages', []), max_tokens=16000, name=f'{q["id"]}-review-improve')
    value['chosen'] = dict(zip(labelled, order)).get(value.get('better'))
    value['labels'] = dict(zip(labelled, order))
    return value, usage


def teacher_solves(q, solutions):
    """The students missed the key (or, without one, disagree): Opus solves it, seeing their attempts as unverified."""
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


def solve(q, progress=None):
    """Run the rule on one question. Returns (record, attempts): record status settled | unverified | needs_review,
    the solution to teach and record['planner']. progress(text), when given, hears each step as it happens."""
    say = progress or (lambda text: None)
    key = q.get('answer')
    record = {'id': q['id'], 'type': q['type'], 'key': key['raw'] if key else None, 'students': {}, 'usage': {}}
    solutions = {}
    for who in STUDENTS:
        try:
            value, usage = student(q, who)
        except Exception as exc:  # noqa: BLE001 - a failed call is recorded and counts as a wrong answer
            value, usage = {'answer': None, 'error': str(exc)[:300]}, {}
        solutions[who] = value
        record['usage'][who] = usage
        s = record['students'][who] = {'answer': value.get('answer'),
                                       'right': bank.marked(key, value.get('answer')) if key else None,
                                       **({'error': value['error']} if 'error' in value else {})}
        say(f'Student {who} answered {s["answer"]}' + (
            '' if not key else ': matches the official key' if s['right'] else
            f': does not match the key ({key["raw"]})' if s['answer'] is not None else
            ': no answer (' + str(s.get('error'))[:80] + ')'))
    a, b = (solutions[w].get('answer') for w in STUDENTS)
    right = [who for who in STUDENTS if record['students'][who]['right']] if key else []
    agreed = len(right) == len(STUDENTS) if key else same(a, b)
    if agreed:
        say('Both students ' + ('match the key' if key else 'agree (no official key)') +
            ', so Opus reviews their solutions blind and improves the better one')
        verdict, usage = review(q, solutions)
        record['usage']['opus'] = usage
        chosen = verdict.get('chosen') or STUDENTS[0]
        improved = verdict.get('solution') if isinstance(verdict.get('solution'), dict) else None
        if improved and not (bank.marked(key, improved.get('answer')) if key else same(improved.get('answer'), a)):
            say('Opus\'s improved version changed the answer, so the original is kept')
            improved = None
        status = 'settled' if key else 'unverified' if verdict.get('agree') else 'needs_review'
        say(f'Opus chose {chosen}\'s solution{" and improved it" if improved else ""}: {verdict.get("why", "")}' +
            ('' if key else ' Opus agrees with the answer: unverified (no key).' if status == 'unverified' else
             ' Opus does not agree with the answer, so it stops here for review.'))
        record.update(route='review', status=status, teacher={k: v for k, v in verdict.items() if k != 'solution'},
                      solution=(improved or solutions[chosen]) if status != 'needs_review' else None,
                      author=chosen, improved=bool(improved), planner='team')
        return record, {**solutions, **({'opus': improved} if improved else {})}
    if key and len(right) == 1:
        who = right[0]
        say(f'Only {who} matches the key: its solution is the one, and {who} plans the clips (no Opus)')
        record.update(route='one_right', status='settled', solution=solutions[who], author=who, planner=who)
        return record, solutions
    say('The students ' + ('both missed the key' if key else 'disagree (no official key)') +
        ', so Opus solves it (it sees their attempts' + (', not the key)' if key else ')'))
    verdict, usage = teacher_solves(q, solutions)
    record['usage']['opus'] = usage
    answer = verdict.get('answer')
    ok = bank.marked(key, answer) if key else (same(answer, a) or same(answer, b))
    status = ('settled' if key else 'unverified') if ok else 'needs_review'
    say(f'Opus answered {answer}: ' + (
        ('matches the key' if key else 'agrees with one student: unverified (no key)') + '; Opus plans the clips alone'
        if ok else ('does not match the key either' if key else 'agrees with neither student') +
        ', so the question stops here for review'))
    record.update(route='teacher_solves', teacher={'answer': answer, 'right': ok, 'students': verdict.get('students'),
                                                   'labels': verdict['labels']},
                  status=status, author='opus' if ok else None, solution=verdict if ok else None,
                  planner='opus' if ok else None)
    return record, {**solutions, 'opus': verdict}
