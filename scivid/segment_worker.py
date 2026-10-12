"""SAM2 cut-outs (runs in the MG-Gen CPU venv). Input/output via a JSON job file.

job = {"image": path, "weights": path, "out": dir, "boxes": {object_id: [x0,y0,x1,y1]}}
writes <out>/<id>.png (cropped RGBA), <out>/<id>-mask.png (full-frame) and <out>/segments.json
"""
import json
import os
import sys
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES'] = ''


def main(job_path):
    import cv2
    import numpy as np
    from PIL import Image
    from ultralytics import SAM
    job = json.loads(Path(job_path).read_text())
    out = Path(job['out'])
    out.mkdir(parents=True, exist_ok=True)
    image = Image.open(job['image']).convert('RGB')
    rgb = np.array(image)
    sam = SAM(job['weights'])
    report = {}
    for oid, box in job['boxes'].items():
        result = sam(source=image, bboxes=[box], device='cpu', verbose=False)[0]
        mask = result.masks.data[0].cpu().numpy() > .5
        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
        if n > 2:
            mask = labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        ys, xs = np.nonzero(mask)
        if not len(xs):
            report[oid] = {'error': 'empty mask'}
            continue
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        rgba = np.dstack([rgb, (mask * 255).astype(np.uint8)])[y0:y1, x0:x1]
        Image.fromarray(rgba).save(out / f'{oid}.png')
        Image.fromarray((mask * 255).astype(np.uint8)).save(out / f'{oid}-mask.png')
        bx = box
        box_area = max(1, (bx[2] - bx[0]) * (bx[3] - bx[1]))
        report[oid] = {'layer': str(out / f'{oid}.png'), 'mask': str(out / f'{oid}-mask.png'),
                       'bbox': [x0, y0, x1, y1], 'area': int(mask.sum()),
                       'fill_of_box': round(float(mask.sum() / box_area), 3)}
    (out / 'segments.json').write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
