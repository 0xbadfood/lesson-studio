"""Round 2: colour-keyed motion paths, layer peeling, a second subject."""
import json
import sys
from qimage import ROOT, generate

CANVAS = ROOT / 'inputs' / 'engine-canvas.png'
W, H = 1664, 944
PATH_STYLE = ('The path is drawn as a thin dashed line in pure bright magenta (#FF00FF); magenta is used '
              'nowhere else in the image. ')

JOBS = [
    ('r2-nopiston', 'Edit the reference engine cutaway: remove only the piston. Show the complete copper connecting '
     'rod including its small end and wrist pin that the piston was hiding, and the empty cylinder bore behind it. '
     'Keep everything else exactly identical and in the same position.', [CANVAS]),
    ('r2-orbit', 'Clean educational illustration, top view, on a plain warm off-white background: a child\'s hand at '
     'the centre whirling a small red stone on a taut string. ' + PATH_STYLE + 'It shows the complete circular path '
     'the stone travels around the hand, passing through the stone. Soft flat colours, no text, no labels.', []),
    ('r2-ramp', 'Clean educational illustration, side view, on a plain warm off-white background: a wooden '
     'skateboard half-pipe ramp with a small blue ball resting at the top of its left side. ' + PATH_STYLE +
     'It shows the path the ball will roll along the ramp surface, down and up the other side. '
     'Soft flat colours, no text, no labels.', []),
]


def main(selected):
    for name, prompt, refs in JOBS:
        if selected and name not in selected:
            continue
        path = generate(name, prompt, width=W, height=H, steps=30, references=refs)
        print(json.dumps({'name': name, 'path': str(path)}), flush=True)


if __name__ == '__main__':
    main(set(sys.argv[1:]))


def round3():
    empty = ROOT / 'registered' / 'b-empty.png'
    return generate('r3-empty-novalves', 'Edit the reference engine cutaway: remove the two valves completely, '
                    'including their stems, heads and springs, leaving the empty valve guides and open ports. Keep '
                    'the empty cylinder, empty crankcase, housing, ports and spark plug exactly identical.',
                    width=W, height=H, steps=30, references=[empty])


def round4():
    out = {}
    out['orbit-bg'] = generate('r4-orbit-bg', 'Edit the reference illustration: remove the red stone and the string '
                               'completely. Keep the hand, the background and the framing exactly identical.',
                               width=W, height=H, steps=30, references=[ROOT / 'paths' / 'r2-orbit-clean.png'])
    out['ramp-bg'] = generate('r4-ramp-bg', 'Edit the reference illustration: remove the blue ball completely. Keep '
                              'the ramp, its shadow, the background and the framing exactly identical.',
                              width=W, height=H, steps=30, references=[ROOT / 'paths' / 'r2-ramp-clean.png'])
    return out


def round5():
    """Hypothesis: edits of the model's NATIVE output stay clean; edits of resampled/inpainted copies get grainy."""
    out = {}
    out['orbit-bg'] = generate('r5-orbit-bg', 'Edit the reference illustration: remove the red stone, the string and the '
                               'magenta dashed circle completely. Keep the hand, the plain background and the framing '
                               'exactly identical.', width=W, height=H, steps=30,
                               references=[sorted((ROOT / 'images').glob('r2-orbit-*.png'))[0]])
    out['ramp-bg'] = generate('r5-ramp-bg', 'Edit the reference illustration: remove the blue ball and the magenta '
                              'dashed line completely. Keep the ramp, its shadow, the plain background and the framing '
                              'exactly identical.', width=W, height=H, steps=30,
                              references=[sorted((ROOT / 'images').glob('r2-ramp-*.png'))[0]])
    return out
