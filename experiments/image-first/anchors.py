"""Snap the vision model's approximate pivots to measured circular features.

The model says *which* pivots exist and roughly where; Hough circles inside the
part's own mask say exactly where. Nothing is hand-calibrated.
"""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
G = ROOT / 'grounding'


def circles_near(gray, point, search=45):
    x, y = point
    x0, y0 = max(0, x - search), max(0, y - search)
    crop = cv2.GaussianBlur(gray[y0:y + search, x0:x + search], (5, 5), 1.5)
    found = cv2.HoughCircles(crop, cv2.HOUGH_GRADIENT, dp=1, minDist=6, param1=90, param2=18,
                             minRadius=6, maxRadius=search)
    if found is None:
        return None
    best = min(found[0], key=lambda c: np.hypot(c[0] + x0 - x, c[1] + y0 - y))
    return [round(float(best[0] + x0), 1), round(float(best[1] + y0), 1), round(float(best[2]), 1)]


def snap(image_path, name):
    gray = cv2.cvtColor(np.array(Image.open(image_path).convert('RGB')), cv2.COLOR_RGB2GRAY)
    H, W = gray.shape
    parts = json.loads((G / f'{name}-parts.json').read_text())['parts']
    out = {}
    for part in parts:
        for key, (px, py) in part.get('points', {}).items():
            point = [round(px * W / 1000), round(py * H / 1000)]
            c = circles_near(gray, point)
            out[f"{part['id']}.{key}"] = {'model_px': point, 'snapped_circle': c,
                                          'moved_px': c and round(float(np.hypot(c[0] - point[0], c[1] - point[1])), 1)}
    return out


if __name__ == '__main__':
    result = snap(ROOT / 'inputs/engine-canvas.png', 'engine')
    manual = {'piston.wrist_pin_centre': [641, 407], 'conrod.small_end_centre': [641, 407],
              'conrod.big_end_centre': [735, 683], 'crankshaft.crank_pin_centre': [735, 683],
              'crankshaft.main_axle_centre': [641, 680]}
    for key, ref in manual.items():
        r = result[key]
        r['manual_px'] = ref
        r['model_error_px'] = round(float(np.hypot(r['model_px'][0] - ref[0], r['model_px'][1] - ref[1])), 1)
        if r['snapped_circle']:
            r['snapped_error_px'] = round(float(np.hypot(r['snapped_circle'][0] - ref[0], r['snapped_circle'][1] - ref[1])), 1)
    (G / 'engine-anchors.json').write_text(json.dumps(result, indent=2))
    for key, r in result.items():
        print(key, {k: v for k, v in r.items() if k != 'model_px'})
