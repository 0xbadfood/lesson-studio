import json
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from manim_api.app import create_app
from manim_api.models import VideoRequest
from manim_api.pipeline import passed
from manim_api.pipeline import Pipeline
from manim_api.prompts import apply_edits,compact_sources,domain_guidance
from manim_api.settings import Settings
from manim_api.storage import JobStore,write_json
from manim_api.validation import arithmetic,validate_code,validate_geometry
from manim_api.worker import Worker,process_identity


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_root=str(tmp_path)),start_worker=False)


def auth(app):return {'Authorization':'Bearer '+app.state.api_key}


def test_auth_and_cookie_session(app):
    with TestClient(app) as client:
        assert client.get('/api/jobs').status_code==401
        assert client.post('/api/session',json={'token':'wrong'}).status_code==401
        assert client.post('/api/session',json={'token':app.state.api_key}).status_code==200
        assert client.get('/api/jobs').status_code==200
        assert client.post('/api/jobs',json={'topic':'Gravity'},headers={'Origin':'https://unrelated.example'}).status_code==403
        assert client.delete('/api/session').status_code==200
        assert client.get('/api/jobs').status_code==401


def test_submit_idempotency_and_input_validation(app):
    with TestClient(app) as client:
        headers={**auth(app),'Idempotency-Key':'lesson-1'}
        first=client.post('/api/jobs',json={'topic':'Gravity'},headers=headers)
        assert first.status_code==202
        same=client.post('/api/jobs',json={'topic':'Gravity'},headers=headers)
        assert same.json()['id']==first.json()['id']
        assert client.post('/api/jobs',json={'topic':'Friction'},headers=headers).status_code==409
        assert client.post('/api/jobs',json={'topic':'   '},headers=auth(app)).status_code==422
        assert client.post('/api/jobs',json={'topic':'Gravity','duration_seconds':3},headers=auth(app)).status_code==422
        assert client.post('/api/jobs',json={'topic':'Gravity','audio':True},headers=auth(app)).status_code==422


def test_download_ready_gate_path_safety_and_resume(app):
    with TestClient(app) as client:
        job=client.post('/api/jobs',json={'topic':'Gravity'},headers=auth(app)).json()
        job_id=job['id'];directory=app.state.store.directory(job_id)
        (directory/'output.mp4').write_bytes(b'not yet validated')
        assert client.get(f'/api/jobs/{job_id}/files/video',headers=auth(app)).status_code==409
        assert client.get(f'/api/jobs/{job_id}/files/settings',headers=auth(app)).status_code==404
        assert client.post(f'/api/jobs/{job_id}/resume',headers=auth(app)).status_code==409
        assert client.post(f'/api/jobs/{job_id}/cancel',headers=auth(app)).json()['status']=='cancelled'
        assert client.post(f'/api/jobs/{job_id}/resume',headers=auth(app)).json()['status']=='queued'
        assert client.get('/api/jobs/bad-id',headers=auth(app)).status_code==404


def test_numerical_checks_do_not_execute_python():
    assert arithmetic('1*4**2/2')==8
    assert arithmetic('sin(pi/2)')==pytest.approx(1)
    for text in ["__import__('os').system('true')",'2**10000','[1][0]','1/0','sin(']:
        with pytest.raises(ValueError):arithmetic(text)


def test_generated_code_rejects_io_and_latex():
    base='import manim as m\nfrom lesson_runtime import finish\nclass GeneratedScene(m.Scene):\n    def construct(self):\n        self.wait(1)\n'
    validate_code(base)
    for statement in ["open('secret')",'m.MathTex("x")','m.Text("")','m.os.system("true")','getattr(m,"os")']:
        with pytest.raises(ValueError):validate_code(base.replace('self.wait(1)',statement))


def test_time_updated_tracker_must_enter_scene():
    source='''import manim as m
class GeneratedScene(m.Scene):
    def construct(self):
        angle=m.ValueTracker(0)
        angle.add_updater(lambda mob,dt:mob.increment_value(dt))
        self.wait(2)
'''
    with pytest.raises(ValueError,match='updaters do not run'):validate_code(source)
    validate_code(source.replace('self.wait(2)','self.add(angle)\n        self.wait(2)'))


