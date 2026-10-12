"""Cut animation layers (MG-Gen venv: SAM2 on CPU) and measure the mechanism.

Sources (all automatic):
  piston, valves  - SAM2 on the original canvas (grounding boxes)
  crankshaft      - SAM2 on the 'extract crankshaft' edit: rod peeled away, hidden surface completed
  connecting rod  - SAM2 on the 'remove piston' edit: small end completed
  background      - 'empty engine, no valves' edit
Anchors come from the vision model's points; the crank axle is refined with Hough circles.
"""
import json
import os
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES'] = ''
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
G, R, OUT = ROOT / 'grounding', ROOT / 'registered', ROOT / 'layers'
W, H = 1672, 941


def px(p):
    return [p[0] * W / 1000, p[1] * H / 1000]


def sam_cut(sam, image_path, box, name):
    image = Image.open(image_path).convert('RGB').resize((W, H))
    result = sam(source=image, bboxes=[box], device='cpu', verbose=False)[0]
    mask = result.masks.data[0].cpu().numpy() > .5
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if n > 2:  # keep the largest component only
        mask = labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    rgba = np.dstack([np.array(image), (mask * 255).astype(np.uint8)])
    ys, xs = np.nonzero(mask)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    Image.fromarray(rgba[y0:y1, x0:x1]).save(OUT / f'{name}.png')
    return {'file': f'{name}.png', 'bbox_px': [x0, y0, x1, y1], 'source': Path(image_path).name,
            'area_px': int(mask.sum())}


def robust_center(image_path, guess, search=60):
    gray = cv2.cvtColor(np.array(Image.open(image_path).convert('RGB').resize((W, H))), cv2.COLOR_RGB2GRAY)
    x, y = map(int, guess)
    crop = cv2.GaussianBlur(gray[y - search:y + search, x - search:x + search], (5, 5), 1.5)
    found = cv2.HoughCircles(crop, cv2.HOUGH_GRADIENT, dp=1, minDist=2, param1=80, param2=14,
                             minRadius=8, maxRadius=search)
    if found is None:
        return list(map(float, guess)), 0
    c = found[0][:, :2] + [x - search, y - search]
    near = c[np.hypot(c[:, 0] - x, c[:, 1] - y) < 25]
    if not len(near):
        return list(map(float, guess)), 0
    return [round(float(np.median(near[:, 0])), 1), round(float(np.median(near[:, 1])), 1)], int(len(near))


def main():
    from ultralytics import SAM
    sam = SAM('/home/nitin/remotion/artifacts/experiments/circular-image-mggen-manim/vendor/MG-GEN/weights/sam2_b.pt')
    OUT.mkdir(exist_ok=True)
    parts = {p['id']: p for p in json.loads((G / 'engine-parts.json').read_text())['parts']}
    fixed = json.loads((G / 'engine-fixed-parts.json').read_text())
    box = lambda pid, pad=0: [parts[pid]['bbox'][0] * W / 1000 - pad, parts[pid]['bbox'][1] * H / 1000 - pad,
                              parts[pid]['bbox'][2] * W / 1000 + pad, parts[pid]['bbox'][3] * H / 1000 + pad]
    canvas = ROOT / 'inputs/engine-canvas.png'
    wrist = px(parts['piston']['points']['wrist_pin_centre'])
    layers = {
        'piston': sam_cut(sam, canvas, box('piston'), 'piston'),
        'valve_L': sam_cut(sam, canvas, box('valve_L'), 'valve_L'),
        'valve_R': sam_cut(sam, canvas, box('valve_R'), 'valve_R'),
        'crankshaft': sam_cut(sam, R / 'a-crankshaft.png', box('crankshaft', 12), 'crankshaft'),
    }
    rb = box('conrod', 8)
    rb[1] = wrist[1] - 40  # the rod's completed small end reaches the wrist pin
    layers['conrod'] = sam_cut(sam, R / 'r2-nopiston.png', rb, 'conrod')
    axle_model = px(parts['crankshaft']['points']['main_axle_centre'])
    axle, votes = robust_center(R / 'a-crankshaft.png', axle_model)
    anchors = {'wrist_pin': [round(v, 1) for v in wrist],
               'crank_pin': [round(v, 1) for v in px(parts['crankshaft']['points']['crank_pin_centre'])],
               'axle': axle, 'axle_model': [round(v, 1) for v in axle_model], 'axle_hough_votes': votes,
               'rod_small_end': [round(v, 1) for v in wrist],
               'rod_big_end': [round(v, 1) for v in px(parts['conrod']['points']['big_end_centre'])],
               'valve_L_head': [round(v, 1) for v in px(parts['valve_L']['points']['valve_head_seat'])],
               'valve_R_head': [round(v, 1) for v in px(parts['valve_R']['points']['valve_head_seat'])]}
    a, p, w = np.array(anchors['axle']), np.array(anchors['crank_pin']), np.array(anchors['wrist_pin'])
    mech = {'crank_radius_px': round(float(np.linalg.norm(p - a)), 1),
            'rod_length_px': round(float(np.linalg.norm(w - p)), 1),
            'pin_angle_deg': round(float(np.degrees(np.arctan2(p[1] - a[1], p[0] - a[0]))), 2),
            'cylinder_axis_offset_px': round(float(w[0] - a[0]), 1)}
    background = sorted((ROOT / 'images').glob('r3-empty-novalves-*.png'))
    scene = {'canvas_size': [W, H], 'layers': layers, 'anchors': anchors, 'mechanism': mech,
             'fixed': {k: ([px(v) for v in fixed[k]] if k.endswith('passage') else
                           (px(fixed[k]) if len(fixed[k]) == 2 else px(fixed[k][:2]) + px(fixed[k][2:])))
                       for k in fixed},
             'background': str(R / 'r3-empty-novalves.png') if background else str(R / 'b-empty.png')}
    (OUT / 'scene.json').write_text(json.dumps(scene, indent=2))
    print(json.dumps({'anchors': anchors, 'mechanism': mech, 'layers': layers}, indent=1))


if __name__ == '__main__':
    main()
