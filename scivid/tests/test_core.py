import json

import pytest
from pydantic import ValidationError

from scivid import audio, curriculum, lesson
from scivid.contract import LessonRequest
from scivid.jobs import Store
from scivid.settings import Settings


def test_request_needs_a_grounding_source():
    with pytest.raises(ValidationError, match='needs a source'):
        LessonRequest(topic='Why pendulums keep time', class_level=7)
    with pytest.raises(ValidationError, match='class level'):
        LessonRequest(topic='Why pendulums keep time', web_research=True)
    assert LessonRequest(topic='Why pendulums keep time', chapter='gecu1:08').chapter == 'gecu1:08'
    assert LessonRequest(topic='Why pendulums keep time', web_research=True, class_level=7).web_research


def plan(**scene):
    base = {'description': 'A pendulum on a stand at rest.',
            'objects': [{'id': 'pendulum', 'description': 'string and bob', 'moves': True},
                        {'id': 'stand', 'description': 'wooden stand', 'moves': False}], 'paths': []}
    base.update(scene)
    demo = [{'id': 'd1', 'watch': 'the pendulum swings to and fro steadily', 'proves': 'it keeps time'}]
    return {'chapters': [{'id': 'c1', 'title': 'Hook', 'objective': 'x', 'route': 'image', 'source_ids': ['N01'],
                          'scene': base, 'demonstrations': demo},
                         {'id': 'c2', 'title': 'Graph', 'objective': 'y', 'route': 'diagram', 'source_ids': ['N01'],
                          'demonstrations': demo,
                          'diagram': {'layout': 'single', 'elements': [
                              {'id': 'work', 'type': 'equation_steps', 'steps': ['T = t / n', 'T = 2\\,\\text{s}']},
                              {'id': 'nl', 'type': 'number_line', 'min': 0, 'max': 4, 'step': 1, 'marks': []}]}}]}


def test_plan_rules():
    diagram_only = plan()
    diagram_only['chapters'][0] = {**diagram_only['chapters'][1], 'id': 'c1'}
    assert lesson.plan_errors(diagram_only, {'N01'}, 'science') == []
    assert any('route must be "diagram"' in e for e in lesson.plan_errors(plan(), {'N01'}, 'science'))
    assert any('cite' in e for e in lesson.plan_errors(diagram_only, {'N02'}, 'science'))
    text_only = plan()
    text_only['chapters'][1]['diagram']['elements'] = [{'id': 'rule', 'type': 'note', 'text': 'Time period is constant'}]
    assert any('visual element' in e for e in lesson.plan_errors(text_only, {'N01'}, 'science'))


def test_script_cues_must_quote_narration_and_name_real_objects():
    p = plan()
    script = {'chapters': [
        {'id': 'c1', 'points': [{'id': 'c1p1', 'narration': 'Watch the pendulum swing to and fro, steady as a clock.'}],
         'cues': [{'verb': 'swing', 'object': 'pendulum', 'point': 'c1p1', 'phrase': 'swing to and fro'},
                  {'verb': 'label', 'object': 'stand', 'text': 'Stand', 'point': 'c1p1', 'phrase': 'Watch the'}]},
        {'id': 'c2', 'points': [{'id': 'c2p1', 'narration': 'Now we draw the graph of time against length.'}],
         'cues': [{'verb': 'next_step', 'target': 'work', 'point': 'c2p1', 'phrase': 'draw the graph'}]}]}
    assert lesson.script_errors(script, p) == []
    script['chapters'][0]['cues'][0]['phrase'] = 'swings back'
    script['chapters'][0]['cues'][1]['verb'] = 'swing'
    errors = lesson.script_errors(script, p)
    assert any('copied exactly' in e for e in errors)
    assert any('only moving objects' in e for e in errors)


def test_locate_phrase_in_aligned_words():
    words = [{'id': f'w{i}', 'word': w, 'start': i * .5, 'end': i * .5 + .4, 'point_id': 'c1p1'}
             for i, w in enumerate('Watch the pendulum’s bob swing, to and fro.'.split())]
    assert audio.locate(words, 'c1p1', "pendulum's bob") == (1.0, 1.9)
    assert audio.locate(words, 'c1p1', 'to and fro') == (2.5, 3.9)
    with pytest.raises(ValueError):
        audio.locate(words, 'c1p1', 'not there')


def test_curriculum_search_finds_the_pendulum_passage():
    chapter = curriculum.find(Settings().ncert_root, 'gecu1:08')
    hits = curriculum.search(chapter, 'simple pendulum oscillation time period', limit=3)
    assert hits and 'pendulum' in hits[0]['text'].lower()
    assert hits[0]['id'].startswith('gecu1:08/p')


def test_redo_requeues_one_chapter(tmp_path):
    store = Store(tmp_path)
    req = LessonRequest(topic='Pendulums', chapter='gecu1:08').model_dump()
    lesson_row = store.submit(req, Settings())
    folder = store.directory(lesson_row['id'])
    (folder / 'chapters-status.json').write_text(json.dumps([{'id': 'c1', 'title': 't', 'route': 'image',
                                                              'status': 'ready', 'detail': ''}]))
    (folder / 'chapters' / 'c1' / 'scene').mkdir(parents=True)
    (folder / 'chapters' / 'c1' / 'scene' / 'scene.json').write_text('{}')
    (folder / 'chapters' / 'c1' / 'chapter.mp4').write_text('x')
    store.set(lesson_row['id'], status='succeeded')
    redone = store.redo(lesson_row['id'], 'c1')
    assert redone['status'] == 'queued'
    assert not (folder / 'chapters' / 'c1' / 'scene' / 'scene.json').exists()
    assert json.loads((folder / 'chapters' / 'c1' / 'redo.json').read_text())['count'] == 1
    with pytest.raises(ValueError):
        store.redo(lesson_row['id'], 'c1')


