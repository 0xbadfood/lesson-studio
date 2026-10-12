"""Check a completed live job through its authenticated HTTP download routes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.prompts import apply_edits


def source_proof(directory,scene_id,source,seen=None):
    """Verify full modules or an exact chain of model-authored replacements."""
    seen=set() if seen is None else seen
    digest=hashlib.sha256(source).hexdigest()
    assert digest not in seen,'Source edit ancestry contains a cycle'
    seen=seen|{digest}
    for path in (directory/'llm').glob(f'code-{scene_id}-*/result.json'):
        if json.loads(path.read_text()).get('code','').encode()==source:
            request_path=path.parent/'request.json'
            request=json.loads(request_path.read_text()) if request_path.exists() else {}
            provider=request.get('provider','qwen')
            return {'mode':'direct_luna_module' if provider=='openai' else 'direct_qwen_module',
                    'provider':provider,'model':request.get('model'),
                    'result':str(path.relative_to(directory))}
    for path in (directory/'scenes'/scene_id).glob('candidate-*.json'):
        candidate=json.loads(path.read_text())
        if candidate.get('code','').encode()!=source or candidate.get('generation_mode') not in ('qwen_edits','luna_edits'):continue
        base=candidate['base_source'].encode()
        assert hashlib.sha256(base).hexdigest()==candidate['base_sha256']
        assert apply_edits(base.decode(),candidate['edits']).encode()==source
        for result_path in (directory/'llm').glob(f'patch-{scene_id}-*/result.json'):
            raw=json.loads(result_path.read_text())
            if raw.get('edits')==candidate['edits']:
                request=json.loads((result_path.parent/'request.json').read_text())
                assert base.decode() in request['prompt']
                provider=request.get('provider','qwen')
                assert provider==('openai' if candidate['generation_mode']=='luna_edits' else 'qwen')
                return {'mode':'luna_replacements' if provider=='openai' else 'qwen_replacements',
                        'provider':provider,'model':request.get('model'),'result':str(result_path.relative_to(directory)),
                        'base':source_proof(directory,scene_id,base,seen)}
    raise AssertionError('Source does not match archived model code or a verified edit chain')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('job_id')
    parser.add_argument('--url',default='http://127.0.0.1:18610')
    args=parser.parse_args()
    token=(ROOT/'api-data/api-token').read_text().strip()
    directory=ROOT/'api-data/runs'/args.job_id
    with httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+token},timeout=30) as client:
        response=client.get('/api/jobs/'+args.job_id)
        response.raise_for_status()
        job=response.json()
        if job['status']!='succeeded':
            raise SystemExit('Job is not ready: '+job['status'])
        downloads={}
        artifacts={}
        for kind,url in job['downloads'].items():
            result=client.get(url)
            result.raise_for_status()
            downloads[kind]={'status':result.status_code,'bytes':len(result.content),
                             'content_type':result.headers['content-type']}
            artifacts[kind]=result.content
        assert {'video','code','storyboard','research','report','log'}<=set(downloads)
        report=json.loads(artifacts['report'])
        video_hash=hashlib.sha256(artifacts['video']).hexdigest()
        assert video_hash==report['sha256']
        assert report['video']['audio'] is False
        assert report['video']['full_decode']=='passed'
        width,height=(1920,1080) if report['request']['quality']=='hd' else (854,480)
        assert report['video']['width']==width and report['video']['height']==height
        assert abs(report['video']['duration_seconds']-sum(scene['duration'] for scene in report['scenes']))<=max(1,len(report['scenes'])*.15)
        partial=client.get(job['downloads']['video'],headers={'Range':'bytes=0-2047'})
        assert partial.status_code==206 and len(partial.content)==2048
        assert partial.content==artifacts['video'][:2048]
        assert client.get(f'/api/jobs/{args.job_id}/files/settings').status_code==404
        scene_provenance=[]
        with zipfile.ZipFile(io.BytesIO(artifacts['code'])) as bundle:
            for scene in report['scenes']:
                source=bundle.read(scene['id']+'.py')
                assert hashlib.sha256(source).hexdigest()==scene['source_sha256']
                candidates=(directory/'scenes'/scene['id']).glob('candidate-*.json')
                matches=[str(path.relative_to(directory)) for path in candidates
                         if json.loads(path.read_text()).get('code','').encode()==source]
                assert matches,'Scene differs from every archived model response'
                proof=source_proof(directory,scene['id'],source)
                assert proof.get('model') in (None,scene['author_model']), 'Author model differs from raw request'
                scene_provenance.append({'id':scene['id'],'model_authorship_verified':True,
                                         'author_model':scene['author_model'],
                                         'authorship_proof':proof,
                                         'candidate_files':matches,'sha256':scene['source_sha256']})
    unauthorized=httpx.get(args.url+job['downloads']['video'],timeout=10)
    assert unauthorized.status_code==401
    result={'job_id':args.job_id,'status':'succeeded','video':report['video'],
            'downloads':downloads,'mp4_download_hash_matches_report':True,
            'video_range_request':partial.status_code,'unauthenticated_download':unauthorized.status_code,
            'scene_provenance':scene_provenance,
            'token_totals':report.get('token_usage',{}).get('by_model',{})}
    output=ROOT/'artifacts/api-output-validation.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/f'artifacts/api-output-validation-{args.job_id}.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
