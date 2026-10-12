"""Watch durable progress without making requests to the model or API."""
import argparse
import json
from pathlib import Path
import time

parser=argparse.ArgumentParser()
parser.add_argument('job_id')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]/'api-data/runs'/args.job_id
last=None
while True:
    state=json.loads((root/'state.json').read_text())
    signature=(state.get('run_id'),state['stage'],state['message'],state.get('attempt'))
    if signature!=last:
        print(json.dumps(state),flush=True)
        last=signature
    if state['stage'] in ('done','failed','cancelled'):
        break
    time.sleep(15)
