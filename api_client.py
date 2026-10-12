"""Small authenticated client for the local Manim API."""
import argparse
import json
import os
from pathlib import Path
import time
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:18610')
    parser.add_argument('--token-file',type=Path,default=Path(__file__).parent/'api-data/api-token')
    commands=parser.add_subparsers(dest='action',required=True)
    commands.add_parser('health');commands.add_parser('list')
    create=commands.add_parser('create')
    create.add_argument('--topic',required=True)
    create.add_argument('--duration',type=int,default=90)
    create.add_argument('--audience',default='High-school students')
    create.add_argument('--instructions',default='')
    create.add_argument('--quality',choices=['preview','hd'],default='hd')
    create.add_argument('--wait',action='store_true')
    create.add_argument('--output',type=Path)
    for action in ['get','resume','cancel']:
        commands.add_parser(action).add_argument('job_id')
    download=commands.add_parser('download')
    download.add_argument('job_id')
    download.add_argument('--kind',choices=['video','code','research','storyboard','report','log','token_usage','token_csv'],default='video')
    download.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    token=os.environ.get('MANIM_API_KEY') or args.token_file.read_text().strip()
    with httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+token},timeout=30) as client:
        if args.action=='download':
            fetch(client,args.job_id,args.kind,args.output);return
        if args.action=='create':
            response=client.post('/api/jobs',json={'topic':args.topic,'audience':args.audience,
                'duration_seconds':args.duration,'quality':args.quality,'instructions':args.instructions})
        elif args.action in ('resume','cancel'):
            response=client.post('/api/jobs/'+args.job_id+'/'+args.action)
        else:
            path='/api/health' if args.action=='health' else '/api/jobs' if args.action=='list' else '/api/jobs/'+args.job_id
            response=client.get(path)
        response.raise_for_status();data=response.json()
        print(json.dumps(data,indent=2))
        if args.action=='create' and args.wait:
            job_id=data['id'];last=None
            while data['status'] in ('queued','running'):
                state=(data['status'],data['progress'].get('message'))
                if state!=last:
                    print(' · '.join(str(x) for x in state),flush=True);last=state
                time.sleep(3)
                response=client.get('/api/jobs/'+job_id);response.raise_for_status();data=response.json()
            if data['status']!='succeeded':raise SystemExit(data.get('error') or data['status'])
            fetch(client,job_id,'video',args.output or Path('manim-'+job_id[:8]+'.mp4'))


def fetch(client,job_id,kind,path):
    with client.stream('GET',f'/api/jobs/{job_id}/files/{kind}') as response:
        response.raise_for_status()
        with path.open('wb') as file:
            for chunk in response.iter_bytes():file.write(chunk)
    print(str(path.resolve()))


if __name__=='__main__':main()