def test_number_check_flags_wrong_arithmetic():
    class Stub:
        def call(self, name, prompt, **kw):
            return {'calculations': [
                {'chapter': 'c1', 'words': 'twenty divided by ten is two', 'expression': '20/10', 'stated': 2, 'tolerance': .001},
                {'chapter': 'c2', 'words': 'about 314 metres', 'expression': '2*pi*50', 'stated': 314, 'tolerance': .02},
                {'chapter': 'c3', 'words': 'three times four is eleven', 'expression': '3*4', 'stated': 11, 'tolerance': .001}]}
    script = {'chapters': [{'id': 'c1', 'points': [{'id': 'c1p1', 'narration': 'x'}]}]}
    wrong = lesson.check_numbers(Stub(), script, 0)
    assert len(wrong) == 1 and 'eleven' in wrong[0]['problem']


def test_diagram_vocabulary_checks():
    from scivid import diagram_spec as ds
    good = {'layout': 'single', 'elements': [
        {'id': 'vt', 'type': 'graph', 'x': {'min': 0, 'max': 10, 'step': 2}, 'y': {'min': 0, 'max': 20, 'step': 5},
         'series': [{'id': 'car', 'function': '2*x'}]},
        {'id': 'tri', 'type': 'shape', 'kind': 'right_triangle', 'a': 3, 'b': 4, 'vertices': ['A', 'B', 'C']}]}
    assert ds.spec_errors(good) == []
    bad = json.loads(json.dumps(good))
    bad['elements'][0]['series'][0]['function'] = '5*x'          # leaves the y axis
    bad['elements'][1] = {'id': 'tri', 'type': 'shape', 'kind': 'triangle', 'a': 1, 'b': 2, 'c': 9}
    errors = ds.spec_errors(bad)
    assert any('outside the y range' in e for e in errors) and any('cannot make a triangle' in e for e in errors)
    assert ds.latex_errors('\\input{/etc/passwd}') and not ds.latex_errors('\\frac{20}{10} = 2')
    assert ds.cue_errors({'verb': 'plot', 'target': 'vt.car'}, good) == []
    assert ds.cue_errors({'verb': 'plot', 'target': 'vt.bus'}, good)
    assert ds.cue_errors({'verb': 'count', 'target': 'tri'}, good)
    pts = ds.shape_points({'kind': 'triangle', 'vertices': ['A', 'B', 'C'], 'sides': {'AB': 5, 'BC': 3, 'CA': 4}})
    assert [round(__import__('math').dist(pts[i], pts[(i + 1) % 3]), 9) for i in range(3)] == [5, 3, 4]


def test_model_registry_rules(tmp_path):
    from scivid import models
    reg = models.Registry(tmp_path, lambda: {'connections': {}, 'steps': {}})
    local = reg.upsert({'type': 'openai_chat', 'label': 'Local text', 'url': 'http://127.0.0.1:9/v1', 'model': 'm'})
    router = reg.upsert({'type': 'openrouter', 'label': 'Router', 'url': 'https://openrouter.ai/api/v1',
                         'model': 'x/y', 'vision': True, 'api_key': 'sk-secret-123'})
    claude = reg.upsert({'type': 'anthropic', 'label': 'Claude', 'url': 'https://api.anthropic.com',
                         'model': 'claude-opus-5-5', 'api_key': 'sk-ant-secret'})
    with pytest.raises(ValueError, match='images'):
        reg.assign({'picture_check': local})                    # text-only connection on an image step
    with pytest.raises(ValueError, match='only works with'):
        reg.assign({'web_research': claude})                    # research agent needs a local endpoint
    reg.assign({'picture_check': claude, 'plan': router, 'web_research': local})
    with pytest.raises(ValueError, match='In use'):
        reg.delete(claude)
    public = json.dumps(reg.public())
    assert 'sk-secret-123' not in public and 'sk-ant-secret' not in public
    assert reg.public()['connections'][router]['key_set'] is True
    snapshot = reg.snapshot()
    assert type(models.client_for(snapshot, 'plan', tmp_path, tmp_path)).__name__ == 'Chat'
    assert type(models.client_for(snapshot, 'picture_check', tmp_path, tmp_path)).__name__ == 'Claude'


def test_visual_rules():
    p = plan()
    slide = json.loads(json.dumps(p))
    slide['chapters'][1]['diagram']['elements'] = [{'id': 'n', 'type': 'note', 'text': 'Rotation is spinning.'},
                                                   {'id': 'c', 'type': 'cards', 'items': [{'id': 'a', 'title': 'x', 'value': '1'},
                                                                                          {'id': 'b', 'title': 'y', 'value': '2'}]}]
    errors = lesson.plan_errors(slide, {'N01'}, 'science')
    assert any('visual element' in e for e in errors) and any('one text element' in e for e in errors)
    nodemo = json.loads(json.dumps(p))
    nodemo['chapters'][0]['demonstrations'] = []
    assert any('demonstrations' in e for e in lesson.plan_errors(nodemo, {'N01'}, 'science'))
    script = {'chapters': [
        {'id': 'c1', 'points': [{'id': 'c1p1', 'narration': 'Look at this pendulum standing still on its stand.'},
                                {'id': 'c1p2', 'narration': 'Now it swings to and fro.'}],
         'cues': [{'verb': 'label', 'object': 'stand', 'text': 'Stand', 'point': 'c1p1', 'phrase': 'Look at this'},
                  {'verb': 'swing', 'object': 'pendulum', 'point': 'c1p2', 'phrase': 'swings to and fro'}]},
        {'id': 'c2', 'points': [{'id': 'c2p1', 'narration': 'Now we draw the graph of time against length.'}],
         'cues': [{'verb': 'next_step', 'target': 'work', 'point': 'c2p1', 'phrase': 'draw the graph'}]}]}
    assert any('first sentence' in e for e in lesson.script_errors(script, p))