def test_review_requires_explicit_valid_approval():
    assert passed({'pass':True,'issues':[]})
    assert passed({'pass':True,'issues':[{'severity':'minor','problem':'Styling'}]})
    for review in [None,[],{'pass':True},{'pass':'true','issues':[]},
                   {'pass':True,'issues':'none'},{'pass':True,'issues':[None]},
                   {'pass':True,'issues':[{'severity':'major'}]},
                   {'pass':True,'issues':[{'severity':'unknown'}]}]:
        assert not passed(review)


def test_generated_code_reports_all_undefined_names_and_wrong_callback_arity():
    source='''import manim as m
class GeneratedScene(m.Scene):
    def construct(self):
        def make_dot(_):
            return m.Dot()
        dot=m.always_redraw(make_dot)
        self.play(FadeIn(dot),run_time=1)
        dot.shift(UP)
'''
    with pytest.raises(ValueError) as error:validate_code(source)
    assert 'FadeIn' in str(error.value) and 'UP' in str(error.value)
    assert 'zero arguments' in str(error.value)
    validate_code(source.replace('make_dot(_)','make_dot()').replace('FadeIn(dot)','m.FadeIn(dot)').replace('shift(UP)','shift(m.UP)'))


def test_scene_apis_are_checked_against_installed_manim():
    source='''import manim as m
class GeneratedScene(m.Scene):
    def construct(self):
        mark=m.X()
        self.add(mark)
'''
    module=SimpleNamespace(Scene=None,Cross=None)
    with pytest.raises(ValueError,match='no module attributes: X'):
        validate_code(source,manim_module=module)
    validate_code(source.replace('m.X()','m.Cross()'),manim_module=module)


def test_equal_force_claim_is_checked_against_measured_vectors():
    data={'samples':[{'time':time,'text_labels':[{'text':'equal magnitude'}],
        'arrows':[{'color':'#FF727C','start':[1,0,0],'end':[0,0,0]},
                  {'color':'#FFC768','start':[1,0,0],'end':[1.6,0,0]}]}
        for time in [1,1.5,2]]}
    with pytest.raises(ValueError,match='different measured lengths'):validate_geometry(data)
    for sample in data['samples']:sample['text_labels']=[{'text':'equalmagnitude'}]
    with pytest.raises(ValueError,match='different measured lengths'):validate_geometry(data)
    for sample in data['samples']:sample['arrows'][1]['end']=[2,0,0]
    validate_geometry(data)
    for sample in data['samples']:
        sample['arrows'][1]['end']=[1.6,0,0]
        sample['text_labels']=[{'text':'Different force magnitudes'}]
    validate_geometry(data)


def test_persistent_text_overlap_rejected_but_transient_transition_allowed():
    labels=[{'text':'Force','min':[0,0],'max':[2,.3]},
            {'text':'Different explanation','min':[1,.2],'max':[3,.5]}]
    data={'samples':[{'time':time,'text_labels':labels} for time in [1,1.5,2]]}
    with pytest.raises(ValueError,match='overlap persistently'):validate_geometry(data)
    validate_geometry({'samples':data['samples'][:2]})
    validate_geometry({'samples':[{'time':time,'text_labels':labels} for time in [1,3,5]]})
    clear=[labels[0],{'text':'Different explanation','min':[1,.4],'max':[3,.7]}]
    validate_geometry({'samples':[{'time':time,'text_labels':clear} for time in [1,1.5,2]]})
def test_worker_reattaches_and_accepts_terminal_result(tmp_path):
    settings=Settings(data_root=str(tmp_path))
    store=JobStore(tmp_path)
    job=store.submit(VideoRequest(topic='Gravity').model_dump(),settings)
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],start_new_session=True)
    try:
        identity=process_identity(child.pid)
        with store.connection() as db:
            db.execute("UPDATE jobs SET status='running',pid=?,pid_start=?,run_id='reattach' WHERE id=?",(child.pid,identity,job['id']))
        write_json(store.directory(job['id'])/'process.json',{'started':time.time()})
        # This worker did not launch the child, matching API restart recovery.
        Worker(store,settings).tick()
        assert store.get(job['id'])['status']=='running'
        write_json(store.directory(job['id'])/'terminal.json',{'status':'succeeded','run_id':'reattach'})
        Worker(store,settings).tick()
        assert store.get(job['id'])['status']=='succeeded'
    finally:
        child.terminate();child.wait(timeout=5)


