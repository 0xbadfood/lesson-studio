"""Lesson pipeline: scope -> evidence -> plan -> script -> narration -> visuals -> render -> assemble.

Run by the queue as `python -m scivid.pipeline --lesson DIR --run-id ID`. Every stage writes its result
into the lesson folder and is skipped on resume when that result exists.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import traceback

from . import audio, coded, curriculum, diagram, imageworld, lesson, review as rubric, slides
from .contract import LessonRequest, STAGE_LABELS
from .jobs import read_json, write_json
from .llm import usage_summary
from . import models
from .settings import Settings

DEFAULT_SPAN = {'label': 3.5, 'highlight': 2.5, 'arrow': 3.0, 'title': 3.0, 'zoom': 3.5, 'shake': 1.5,
                'show': .6, 'hide': .6, 'trace': 3.0}
TAIL = .5   # seconds of picture after the last word of a chapter


class Lesson:
    def __init__(self, folder, run_id):
        self.dir = Path(folder).resolve()
        self.run_id = run_id
        self.request = LessonRequest.model_validate(read_json(self.dir / 'request.json')).model_dump()
        self.settings = Settings(**read_json(self.dir / 'settings.json'))
        snapshot = read_json(self.dir / 'models.json')
        if snapshot is None:   # lessons from before per-step settings: one local endpoint for everything
            snapshot = {'connections': {'legacy': {'type': 'openai_chat', 'url': self.settings.planner_url,
                                                   'model': None, 'timeout': self.settings.model_timeout}},
                        'steps': {s: 'legacy' for s in models.STEP_IDS}}
        self.models = snapshot
        # Lessons from before the coded route keep the diagram route on resume.
        self.route = snapshot.get('options', {}).get('scene_route', 'diagram')
        rubric.configure(snapshot.get('review_rules'))   # global minimum scores, frozen with the lesson
        options = snapshot.get('options', {})
        self.remote_voice = self.settings.spark_voice_url if options.get('voice_server') == 'spark' else None
        self.keep_image_model = bool(self.remote_voice)      # the local GPU only draws pictures: keep it loaded
        self.workers = max(1, int(options.get('chapter_workers', '1')))
        self.parallel_reviews = self.workers > 1             # cloud reviewers: content and frame review side by side
        self._lock = threading.RLock()                       # chapters may run in parallel
        self._clients = {}
        self.chapters_status = read_json(self.dir / 'chapters-status.json', [])
        self.warnings = read_json(self.dir / 'warnings.json', {})

    def llm(self, step):
        with self._lock:
            if step not in self._clients:
                self._clients[step] = models.client_for(self.models, step, self.dir, self.dir.parents[1])
            return self._clients[step]

    def local_judge(self):
        """A local model for cheap yes/no checks (first step assigned to a local URL), or None."""
        for step, cid in self.models['steps'].items():
            if self.models['connections'].get(cid, {}).get('type') == 'openai_chat':
                return self.llm(step)
        return None

    # ---------------------------------------------------------------- progress
    def stage(self, stage, message=None, **detail):
        state = {'stage': stage, 'label': STAGE_LABELS.get(stage, stage), 'message': message or STAGE_LABELS.get(stage),
                 'updated': time.time(), 'run_id': self.run_id, **detail}
        with self._lock:
            write_json(self.dir / 'state.json', state)
            with (self.dir / 'events.jsonl').open('a') as f:
                f.write(json.dumps(state, ensure_ascii=False) + '\n')
            write_json(self.dir / 'usage.json', usage_summary(self.dir))
            print(f'[{stage}] {state["message"]}', flush=True)

    def log(self, message):
        with self._lock:
            print('  ' + message, flush=True)
            state = read_json(self.dir / 'state.json', {})
            state.update(message=message, updated=time.time())
            write_json(self.dir / 'state.json', state)

    def chapter_status(self, cid, status, detail=''):
        with self._lock:
            for c in self.chapters_status:
                if c['id'] == cid:
                    c.update(status=status, detail=detail)
            write_json(self.dir / 'chapters-status.json', self.chapters_status)

    def warn(self, cid, notes):
        with self._lock:
            if notes:
                self.warnings[cid] = self.warnings.get(cid, []) + list(notes)
            write_json(self.dir / 'warnings.json', self.warnings)

    def cached(self, name, build):
        path = self.dir / name
        if path.exists():
            return read_json(path)
        value = build()
        write_json(path, value)
        return value

    # ---------------------------------------------------------------- stages
    def scope(self):
        def build():
            r = self.request
            if r['chapter']:
                c = curriculum.find(self.settings.ncert_root, r['chapter'])
                bank = curriculum.knowledge_bank(c) or {}
                return {'chapter': c['id'], 'class': r['class_level'] or c['class'], 'subject': c['subject'], 'book': c['book_title'],
                        'chapter_title': c['title'], 'chapter_number': c['chapter'],
                        'chapter_summary': bank.get('chapter_summary'),
                        'textbook_order': [s.get('description') for s in bank.get('learning_progression', [])]}
            return {'chapter': None, 'class': r['class_level'], 'subject': None, 'book': None, 'chapter_title': None}
        return self.cached('scope.json', build)

    def evidence(self, scope):
        def build():
            r = self.request
            items, notes = [], []
            if r['chapter']:
                self.log('Reading the textbook chapter')
                chapter, ncert, bank = lesson.chapter_evidence(self.settings.ncert_root, r['chapter'],
                                                               r['topic'] + ' ' + r['notes'])
                items += ncert
                if bank:
                    notes.append('Textbook facts come from the audited chapter knowledge bank and its pages.')
                if not ncert or max(e['score'] for e in ncert) < 2:
                    notes.append('The topic matches this chapter weakly; check that the right chapter was chosen.')
            if r['web_research']:
                self.log('Searching the web' + (' to fill gaps' if r['chapter'] else ''))
                guidance = {'focus': r['notes'], 'audience': lesson.audience(scope['class']) + ' students',
                            'medium': 'narrated animated science/maths lesson'}
                web = self.models['connections'][self.models['steps']['web_research']]
                items += lesson.web_evidence(self.settings, self.dir, r['topic'], guidance, model_url=web['url'])
            if r['chapter'] and r['web_research']:
                notes.append('Textbook passages are primary; web sources only add to them.')
            if not r['chapter'] and not r['web_research']:
                notes.append("No sources by request: planned and written from the models' own knowledge, "
                             'then checked by the reviewers and the code-run numbers check.')
            return {'items': items, 'notes': notes}
        return self.cached('evidence.json', build)

    def plan(self, scope, evidence):
        def build():
            plan, review = lesson.make_plan(self.llm('plan'), self.llm('plan_review'), self.request, scope,
                                            evidence['items'], self.log, route=self.route)
            return {'plan': plan, 'review': review}
        value = self.cached('plan.json', build)
        plan = value['plan']
        if not self.chapters_status:
            self.chapters_status = [{'id': c['id'], 'title': c['title'], 'route': c['route'], 'status': 'planned',
                                     'complexity': c.get('complexity'), 'history': bool(c.get('history')),
                                     'detail': ''} for c in plan['chapters']]
            write_json(self.dir / 'chapters-status.json', self.chapters_status)
        from .jobs import Store
        Store(self.dir.parents[1]).set(self.dir.name, title=plan['title'])
        return plan

    def script(self, scope, plan, evidence):
        def build():
            script, review = lesson.make_script(self.llm('script'), self.llm('script_review'), self.request, scope, plan,
                                                evidence['items'], self.log, numbers=self.llm('numbers'),
                                                judge=self.local_judge())
            return {'script': script, 'review': review}
        value = self.cached('script.json', build)
        # a saved script (resume) gets the current spoken-form normalizer, so its fixes reach narration
        before = json.dumps(value['script'])
        lesson.repair_phrases(value['script'], judge=self.local_judge(), log=self.log)
        if json.dumps(value['script']) != before:
            self.log('Saved script re-normalized to the current spoken form')
            write_json(self.dir / 'script.json', value)
        return value['script']

    def narrate(self, script):
        chapters = [(sc['id'], sc['points']) for sc in script['chapters']]
        for cid, _ in chapters:
            self.chapter_status(cid, 'recording')
        self.log(f'Recording {len(chapters)} chapters in one session')
        if self.settings.tts_engine == 'luxtts':
            self.log('Recording with LuxTTS on the CPU')
        elif self.remote_voice:
            self.log('Recording on the Spark voice server')
        timings = audio.narrate_all(self.settings, self.dir / 'chapters', chapters, self.request['voice'],
                                    remote=self.remote_voice, log=self.log)
        for cid, _ in chapters:
            self.chapter_status(cid, 'recorded', f"{timings[cid]['duration']:.1f}s of narration")
        return timings

    def resolve(self, sc, timing, route):
        """Cue phrases -> seconds on this chapter's narration clock."""
        words = timing['words']
        duration = timing['duration'] + TAIL
        point_end = {p['point_id']: p['end'] for p in timing['points']}
        resolved = []
        for c in sc.get('cues') or []:
            start, phrase_end = audio.locate(words, c['point'], c['phrase'])
            if c.get('until'):
                end = audio.locate(words, c.get('until_point', c['point']), c['until'])[1]
            elif route == 'image' and c['verb'] in ('move_along', 'rotate', 'swing'):
                end = max(phrase_end, point_end[c['point']])
            elif route == 'image':
                end = max(phrase_end, start + DEFAULT_SPAN.get(c['verb'], 2.5))
            elif route == 'coded':
                end = max(phrase_end, start + 2.0)
            elif c.get('verb') in ('move', 'count'):
                end = max(phrase_end, point_end[c['point']])
            else:
                end = max(phrase_end, start + {'plot': 2.5, 'highlight': 2.5, 'focus': 3.0}.get(c.get('verb'), 1.5))
            end = min(end, duration - .1)
            resolved.append({**c, 'start': round(start, 3), 'end': round(max(end, start + .3), 3)})
        return resolved, duration

    def visuals_and_render(self, plan, script, timings, evidence):
        for cid, saved in read_json(self.dir / 'rerouted.json', {}).items():
            for i, c in enumerate(plan['chapters']):
                if c['id'] == cid:
                    plan['chapters'][i] = saved['chapter']
            for sc in script['chapters']:
                if sc['id'] == cid:
                    sc['cues'] = saved['cues']
        style = plan.get('style', 'Clean, bright educational illustration')
        cited = {e['id']: e for e in evidence['items']}
        videos = {}
        # Pictures first (GPU), then release the image model before CPU rendering.
        scenes = {}
        image_chapters = [c for c in plan['chapters'] if c['route'] == 'image']
        if image_chapters:
            self.stage('visuals')
            for c in image_chapters:
                self.chapter_status(c['id'], 'drawing')
                try:
                    scenes[c['id']] = imageworld.build(self.settings, self.llm('picture_check'),
                                                       self.dir / 'chapters' / c['id'] / 'scene', c, style, log=self.log)
                    self.chapter_status(c['id'], 'drawn')
                except imageworld.PictureRejected as exc:
                    self.log(f"Chapter {c['id'][1:]} will be drawn as a diagram instead")
                    self.reroute(c, script, str(exc), evidence)
            imageworld.release_image_model(self.settings)
        self.stage('render')

        def one(c, sc):
            try:
                return chapter(c, sc)
            except Exception as exc:   # report at once; the other chapters keep going
                self.chapter_status(c['id'], 'failed', f'{type(exc).__name__}: {str(exc)[:160]}')
                self.log(f"Chapter {c['id'][1:]} failed: {type(exc).__name__}: {str(exc)[:200]}")
                raise

        def chapter(c, sc):
            folder = self.dir / 'chapters' / c['id']
            out = folder / 'chapter.mp4'
            recorded = folder / 'audio' / 'timing.json'
            if out.exists() and recorded.exists() and recorded.stat().st_mtime > out.stat().st_mtime:
                # the narration was recorded again (its text changed): the scene was timed to the old voice
                self.log(f"Chapter {c['id'][1:]}: narration changed since it was animated; animating it again")
                for stale in ('chapter.mp4', 'code/accepted.json', 'cues-resolved.json'):
                    (folder / stale).unlink(missing_ok=True)
            if out.exists():
                self.chapter_status(c['id'], 'ready')
                return out
            cues, duration = self.resolve(sc, timings[c['id']], c['route'])
            write_json(folder / 'cues-resolved.json', cues)
            self.chapter_status(c['id'], 'animating')
            if c['route'] == 'image':
                cues = self.usable_cues(c['id'], scenes[c['id']], cues)
                video = self.render_image(folder, scenes[c['id']], cues, duration)
            elif c['route'] == 'slide':
                video, notes = slides.render_chapter(self, plan, c, sc, timings[c['id']], duration, folder / 'slides')
                self.warn(c['id'], notes)
            elif c['route'] == 'coded':
                chapter_evidence = [cited[s] for s in c.get('source_ids', []) if s in cited]
                video = self.render_coded(folder, plan, c, sc, timings[c['id']], cues, duration, chapter_evidence)
            else:
                chapter_evidence = [cited[s] for s in c.get('source_ids', []) if s in cited]
                video = self.render_diagram(folder, c, sc, timings[c['id']], cues, duration, chapter_evidence)
            self.warn(c['id'], [])
            self.mux(video, timings[c['id']]['audio'], duration, out)
            self.chapter_status(c['id'], 'ready')
            return out

        pairs = list(zip(plan['chapters'], script['chapters']))
        if self.workers == 1 or len(pairs) == 1:
            for c, sc in pairs:
                videos[c['id']] = one(c, sc)
            return videos
        # Slides first (their pictures use the GPU while the coded chapters use the cloud and the CPU), then the
        # hardest coded chapters, which take longest. A failed chapter does not stop the others: whatever finished
        # is kept for a resume, then the first failure is raised.
        weight = {'novel': 0, 'involved': 1, 'routine': 2}
        order = sorted(pairs, key=lambda p: (p[0]['route'] != 'slide', weight.get(p[0].get('complexity'), 3)))
        self.log(f'Animating {len(pairs)} chapters, {self.workers} at a time')
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='chapter') as pool:
            futures = {c['id']: pool.submit(one, c, sc) for c, sc in order}
        errors = []
        for c, _ in pairs:
            try:
                videos[c['id']] = futures[c['id']].result()
            except Exception as exc:   # noqa: BLE001 - reported after every chapter has had its turn
                errors.append((c['id'], exc))
                self.chapter_status(c['id'], 'failed', str(exc)[:200])
        if errors:
            raise errors[0][1]
        return videos

    def reroute(self, chapter, script, reason, evidence):
        """Turn a picture chapter into a diagram chapter with its own validated spec and cues."""
        sc = next(s for s in script['chapters'] if s['id'] == chapter['id'])
        cited = {e['id']: e for e in evidence['items']}
        designed = lesson.diagram_chapter(self.llm('diagram_design'), chapter, sc,
                                          [cited[s] for s in chapter.get('source_ids', []) if s in cited],
                                          '', f"diagram-reroute-{chapter['id']}")
        chapter['route'], chapter['diagram'] = 'diagram', designed['diagram']
        sc['cues'] = designed['cues']
        self.warnings.setdefault(chapter['id'], []).append('The picture kept failing review (' + reason[:200] +
                                                            '); this chapter is drawn as a diagram instead')
        for s in self.chapters_status:
            if s['id'] == chapter['id']:
                s['route'] = 'diagram'
        self.chapter_status(chapter['id'], 'recorded', 'redrawn as a diagram')
        write_json(self.dir / 'rerouted.json', {**read_json(self.dir / 'rerouted.json', {}),
                                                chapter['id']: {'chapter': chapter, 'cues': sc['cues']}})

    def usable_cues(self, cid, scene, cues):
        """Drop cues the measured scene cannot honour (missing objects/paths, motion on still objects)."""
        objects, paths = scene['objects'], scene['paths']
        keep, dropped = [], []
        for c in cues:
            o = c.get('object')
            if (o and o not in objects) or (c.get('path') and c['path'] not in paths) or \
                    (c['verb'] in lesson.MOTION_VERBS and not objects.get(o, {}).get('layer')):
                dropped.append(c)
            else:
                keep.append(c)
        warnings = list(scene.get('warnings', []))
        if dropped:
            warnings.append(f'{len(dropped)} visual cue(s) could not be shown and were left out')
        with self._lock:
            self.warnings[cid] = warnings
        return keep

    def render_coded(self, folder, plan, chapter, sc, timing, cues, duration, evidence):
        """An LLM-coded scene timed to the narration (tiered coder, sandboxed render, content and frame review)."""
        redo = read_json(folder / 'redo.json', {'count': 0})['count']
        extra = f'The teacher asked for a different, clearer version (variation {redo}).' if redo else ''
        video, record = coded.code_chapter(self, plan, chapter, sc, timing, cues, duration,
                                           lesson.evidence_text(evidence, 6000), folder / 'code', extra)
        tier_note = f"{record['tier']} coder" + (f", {record['attempts']} attempts" if record['attempts'] > 1 else '')
        self.chapter_status(chapter['id'], 'animating', tier_note)
        self.warn(chapter['id'], record['notes'])
        return video

    def render_diagram(self, folder, chapter, sc, timing, cues, duration, evidence):
        """Deterministic diagram render, a frame review, and at most one spec revision."""
        n = chapter['id'][1:]
        spec, warnings = chapter['diagram'], []
        redo = read_json(folder / 'redo.json', {'count': 0})['count']
        if redo:
            self.log(f'Animating chapter {n}: designing a fresh diagram')
            fresh = lesson.diagram_chapter(self.llm('diagram_design'), chapter, sc, evidence,
                                           f'The teacher asked for a different, clearer version (variation {redo}).',
                                           f"diagram-redo-{chapter['id']}-{redo}")
            spec = fresh['diagram']
            cues, duration = self.resolve({**sc, 'cues': fresh['cues']}, timing, 'diagram')
        for round_ in range(2):
            self.log(f'Animating chapter {n}: drawing the diagram' + (' (revised)' if round_ else ''))
            video = diagram.render_spec(self.settings, folder / f'diagram-{round_}', spec, cues, duration,
                                        chapter['title'], 'final')
            moments = [c for c in cues if c['verb'] not in ('hide',)][:4]
            times = [min(duration - .2, c['start'] + .7 * (c['end'] - c['start']) + .4) for c in moments]
            shots = diagram.frames(video, times, folder / f'diagram-{round_}')
            review = rubric.review(self.llm('diagram_review'), f"diagram-review-{chapter['id']}-{round_}", 'diagram_frames', (
                'Review frames of one animated diagram from a school lesson. Frames are taken during these narration '
                'cues, in order: ' + json.dumps([{k: c.get(k) for k in ('verb', 'target', 'phrase')} for c in moments], ensure_ascii=False) +
                '\nLayout style lowers no score.\nDIAGRAM SPEC:\n' + json.dumps(spec, ensure_ascii=False) +
                '\nEVIDENCE:\n' + lesson.evidence_text(evidence, 4000)),
                images=shots, thinking=1024, max_tokens=4500)
            majors = rubric.findings(review)
            if review['decision']['pass']:
                break
            if round_ == 1:
                warnings += [f"Diagram kept with review note ({m['label']}): {m['reason'][:200]}" for m in majors]
                break
            self.log(f'Animating chapter {n}: improving the diagram after review')
            revised = lesson.diagram_chapter(self.llm('diagram_design'), chapter, sc, evidence, json.dumps(majors, ensure_ascii=False),
                                             f"diagram-revise-{chapter['id']}")
            spec = revised['diagram']
            cues, duration = self.resolve({**sc, 'cues': revised['cues']}, timing, 'diagram')
            write_json(folder / 'cues-resolved.json', cues)
        write_json(folder / 'diagram-accepted.json', {'spec': spec, 'cues': cues, 'review': review})
        self.warn(chapter['id'], warnings)
        return video

    def render_image(self, folder, scene, cues, duration):
        spec = {'size': scene['size'], 'background': scene['background'], 'objects': scene['objects'],
                'paths': scene['paths'], 'cues': cues, 'duration': round(duration, 3),
                'media_dir': str(folder / 'media'), 'name': 'chapter',
                'resolution': [self.settings.height, self.settings.width, self.settings.fps]}
        write_json(folder / 'render-spec.json', spec)
        result = subprocess.run([self.settings.manim_python, str(Path(__file__).with_name('scene_render.py')),
                                 str(folder / 'render-spec.json')], capture_output=True, text=True,
                                timeout=self.settings.render_timeout)
        if result.returncode:
            raise RuntimeError('Chapter render failed: ' + (result.stderr or result.stdout)[-1500:])
        return Path(json.loads(result.stdout.strip().splitlines()[-1])['video'])

    @staticmethod
    def mux(video, narration, duration, out):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-i', str(narration),
                        '-filter_complex', f'[1:a]apad,atrim=0:{duration:.3f},aresample=48000[a]',
                        '-map', '0:v', '-map', '[a]', '-t', f'{duration:.3f}', '-c:v', 'libx264', '-preset', 'medium',
                        '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', str(out)],
                       check=True, timeout=600)

    def assemble(self, plan, script, timings, videos, evidence):
        out = self.dir / 'output'
        out.mkdir(exist_ok=True)
        listing = self.dir / 'concat.txt'
        listing.write_text(''.join(f"file '{videos[c['id']]}'\n" for c in plan['chapters']))
        raw = self.dir / 'lesson-raw.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
                        '-c', 'copy', str(raw)], check=True, timeout=600)
        # Captions from MFA words, offset by each chapter's start.
        cues_vtt, events, offset = [], [], 0.0
        for c in plan['chapters']:
            t = timings[c['id']]
            chunk = []
            for w in t['words']:
                chunk.append(w)
                if w['word'][-1:] in '.,;:?!' or len(chunk) >= 7:
                    events.append((offset + chunk[0]['start'], offset + chunk[-1]['end'] + .15,
                                   ' '.join(x['word'] for x in chunk)))
                    chunk = []
            if chunk:
                events.append((offset + chunk[0]['start'], offset + chunk[-1]['end'] + .15,
                               ' '.join(x['word'] for x in chunk)))
            offset += t['duration'] + TAIL

        def stamp(s, sep='.'):
            h, rem = divmod(s, 3600)
            mnt, sec = divmod(rem, 60)
            return f'{int(h):02d}:{int(mnt):02d}:{sec:06.3f}'.replace('.', sep)
        (out / 'lesson.vtt').write_text('WEBVTT\n\n' + '\n'.join(
            f'{stamp(a)} --> {stamp(b)}\n{text}\n' for a, b, text in events))
        ass = ['[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {self.settings.width}',
               f'PlayResY: {self.settings.height}', '', '[V4+ Styles]',
               'Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, '
               'Outline, Shadow, Alignment, MarginL, MarginR, MarginV',
               'Style: Cap,DejaVu Sans,30,&H00FFFFFF,&H00000000,&H9A141E28,0,3,10,0,2,80,80,26', '',
               '[Events]', 'Format: Layer, Start, End, Style, Text']
        ass += [f'Dialogue: 0,{stamp(a)[1:-1]},{stamp(b)[1:-1]},Cap,{text}' for a, b, text in events]
        (self.dir / 'captions.ass').write_text('\n'.join(ass) + '\n')
        final = out / 'lesson.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-vf', f"ass={self.dir / 'captions.ass'}",
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'copy',
                        '-movflags', '+faststart', str(final)], check=True, timeout=1200)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                                                    '-of', 'json', str(final)], timeout=60))
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(final), '-f', 'null', '-'], check=True, timeout=600)
        poster_t = min(4.0, float(probe['format']['duration']) / 3)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(poster_t), '-i', str(final), '-frames:v', '1',
                        '-vf', 'scale=640:-1', '-q:v', '3', str(out / 'poster.jpg')], check=True, timeout=60)
        used = {s for c in plan['chapters'] for s in c.get('source_ids', [])}
        write_json(out / 'sources.json', {'notes': evidence['notes'],
                                          'sources': [e for e in evidence['items'] if e['id'] in used]})
        write_json(out / 'script.json', {'title': plan['title'], 'chapters': [
            {**{k: c[k] for k in ('id', 'title', 'objective', 'route', 'source_ids')},
             'narration': [p['narration'] for p in sc['points']], 'cues': sc.get('cues') or [], **({'slides': sc['slides']} if sc.get('slides') else {})}
            for c, sc in zip(plan['chapters'], script['chapters'])]})
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        report = {'request': self.request, 'title': plan['title'],
                  'duration_seconds': round(float(probe['format']['duration']), 2),
                  'video': {'width': video['width'], 'height': video['height'], 'codec': video['codec_name'],
                            'audio': any(s['codec_type'] == 'audio' for s in probe['streams']), 'full_decode': 'passed'},
                  'chapters': [{'id': c['id'], 'title': c['title'], 'route': c['route'], 'complexity': c.get('complexity'),
                                'narration_seconds': round(timings[c['id']]['duration'], 2),
                                **({k: v for k, v in (read_json(self.dir / 'chapters' / c['id'] / 'code' / 'accepted.json')
                                                      or {}).items() if k in ('tier', 'attempts')})}
                               for c in plan['chapters']],
                  'config': {'preset': self.models.get('preset'), 'scene_route': self.route,
                             'steps': {s: (self.models['connections'].get(cid) or {}).get('label', cid)
                                       for s, cid in self.models['steps'].items()}},
                  'model_usage': usage_summary(self.dir), 'evidence_notes': evidence['notes'],
                  'warnings': {**{k: v for k, v in self.warnings.items() if v},
                               **{stage: [f"Reviewer note kept ({i['label']}, {i['score']}/3): {i['reason'][:220]}"
                                          for i in ((read_json(self.dir / f'{stage}.json', {}).get('review') or {})
                                                    .get('decision') or {}).get('failed', [])]
                                  for stage in ('plan', 'script')
                                  if (read_json(self.dir / f'{stage}.json', {}).get('review') or {}).get('accepted_with_notes')},
                               **({'script': ['Calculation check ' + read_json(self.dir / 'script.json')['review']['numbers_check']]}
                                  if read_json(self.dir / 'script.json', {}).get('review', {}).get('numbers_check') else {})},
                  'checks': ['plan and script validated in code and reviewed', 'narration passed the speech audit',
                             'cue phrases located in aligned narration',
                             *(['coded scenes checked in code, rendered in a sandbox with measured overlaps and cue '
                                'timing, then reviewed for content and from frames at the cue moments']
                               if self.route == 'coded' else
                               ['diagram chapters rendered in a sandbox with geometry checks']),
                             'final video fully decoded'],
                  'human_review': 'pending'}
        write_json(out / 'report.json', report)
        return report

    def run(self):
        self.stage('scope')
        scope = self.scope()
        self.stage('evidence')
        evidence = self.evidence(scope)
        if not evidence['items'] and (self.request['chapter'] or self.request['web_research']):
            raise RuntimeError('No usable evidence was found for this topic')
        self.stage('plan')
        plan = self.plan(scope, evidence)
        self.stage('script')
        script = self.script(scope, plan, evidence)
        self.stage('narration')
        timings = self.narrate(script)
        videos = self.visuals_and_render(plan, script, timings, evidence)
        self.stage('assemble')
        report = self.assemble(plan, script, timings, videos, evidence)
        self.stage('done', f"Lesson ready: {report['duration_seconds']:.0f} seconds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lesson', required=True)
    ap.add_argument('--run-id', required=True)
    args = ap.parse_args()
    job = Lesson(args.lesson, args.run_id)
    try:
        job.run()
    except Exception as exc:
        error = str(exc)
        for key in ('TAVILY_API_KEY', 'OPENAI_API_KEY', 'OPENAI_TOKEN', 'SCIVID_API_KEY', 'OPENROUTER_API_KEY',
                    'ANTHROPIC_API_KEY', 'VLLM_API_KEY'):
            if os.environ.get(key):
                error = error.replace(os.environ[key], '[redacted]')
        traceback.print_exc()
        write_json(job.dir / 'terminal.json', {'status': 'failed', 'error': error[:2000], 'run_id': args.run_id})
        write_json(job.dir / 'usage.json', usage_summary(job.dir))
        job.stage('failed', error[:600])
        raise SystemExit(1)
    write_json(job.dir / 'terminal.json', {'status': 'succeeded', 'run_id': args.run_id})


if __name__ == '__main__':
    main()
