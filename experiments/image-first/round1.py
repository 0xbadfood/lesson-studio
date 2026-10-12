"""Round 1: can Qwen Image 2.1 supply parts, states and paths for the engine canvas?"""
import json
import sys
from qimage import ROOT, generate

CANVAS = ROOT / 'inputs' / 'engine-canvas.png'
W, H = 1664, 944  # canvas is 1672x941; nearest /16 size with the same aspect
RGBA = 'This is an RGBA image with transparency. '
ALPHA = ' The image has alpha channel and the background is transparent.'

JOBS = [
    # A: transparent, complete moving parts extracted from the canvas (editing).
    ('a-piston', RGBA + 'Extract only the piston (with its rings and wrist pin) from the reference engine cutaway. '
     'Keep its exact appearance, size and position in the frame. Remove everything else.' + ALPHA, True),
    ('a-crankshaft', RGBA + 'Extract only the crankshaft from the reference engine cutaway: the dark round crank web '
     'with its counterweight, the main shaft hub and the crank pin. Show the complete crankshaft, including the parts '
     'currently hidden behind the connecting rod. Keep its exact appearance, size and position. Remove everything else.' + ALPHA, True),
    ('a-rod', RGBA + 'Extract only the copper connecting rod from the reference engine cutaway, complete from the '
     'small end to the big end. Keep its exact appearance, size and position. Remove everything else.' + ALPHA, True),
    ('a-valves', RGBA + 'Extract only the two valves (intake and exhaust, each with its stem and spring) from the '
     'reference engine cutaway. Keep their exact appearance, size and position. Remove everything else.' + ALPHA, True),
    # B: the world model supplies the scene's other states.
    ('b-empty', 'Edit the reference engine cutaway: remove the piston, the connecting rod and the crankshaft, '
     'leaving the empty cylinder bore and the empty crankcase cavity with clean walls. Keep the engine housing, '
     'ports, valves, springs and spark plug exactly identical and in the same position.', True),
    ('b-bdc', 'Edit the reference engine cutaway to show the next moment of the engine: the crankshaft has rotated '
     'half a turn so the crank pin is now at the bottom, and the piston has moved down to the bottom of the cylinder '
     '(bottom dead centre), still joined to the crank pin by the connecting rod. Keep the engine housing, valves, '
     'spark plug, colours, style and framing exactly identical.', True),
    # C: a new subject whose motion path is drawn by the image model, then erased.
    ('c-orbit-path', 'Clean educational illustration, top view, on a plain warm off-white background: a child\'s '
     'hand at the centre whirling a small red stone on a string. A dashed circular line shows the full path the stone '
     'travels around the hand. Soft flat colours, no text, no labels.', False),
]


def main(selected):
    for name, prompt, uses_canvas in JOBS:
        if selected and name not in selected:
            continue
        path = generate(name, prompt, width=W, height=H, steps=30,
                        references=[CANVAS] if uses_canvas else ())
        print(json.dumps({'name': name, 'path': str(path)}), flush=True)
    # The orbit path is erased by a follow-up edit of the generated image.
    if not selected or 'c-orbit-clean' in selected:
        source = sorted((ROOT / 'images').glob('c-orbit-path-*.png'))[-1]
        path = generate('c-orbit-clean', 'Edit the reference illustration: remove only the dashed circular path line. '
                        'Keep the hand, string, stone, background and framing exactly identical.',
                        width=W, height=H, steps=30, references=[source])
        print(json.dumps({'name': 'c-orbit-clean', 'path': str(path)}), flush=True)


if __name__ == '__main__':
    main(set(sys.argv[1:]))