def test_phrases_across_dashes():
    text = 'A stone is racing round on a string\u2014what happens when its lifeline snaps? Now snap! The string breaks.'
    assert audio.phrase_in_text(text, 'A stone is racing round on a string')
    assert audio.phrase_in_text(text, 'what happens when')
    assert audio.phrase_in_text(text, 'Now snap! The string breaks')
    words = [{'id': f'w{i}', 'word': w, 'start': float(i), 'end': i + .5, 'point_id': 'p'} for i, w in enumerate(text.split())]
    assert audio.locate(words, 'p', 'on a string') == (5.0, 7.5)      # "string\u2014what" is aligned word 7


def test_reworded_phrases_are_patched():
    script = {'chapters': [{'id': 'c1', 'points': [{'id': 'c1p1', 'narration':
              'A stone is racing round on a string. Now snap! The string breaks and it flies off.'}],
              'cues': [{'verb': 'release', 'object': 'stone', 'point': 'c1p1', 'phrase': 'now the string snaps and breaks'},
                       {'verb': 'move_along', 'object': 'stone', 'point': 'c1p1', 'phrase': 'A stone racing round on a string'},
                       {'verb': 'label', 'object': 'stone', 'point': 'c1p1', 'phrase': 'completely different words here'}]}]}
    assert lesson.repair_phrases(script) == 1          # only the strong match is patched without a judge
    cues = script['chapters'][0]['cues']
    assert audio.phrase_in_text(script['chapters'][0]['points'][0]['narration'], cues[1]['phrase'])
    assert cues[2]['phrase'] == 'completely different words here'


def test_speakable_units():
    assert audio.speakable('a = v²/r, about 9.8 m/s²; speed 5 m/s') == \
        'a equals v squared over r, about nine point eight metres per second squared; speed five metres per second'
    assert audio.speakable('the stone’s path, 30°C and 50%') == "the stone's path, thirty degrees Celsius and fifty percent"
    assert audio.speakable('It moves fast. Is it?') == 'It moves fast. Is it?'
    assert audio.speakable('speed in metres per second, or m/s; mass in kg') == 'speed in metres per second; mass in kilograms'
    assert audio.speakable('radius in metres, or m; force in newtons, or N.') == 'radius in metres; force in newtons.'
    assert audio.speakable('In the 1600s, 2 s later') == 'In the sixteen hundreds, two seconds later'


def test_spoken_form_has_only_heard_words():
    from scivid.spoken import leftovers, spoken
    cases = {
        'Newton published in 1687; by 1905 Einstein': 'Newton published in sixteen eighty-seven; by nineteen oh five Einstein',
        'a² + 2ab + b², then b² - 4ac in 3D': 'a squared plus two times a times b plus b squared, then b squared minus four times a times c in three-D',
        'minus two a b cosine c': 'minus two times a times b cosine c',
        'survival is exp of minus five over two point two': 'survival is e to the power of minus five over two point two',
        'v = sqrt(2gh) or sqrt of two': 'v equals the square root of (two times g times h) or the square root of two',
        'It costs ₹1,500 or $2.5 million.': 'It costs one thousand five hundred rupees or two point five million dollars.',
        'For our 3-4-5 triangle, 9 plus 16 is 25, and': 'For our three four five triangle, nine plus sixteen is twenty-five, and',
        'from 5-10 km at -40 °C': 'from five to ten kilometres at minus forty degrees Celsius',
        'θ ≈ 30°, so sin θ = 0.5': 'theta is approximately thirty degrees, so sine theta equals zero point five',
        'c = 3 × 10^8 m/s, e.g. light': 'c equals three times ten to the power eight metres per second, for example light',
        'About 1/2 or 3/4 of it, the 21st time, 1 m': 'About one half or three quarters of it, the twenty-first time, one metre',
        'the 1990s and the 80s': 'the nineteen nineties and the eighties',
    }
    for text, said in cases.items():
        assert spoken(text) == said
        assert spoken(said) == said and not leftovers(said)


def test_scene_text_is_one_frozen_moment():
    from scivid import imageworld
    text = ('One frozen moment viewed from above: a hand holds a taut string, ready to be whirled. The animation '
            'shows the circle, then the release.')
    assert imageworld.frozen(text) == 'One frozen moment viewed from above: a hand holds a taut string, ready to be whirled.'
    assert imageworld.is_setting({'id': 'rink', 'description': 'A skating-rink floor.', 'moves': False})
    assert not imageworld.is_setting({'id': 'roller_skater', 'description': 'A skater on the rink.', 'moves': True})


