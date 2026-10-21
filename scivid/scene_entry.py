"""Sandboxed runner for one LLM-coded chapter: checks the code, renders it, and measures what was drawn.

Usage (inside bwrap): python scene_entry.py scene.py WIDTH HEIGHT FPS DURATION. Writes result.json.
"""
import importlib.util
import json
from pathlib import Path
import sys
import traceback

import manim as m
import numpy as np

from scene_check import CLASS, validate_code


def main():
    source, width, height, fps, duration = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
    result = {'duration': duration}
    try:
        validate_code(Path(source).read_text(), manim_module=m)
        spec = importlib.util.spec_from_file_location('chapter_scene', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, CLASS)
        samples, band, off = [], [], []
        original = cls.update_mobjects
        last = [-1.0]

        def monitored(scene, dt):
            original(scene, dt)
            if scene.time - last[0] < .3:
                return
            last[0] = scene.time
            labels, seen = [], set()
            # What the viewer sees, not the heading or invisible helpers: the picture (graphics) apart from its
            # words, so a caption cannot make a tiny drawing look like a full frame.
            content = {'graphics': [], 'text': []}
            for obj in scene.mobjects:
                if isinstance(obj, m.ValueTracker):   # stores its value as a point; never drawn
                    continue
                if getattr(obj, '_kit_reserved', False):
                    continue
                words = {id(g) for t in obj.get_family() if isinstance(t, (m.Text, m.MathTex, m.Tex))
                         for g in t.get_family()}
                for f in obj.family_members_with_points():
                    visible = max(f.get_fill_opacity(), f.get_stroke_opacity() if f.get_stroke_width() else 0)
                    if visible >= .1 and np.isfinite(f.points).all():
                        content['text' if id(f) in words else 'graphics'].append(
                            (f.points.min(axis=0)[:2], f.points.max(axis=0)[:2]))
                points = obj.get_all_points()
                if len(points) and np.isfinite(points).all():
                    lo, hi = points.min(axis=0), points.max(axis=0)
                    if lo[0] < -7.15 or hi[0] > 7.15 or lo[1] < -4.05 or hi[1] > 4.05:
                        off.append({'time': round(scene.time, 1), 'type': type(obj).__name__,
                                    'min': np.round(lo[:2], 2).tolist(), 'max': np.round(hi[:2], 2).tolist()})
                for f in obj.get_family():
                    if id(f) in seen or not isinstance(f, (m.Text, m.MathTex)) or getattr(f, '_kit_reserved', False):
                        continue
                    seen.add(id(f))
                    # The parent of a MathTex holds no points of its own: judge visibility by its glyphs.
                    glyphs = [g for g in f.get_family() if len(g.points)]
                    if not glyphs or max(g.get_fill_opacity() for g in glyphs) < .6 or f.width < .02:
                        continue
                    name = getattr(f, 'original_text', None) or getattr(f, 'tex_string', '') or type(f).__name__
                    box = {'text': str(name)[:60], 'min': np.round(f.get_corner(m.DL)[:2], 3).tolist(),
                           'max': np.round(f.get_corner(m.UR)[:2], 3).tolist()}
                    labels.append(box)
                    if box['max'][1] > 2.95 or box['min'][1] < -2.75:
                        band.append({'time': round(scene.time, 1), **box})
            sample = {'time': round(scene.time, 2), 'labels': labels}
            parts = content['graphics'] or content['text']     # an all-text scene is judged by its text
            if parts:
                lo = np.min([c[0] for c in parts], axis=0)
                hi = np.max([c[1] for c in parts], axis=0)
                sample['content'] = np.round([lo[0], lo[1], hi[0], hi[1]], 2).tolist()
            samples.append(sample)
        cls.update_mobjects = monitored
        plays, original_play = [], cls.play

        def recorded(scene, *animations, **kwargs):
            start = scene.time
            original_play(scene, *animations, **kwargs)
            if not all(isinstance(a, m.Wait) for a in animations):   # waits (at()) are rest, not motion
                plays.append([start, scene.time])
        cls.play = recorded
        with m.tempconfig({'pixel_height': height, 'pixel_width': width, 'frame_rate': fps, 'media_dir': 'media',
                           'output_file': 'chapter', 'preview': False, 'disable_caching': True,
                           'verbosity': 'WARNING'}):
            scene = cls()
            scene.render()
            result.update(elapsed=float(scene.time), output=str(scene.renderer.file_writer.movie_file_path),
                          late=getattr(scene, '_kit_late', []))
        # Keep each distinct problem once (a label stuck in a band would otherwise repeat every sample).
        result['band_text'] = list({b['text']: b for b in band}.values())
        result['off_frame'] = list({o['type']: o for o in off}.values())
        result['samples'] = samples
        origin = getattr(scene, '_kit_start', 0.0)   # the chapter clock starts at begin()
        result['plays'] = [[round(a - origin, 3), round(b - origin, 3)] for a, b in plays]
    except Exception as exc:   # the coder gets the error back; keep the useful tail of the traceback
        result['error'] = (type(exc).__name__ + ': ' + str(exc))[:1500]
        result['traceback'] = ''.join(traceback.format_exc().splitlines(True)[-14:])[-3000:]
    Path('result.json').write_text(json.dumps(result))


if __name__ == '__main__':
    main()
