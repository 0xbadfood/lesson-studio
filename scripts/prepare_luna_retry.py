"""Queue fresh Luna scene code using the accepted inputs of an earlier job."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manim_api.models import Storyboard,VideoRequest
from manim_api.settings import Settings
from manim_api.storage import JobStore,read_json,write_json
from manim_api.validation import validate_plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('original_job')
    parser.add_argument('--fresh-plan',action='store_true',help='reuse only the research; the planner writes a new storyboard')
    args=parser.parse_args()
    settings=Settings.from_env()
    coder={'luna':'Luna','qwen':'Qwen'}[settings.coding_provider]
    if settings.coder_routine_model or settings.coder_hard_model:
        coder=f'tiered ({settings.coder_routine_model} / {settings.coder_hard_model})'
    store=JobStore(settings.data_root)
    server=store.root/'server.json'
    from manim_api.worker import process_identity
    if server.exists():
        state=read_json(server)
        if process_identity(state['pid'])==state['identity']:
            raise SystemExit('Stop the API before preparing cached inputs to avoid a queue race')
    old=store.directory(args.original_job)
    request=VideoRequest.model_validate(read_json(old/'request.json'))
    research=read_json(old/'research.json')
    storyboard=Storyboard.model_validate(read_json(old/'storyboard.json'))
    validate_plan(storyboard,request,{s['id'] for s in research['sources']})
    job=store.submit(request.model_dump(),settings)
    root=store.directory(job['id'])
    hashes={}
    for name in ('research.json',) if args.fresh_plan else ('research.json','storyboard.json','calculations.json'):
        shutil.copy2(old/name,root/name)
        hashes[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
    # Preserve original fetched pages and planning provenance outside new-call accounting.
    if (old/'research').exists():shutil.copytree(old/'research',root/'reused-inputs/research')
    for directory in () if args.fresh_plan else (old/'llm').glob('plan-*'):
        shutil.copytree(directory,root/'reused-inputs/llm'/directory.name)
    write_json(root/'reused-inputs.json',{'original_job_id':args.original_job,'original_directory':str(old),
        'artifacts':hashes,'coding_url':settings.qwen_url if coder=='Qwen' else settings.luna_url,'scope':('Reuse Qwen research only; the planner ('+(settings.planner_model or 'Qwen')+') writes a fresh storyboard. ' if args.fresh_plan else 'Reuse Qwen research and accepted storyboard unchanged. ')+'Scene modules are coded fresh by '+coder+'; Qwen performs content/layout reviews.'})
    write_json(ROOT/f'artifacts/{settings.coding_provider}-coding-retry.json',{'job_id':job['id'],'original_job_id':args.original_job,
        'request':request.model_dump(),'coding_provider':settings.coding_provider,'coding_model':settings.luna_model if coder=='Luna' else 'qwen (local)'})
    print(json.dumps({'job_id':job['id'],'request':request.model_dump(),'coding_model':settings.luna_model if coder=='Luna' else 'qwen (local)'},indent=2))


if __name__=='__main__':main()
