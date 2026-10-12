"""Account for actual archived model responses, including unsuccessful attempts."""
import csv
from datetime import datetime, timezone
import re
from pathlib import Path

from .storage import read_json, write_json

FIELDS = ('input_tokens', 'cached_input_tokens', 'uncached_input_tokens',
          'cache_write_tokens', 'output_tokens', 'reasoning_tokens',
          'non_reasoning_output_tokens', 'total_tokens')


def normalize_usage(raw):
    usage = raw.get('usage') or {}
    responses = 'input_tokens' in usage
    inp = usage.get('input_tokens' if responses else 'prompt_tokens')
    out = usage.get('output_tokens' if responses else 'completion_tokens')
    input_detail = usage.get('input_tokens_details' if responses else 'prompt_tokens_details') or {}
    output_detail = usage.get('output_tokens_details' if responses else 'completion_tokens_details') or {}
    cached = input_detail.get('cached_tokens')
    reasoning = output_detail.get('reasoning_tokens')
    return {'input_tokens': inp, 'cached_input_tokens': cached,
            'uncached_input_tokens': inp - cached if inp is not None and cached is not None else None,
            'cache_write_tokens': input_detail.get('cache_write_tokens'),
            'output_tokens': out, 'reasoning_tokens': reasoning,
            'non_reasoning_output_tokens': out - reasoning if out is not None and reasoning is not None else None,
            'total_tokens': usage.get('total_tokens'), 'raw_usage': usage or None}


def summarize(calls):
    result = {'calls': len(calls), 'responses_with_usage': sum(c['raw_usage'] is not None for c in calls),
              'elapsed_seconds': round(sum(c['elapsed_seconds'] or 0 for c in calls), 3)}
    for field in FIELDS:
        values = [c[field] for c in calls if c[field] is not None]
        result[field] = sum(values) if values else None
        if values and len(values) != len(calls):
            result.setdefault('partially_reported_fields', []).append(field)
    return result


def write_usage_report(root):
    root = Path(root)
    calls = []
    for directory in sorted((root/'llm').glob('*')):
        request_path = directory/'request.json'
        if not request_path.exists():
            continue
        request = read_json(request_path)
        name = request.get('name') or directory.name
        scene = re.search(r'-(s\d+)-', name)
        role = 'coding' if name.startswith('code-') else 'repair' if name.startswith('patch-') else 'review' if name.startswith(('content-', 'layout-', 'review-', 'plan-review-')) else 'planning'
        provider = request.get('provider', 'qwen')
        paths=list(directory.glob('response-*.json'))
        paths.extend(p for p in directory.glob('error-*.json')
                     if not (directory/p.name.replace('error-','response-',1)).exists())
        for path in sorted(paths):
            raw = read_json(path)
            status = raw.get('status') or (raw.get('choices') or [{}])[0].get('finish_reason') or ('http_error' if raw.get('http_status') else 'transport_error' if path.name.startswith('error-') else 'unknown')
            calls.append({'name': name, 'scene': scene.group(1) if scene else None,
                          'role': role, 'provider': provider, 'model': raw.get('model') or request['model'],
                          'attempt': int(path.stem.split('-')[-1]) + 1,
                          'status': status, 'response_id': raw.get('id'),
                          'reasoning_effort': request.get('reasoning_effort'),
                          'max_output_tokens': request.get('max_tokens'),
                          'elapsed_seconds': raw.get('elapsed_seconds'),
                          'response_file': str(path.relative_to(root)),
                          **normalize_usage(raw)})
    groups = {}
    for c in calls:
        key = c['provider'] + ':' + c['model']
        groups.setdefault(key, []).append(c)
    scenes = {}
    for c in calls:
        if c['role'] in ('coding', 'repair'):
            scenes.setdefault(c['scene'], []).append(c)
    reused = read_json(root/'reused-inputs.json') if (root/'reused-inputs.json').exists() else None
    report = {'schema_version': 1, 'updated_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Actual API responses archived in this job. Cached local results add no new call. Reused research/storyboard calls from an earlier job are excluded.',
              'accounting': ['cached_input_tokens are a subset of input_tokens',
                             'reasoning_tokens are a subset of output_tokens',
                             'non_reasoning_output_tokens = output_tokens - reasoning_tokens',
                             'null means the provider did not report that field; no estimated counts',
                             'Incomplete responses and API retries are included when archived; unknown usage on transport errors is not estimated.'],
              'total': summarize(calls),
              'by_model': {key: summarize(group) for key, group in groups.items()},
              'by_role': {role: summarize([c for c in calls if c['role'] == role]) for role in sorted({c['role'] for c in calls})},
              'coding_by_scene': {scene: summarize(group) for scene, group in sorted(scenes.items())},
              'calls': calls, 'reused_inputs': reused}
    write_json(root/'token-usage.json', report)
    columns = ['scene', 'role', 'provider', 'model', 'attempt', 'status', *FIELDS,
               'elapsed_seconds', 'reasoning_effort', 'max_output_tokens', 'response_id', 'response_file']
    with (root/'token-usage.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction='ignore')
        writer.writeheader(); writer.writerows(calls)
    return report