def test_worker_detects_pid_reuse_and_allows_resume(tmp_path):
    store=JobStore(tmp_path);settings=Settings(data_root=str(tmp_path))
    job=store.submit(VideoRequest(topic='Gravity').model_dump(),settings)
    with store.connection() as db:
        db.execute("UPDATE jobs SET status='running',pid=1,pid_start='impossible' WHERE id=?",(job['id'],))
    Worker(store,settings).tick()
    assert store.get(job['id'])['status']=='interrupted'
    assert store.resume(job['id'])['status']=='queued'


def test_qwen_source_edits_preserve_unrelated_code_and_reject_ambiguous_matches():
    source='keep_this = 1\nblocks = []\nuse(blocks)\n'
    assert apply_edits(source,[{'old':'blocks = []','new':'blocks = [[], []]'}])=='keep_this = 1\nblocks = [[], []]\nuse(blocks)\n'
    for edits in ([],[{'old':'','new':'replacement'}],[{'old':'missing','new':'replacement'}],
                  [{'old':'blocks','new':'groups'}],[{'old':'blocks = []','new':'blocks = []'}]):
        with pytest.raises(ValueError):apply_edits(source,edits)


def test_scene_evidence_retains_original_support_and_topic_specific_guidance():
    source={'id':'R01','url':'https://source.example','claims':[
        {'claim':'An unrelated discussion','passage_ids':['P01']},
        {'claim':'Simple interest is linear','passage_ids':['P02']}],
        'passages':[{'id':'P01','text':'Other facts'},{'id':'P02','text':'Original linear-interest evidence'}]}
    result=compact_sources([source],'Simple interest linear',max_claims=1)
    assert result[0]['claims']==[source['claims'][1]]
    assert result[0]['passages']==[{'id':'P02','text':'Original linear-interest evidence'}]
    assert domain_guidance('Compound interest')==''
    assert 'angle -a' in domain_guidance('Centripetal and centrifugal forces')


@pytest.mark.parametrize('fail_part',['content','layout'])
def test_failed_review_cannot_be_overridden_by_another_review_part(fail_part):
    calls=[]
    class Model:
        def call(self,name,prompt,**kwargs):
            calls.append((name,prompt,kwargs))
            fail=name.startswith(fail_part+'-')
            return {'pass':not fail,'issues':[{'severity':'major','problem':'Verified defect'}] if fail else []}
    pipeline=Pipeline.__new__(Pipeline)
    pipeline.qwen=Model();pipeline.settings=Settings();pipeline.run_id='test'
    pipeline.event=lambda *args,**kwargs:None
    spec=SimpleNamespace(id='s01',title='Interest',caption='Linear growth',visual='Growing bars')
    combined,detail=pipeline.review_scene(spec,{'scene':'interest'},'exact source',{'duration':18,'samples':[]},
                                         ['one.png','two.png','three.png','four.png'],1,1,0)
    assert not passed(combined)
    assert detail['content_review'] is not None
    if fail_part=='content':assert detail['layout_review'] is None
    content_call=calls[0]
    assert 'images' not in content_call[2]
    assert 'rotating' not in content_call[1]


def test_model_reasoning_budget_is_sent_and_cached_author_is_retained(tmp_path,monkeypatch):
    import httpx
    from manim_api.llm import Qwen
    requests=[]
    def respond(request):
        requests.append(request)
        if request.url.path.endswith('/models'):
            return httpx.Response(200,json={'data':[{'id':'local-qwen'}]})
        body=json.loads(request.content)
        assert body['thinking_budget_tokens']==3072
        assert body['max_tokens']>body['thinking_budget_tokens']
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"pass":true,"issues":[]}'}}]})
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    settings=Settings()
    model=Qwen(settings,tmp_path)
    assert passed(model.call('case','Review evidence',thinking=settings.code_thinking))
    cached=Qwen(settings,tmp_path)
    assert passed(cached.call('case','Review evidence',thinking=settings.code_thinking))
    assert cached.model=='local-qwen'
    assert len(requests)==2


