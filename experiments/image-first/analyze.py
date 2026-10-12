"""Measure round-1 images against the canvas and the pilot's hand-calibrated masks."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
PILOT = Path('/home/nitin/remotion/artifacts/experiments/four-stroke-image-mggen-manim/layers')
CANVAS = np.array(Image.open(ROOT / 'inputs/engine-canvas.png').convert('RGB'))
H, W = CANVAS.shape[:2]


def latest(name):
    found = sorted((ROOT / 'images').glob(name + '-*.png'), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def manual(*names):
    mask = np.zeros((H, W), bool)
    for n in names:
        mask |= np.array(Image.open(PILOT / f'{n}-mask.png')) > 127
    return mask


def to_canvas(img):
    return np.array(img.resize((W, H), Image.LANCZOS))


def checkerboard_score(rgb, opaque):
    """Baked-in transparency grids: alternating light-grey squares in 'opaque' background."""
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(float)
    region = ~opaque
    if region.sum() < 1000:
        region = np.ones_like(opaque)
    low_sat = (rgb.max(2).astype(int) - rgb.min(2)) < 12
    return float((low_sat & region).mean()), float(grey[region].std())


def part_report(name, manual_names):
    path = latest(name)
    if not path:
        return None
    img = Image.open(path)
    out = {'file': path.name, 'mode': img.mode, 'size': img.size}
    if img.mode != 'RGBA':
        out['verdict'] = 'no alpha channel'
        return out
    rgba = to_canvas(img)
    alpha = rgba[..., 3]
    opaque = alpha > 127
    out['alpha'] = {'opaque_fraction': round(float(opaque.mean()), 4),
                    'transparent_fraction': round(float((alpha < 8).mean()), 4),
                    'soft_edge_fraction': round(float(((alpha >= 8) & (alpha <= 247)).mean()), 4)}
    # Checkerboard: if transparent areas are actually painted, the alpha says opaque everywhere.
    out['fake_transparency_suspect'] = bool(opaque.mean() > .9)
    ref = manual(*manual_names)
    inter, union = (opaque & ref).sum(), (opaque | ref).sum()
    ys, xs = np.nonzero(opaque)
    ry, rx = np.nonzero(ref)
    if len(xs):
        gb = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        rb = [int(rx.min()), int(ry.min()), int(rx.max()), int(ry.max())]
        out['vs_manual_mask'] = {
            'iou': round(float(inter / union), 3),
            'manual_covered': round(float(inter / ref.sum()), 3),
            'area_ratio': round(float(opaque.sum() / ref.sum()), 3),
            'centroid_offset_px': [round(float(xs.mean() - rx.mean()), 1), round(float(ys.mean() - ry.mean()), 1)],
            'bbox_generated': gb, 'bbox_manual': rb,
            'scale_ratio_wh': [round((gb[2] - gb[0]) / max(1, rb[2] - rb[0]), 3),
                               round((gb[3] - gb[1]) / max(1, rb[3] - rb[1]), 3)]}
        # Appearance: colour difference against canvas pixels inside the overlap.
        both = opaque & ref
        if both.sum():
            out['vs_manual_mask']['mean_rgb_diff_in_overlap'] = round(float(
                np.abs(rgba[..., :3].astype(int) - CANVAS.astype(int))[both].mean()), 1)
    return out


def scene_diff(name, moving_names):
    path = latest(name)
    if not path:
        return None
    rgb = to_canvas(Image.open(path).convert('RGB')).astype(int)
    diff = np.abs(rgb - CANVAS.astype(int)).mean(2)
    moving = cv2.dilate(manual(*moving_names).astype(np.uint8), np.ones((41, 41), np.uint8)) > 0
    # Region the edit was told to keep identical: everything except the moving parts and the cavities.
    keep = ~moving
    changed = diff > 30
    return {'file': path.name,
            'mean_diff_keep_region': round(float(diff[keep].mean()), 2),
            'changed_fraction_keep_region': round(float(changed[keep].mean()), 4),
            'mean_diff_moving_region': round(float(diff[moving].mean()), 2),
            'changed_fraction_moving_region': round(float(changed[moving].mean()), 4)}


def fit_circle(xs, ys):
    A = np.c_[2 * xs, 2 * ys, np.ones(len(xs))]
    b = xs ** 2 + ys ** 2
    cx, cy, c = np.linalg.lstsq(A, b, rcond=None)[0]
    r = np.sqrt(c + cx ** 2 + cy ** 2)
    resid = np.abs(np.hypot(xs - cx, ys - cy) - r)
    return float(cx), float(cy), float(r), resid


def path_report():
    a, b = latest('c-orbit-path'), latest('c-orbit-clean')
    if not (a and b):
        return None
    pa = np.array(Image.open(a).convert('RGB')).astype(int)
    pb = np.array(Image.open(b).convert('RGB')).astype(int)
    diff = np.abs(pa - pb).mean(2)
    mask = (diff > 40).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    ys, xs = np.nonzero(mask)
    out = {'files': [a.name, b.name], 'diff_pixels': int(len(xs)),
           'mean_diff_elsewhere': round(float(diff[mask == 0].mean()), 2)}
    if len(xs) > 50:
        cx, cy, r, resid = fit_circle(xs.astype(float), ys.astype(float))
        inl = resid < 6
        cx, cy, r, resid2 = fit_circle(xs[inl].astype(float), ys[inl].astype(float))
        ang = np.degrees(np.arctan2(ys[inl] - cy, xs[inl] - cx))
        cover = len(np.unique((ang // 5).astype(int))) * 5
        out['circle'] = {'center_px': [round(cx, 1), round(cy, 1)], 'radius_px': round(r, 1),
                         'inlier_fraction': round(float(inl.mean()), 3),
                         'median_residual_px': round(float(np.median(resid2)), 2),
                         'angular_coverage_deg': int(cover)}
        Image.fromarray(mask * 255).save(ROOT / 'images' / 'c-orbit-path-mask.png')
    return out


def main():
    report = {
        'parts': {n: part_report(n, m) for n, m in [
            ('a-piston', ['piston']), ('a-crankshaft', ['crankshaft']),
            ('a-rod', ['connecting_rod']), ('a-valves', ['intake_valve', 'exhaust_valve'])]},
        'states': {n: scene_diff(n, ['piston', 'connecting_rod', 'crankshaft']) for n in ['b-empty', 'b-bdc']},
        'path': path_report()}
    (ROOT / 'round1-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
