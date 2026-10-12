"""Narration via the frozen infofilm audio stack (used as a library, never modified).

VibeVoice point batches -> Whisper audit (+ model judge, fallback ASR) -> point-local MFA.
infofilm takes the shared GPU lease, unloads Qwen Image and releases VibeVoice itself.
"""
import json
import re
import sys
from pathlib import Path


def _infofilm(remotion_root):
    if remotion_root not in sys.path:
        sys.path.insert(0, remotion_root)
    from infofilm import core, media, narrators, vibe_media
    return core, media, narrators, vibe_media


def narrate(settings, folder, chapter_id, points, voice='default', remote=None, log=print):
    """Record, audit and align one chapter. Returns timing with words [{id, word, start, end, point_id}]."""
    core, media, narrators, vibe_media = _infofilm(settings.remotion_root)
    folder = Path(folder)
    final = folder / 'timing.json'
    if final.exists():
        saved = json.loads(final.read_text())
        if saved.get('points_text') == [p['narration'] for p in points]:
            return saved
    config = core.configuration(Path(settings.remotion_root) / 'config.json')
    config['tts_engine'] = 'vibevoice'
    config['gpu_lock'] = settings.gpu_lock
    if remote:
        from . import voice_proxy
        voice_proxy.wait_until_idle(remote, log)
        with voice_proxy.adapter(remote) as base:
            config.update(tts_url=base, image_url=base + '/image', gpu_lock=settings.remote_voice_lock)
            # Provider job ids live on that server, and infofilm will not resume a narration at another batch
            # size: a narration begun at an older size keeps it; new ones use one large batch (the Spark renders
            # 40 points in ~42 s, barely longer than one point, so a whole lesson usually goes in one job).
            store = 'infofilm-spark'
            if not (folder / store / 'audio').exists():
                store, config['vibe_batch_size'] = 'infofilm-spark-b40', 40
                if (folder / 'infofilm-spark-b5' / 'audio').exists():
                    store, config['vibe_batch_size'] = 'infofilm-spark-b5', 5
            return _record(core, media, narrators, vibe_media, config, folder, final, chapter_id, points, voice, store)
    return _record(core, media, narrators, vibe_media, config, folder, final, chapter_id, points, voice)


def _record(core, media, narrators, vibe_media, config, folder, final, chapter_id, points, voice, store_name='infofilm'):
    config = narrators.select_reference(config, narrator=None if voice == 'default' else voice)
    store = core.Store(folder / store_name)
    script = {'points': [{'id': p['id'], 'narration': p['narration']} for p in points]}
    text = '\n\n'.join(p['narration'] for p in points)
    audio = info = audit = None
    for attempt in range(2):
        audio, info = vibe_media.render_vibevoice({**config, 'audio_variant': attempt}, store, script['points'],
                                                  f'{chapter_id}-narration-{attempt}')
        audit = media.audit_audio(config, store, audio, text, points=script['points'])
        if audit['status'] == 'passed':
            break
    else:
        raise RuntimeError(f'Narration for {chapter_id} failed the speech audit twice; takes and audits are saved')
    timing = vibe_media.align_vibevoice(config, store, audio, script, info, f'{chapter_id}-alignment')
    result = {'audio': str(timing['audio']), 'duration': timing['audio_info']['duration_seconds'],
              'words': [{k: w[k] for k in ('id', 'word', 'start', 'end', 'point_id')} for w in timing['words']],
              'points': timing['points'], 'audit_status': audit['status'],
              'points_text': [p['narration'] for p in points]}
    final.write_text(json.dumps(result, indent=1))
    return result


def norm(word):
    return re.sub(r"[^a-z0-9%]+", '', word.lower().replace('’', "'"))


SPLIT = r'[\s\u2014\u2013\-/]+'     # spaces, em/en dashes, hyphens, slashes join words in writing


def _subtokens(words):
    """(normalised sub-word, index of the whole word) pairs: "string—what" gives string and what, both word i."""
    out = []
    for i, w in enumerate(words):
        for part in re.split(SPLIT, w):
            if norm(part):
                out.append((norm(part), i))
    return out


