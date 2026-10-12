"""Qwen research/planning/review + configurable coding -> silent Manim MP4."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

from .llm import Qwen, Luna
from .models import Storyboard, VideoRequest
from .prompts import STYLE, RUNTIME_CONTRACT, apply_edits, compact_geometry, compact_sources, concise_feedback, domain_guidance
from .renderer import render, checkpoints, join_and_check
from .settings import Settings, research_environment
from .storage import read_json, write_json
from .validation import validate_code, validate_geometry, validate_plan
from .usage import write_usage_report


def passed(review):
    if not isinstance(review,dict) or review.get('pass') is not True:
        return False
    issues=review.get('issues')
    return isinstance(issues,list) and all(
        isinstance(issue,dict) and issue.get('severity')=='minor' for issue in issues)


class Pipeline:
    def __init__(self,directory,run_id):
        self.root=Path(directory).resolve()
        self.request=VideoRequest.model_validate(read_json(self.root/'request.json'))
        snapshot=read_json(self.root/'settings.json')
        # Older frozen jobs retain their original Qwen coding provider.
        snapshot.setdefault('coding_provider','qwen')
        self.settings=Settings(**snapshot)
        self.run_id=run_id
        self.qwen=Qwen(self.settings,self.root)
        self.coder=Luna(self.settings,self.root) if self.settings.coding_provider=='luna' else self.qwen
        key=os.environ.get('OPENROUTER_API_KEY')
        hosted=lambda model:Qwen(self.settings,self.root,url=self.settings.openrouter_url,model=model,api_key=key,label='openrouter')
        if (self.settings.planner_model or self.settings.coder_routine_model or self.settings.coder_hard_model) and not key:
            raise RuntimeError('Set OPENROUTER_API_KEY for the hosted planner/coders')
        self.planner=hosted(self.settings.planner_model) if self.settings.planner_model else self.qwen
        # Tiered coding: the planner tags each scene; routine scenes go to one model, involved/novel to another.
        self.tier_coders={'routine':hosted(self.settings.coder_routine_model) if self.settings.coder_routine_model else None,
                          'hard':hosted(self.settings.coder_hard_model) if self.settings.coder_hard_model else None}
        self.default_coder=self.coder

    @property
    def coding_label(self):
        if getattr(self.coder,'api_key',None):
            return self.coder.model
        return 'Luna' if self.coder.__class__.__name__=='Luna' else 'Qwen'

    def coder_for(self,spec):
        tier=spec.complexity or 'involved'
        chosen=self.tier_coders['routine' if tier=='routine' else 'hard']
        return chosen or self.default_coder

    def event(self,stage,message,**detail):
        state={'stage':stage,'message':message,'updated':time.time(),'run_id':self.run_id,**detail}
        write_json(self.root/'state.json',state)
        with (self.root/'events.jsonl').open('a') as file:
            file.write(json.dumps(state)+'\n')
        print(f'[{stage}] {message}',flush=True)

    def research(self):
        path=self.root/'research.json'
        if path.exists():return read_json(path)
        self.event('research','Qwen is searching and reading source pages')
        env=research_environment(self.settings)
        if not env.get('TAVILY_API_KEY'):
            raise RuntimeError('Tavily research credential is missing from the environment and Remotion configuration')
        directory=self.root/'research'/'archive'
        request=directory/'request.json'
        write_json(request,{'subject':self.request.topic,'directory':str(directory),
            'kbagent_root':self.settings.kbagent_root,'model_url':self.settings.qwen_url,
            'subject_guidance':{'focus':self.request.instructions,'audience':self.request.audience,
                'medium':'silent Manim educational animation; prioritize mechanisms and numerical definitions'}})
        # Inherit the pipeline's durable log so web users see search/fetch progress.
        process=subprocess.run([self.settings.research_python,'-u','-m','infofilm.research_worker',str(request)],
            cwd=self.settings.remotion_root,env=env,stderr=subprocess.STDOUT,timeout=self.settings.research_timeout)
        if process.returncode:
            failure=directory/'failure.json'
            reason=read_json(failure).get('error') if failure.exists() else (self.root/'worker.log').read_text()[-1500:]
            raise RuntimeError('Research failed: '+str(reason))
        extracted=read_json(directory/'extracted.json')
        sources=[]
        for item in extracted['results']:
            digest=item.get('source_digest',{})
            if not digest.get('claims'):continue
            sources.append({'id':f'R{len(sources)+1:02d}','url':item['url'],
                'claims':digest['claims'],'cautions':digest.get('cautions',[]),
                'passages':digest.get('passages',[])})
        if not sources:raise RuntimeError('Research did not produce any usable fetched source')
        result={'topic':self.request.topic,'sources':sources,
                'summary':(directory/'answer.txt').read_text(),'research_model_url':self.settings.qwen_url,
                'scope':'Bounded web research using fetched pages; sources and original passages archived'}
        write_json(path,result)
        return result

    def plan(self,research):
        path=self.root/'storyboard.json'
        source_ids={s['id'] for s in research['sources']}
        if path.exists():
            plan=Storyboard.model_validate(read_json(path))
            checks=validate_plan(plan,self.request,source_ids)
            return plan,checks
        self.event('planning',f'{self.planner.model or "Qwen"} is creating a source-grounded storyboard')
        schema=Storyboard.model_json_schema()
        prompt=('Plan a silent Manim explainer of the exact requested topic. Include a hook, '
            'one idea per scene, a misconception correction when useful, and a concise closing idea. '
            'Use 2–7 scenes with IDs s01,s02,... and durations totaling the requested approximate length. '
            'Each scene must contain meaningful moving/changing diagrams. Captions max20 words. '
            'Dark navy, cyan objects, green change, red comparisons, amber highlights; '
            'assign consistent color meanings appropriate to the requested topic. '
            'Provide only source IDs that were actually fetched. Do not invent source URLs or facts. '
            'Calculations are optional: include simple numerical expressions for claims with exact '
            'numbers, expected results, tolerance and source IDs. Expressions support numbers, pi/e, '
            '+ - * / **, sin,cos,tan,sqrt,exp,log,log10,radians. These are arithmetic checks, not proof '
            'that a physical model or fact is correct. State assumptions and schematic scales. '
            'No external visual assets, no audio. '+
            ('For every scene set "complexity" to how hard its animation is to code: "routine" (standard plots, '
             'bars, worked equations, one labelled motion), "involved" (several synced moving parts, custom '
             'geometry, transforms between representations) or "novel" (original visual constructions, 3D, '
             'physical simulation). This routes the scene to a cheaper or stronger coder; do not under-rate. '
             if self.tier_coders['routine'] or self.tier_coders['hard'] else '')+
            'Return exactly the JSON schema.\nRequest:\n'+
            self.request.model_dump_json()+'\nResearch:\n'+json.dumps(compact_sources(research['sources'],self.request.topic))+
            '\nTopic conventions:\n'+domain_guidance(self.request.topic)+'\nSchema:\n'+json.dumps(schema))
        feedback=''
        for attempt in range(3):
            candidate=self.planner.call(f'plan-{self.run_id}-{attempt}',prompt+feedback,
                                    thinking=self.settings.plan_thinking,max_tokens=7500)
            try:
                plan=Storyboard.model_validate(candidate)
                checks=validate_plan(plan,self.request,source_ids)
            except ValueError as exc:
                feedback='\nRepair this prior plan:\n'+json.dumps(candidate)+'\nValidation error:\n'+str(exc)
                continue
            review=self.planner.call(f'plan-review-{self.run_id}-{attempt}',
                'Review the storyboard for source-supported facts, correct causality, understandable '
                'silent diagrams, assumptions and numerical units. Optional styling is minor. '
                'Return {pass:boolean,issues:[{severity:"major"|"minor",scene:string,problem:string,correction:string}]}. '
                'Reject only verified major errors, not speculation.\nResearch:\n'+
                json.dumps(compact_sources(research['sources'],self.request.topic))+
                '\nStoryboard:\n'+plan.model_dump_json(),thinking=self.settings.content_thinking,max_tokens=4000)
            write_json(self.root/f'plan-review-{attempt}.json',review)
            if passed(review):
                write_json(path,plan.model_dump())
                write_json(self.root/'calculations.json',checks)
                return plan,checks
            feedback='\nRepair this plan:\n'+plan.model_dump_json()+'\nReview:\n'+json.dumps(review)
        raise RuntimeError('The planner could not produce an accepted storyboard within three attempts')

    def audit_review(self,name,report,context,code,geometry,images=()):
        issues=[issue for issue in report.get('issues',[]) if isinstance(issue,dict) and issue.get('severity')=='major']
        return self.qwen.call(name,
            'Check at most three disputed major findings. First derive the result from the '
            'exact code and evidence below; then compare the disputed claims. Recompute the '
            'specific arithmetic or object membership involved. Do not assume another review '
            'is correct. A temporary animation state, schematic styling or optional preference '
            'is minor. Reject only an established error affecting the explanation or legibility. '
            'Return compact JSON {pass:boolean,issues:[{severity:"major"|"minor",problem:string,'
            'evidence:string,correction:string}],findings:[{verdict:string,reason:string}],limitations:[string]}. '
            'pass must be true when no major issue remains. Maximum 300 words.\n'
            'Evidence:\n'+json.dumps(context)+'\nExact code:\n'+code+
            '\nMeasured geometry:\n'+json.dumps(compact_geometry(geometry,3))+
            '\nFindings to test:\n'+json.dumps(issues[:3]),images=images,
            thinking=self.settings.content_thinking,max_tokens=4000)

    def review_scene(self,spec,context,code,geometry,images,index,total,attempt):
        tag=f'{spec.id}-{self.run_id}-{attempt}'
        self.event('review',f'Qwen is checking content in scene {index}/{total}',scene=spec.id,
                   scene_index=index,scene_count=total,review_part='content')
        content=self.qwen.call('content-'+tag,
            'Check ONLY factual/numerical correctness and whether the exact code realizes '
            'the lesson model. Derive quantities and check which objects actually enter the '
            'scene. For grouped objects, follow loop indices and list membership; do not infer '
            'presence from variable names. Final amounts, directions and labels must agree. '
            'Temporary drawing states and optional design choices are not major defects. '
            'Do not review label spacing here; a separate layout check handles that. '
            'State only errors supported by the supplied evidence/code. Return JSON '
            '{pass:boolean,issues:[{severity:"major"|"minor",problem:string,evidence:string,'
            'correction:string}],strengths:[string],limitations:[string]}. '
            'pass=true when no major issue remains; at most 3 issues, maximum 250 words.\n'
            'Lesson/evidence:\n'+json.dumps(context)+'\nExact code:\n'+code+
            '\nFinal sampled geometry:\n'+json.dumps(compact_geometry(geometry,2)),
            thinking=self.settings.content_thinking,max_tokens=4000)
        content_audit=None
        final_content=content
        if not passed(content):
            self.event('audit',f'Qwen is checking content findings in scene {index}/{total}',scene=spec.id,
                       scene_index=index,scene_count=total)
            content_audit=self.audit_review('content-audit-'+tag,content,context,code,geometry)
            final_content=content_audit
        layout=None
        layout_audit=None
        final_layout=None
        if passed(final_content):
            self.event('review',f'Qwen is checking layout in scene {index}/{total}',scene=spec.id,
                       scene_index=index,scene_count=total,review_part='layout')
            layout_images=[images[1],images[3]]
            layout=self.qwen.call('layout-'+tag,
                'Check ONLY visible legibility, clipping, misplaced labels and diagram clarity '
                'in these two checkpoint stills. Content has been checked separately. Reject '
                'only a clear persistent defect that prevents understanding. Draw-in/fade '
                'transitions, color preferences, leader lines touching a box edge and schematic '
                'styling are minor. Do not invent factual corrections from partial shapes. '
                'Sampled geometry is not full visibility evidence. Return compact JSON '
                '{pass:boolean,issues:[{severity:"major"|"minor",problem:string,evidence:string,'
                'correction:string}],strengths:[string],limitations:[string]}. '
                'pass=true when no major issue remains; at most 3 issues, maximum 200 words.\n'
                'Intended diagram:\n'+json.dumps({'title':spec.title,'caption':spec.caption,'visual':spec.visual})+
                '\nMeasured geometry:\n'+json.dumps(compact_geometry(geometry,3)),
                images=layout_images,thinking=self.settings.layout_thinking,max_tokens=2600)
            final_layout=layout
            if not passed(layout):
                self.event('audit',f'Qwen is checking layout findings in scene {index}/{total}',scene=spec.id,
                           scene_index=index,scene_count=total)
                layout_audit=self.audit_review('layout-audit-'+tag,layout,context,code,geometry,layout_images)
                final_layout=layout_audit
        reports=[value for value in (final_content,final_layout) if value is not None]
        combined={'pass':passed(final_content) and passed(final_layout),
                  'issues':[issue for value in reports for issue in value.get('issues',[]) if isinstance(issue,dict)],
                  'scope':'Separate code/evidence content review and two-still layout review; not full playback.'}
        detail={'review_version':2,'review':combined,'content_review':content,'layout_review':layout,
                'audit':{'content':content_audit,'layout':layout_audit}}
        return combined,detail

    def scene(self,spec,research,checks,index,total):
        directory=self.root/'scenes'/spec.id
        accepted=directory/'accepted.json'
        resume_feedback=''
        if accepted.exists():
            saved=read_json(accepted)
            source=directory/'scene.py'
            if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest()==saved['source_sha256']:
                if Path(saved['preview']).exists():
                    try:
                        validate_code(source.read_text())
                        validate_geometry(read_json(saved['geometry']))
                    except (ValueError,SyntaxError) as exc:resume_feedback=str(exc)
                    else:return saved
        directory.mkdir(parents=True,exist_ok=True)
        self.coder=self.coder_for(spec)
        source_ids=set(spec.source_ids)|{source_id for calc in spec.calculations for source_id in calc.source_ids}
        relevant=[s for s in research['sources'] if s['id'] in source_ids]
        context={'scene':spec.model_dump(),'assumptions':read_json(self.root/'storyboard.json')['assumptions'],
                 'sources':compact_sources(relevant,spec.title+' '+spec.goal),
                 'numerical_checks':[c for c in checks if c['scene']==spec.id],
                 'runtime_contract':RUNTIME_CONTRACT,
                 'topic_conventions':domain_guidance(self.request.topic,spec.model_dump())}
        if (self.root/'manual-content-review.json').exists():
            context['content_review_feedback']=read_json(self.root/'manual-content-review.json')
        prompt=STYLE+'\nScene/evidence:\n'+json.dumps(context)
        previous=(directory/'scene.py').read_text() if (directory/'scene.py').exists() else ''
        feedback=(directory/'feedback.txt').read_text() if (directory/'feedback.txt').exists() else ''
        review_current=bool(previous)
        feedback_record=directory/'feedback.json'
        if previous and feedback_record.exists():
            recorded=read_json(feedback_record)
            if recorded.get('source_sha256')==hashlib.sha256(previous.encode()).hexdigest():
                feedback=recorded['error']
                review_current=False
        if resume_feedback:feedback=resume_feedback
        if previous:
            try:validate_code(previous)
            except (ValueError,SyntaxError) as exc:
                feedback='Current source validation: '+str(exc)
                review_current=False
            preview_geometry=directory/'preview'/'geometry.json'
            preview_source=directory/'preview'/'scene.py'
            if preview_geometry.exists() and preview_source.exists() and preview_source.read_text()==previous:
                try:validate_geometry(read_json(preview_geometry))
                except ValueError as exc:
                    feedback+='\nMeasured geometry validation: '+str(exc)
                    review_current=False
        for attempt in range(self.settings.max_attempts):
            try:
                if attempt==0 and review_current:
                    code=previous
                    result={'code':code,'notes':['Rechecked the saved model source with the updated reviews.'],
                            'generation_mode':'saved_source'}
                else:
                    self.event('coding',f'{self.coding_label} is coding scene {index}/{total}',scene=spec.id,
                        scene_index=index,scene_count=total,attempt=attempt+1,coding_provider=self.settings.coding_provider)
                    if previous:
                        base=previous
                        raw=self.coder.call(f'patch-{spec.id}-{self.run_id}-{attempt}',
                            'Repair only the identified defects in this Manim module. Preserve '
                            'working geometry, timing and unrelated code. Return JSON '
                            '{edits:[{old:"exact uniquely matching source text",new:"replacement text"}],notes:[string]}. '
                            'Use 1–8 replacements with exact indentation and newlines. Return edits, '
                            'not a rewritten module. Follow list membership and grouping carefully.\n'
                            'Runtime/lesson:\n'+json.dumps(context)+'\nCurrent source:\n'+base+
                            '\nDefects to repair:\n'+concise_feedback(feedback),
                            thinking=self.settings.code_thinking,
                            max_tokens=self.settings.luna_patch_max_output_tokens if self.settings.coding_provider=='luna' else 7500)
                        try:code=apply_edits(base,raw.get('edits'))
                        except ValueError as exc:
                            if self.coder.__class__.__name__=='Luna':
                                raise ValueError('Could not apply source edits: '+str(exc)+'\nOriginal defects:\n'+feedback) from exc
                            # Qwen's edits did not apply (e.g. an unchanged "replacement"): ask for the whole module.
                            raw=self.coder.call(f'rewrite-{spec.id}-{self.run_id}-{attempt}',prompt+
                                '\nYour previous module had these defects; return the complete corrected module '
                                '(same JSON shape) with every defect fixed:\n'+concise_feedback(feedback)+
                                '\nPrevious module:\n'+base,thinking=self.settings.code_thinking,max_tokens=self.settings.qwen_code_max_tokens)
                            code=raw.get('code','')
                        result={**raw,'code':code,'generation_mode':self.settings.coding_provider+'_edits',
                                'coding_provider':self.settings.coding_provider,
                                'base_source':base,'base_sha256':hashlib.sha256(base.encode()).hexdigest()}
                    else:
                        result=self.coder.call(f'code-{spec.id}-{self.run_id}-{attempt}',prompt,
                            thinking=self.settings.code_thinking,
                            max_tokens=self.settings.luna_code_max_output_tokens if self.settings.coding_provider=='luna' else self.settings.qwen_code_max_tokens)
                        code=result.get('code','')
                    previous=code
                write_json(directory/f'candidate-{self.run_id}-{attempt}.json',result)
                validate_code(code)
                (directory/'scene.py').write_text(code)
                self.event('preview',f'Rendering scene {index}/{total} for checks',scene=spec.id,
                    scene_index=index,scene_count=total,attempt=attempt+1)
                preview,geometry=render(self.settings,directory/'preview',code,'preview',spec.duration_seconds)
                images=checkpoints(preview,directory/'preview',geometry['duration'])
                report,detail=self.review_scene(spec,context,code,geometry,images,index,total,attempt)
                write_json(directory/f'review-{self.run_id}-{attempt}.json',detail)
                if not passed(report):
                    raise ValueError('Verified major review findings:\n'+json.dumps(report))
                saved={'id':spec.id,'preview':str(preview),'duration':geometry['duration'],
                       'source_sha256':hashlib.sha256(code.encode()).hexdigest(),
                       'author_model':self.coder.model,'coding_provider':self.coding_label,'complexity':spec.complexity,
                       'reviewer_model':self.qwen.model,'review':report,'review_audit':detail['audit'],
                       'review_version':2,'content_review':detail['content_review'],'layout_review':detail['layout_review'],
                       'geometry':str(directory/'preview'/'geometry.json'),
                       'source':str(directory/'scene.py'),'notes':result.get('notes',[])}
                write_json(accepted,saved)
                return saved
            except (ValueError,SyntaxError,subprocess.TimeoutExpired) as exc:
                # A reply that ran out of budget says nothing about the code: resend the real defect.
                feedback=(feedback+'\n(Your previous reply ran out of output budget before finishing; reply more '
                          'concisely.)') if 'output budget' in str(exc) and feedback else str(exc)
                (directory/'feedback.txt').write_text(feedback)
                write_json(directory/'feedback.json',{'source_sha256':hashlib.sha256(previous.encode()).hexdigest(),
                                                     'error':feedback,'run_id':self.run_id})
                self.event('repair',f'Sending scene {index}/{total} errors back to {self.coding_label}',scene=spec.id,
                    scene_index=index,scene_count=total,attempt=attempt+1)
        raise RuntimeError(f'Scene {spec.id} exhausted its {self.settings.max_attempts} coding/repair attempts; inspect saved logs and feedback')

    def run(self):
        research=self.research()
        plan,checks=self.plan(research)
        selected=[self.scene(s,research,checks,i+1,len(plan.scenes)) for i,s in enumerate(plan.scenes)]
        clips=[]
        for i,(spec,saved) in enumerate(zip(plan.scenes,selected)):
            if self.request.quality=='hd':
                self.event('rendering',f'Rendering HD scene {i+1}/{len(selected)}',scene=spec.id,
                           scene_index=i+1,scene_count=len(selected))
                code=Path(saved['source']).read_text()
                directory=self.root/'scenes'/spec.id/'hd'
                path,geometry=render(self.settings,directory,code,'hd',spec.duration_seconds)
                checkpoints(path,directory,geometry['duration'])
            else:path=Path(saved['preview'])
            clips.append(path)
        self.event('validating','Joining scenes and checking the complete MP4')
        video=join_and_check(clips,self.root/'output.mp4',self.request.quality)
        if abs(video['duration_seconds']-sum(s['duration'] for s in selected))>max(1,len(selected)*.15):
            raise ValueError('Joined video duration differs from the accepted scene timings')
        with zipfile.ZipFile(self.root/'source.zip','w',zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(Path(__file__).parent/'lesson_runtime.py','lesson_runtime.py')
            bundle.write(self.root/'storyboard.json','storyboard.json')
            for saved in selected:
                bundle.write(saved['source'],saved['id']+'.py')
            bundle.writestr('requirements.txt','manim==0.21.0\nnumpy>=2.1\n')
            bundle.writestr('README.txt',self.coding_label+' authored each scene module and any exact source replacements. The layout helpers are supplied by the API.\n'
                'Install FFmpeg, Cairo/Pango development packages and requirements.txt.\n'
                'Render without a player: manim -qh --fps 30 s01.py GeneratedScene\n'
                'Render each scene then concatenate the MP4s in storyboard order.\n')
        usage=write_usage_report(self.root)
        report={'request':self.request.model_dump(),'video':video,'scenes':selected,'token_usage':usage,
            'numerical_checks':checks,'numerical_check_scope':'Arithmetic is checked; this does not independently establish every researched fact or physical model.',
            'author_model':self.coder.model or selected[0]['author_model'],
            'coding_provider':self.settings.coding_provider,
            'model_url':self.settings.luna_url if self.settings.coding_provider=='luna' else self.settings.qwen_url,
            'reviewer_model':self.qwen.model,'reviewer_model_url':self.settings.qwen_url,
            'research_model_url':self.settings.qwen_url,
            'research_sources':[{k:s[k] for k in ('id','url')} for s in research['sources']],
            'generated_scene_code_hand_edited':False,'trusted_layout_helpers_author':'API implementation',
            'review_scope':'New scenes receive separate code/evidence content checks and two-still layout checks. Previously accepted scenes retain their archived review scope. Actual frame bounds were monitored; HD checkpoints and full MP4 decode were checked. Full playback was not watched.',
            'generation_settings':{'code_thinking':self.settings.code_thinking if self.settings.coding_provider=='qwen' else None,
                                   'luna_reasoning_effort':self.settings.luna_reasoning_effort if self.settings.coding_provider=='luna' else None,
                                   'luna_code_max_output_tokens':self.settings.luna_code_max_output_tokens if self.settings.coding_provider=='luna' else None,
                                   'luna_patch_max_output_tokens':self.settings.luna_patch_max_output_tokens if self.settings.coding_provider=='luna' else None,
                                   'content_thinking':self.settings.content_thinking,
                                   'layout_thinking':self.settings.layout_thinking},
            'source_policy':'Initial modules and exact repair replacements are '+self.coding_label+'-authored; the API applies uniquely matched replacements and archives their base source and edit text.',
            'sha256':hashlib.sha256((self.root/'output.mp4').read_bytes()).hexdigest()}
        if (self.root/'manual-content-review.json').exists():
            report['manual_content_review']=read_json(self.root/'manual-content-review.json')
        write_json(self.root/'report.json',report)
        self.event('done','Silent video is ready',video=video)
        return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',required=True,type=Path)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    pipeline=Pipeline(args.job,args.run_id)
    try:
        pipeline.run()
    except Exception as exc:
        # Search credentials are kept out of published errors and artifacts.
        error=str(exc)
        for key in ['TAVILY_API_KEY','MANIM_API_KEY','VLLM_API_KEY','OPENAI_API_KEY','OPENAI_TOKEN','OPENROUTER_API_KEY']:
            secret=os.environ.get(key)
            if secret:error=error.replace(secret,'[redacted]')
        write_json(pipeline.root/'terminal.json',{'status':'failed','error':error,'run_id':args.run_id})
        write_usage_report(pipeline.root)
        pipeline.event('failed',error[:1000])
        raise SystemExit(1)
    write_json(pipeline.root/'terminal.json',{'status':'succeeded','run_id':args.run_id})


if __name__=='__main__':main()
