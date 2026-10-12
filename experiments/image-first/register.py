"""Register edited images to the canvas (similarity transform) and report the warp.

Edits may rescale/shift the whole scene (b-bdc did). Feature matching on the fixed
housing recovers that transform so measured positions share the canvas frame.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'registered'
BG = (253, 250, 242)


def load_rgb(path, size=None):
    im = Image.open(path)
    if im.mode == 'RGBA':
        bg = Image.new('RGBA', im.size, BG + (255,))
        bg.alpha_composite(im)
        im = bg
    im = im.convert('RGB')
    return np.array(im.resize(size, Image.LANCZOS) if size else im)


def register(moving_path, fixed_path=ROOT / 'inputs/engine-canvas.png', exclude=None):
    fixed = load_rgb(fixed_path)
    H, W = fixed.shape[:2]
    moving = load_rgb(moving_path, (W, H))
    sift = cv2.SIFT_create(6000)
    gf, gm = cv2.cvtColor(fixed, cv2.COLOR_RGB2GRAY), cv2.cvtColor(moving, cv2.COLOR_RGB2GRAY)
    mask = None
    if exclude is not None:
        mask = (~exclude).astype(np.uint8) * 255  # features only on the fixed housing
    kf, df = sift.detectAndCompute(gf, mask)
    km, dm = sift.detectAndCompute(gm, None)
    matches = cv2.BFMatcher().knnMatch(dm, df, k=2)
    good = [m for m, n in matches if m.distance < .7 * n.distance]
    src = np.float32([km[m.queryIdx].pt for m in good])
    dst = np.float32([kf[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3)
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    angle = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    warped = cv2.warpAffine(moving, M, (W, H), borderValue=BG)
    resid = np.abs(warped.astype(int) - fixed.astype(int)).mean(2)
    keep = exclude is None or ~exclude
    info = {'matches': len(good), 'inliers': int(inl.sum()), 'scale': round(scale, 4), 'rotation_deg': round(angle, 3),
            'translation_px': [round(float(M[0, 2]), 1), round(float(M[1, 2]), 1)],
            'mean_diff_fixed_region_after': round(float(resid[keep].mean()), 2),
            'matrix': M.tolist()}
    OUT.mkdir(exist_ok=True)
    name = Path(moving_path).stem.rsplit('-', 1)[0]
    Image.fromarray(warped).save(OUT / f'{name}.png')
    # Keep the edit's own alpha (if any) under the same warp.
    src_img = Image.open(moving_path)
    if src_img.mode == 'RGBA':
        a = np.array(src_img.resize((W, H), Image.LANCZOS))
        Image.fromarray(cv2.warpAffine(a, M, (W, H), borderValue=(0, 0, 0, 0))).save(OUT / f'{name}-rgba.png')
    return info


if __name__ == '__main__':
    # Exclusion uses the automatic grounding masks, not the pilot's hand calibration.
    moving = np.zeros((941, 1672), bool)
    for m in (ROOT / 'grounding').glob('engine-*-mask.png'):
        moving |= np.array(Image.open(m)) > 127
    moving = cv2.dilate(moving.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    report = {}
    for name in sys.argv[1:]:
        path = sorted((ROOT / 'images').glob(name + '-*.png'), key=lambda p: p.stat().st_mtime)[-1]
        try:
            report[name] = register(path, exclude=moving)
        except TypeError:
            print(name, "no housing to register (isolated part)"); continue
        print(name, json.dumps({k: v for k, v in report[name].items() if k != 'matrix'}))
    (OUT / 'registration.json').write_text(json.dumps(report, indent=2))