def test_levels_up_to_12_and_open():
    assert LessonRequest(topic='Electromagnetic induction', web_research=True, class_level=12).class_level == 12
    assert LessonRequest(topic='Maxwell equations', web_research=True, class_level='open').class_level == 'open'
    assert LessonRequest(topic='Why pendulums keep time', chapter='gecu1:08', class_level='open').class_level == 'open'
    with pytest.raises(ValidationError, match='6 to 12'):
        LessonRequest(topic='Electromagnetic induction', web_research=True, class_level=13)
    assert 'undergraduate' in lesson.audience('open') and lesson.audience(11) == 'Class 11'
    assert lesson.TONE['open'] and lesson.TONE[12]


def test_open_level_may_skip_sources():
    r = LessonRequest(topic='Maxwell equations and light', class_level='open')
    assert not r.chapter and not r.web_research
    with pytest.raises(ValidationError, match='school-level'):
        LessonRequest(topic='Maxwell equations and light', class_level=12)
    p = plan()
    p['chapters'][0] = {**p['chapters'][1], 'id': 'c1'}
    for c in p['chapters']:
        c['source_ids'] = []
    assert lesson.plan_errors(p, set(), 'science') == []          # nothing to cite when no sources were gathered
    assert lesson.evidence_text([]).startswith('NONE')


def coded_plan():
    demo = [{'id': 'd1', 'watch': 'two balances grow apart year by year', 'proves': 'compounding pulls ahead'}]
    visual = ('Left: axes with years 0 to 20 and balance; a red line and a cyan curve draw together with live '
              'readouts. Right: the gap shaded amber grows.')
    return {'chapters': [{'id': f'c{i}', 'title': 't', 'objective': 'o', 'route': 'coded', 'complexity': tier,
                          'source_ids': [], 'demonstrations': demo, 'visual': visual}
                         for i, tier in ((1, 'routine'), (2, 'involved'))],
            'theme': {'background': '#0b1220', 'accent': '#ffc768', 'text': '#edf3ff'}}


def test_slide_and_history_chapters():
    p = coded_plan()
    p['chapters'].append({'id': 'c3', 'title': 'Who found it', 'objective': 'o', 'route': 'slide', 'history': True,
                          'source_ids': [], 'demonstrations': [],
                          'visual': 'A picture card of an old counting house, then a three-step flow card.'})
    assert lesson.plan_errors(p, set(), 'maths', 'coded', history=True) == []
    assert any('did not ask for historical context' in e for e in lesson.plan_errors(p, set(), 'maths', 'coded'))
    p['chapters'][0]['history'] = True
    assert any('always slides' in e for e in lesson.plan_errors(p, set(), 'maths', 'coded', history=True))
    p['chapters'][0]['history'] = False
    p['theme']['background'] = '#f0f0f0'
    assert any('dark' in e for e in lesson.plan_errors(p, set(), 'maths', 'coded', history=True))
    p['theme']['background'] = '#0b1220'
    script = {'chapters': [
        {'id': 'c1', 'points': [{'id': 'c1p1', 'narration': 'Two savers start with one hundred rupees each.'}],
         'cues': [{'point': 'c1p1', 'phrase': 'Two savers', 'show': 'two cyan bars of 100 rise side by side'}]},
        {'id': 'c2', 'points': [{'id': 'c2p1', 'narration': 'Watch the gap grow over twenty years.'}],
         'cues': [{'point': 'c2p1', 'phrase': 'Watch the gap grow', 'show': 'both curves draw and the gap shades amber'}]},
        {'id': 'c3', 'points': [{'id': 'c3p1', 'narration': 'Merchants kept interest tables for centuries.'},
                                {'id': 'c3p2', 'narration': 'Each year the interest joins the money.'}],
         'slides': [{'point': 'c3p1', 'kind': 'image', 'heading': 'Interest tables', 'summary': 'Merchants computed growth by hand.',
                     'banner': 'History', 'picture': 'A dim old counting house with ledgers, an abacus and coins on a '
                     'wooden desk lit by a window, merchants as small generic figures in the background.'},
                    {'point': 'c3p2', 'kind': 'flow', 'heading': 'One year of growth',
                     'labels': ['Start', 'Add interest', 'New balance'],
                     'details': ['P rupees', 'P times r', 'P(1+r)'],
                     'reveal': ['Each year', 'the interest', 'joins the money']}]}]}
    assert lesson.script_errors(script, p) == []
    script['chapters'][2]['slides'][1]['details'] = ['P rupees']
    script['chapters'][2]['slides'][0]['picture'] = 'coins'
    errors = lesson.script_errors(script, p)
    assert any('as many details' in e for e in errors) and any('15-60 words' in e for e in errors)
    from scivid import slides
    times = slides.scene_times([{'start': 0.3}, {'start': 4.0}], 7.5, 30)
    assert times == [(0, 120), (120, 225)]
    data = slides.timeline(p, p['chapters'][2], script['chapters'][2]['slides'], ['/x.png', None], times, 30)['data']
    assert data['durationInFrames'] == 225 and data['scenes'][0]['src'] == '/x.png' and 'src' not in data['scenes'][1]
    assert data['creativeBrief']['theme'] == p['theme']
    words = [{'word': w, 'start': 4.0 + 0.5 * i, 'end': 4.4 + 0.5 * i, 'point_id': 'c3p2'}
             for i, w in enumerate('Each year the interest joins the money.'.split())]
    card = script['chapters'][2]['slides'][1]
    assert slides.reveal_frames(card, 120, {'words': words}, 30) == [0, 30, 60]     # 4.0 s, 5.0 s, 6.0 s
    script['chapters'][2]['slides'][1]['reveal'] = ['Each year', 'the money grows']
    assert any('reveal' in e for e in lesson.script_errors(script, p))


