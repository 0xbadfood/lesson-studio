"""Compare this fresh Luna run with the actual earlier Qwen attempts."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.storage import read_json,write_json
from manim_api.usage import write_usage_report


def intervals(root):
    events=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
    stages=defaultdict(float)
    scenes=defaultdict(lambda:defaultdict(float))
    attempts=defaultdict(int)
    for event in events:
        if event['stage']=='coding':attempts[event['scene']]+=1
    for current,following in zip(events,events[1:]):
        if current['run_id']!=following['run_id']:continue
        elapsed=following['updated']-current['updated']
        stages[current['stage']]+=elapsed
        if current.get('scene'):scenes[current['scene']][current['stage']]+=elapsed
    return {'stages':{k:round(v,3) for k,v in stages.items()},
            'scene_stages':{s:{k:round(v,3) for k,v in stages.items()} for s,stages in scenes.items()},
            'coding_attempts':dict(attempts)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('job_id');parser.add_argument('original_job')
    args=parser.parse_args()
    runs=ROOT/'api-data/runs'
    root=runs/args.job_id;old=runs/args.original_job
    if read_json(root/'terminal.json')['status']!='succeeded':raise SystemExit('New video is not complete')
    report=read_json(root/'report.json')
    assert report['request']==read_json(old/'request.json')
    assert all(s['author_model']=='gpt-6-luna' and s['review']['pass'] is True for s in report['scenes'])
    usage=write_usage_report(root)
    before=intervals(old);after=intervals(root)
    result={'job_id':args.job_id,'original_job_id':args.original_job,'request':report['request'],
            'video':report['video'],'new_model_tokens':usage['by_model'],
            'new_coding_by_scene':usage['coding_by_scene'],
            'new_stage_seconds':after['stages'],'previous_stage_seconds':before['stages'],
            'coding_comparison':[{ 'scene':s['id'],
                'previous_qwen_coding_attempts':before['coding_attempts'].get(s['id']),
                'previous_qwen_coding_seconds':before['scene_stages'].get(s['id'],{}).get('coding'),
                'new_luna_coding_attempts':after['coding_attempts'].get(s['id']),
                'new_luna_coding_seconds':after['scene_stages'][s['id']]['coding'],
                'new_scene_accepted':s['review']['pass']} for s in report['scenes']],
            'limitations':['One video, not a general model benchmark.',
                           'Qwen previously failed before completing all scenes; its attempts span three interrupted/retried runs.',
                           'Both providers use the same lesson inputs; runtime helper fixes and reasoning budgets differ.',
                           'New run reused existing research/storyboard; those older calls are excluded from its token totals.',
                           'Luna high reasoning matches the existing Remotion provider setting.']}
    write_json(root/'coding-benchmark.json',result)
    write_json(ROOT/'artifacts/luna-coding-benchmark.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
