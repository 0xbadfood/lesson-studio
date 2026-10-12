"""Extract colour-keyed (magenta) motion paths, fit/order them, and erase them."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'paths'


def magenta_mask(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    # OpenCV hue 0-179: magenta ~150; saturated and bright.
    m = ((hsv[..., 0] > 135) & (hsv[..., 0] < 165) & (hsv[..., 1] > 110) & (hsv[..., 2] > 120))
    return m


def fit_circle(xs, ys):
    A = np.c_[2 * xs, 2 * ys, np.ones(len(xs))]
    cx, cy, c = np.linalg.lstsq(A, xs ** 2 + ys ** 2, rcond=None)[0]
    r = np.sqrt(c + cx ** 2 + cy ** 2)
    return float(cx), float(cy), float(r), np.abs(np.hypot(xs - cx, ys - cy) - r)


def order_open_path(mask, start_hint=None):
    """Chain dashed segments into one ordered polyline (nearest-neighbour on dash centroids)."""
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    pts = [(c, i) for i, c in enumerate(cents) if i and stats[i, cv2.CC_STAT_AREA] >= 4]
    # Use dense samples (skeleton-ish): every pixel thinned by dash, ordered along the chain.
    remaining = {i: c for c, i in pts}
    if start_hint is None:
        current = min(remaining, key=lambda i: remaining[i][0])
    else:
        current = min(remaining, key=lambda i: np.hypot(*(remaining[i] - start_hint)))
    order = [current]
    pos = remaining.pop(current)
    while remaining:
        nxt = min(remaining, key=lambda i: np.hypot(*(remaining[i] - pos)))
        gap = np.hypot(*(remaining[nxt] - pos))
        if gap > 120:
            break
        order.append(nxt)
        pos = remaining.pop(nxt)
    return [cents[i].tolist() for i in order], len(remaining)


def process(name, kind, start_hint=None):
    path = sorted((ROOT / 'images').glob(name + '-*.png'))[-1]
    rgb = np.array(Image.open(path).convert('RGB'))
    mask = magenta_mask(rgb)
    OUT.mkdir(exist_ok=True)
    Image.fromarray((mask * 255).astype(np.uint8)).save(OUT / f'{name}-mask.png')
    ys, xs = np.nonzero(mask)
    report = {'image': path.name, 'size': [rgb.shape[1], rgb.shape[0]], 'magenta_pixels': int(len(xs))}
    if kind == 'circle':
        cx, cy, r, resid = fit_circle(xs.astype(float), ys.astype(float))
        ang = np.degrees(np.arctan2(ys - cy, xs - cx))
        report['circle'] = {'center_px': [round(cx, 1), round(cy, 1)], 'radius_px': round(r, 1),
                            'median_residual_px': round(float(np.median(resid)), 2),
                            'p95_residual_px': round(float(np.percentile(resid, 95)), 2),
                            'angular_coverage_deg': int(len(np.unique((ang // 5).astype(int))) * 5)}
    else:
        points, leftover = order_open_path(mask, None if start_hint is None else np.array(start_hint))
        length = float(sum(np.hypot(*(np.subtract(b, a))) for a, b in zip(points, points[1:])))
        report['polyline'] = {'points_px': [[round(x, 1), round(y, 1)] for x, y in points],
                              'segments': len(points), 'unchained_segments': leftover,
                              'length_px': round(length, 1)}
    # Erase: inpaint the dilated magenta mask (thin line on a mostly flat surface).
    erase = cv2.dilate(mask.astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    clean = cv2.inpaint(bgr, erase, 5, cv2.INPAINT_TELEA)
    cv2.imwrite(str(OUT / f'{name}-clean.png'), clean)
    left = magenta_mask(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB)).sum()
    report['erase'] = {'method': 'cv2.inpaint TELEA on dilated colour mask', 'magenta_pixels_left': int(left)}
    (OUT / f'{name}.json').write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    print(json.dumps({k: v for k, v in process('r2-orbit', 'circle').items()}, indent=1))
    r = process('r2-ramp', 'open')
    r['polyline']['points_px'] = r['polyline']['points_px'][:3] + ['...'] + r['polyline']['points_px'][-2:]
    print(json.dumps(r, indent=1))