def test_coded_plan_and_cue_rules():
    p = coded_plan()
    assert lesson.plan_errors(p, set(), 'maths', 'coded') == []
    p['chapters'][1]['complexity'] = 'hard'
    p['chapters'][0]['visual'] = 'a graph'
    errors = lesson.plan_errors(p, set(), 'maths', 'coded')
    assert any('complexity' in e for e in errors) and any('storyboard' in e for e in errors)
    script = {'chapters': [
        {'id': 'c1', 'points': [{'id': 'c1p1', 'narration': 'Two savers start with one hundred rupees each.'},
                                {'id': 'c1p2', 'narration': 'After two years they differ by one rupee.'}],
         'cues': [{'point': 'c1p1', 'phrase': 'Two savers', 'show': 'two cyan bars of 100 rise side by side'},
                  {'point': 'c1p2', 'phrase': 'differ by one rupee', 'show': 'readout 120 vs 121 appears'}]},
        {'id': 'c2', 'points': [{'id': 'c2p1', 'narration': 'Watch the gap grow over twenty years.'}],
         'cues': [{'point': 'c2p1', 'phrase': 'Watch the gap grow', 'until': 'twenty years',
                   'show': 'both curves draw across twenty years and the gap shades amber'}]}]}
    assert lesson.script_errors(script, coded_plan()) == []
    script['chapters'][0]['cues'] = script['chapters'][0]['cues'][1:]
    errors = lesson.script_errors(script, coded_plan())
    assert any('every narration point' in e for e in errors) and any("first words" in e for e in errors)


SCENE = """import manim as m
import numpy as np
import math
from scene_kit import begin, at, finish, text, tex, arrow, polyline, BG, WHITE, CYAN, GREEN, RED, AMBER, VIOLET, GREY


class ChapterScene(m.Scene):
    def construct(self):
        begin(self, "Two savers")
        at(self, 0.2)
        bar = m.Rectangle(width=1, height=2, color=CYAN).move_to([-2, 0, 0])
        self.play(m.GrowFromEdge(bar, m.DOWN), run_time=1)
        at(self, 2.0)
        self.play(m.Write(tex(r"P(1+r)^2").move_to([2, 0, 0])), run_time=1)
        finish(self, 4.0)
"""


def test_scene_code_rules():
    from scivid.scene_check import geometry_defects, validate_code
    validate_code(SCENE)
    with pytest.raises(ValueError, match='at\\(self'):
        validate_code(SCENE.replace('at(self, 0.2)', 'pass').replace('at(self, 2.0)', 'pass'))
    with pytest.raises(ValueError, match='Import only'):
        validate_code('import os\n' + SCENE)
    with pytest.raises(ValueError, match='self.wait'):
        validate_code(SCENE.replace('at(self, 2.0)', 'at(self, 2.0); self.wait(1)'))
    a = {'text': 'A', 'min': [0, 0], 'max': [1, 1]}
    b = {'text': 'B', 'min': [.5, .5], 'max': [1.5, 1.5]}
    samples = [{'time': t / 10, 'labels': [a, b]} for t in range(0, 15, 3)]
    found = geometry_defects({'samples': samples, 'late': [{'cue_time': 2.0, 'reached_at': 3.1}],
                              'duration': 5, 'elapsed': 5})
    assert any('overlap' in d for d in found) and any('lags the narration' in d for d in found)


def test_presets_freeze_a_configuration(tmp_path):
    from scivid import models
    r = models.Registry(tmp_path, lambda: {'connections': {
        'a': {'type': 'openai_chat', 'label': 'A', 'url': 'http://a/v1', 'model': 'x', 'vision': True},
        'b': {'type': 'openai_chat', 'label': 'B', 'url': 'http://b/v1', 'model': 'y', 'vision': True}}, 'steps': {}})
    r.save(r.load())
    r.assign({'plan': 'b'})
    pid = r.save_preset('Bench', 'reference', True)
    r.assign({'plan': 'a'})
    r.set_options({'scene_route': 'diagram'})
    assert r.public()['active_preset'] is None
    snap = r.snapshot(pid)
    assert snap['steps']['plan'] == 'b' and snap['options']['scene_route'] == 'coded' and snap['preset']['label'] == 'Bench'
    assert r.load()['steps']['plan'] == 'a'          # choosing a preset per lesson leaves the settings alone
    r.apply_preset(pid)
    assert r.public()['active_preset'] == pid
    with pytest.raises(ValueError):
        r.set_options({'scene_route': 'image'})


def test_speakable_numbers_whisper_can_match():
    assert audio.speakable('The perimeter is two n sine of pi over n, about two pi.') == \
        'The perimeter is two times n sine of pi over n, about two pi.'
    assert audio.speakable('so its slope is nonzero') == 'so its slope is non-zero'
    assert audio.speakable('Plan A has two a day') == 'Plan A has two a day'