def _find(words, phrase):
    subs = _subtokens(words)
    target = [norm(t) for t in re.split(SPLIT, phrase) if norm(t)]
    keys = [k for k, _ in subs]
    if not target:
        return None
    for i in range(len(keys) - len(target) + 1):
        if keys[i:i + len(target)] == target:
            return subs[i][1], subs[i + len(target) - 1][1]
    return None


def locate(words, point_id, phrase):
    """Find a phrase inside one point's aligned words; returns (start, end) seconds."""
    seq = [w for w in words if w['point_id'] == point_id]
    span = _find([w['word'] for w in seq], phrase)
    if span is None:
        raise ValueError(f'Cue phrase "{phrase}" is not in point {point_id}')
    return seq[span[0]]['start'], seq[span[1]]['end']


def phrase_in_text(text, phrase):
    return _find(text.split(), phrase) is not None


def narrate_all(settings, folder, chapters, voice='default', remote=None, log=print):
    """Record every chapter in one VibeVoice batch (one model load), align once, then cut per chapter.

    chapters: [(chapter_id, points)]. Returns {chapter_id: timing} in the same shape as narrate().
    """
    import subprocess
    folder = Path(folder)
    results, missing = {}, []
    for cid, points in chapters:
        saved = folder / cid / 'audio' / 'timing.json'
        value = json.loads(saved.read_text()) if saved.exists() else None
        if value and value.get('points_text') == [p['narration'] for p in points]:
            results[cid] = value
        else:
            missing.append((cid, points))
    if not missing:
        return results
    all_points = [p for _, points in missing for p in points]
    joined = narrate(settings, folder / '_batch' / '-'.join(c for c, _ in missing), 'lesson', all_points, voice,
                     remote=remote, log=log)
    for cid, points in missing:
        ids = [p['id'] for p in points]
        bounds = [b for b in joined['points'] if b['point_id'] in ids]
        start = max(0.0, bounds[0]['start'] - .2)
        end = min(joined['duration'], bounds[-1]['end'] + .35)
        out = folder / cid / 'audio'
        out.mkdir(parents=True, exist_ok=True)
        clip = out / 'narration.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', joined['audio'], '-ss', f'{start:.4f}', '-to', f'{end:.4f}',
                        '-c:a', 'pcm_s16le', str(clip)], check=True, timeout=120)
        words = [{**w, 'start': round(w['start'] - start, 4), 'end': round(w['end'] - start, 4)}
                 for w in joined['words'] if w['point_id'] in ids]
        value = {'audio': str(clip), 'duration': round(end - start, 4), 'words': words,
                 'points': [{**b, 'start': round(b['start'] - start, 4), 'end': round(b['end'] - start, 4)}
                            for b in bounds],
                 'audit_status': joined['audit_status'], 'points_text': [p['narration'] for p in points],
                 'cut_from': {'audio': joined['audio'], 'start': start, 'end': end}}
        (out / 'timing.json').write_text(json.dumps(value, indent=1))
        results[cid] = value
    return results


def closest_span(text, phrase):
    """Best-matching run of words in `text` for a paraphrased cue phrase: (exact words, similarity 0..1)."""
    import difflib
    words = text.split()
    target = [norm(t) for t in re.split(SPLIT, phrase) if norm(t)]
    if not target or not words:
        return None, 0.0
    best = (None, 0.0)
    for n in range(max(1, len(target) - 3), len(target) + 4):
        for i in range(0, max(1, len(words) - n + 1)):
            span = words[i:i + n]
            keys = [norm(t) for w in span for t in re.split(SPLIT, w) if norm(t)]
            score = difflib.SequenceMatcher(None, keys, target).ratio()
            if score > best[1]:
                best = (' '.join(span), score)
    return best


def speakable(text):
    """Spoken form of narration (see spoken.py): what the listener hears, so TTS, MFA and the audit agree."""
    from .spoken import spoken
    return spoken(text)
