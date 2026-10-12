"""E4: can a vision model + SAM2 find the moving parts without hand calibration?

Step 1 (system python): Qwen vision on 10.8.0.5 names the movable parts, their roles,
boxes and attachment points. Step 2 (MG-Gen venv): SAM2 refines each box into a mask.
Both are compared with the four-stroke pilot's hand-calibrated masks.
"""
import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QWEN = 'http://10.8.0.5:8001/v1'
OUT = ROOT / 'grounding'

PROMPT = '''You are preparing an educational animation from this illustration.
List every part that MOVES when this machine operates (not the fixed housing).
For each part give a short id, its role, a tight bounding box, and named attachment
points (pivots, joints, axle centres) that an animator needs.
Coordinates: integers on a 0-1000 scale relative to image width (x) and height (y).
Also say how each part moves (rotate about a pivot, slide along an axis, swing, open/close)
and which parts are linked to each other.
Return JSON: {"parts":[{"id":str,"role":str,"bbox":[x1,y1,x2,y2],
"points":{"name":[x,y]},"motion":str,"linked_to":[str]}],"fixed":[str],"notes":str}'''


def ask(image_path, prompt=PROMPT, name='engine'):
    import httpx
    data = base64.b64encode(Path(image_path).read_bytes()).decode()
    with httpx.Client(timeout=600) as client:
        model = client.get(QWEN + '/models').json()['data'][0]['id']
        body = {'model': model, 'temperature': 0.1, 'max_tokens': 6000,
                'response_format': {'type': 'json_object'},
                'chat_template_kwargs': {'enable_thinking': True}, 'thinking_budget_tokens': 2048,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + data}},
                    {'type': 'text', 'text': prompt}]}]}
        raw = client.post(QWEN + '/chat/completions', json=body).raise_for_status().json()
    OUT.mkdir(exist_ok=True)
    (OUT / f'{name}-response.json').write_text(json.dumps(raw, indent=2))
    text = re.sub(r'<think>.*?</think>', '', raw['choices'][0]['message']['content'] or '', flags=re.S).strip()
    result = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', text))
    (OUT / f'{name}-parts.json').write_text(json.dumps(result, indent=2))
    return result


def segment(image_path, name='engine'):
    """Run inside the MG-Gen venv (ultralytics SAM2, CPU)."""
    import os
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    import numpy as np
    from PIL import Image
    from ultralytics import SAM
    weights = '/home/nitin/remotion/artifacts/experiments/circular-image-mggen-manim/vendor/MG-GEN/weights/sam2_b.pt'
    image = Image.open(image_path).convert('RGB')
    W, H = image.size
    parts = json.loads((OUT / f'{name}-parts.json').read_text())['parts']
    sam = SAM(weights)
    masks = {}
    for part in parts:
        x1, y1, x2, y2 = part['bbox']
        box = [x1 * W / 1000, y1 * H / 1000, x2 * W / 1000, y2 * H / 1000]
        result = sam(source=image, bboxes=[box], device='cpu', verbose=False)[0]
        mask = result.masks.data[0].cpu().numpy() > .5
        Image.fromarray((mask * 255).astype(np.uint8)).save(OUT / f"{name}-{part['id']}-mask.png")
        rgba = np.dstack([np.array(image), (mask * 255).astype(np.uint8)])
        Image.fromarray(rgba).save(OUT / f"{name}-{part['id']}.png")
        masks[part['id']] = box
    (OUT / f'{name}-boxes-px.json').write_text(json.dumps(masks, indent=2))


def compare(name='engine'):
    import numpy as np
    from PIL import Image
    pilot = Path('/home/nitin/remotion/artifacts/experiments/four-stroke-image-mggen-manim')
    manual = json.loads((pilot / 'parts-spec.json').read_text())['parts']
    found = json.loads((OUT / f'{name}-parts.json').read_text())['parts']
    W, H = 1672, 941
    rows = []
    for part_id in manual:
        ref = np.array(Image.open(pilot / 'layers' / f'{part_id}-mask.png')) > 127
        best = None
        for part in found:
            path = OUT / f"{name}-{part['id']}-mask.png"
            if not path.exists():
                continue
            m = np.array(Image.open(path)) > 127
            iou = (m & ref).sum() / max(1, (m | ref).sum())
            if best is None or iou > best[1]:
                best = (part['id'], float(iou))
        anchors = manual[part_id].get('source_anchors', {})
        rows.append({'manual_part': part_id, 'matched': best and best[0], 'mask_iou': best and round(best[1], 3),
                     'manual_anchors_px': anchors})
    pts = {p['id']: {k: [round(v[0] * W / 1000), round(v[1] * H / 1000)] for k, v in p.get('points', {}).items()}
           for p in found}
    report = {'per_manual_part': rows, 'model_points_px': pts,
              'model_motion': {p['id']: p.get('motion') for p in found},
              'model_links': {p['id']: p.get('linked_to') for p in found}}
    (OUT / f'{name}-compare.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    step, image = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else str(ROOT / 'inputs/engine-canvas.png')
    name = sys.argv[3] if len(sys.argv) > 3 else 'engine'
    {'ask': lambda: print(json.dumps(ask(image, name=name), indent=2)),
     'segment': lambda: segment(image, name), 'compare': lambda: compare(name)}[step]()
