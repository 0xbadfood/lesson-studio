"""Background = clean first-generation 'empty engine' + valve zones from the valve-free re-edit."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
L = ROOT / 'layers'


def main():
    scene = json.loads((L / 'scene.json').read_text())
    W, H = scene['canvas_size']
    base = np.array(Image.open(ROOT / 'registered/b-empty.png').convert('RGB')).astype(float)
    patch = np.array(Image.open(ROOT / 'registered/r3-empty-novalves.png').convert('RGB')).astype(float)
    zone = np.zeros((H, W), np.uint8)
    for name in ('valve_L', 'valve_R'):
        info = scene['layers'][name]
        x0, y0, x1, y1 = info['bbox_px']
        alpha = np.array(Image.open(L / info['file']))[..., 3] > 127
        zone[y0:y1, x0:x1] |= alpha.astype(np.uint8)
    zone = cv2.dilate(zone, np.ones((17, 17), np.uint8))
    # Match the patch's tone to the base just outside the zone.
    ring = (cv2.dilate(zone, np.ones((31, 31), np.uint8)) > 0) & (zone == 0)
    patch = patch + (base[ring].mean(0) - patch[ring].mean(0))
    # Page-coloured pixels inside the zone become the flat page colour (removes edit grain).
    page = np.median(base[:40, -200:].reshape(-1, 3), axis=0)
    near_page = np.abs(patch - page).max(2) < 22
    patch[near_page] = page
    feather = cv2.GaussianBlur(zone.astype(float), (0, 0), 3)[..., None]
    out = np.clip(base * (1 - feather) + patch * feather, 0, 255).astype(np.uint8)
    Image.fromarray(out).save(L / 'background.png')
    scene['background'] = str(L / 'background.png')
    scene['background_recipe'] = 'b-empty + feathered valve zones from r3-empty-novalves (tone-matched)'
    (L / 'scene.json').write_text(json.dumps(scene, indent=2))


if __name__ == '__main__':
    main()