def test_source_provenance_verifies_qwen_edit_chain_and_rejects_unrecorded_changes(tmp_path):
    import hashlib
    import importlib.util
    spec=importlib.util.spec_from_file_location('local_output_check',Path(__file__).resolve().parents[1]/'scripts/check_api_output.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source_proof=module.source_proof
    base='value = 1\n'
    edits=[{'old':'value = 1','new':'value = 2'}]
    repaired=apply_edits(base,edits)
    write_json(tmp_path/'llm/code-s01-original/result.json',{'code':base})
    write_json(tmp_path/'llm/patch-s01-repair/result.json',{'edits':edits})
    write_json(tmp_path/'llm/patch-s01-repair/request.json',{'prompt':'Current source:\n'+base})
    write_json(tmp_path/'scenes/s01/candidate-repair.json',{'code':repaired,'generation_mode':'qwen_edits',
        'edits':edits,'base_source':base,'base_sha256':hashlib.sha256(base.encode()).hexdigest()})
    proof=source_proof(tmp_path,'s01',repaired.encode())
    assert proof['mode']=='qwen_replacements' and proof['base']['mode']=='direct_qwen_module'
    with pytest.raises(AssertionError,match='does not match archived'):
        source_proof(tmp_path,'s01',(repaired+'unrecorded = 3\n').encode())


def test_mobject_updater_and_scene_cleanup_errors_are_reported_together():
    source='''import manim as m
class GeneratedScene(m.Scene):
    def construct(self):
        dot=m.Dot()
        def update_label():
            dot.shift(m.RIGHT)
        dot.add_updater(update_label)
        self.clear_updaters()
'''
    with pytest.raises(ValueError) as error:validate_code(source)
    assert 'mob parameter' in str(error.value) and 'Scene has no' in str(error.value)
    validate_code(source.replace('update_label():','update_label(mob):').replace('self.clear_updaters()','dot.clear_updaters()'))


@pytest.mark.parametrize('same_source',[True,False])
def test_resume_uses_feedback_only_for_the_source_that_was_reviewed(tmp_path,monkeypatch,same_source):
    import hashlib
    import manim_api.pipeline as pipeline_module
    source='import manim as m\nfrom lesson_runtime import finish\nclass GeneratedScene(m.Scene):\n    def construct(self):\n        self.wait(1)\n'
    scene=tmp_path/'scenes/s01';scene.mkdir(parents=True)
    (scene/'scene.py').write_text(source)
    write_json(tmp_path/'storyboard.json',{'assumptions':[]})
    write_json(scene/'feedback.json',{'source_sha256':hashlib.sha256((source if same_source else source+'# old').encode()).hexdigest(),
                                     'error':'Duration must be two seconds'})
    calls=[]
    class Model:
        model='local-qwen'
        def call(self,name,*args,**kwargs):
            calls.append(name)
            return {'edits':[{'old':'self.wait(1)','new':'self.wait(2)'}],'notes':[]}
    def fake_render(settings,directory,code,quality,duration):
        directory.mkdir(parents=True,exist_ok=True)
        clip=directory/'clip.mp4';clip.write_bytes(b'fake test clip')
        geometry={'duration':2,'samples':[]}
        write_json(directory/'geometry.json',geometry)
        return clip,geometry
    monkeypatch.setattr(pipeline_module,'render',fake_render)
    monkeypatch.setattr(pipeline_module,'checkpoints',lambda *args:[])
    pipeline=Pipeline.__new__(Pipeline)
    pipeline.root=tmp_path;pipeline.run_id='retry';pipeline.settings=Settings(coding_provider='qwen');pipeline.qwen=Model();pipeline.coder=pipeline.qwen
    pipeline.request=VideoRequest(topic='Interest');pipeline.event=lambda *args,**kwargs:None
    approved={'pass':True,'issues':[]}
    pipeline.review_scene=lambda *args:(approved,{'audit':{},'content_review':approved,'layout_review':approved})
    spec=SimpleNamespace(id='s01',source_ids=[],calculations=[],title='Interest',goal='Explain growth',
                         duration_seconds=2,model_dump=lambda:{})
    pipeline.scene(spec,{'sources':[]},[],1,1)
    assert bool(calls)==same_source
    expected=source.replace('self.wait(1)','self.wait(2)') if same_source else source
    assert (scene/'scene.py').read_text()==expected


def test_persistent_same_color_bar_text_is_rejected_but_transitions_and_contrasting_text_pass():
    labels=[{'text':'+$11.00','color':'#49D6F5','min':[0,0],'max':[1,.3]}]
    fills=[{'color':'#49D6F5','min':[0,-1],'max':[.8,.4]}]
    data={'samples':[{'time':time,'text_labels':labels,'filled_rectangles':fills} for time in [1,1.5,2]]}
    with pytest.raises(ValueError,match='hidden against a filled rectangle'):validate_geometry(data)
    validate_geometry({'samples':data['samples'][:2]})
    labels[0]['color']='#0B1220'
    validate_geometry(data)


def test_luna_routes_only_code_and_archives_exact_usage_without_credentials(tmp_path,monkeypatch):
    import httpx
    from manim_api.llm import Luna
    requests=[]
    def respond(request):
        requests.append(request)
        body=json.loads(request.content)
        assert str(request.url)=='https://api.openai.com/v1/responses'
        assert request.headers['authorization']=='Bearer dummy-test-token'
        assert body['model']=='gpt-6-luna' and body['reasoning']=={'effort':'high'}
        assert body['max_output_tokens']==24000 and body['store'] is False
        assert 'temperature' not in body and body['text']['format']['type']=='json_object'
        return httpx.Response(200,json={'id':'test-response','model':'gpt-6-luna','status':'completed',
            'output':[{'type':'message','content':[{'type':'output_text','text':'{"code":"value = 1\\n","notes":[]}'}]}],
            'usage':{'input_tokens':2000,'input_tokens_details':{'cached_tokens':1200},
                     'output_tokens':500,'output_tokens_details':{'reasoning_tokens':300},'total_tokens':2500}})
    real_client=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    monkeypatch.setenv('OPENAI_TOKEN','dummy-test-token');monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    luna=Luna(Settings(),tmp_path)
    assert luna.call('code-s01-run-0','Return code JSON')['code']=='value = 1\n'
    assert luna.call('code-s01-run-0','Return code JSON')['code']=='value = 1\n'
    with pytest.raises(ValueError,match='coding and repairs only'):luna.call('layout-s01-run-0','Review JSON')
    usage=json.loads((tmp_path/'token-usage.json').read_text())
    totals=usage['by_model']['openai:gpt-6-luna']
    assert totals['calls']==1 and len(requests)==1
    assert totals['input_tokens']==2000 and totals['cached_input_tokens']==1200 and totals['uncached_input_tokens']==800
    assert totals['output_tokens']==500 and totals['reasoning_tokens']==300 and totals['non_reasoning_output_tokens']==200
    assert totals['total_tokens']==2500
    assert all('dummy-test-token' not in p.read_text() for p in tmp_path.rglob('*.json'))


def test_token_report_includes_incomplete_calls_and_preserves_missing_counts(tmp_path):
    from manim_api.usage import write_usage_report
    for index,status in enumerate(('incomplete','completed')):
        directory=tmp_path/'llm'/f'code-s01-run-{index}'
        write_json(directory/'request.json',{'provider':'openai','model':'gpt-6-luna','name':f'code-s01-run-{index}'})
        write_json(directory/'response-0.json',{'model':'gpt-6-luna','status':status,'elapsed_seconds':1.5,
            'usage':{'input_tokens':20,'output_tokens':40,'output_tokens_details':{'reasoning_tokens':30},'total_tokens':60}})
    # Invalid JSON with an archived API response does not create a second billable call.
    write_json(tmp_path/'llm/code-s01-run-0/error-0.json',{'error':'JSON parse failure'})
    unknown=tmp_path/'llm/code-s02-run-0'
    write_json(unknown/'request.json',{'provider':'openai','model':'gpt-6-luna','name':'code-s02-run-0'})
    write_json(unknown/'error-0.json',{'error':'Transport timeout','elapsed_seconds':5,'usage':None})
    report=write_usage_report(tmp_path)
    assert report['total']['calls']==3 and report['total']['input_tokens']==40
    assert report['total']['responses_with_usage']==2
    assert report['total']['output_tokens']==80 and report['total']['reasoning_tokens']==60
    assert report['total']['cached_input_tokens'] is None
    assert report['coding_by_scene']['s01']['total_tokens']==120
    assert report['coding_by_scene']['s02']['input_tokens'] is None
    assert [c['status'] for c in report['calls']]==['incomplete','completed','transport_error']


def test_pipeline_provider_switch_leaves_qwen_planning_and_reviews(tmp_path):
    from manim_api.llm import Qwen,Luna
    write_json(tmp_path/'request.json',VideoRequest(topic='Compound interest').model_dump())
    write_json(tmp_path/'settings.json',Settings().public())
    pipeline=Pipeline(tmp_path,'test')
    assert isinstance(pipeline.qwen,Qwen) and isinstance(pipeline.coder,Luna)
    old=Settings().public();old.pop('coding_provider')
    write_json(tmp_path/'settings.json',old)
    legacy=Pipeline(tmp_path,'legacy')
    assert legacy.coder is legacy.qwen and legacy.settings.coding_provider=='qwen'