def test_review_loop_keeps_log_and_skips_same_model_escalation(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from scivid import coded, review
    renders = []
    monkeypatch.setattr(coded, 'validate_code', lambda code: None)
    monkeypatch.setattr(coded, 'contact_sheet', lambda video, moments, out: out)
    def fake_render(settings, work, code, duration, background=None):
        renders.append(code)
        return Path(work) / 'chapter.mp4', {}
    monkeypatch.setattr(coded, 'render', fake_render)
    prompts, logs = [], []
    perfect = lambda kind: {'scores': {c['id']: {'score': 3} for c in review.criteria(kind)}}
    wrong = perfect('scene_content')
    wrong['scores']['numbers'] = {'score': 1, 'reason': 'counter wrong', 'fix': 'x', 'pass': True}  # a model "pass" is ignored
    content_replies = iter([wrong, wrong, perfect('scene_content')])

    class Model:
        def __init__(self, step):
            self.step = step
        def call(self, tag, prompt, **kw):
            prompts.append((self.step, prompt))
            if self.step.startswith('scene_code'):
                if tag.startswith('code-'):
                    return {'code': 'v1'}
                if tag.endswith('-1'):
                    return {'edits': [{'old': 'v1', 'new': 'v2'}], 'notes': ['fixed counter']}
                return {'disputes': [{'finding': 'counter wrong', 'reason': 'it resets for each run'}]}
            if self.step == 'content_review':
                return next(content_replies)
            return perfect('scene_frames')
    job = SimpleNamespace(settings=SimpleNamespace(code_attempts=4), log=logs.append,
                          chapter_status=lambda *a: None, llm=Model,
                          models={'steps': {f'scene_code_{t}': 'haiku' for t in coded.TIERS}})
    chapter = {'id': 'c1', 'title': 'T', 'complexity': 'routine'}
    sc = {'points': [{'id': 'c1p1', 'narration': 'Watch.'}]}
    timing = {'points': [{'point_id': 'c1p1', 'start': 0, 'end': 3}]}
    cues = [{'phrase': 'Watch', 'start': 0.2, 'end': 2.2, 'show': 'counter'}]
    video, record = coded.code_chapter(job, {'title': 'L'}, chapter, sc, timing, cues, 3.0, '', tmp_path)
    assert record['attempts'] == 3 and renders == ['v1', 'v2']          # the dispute round reused the v2 render
    assert not any('moving up' in line for line in logs)                  # every tier is the same model
    last_review = [p for step, p in prompts if step == 'content_review'][-1]
    assert 'EARLIER REVIEW ROUNDS' in last_review and 'it resets for each run' in last_review
    assert 'fixed counter' in last_review


def test_review_pass_fail_is_owned_by_code():
    from scivid import review
    scores = {c['id']: {'score': 3} for c in review.criteria('scene_content')}
    scores['sync'] = {'score': 2, 'reason': 'cue k2 lands half a second early', 'fix': 'move at()'}
    result = review.decide('scene_content', {'pass': False, 'scores': scores})
    assert result['pass'] and [n['criterion'] for n in result['notes']] == ['sync']      # a 2 is a note, not a retry
    scores['science'] = {'score': 2, 'reason': 'illustrative decay constant', 'fix': 'derive it'}
    assert review.decide('scene_content', {'scores': scores})['pass']        # correct but simplified: a note
    scores['science'] = {'score': 1, 'reason': 'arrow points outward', 'fix': 'point it inward'}
    result = review.decide('scene_content', {'pass': True, 'scores': scores})
    assert not result['pass'] and [f['criterion'] for f in result['failed']] == ['science']   # any real error is <= 1
    assert 'at most 1' in review.prompt('scene_content')
    try:
        review.check('scene_content')({'scores': {**scores, 'numbers': {'score': 1}}})
        raise AssertionError('a low score without a reason must be rejected')
    except ValueError as exc:
        assert 'reason' in str(exc)
    review.configure({'scene_content': {'science': 1}})
    try:
        assert review.decide('scene_content', {'scores': scores})['pass']                 # global minimums apply
    finally:
        review.configure({})
    assert review.clean_rules({'scene_content': {'science': 2, 'sync': 1}}) == {'scene_content': {'sync': 1}}
    failed = review.decide('scene_content', {'scores': scores})
    review.overrule({'decision': failed}, 'science', 'arbiter: the arrow is right')
    assert failed['pass'] and failed['notes'][-1]['overruled'].startswith('arbiter')
    assert [c['id'] for c in review.criteria('plan', 'coded')] == ['accuracy', 'order', 'coverage', 'form', 'complexity']
    assert 'Return {"scores"' in review.prompt('picture') and 'no_text' in review.prompt('picture')


def test_review_frames_are_taken_at_rest():
    from scivid.coded import at_rest
    cues = [{'start': 0.2, 'end': 2.2}, {'start': 3.9, 'end': 8.0}, {'start': 9.0, 'end': 12.0}]
    plays = [[0.0, 0.4], [0.8, 1.4], [1.4, 2.3], [3.9, 5.5], [12.6, 13.0]]     # the last play is finish()'s fade-out
    assert at_rest(cues, 0, plays, 13.0) == 2.5            # after the transform ends, not mid-morph at 1.9
    assert at_rest(cues, 1, plays, 13.0) == 5.7
    assert at_rest(cues, 2, plays, 13.0) == 0.85 * 3 + 9.0  # no motion recorded: late in the cue's window
    gap = [{'start': 2.63, 'end': 4.63}, {'start': 10.47, 'end': 12.5}]
    moves = [[2.63, 2.9], [2.9, 4.6], [6.2, 7.43]]              # the last one is a fade-out between the cues
    assert round(at_rest(gap, 0, moves, 30.0), 2) == 4.8      # photographed after the ball, before the fade


def test_pictures_are_scenes_not_icons():
    from scivid import slides
    points = [{'id': 'c6p1'}]
    card = {'point': 'c6p1', 'kind': 'image', 'heading': 'Step one', 'summary': 'Take the difference.',
            'picture': 'A single outline block drawn in thin cyan strokes beside a faint outline of a second block, '
                       'on a plain navy background with flat lighting.'}
    assert any('real-world scene' in e for e in slides.slide_errors({'id': 'c6', 'slides': [card]}, points))
    card['picture'] = ('A market stall in Pune at dusk where a shopkeeper stacks fifteen crates of mangoes, '
                       'warm lamp light, people as small generic figures.')
    assert slides.slide_errors({'id': 'c6', 'slides': [card]}, points) == []
    p = coded_plan()
    p['theme']['picture_style'] = 'Flat outline-only pictograms drawn with a single cyan stroke.'
    assert any('picture_style' in e for e in lesson.plan_errors(p, set(), 'maths', 'coded'))


def test_voice_adapter_forwards_and_answers_housekeeping():
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import httpx
    from scivid import voice_proxy
    seen = []

    class Remote(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append(('GET', self.path))
            body = _json.dumps({'ok': True, 'model_loaded': 'en_indian', 'active_job': False}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            data = self.rfile.read(int(self.headers['Content-Length']))
            seen.append(('POST', self.path, data))
            body = b'{"accepted": true}' if self.path != '/unload' else b'{"ok": true, "unload_disabled": true}'
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    remote = ThreadingHTTPServer(('127.0.0.1', 0), Remote)
    threading.Thread(target=remote.serve_forever, daemon=True).start()
    try:
        with voice_proxy.adapter(f'http://127.0.0.1:{remote.server_address[1]}') as base:
            assert httpx.get(base + '/health').json()['model_loaded'] == 'en_indian'
            assert httpx.post(base + '/render-batch', json={'job_id': 'j1'}).json() == {'accepted': True}
            assert httpx.post(base + '/unload').json() == {'ok': True, 'model_loaded': None}       # never reaches remote
            assert httpx.get(base + '/image/api/status').json()['state'] == 'unloaded'              # local image kept
        assert [s[:2] for s in seen] == [('GET', '/health'), ('POST', '/render-batch')]
        assert _json.loads(seen[1][2]) == {'job_id': 'j1'}
    finally:
        remote.shutdown()


def test_negated_mentions_do_not_count_as_asking_for_icons():
    from scivid.slides import non_scene_words
    assert non_scene_words('Realistic photographic-style illustration of 19th-century laboratories, natural light, '
                           'and no icons, pictograms, line art or diagrams.') == []
    assert non_scene_words('Realistic painted scenes, never icons; true materials. Avoid diagrams.') == []
    assert non_scene_words('Flat outline-only pictograms drawn with a single cyan stroke.') == ['outline', 'pictograms', 'stroke']


def test_patch_operations_use_stable_ids():
    from scivid import patch
    plan = coded_plan()
    out = patch.apply('plan', plan, [{'op': 'set', 'path': 'chapters.c2.visual', 'value': 'new storyboard'},
                                     {'op': 'set', 'path': 'chapters.c1.demonstrations.d1.watch', 'value': 'w'},
                                     {'op': 'set', 'path': 'theme.accent', 'value': '#22d3ee'}])
    assert out['chapters'][1]['visual'] == 'new storyboard' and out['chapters'][0]['demonstrations'][0]['watch'] == 'w'
    assert plan['chapters'][1]['visual'] != 'new storyboard'                       # the original is untouched
    for bad in ({'op': 'set', 'path': 'chapters.c9.visual', 'value': 'x'}, {'op': 'set', 'path': 'chapters.0.visual'},
                {'op': 'remove', 'path': 'title'}):
        try:
            patch.apply('plan', plan, [bad])
            raise AssertionError(f'{bad} must be rejected')
        except ValueError:
            pass
    script = patch.number_cues({'chapters': [{'id': 'c1', 'points': [{'id': 'c1p1', 'narration': 'a b'}],
                                              'cues': [{'phrase': 'a'}, {'phrase': 'b'}, {'phrase': 'c'}]}]})
    out = patch.apply('script', script, [{'op': 'remove', 'path': 'cues.c1.k1'},
                                         {'op': 'set', 'path': 'points.c1p1.narration', 'value': 'b c'},
                                         {'op': 'add', 'path': 'cues.c1', 'value': {'phrase': 'd'}}])
    assert [(c['id'], c['phrase']) for c in out['chapters'][0]['cues']] == [('k1', 'b'), ('k2', 'c'), ('k3', 'd')]


def test_plan_review_failure_is_patched_not_rewritten():
    from scivid import review
    calls = []
    good = coded_plan()
    good['chapters'][1]['visual'] = good['chapters'][1]['visual'].replace('red line', 'red straight line')

    def scores(kind, low=None):
        out = {'scores': {c['id']: {'score': 3} for c in review.criteria(kind, 'coded')}}
        if low:
            out['scores'][low] = {'score': 1, 'reason': 'c2 draws the simple-interest line wrong', 'fix': 'say straight'}
        return out
    replies = {'plan-review': iter([scores('plan', 'accuracy'), scores('plan')])}

    class Model:
        def call(self, name, prompt, validate=None, **kw):
            calls.append(name)
            if name.startswith('plan-review'):
                return next(replies['plan-review'])
            if name.startswith('plan-patch'):
                reply = {'ops': [{'op': 'set', 'path': 'chapters.c2.visual', 'value': good['chapters'][1]['visual']}]}
            else:
                reply = coded_plan()
            if validate:
                validate(reply)
            return reply
    request = {'topic': 'compound interest', 'mode': 'explainer', 'notes': '', 'duration_seconds': 90}
    plan, result = lesson.make_plan(Model(), Model(), request, {'class': 9}, [], log=lambda m: None, route='coded')
    assert [c.split('-')[0] + '-' + c.split('-')[1] for c in calls] == ['plan-0', 'plan-review', 'plan-patch', 'plan-review']
    assert plan['chapters'][1]['visual'] == good['chapters'][1]['visual'] and result['decision']['pass']


def test_findings_are_collected_judged_and_counted(tmp_path):
    import json as _json
    from scivid import findings, review
    call = tmp_path / 'lessons' / 'L1' / 'llm' / 'frame-review-c4-0-abc'
    call.mkdir(parents=True)
    scores = {c['id']: {'score': 3} for c in review.criteria('scene_frames')}
    scores['legibility'] = {'score': 1, 'reason': 'frame 1 line is a garbled strip', 'fix': 'enlarge it'}
    (call / 'result.json').write_text(_json.dumps({'scores': scores}))
    (call / 'request.json').write_text(_json.dumps({'provider': 'qwen-local', 'model': 'q', 'prompt': 'p', 'images': []}))
    old = tmp_path / 'lessons' / 'L1' / 'llm' / 'content-review-c1-0-def'
    old.mkdir()
    (old / 'result.json').write_text(_json.dumps({'pass': False, 'issues': [{'severity': 'major', 'problem': 'x'},
                                                                             {'severity': 'minor', 'problem': 'y'}]}))
    (old / 'request.json').write_text(_json.dumps({'provider': 'qwen-local', 'prompt': 'p'}))
    found = findings.collect(tmp_path)
    assert sorted((f['review'], f['criterion']) for f in found) == [('scene_content', '(old format)'),
                                                                     ('scene_frames', 'legibility')]
    frame = next(f for f in found if f['review'] == 'scene_frames')
    findings.set_label(tmp_path, frame['id'], 'right', by='auditor', note='looks garbled')
    findings.set_label(tmp_path, frame['id'], 'wrong', note='mid-transform frame')       # the teacher overrides
    marks = findings.labels(tmp_path)
    assert findings.verdict(marks[frame['id']]) == 'wrong' and marks[frame['id']]['auditor']['verdict'] == 'right'
    row = next(r for r in findings.stats(found, marks) if r['criterion'] == 'legibility')
    assert (row['findings'], row['judged'], row['wrong'], row['false_positive_rate']) == (1, 1, 1, 1.0)


def test_disputed_findings_go_to_the_arbiter(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from scivid import coded, review
    monkeypatch.setattr(coded, 'validate_code', lambda code: None)
    monkeypatch.setattr(coded, 'contact_sheet', lambda video, moments, out: out)
    monkeypatch.setattr(coded, 'render', lambda s, work, code, d, bg=None: (Path(work) / 'chapter.mp4', {}))
    perfect = lambda kind: {'scores': {c['id']: {'score': 3} for c in review.criteria(kind)}}
    bad = perfect('scene_frames')
    bad['scores']['visual_correctness'] = {'score': 1, 'reason': 'frame 2: no current arrow yet', 'fix': 'draw it'}
    frames = iter([bad, bad])
    calls = []

    class Model:
        def __init__(self, step):
            self.step = step

        def call(self, tag, prompt, validate=None, **kw):
            calls.append(tag)
            if tag.startswith('code-'):
                return {'code': 'v1'}
            if tag.startswith('repair-'):
                return {'disputes': [{'finding': 'no current arrow', 'reason': 'its cue is at 10.32 s, after frame 2'}]}
            if tag.startswith('arbitrate-'):
                reply = {'rulings': [{'review': 'frames', 'criterion': 'visual_correctness', 'verdict': 'wrong',
                                      'reason': 'the arrow belongs to the next cue'}]}
                validate(reply)
                return reply
            return perfect('scene_content') if self.step == 'content_review' else next(frames)
    steps = {f'scene_code_{t}': 'haiku' for t in coded.TIERS} | {'review_audit': 'opus'}
    job = SimpleNamespace(settings=SimpleNamespace(code_attempts=4), log=lambda m: None, chapter_status=lambda *a: None,
                          llm=Model, models={'steps': steps})
    sc = {'points': [{'id': 'c1p1', 'narration': 'Watch.'}]}
    timing = {'points': [{'point_id': 'c1p1', 'start': 0, 'end': 3}]}
    cues = [{'phrase': 'Watch', 'start': 0.2, 'end': 2.2, 'show': 'current arrow'}]
    _, record = coded.code_chapter(job, {'title': 'L'}, {'id': 'c1', 'title': 't', 'complexity': 'routine'}, sc,
                                   timing, cues, 3.0, '', tmp_path)
    assert record['attempts'] == 2 and any(t.startswith('arbitrate-') for t in calls)   # passed after the ruling
    assert record['history'][1]['arbitration'][0]['verdict'] == 'wrong'


def test_a_broken_edit_is_a_defect_not_a_crash():
    from scivid.scene_check import validate_code
    try:
        validate_code(SCENE.replace('        at(self, 2.0)', '            at(self, 2.0)'))
        raise AssertionError('bad indentation must be reported')
    except ValueError as exc:
        assert 'does not parse' in str(exc) and 'line' in str(exc)
