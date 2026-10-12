"""Submit a real API pilot without printing the API token."""
import json
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
headers={'Authorization':'Bearer '+(ROOT/'api-data/api-token').read_text().strip()}
with httpx.Client(base_url='http://127.0.0.1:18610',headers=headers,timeout=30) as client:
    health=client.get('/api/health');health.raise_for_status()
    print('Health:',json.dumps(health.json()),flush=True)
    response=client.post('/api/jobs',headers={'Idempotency-Key':'live-api-pilot-01'},json={
        'topic':'Centripetal and centrifugal force: circular motion and the two viewpoints',
        'audience':'High-school students','duration_seconds':30,'quality':'hd',
        'instructions':'Use exactly two concise scenes. Show inward real force and tangent velocity in a top view, then distinguish the rotating frame outward pseudo-force. Correct the misconception of a real outward force. Ignore gravity and drag. Prefer simple clear computed diagrams.'})
    response.raise_for_status();job=response.json()
    (ROOT/'artifacts/api-live-pilot.json').write_text(json.dumps({'job_id':job['id'],'request':job['request']},indent=2)+'\n')
    print('Submitted:',job['id'],job['status'],flush=True)
