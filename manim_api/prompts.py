"""Bounded, task-specific evidence and exact Qwen-authored source edits."""
import json
import re


STYLE = '''Write one silent Manim Community 0.21 scene. Return JSON
{"code":"complete Python module","notes":["brief notes"]}.
Imports: import manim as m; import numpy as np; import math;
from lesson_runtime import begin, finish, text, arrow, polyline, BG, WHITE, CYAN, GREEN, RED, AMBER.
Define GeneratedScene(m.Scene), construct(self). First: started=begin(self,title,caption).
Last: finish(self,started,duration). The helpers supply the title and caption.
Keep body objects within x=-6.1..6.1,y=-2.6..2.6, with separate text boxes.
Qualify all Manim symbols, including m.FadeIn,m.UP. Positions are numpy arrays.
Use Text through text(), no LaTeX, empty text, external assets, IO or other imports.
Use tracker.animate.set_value(value), never assignment inside self.play().
always_redraw callbacks take zero arguments; add_updater callbacks receive mob
or (mob,dt). Scene has no self.clear_updaters(); finish() handles cleanup.
Add time-updated trackers to the scene. Clear updaters before fading objects.
Example: t=m.ValueTracker(0); self.add(t);
self.play(t.animate.set_value(3),run_time=2,rate_func=m.linear).
Use mob.become(new_object) to update geometry; no set_start_and_end_points.
Use polyline([point1,point2,...],color=CYAN) for an open connected path.
Do not invent m.PolyLine or construct an empty VMobject with coordinate arguments.
No m.X,m.CYAN,m.AMBER,m.Color; use supplied colors and m.Cross or two Lines.
Axes must not add_numbers; place text ticks manually. Avoid unnecessary objects.
Compute quantities from the lesson's model. Derive coordinates from one consistent
scale. Give each item's objects their own group/list; animate the correct group.
Keep unchanged logic when repairing. Caption and diagrams explain without audio.
'''

RUNTIME_CONTRACT = {
    'begin': 'begin(scene,title,caption) -> started time; heading y=3.2, caption y=-3.2',
    'finish': 'finish(scene,started,duration) holds to duration, clears updaters, fades all objects',
    'text': 'text(value,size=28,color=WHITE,width=11) -> wrapped m.Text, scaled to max width',
    'arrow': 'arrow(start,end,color=RED,**kwargs) -> m.Arrow(start,end,buff=.01,stroke_width=4,...); norm(end-start)>=.03',
    'polyline': 'polyline(points,color=RED,width=4) -> open m.VMobject.set_points_as_corners(np.array(points)); point_from_proportion(t) is valid after construction',
    'colors': {'BG':'#0B1220','WHITE':'#EDF3FF','CYAN':'#49D6F5','GREEN':'#71E3A2','RED':'#FF727C','AMBER':'#FFC768'},
}


def domain_guidance(topic, scene=None):
    """Only include rotation conventions when the requested lesson uses them."""
    value=topic+' '+json.dumps(scene or {})
    if re.search(r'centripet|centrifug|circular motion|rotating frame|inertial frame',value,re.I):
        return ('For this circular-motion lesson: velocity is tangent; real centripetal force '
                'is inward. Balanced arrows use one force scale. In a co-rotating camera the '
                'object and frame own axes stay fixed; inertial background axes counter-rotate. '
                'Derive rotation from the actual matrix multiplication: for '
                'R=[[cos(a),-sin(a)],[sin(a),cos(a)]], [1,0] @ R=[cos(a),-sin(a)] '
                'has angle -a, whereas R @ [1,0]=[cos(a),sin(a)] has angle +a.')
    return ''


def compact_sources(sources, focus='', max_claims=3, max_passages=5):
    """Select original claims and their original support; never invent a digest."""
    words=set(re.findall(r'[a-z]{3,}|\d+(?:\.\d+)?',focus.lower()))
    words-=set('the and with show scene year years interest balance amount growth from each this that'.split())
    selected=[]
    for source in sources:
        claims=source.get('claims',[])
        def score(claim):
            text=claim.get('claim','') if isinstance(claim,dict) else str(claim)
            return len(words & set(re.findall(r'[a-z]{3,}|\d+(?:\.\d+)?',text.lower())))
        claims=sorted(claims,key=score,reverse=True)[:max_claims]
        ids={item for claim in claims if isinstance(claim,dict) for item in claim.get('passage_ids',[])}
        passages=[{'id':p['id'],'text':p['text']} for p in source.get('passages',[]) if p.get('id') in ids]
        selected.append({'id':source['id'],'url':source['url'],'claims':claims,
                         'cautions':source.get('cautions',[])[:2],
                         'passages':passages[:max_passages],
                         'scope':'Selected original evidence; full sources are archived in research.json.'})
    return selected


def compact_geometry(geometry,count=4):
    samples=geometry.get('samples',[])
    # Include an early frame and the final hold, before the closing FadeOut.
    if len(samples)>count:
        last=max(0,len(samples)-3)
        indices=sorted({round(last*i/(count-1)) for i in range(count)})
        samples=[samples[i] for i in indices]
    def rounded(value):
        if isinstance(value,float):return round(value,4)
        if isinstance(value,list):return [rounded(item) for item in value]
        if isinstance(value,dict):return {k:rounded(v) for k,v in value.items()}
        return value
    return rounded({'duration':geometry['duration'],'out_of_frame':geometry.get('out_of_frame',[]),
        'samples':samples,
        'scope':'Sampled geometry, not pixel visibility. Group boxes include child objects; absence of a child as a top-level box does not prove it is absent. Animated partial shapes/labels may be transient.'})


def apply_edits(source,edits):
    """Apply only uniquely matched replacement text returned by Qwen."""
    if not isinstance(edits,list) or not 1<=len(edits)<=8:
        raise ValueError('Return 1–8 exact source edits')
    result=source
    for edit in edits:
        if not isinstance(edit,dict) or set(edit)!={'old','new'}:
            raise ValueError('Each edit must contain exactly old and new strings')
        old,new=edit['old'],edit['new']
        if not isinstance(old,str) or not old.strip() or not isinstance(new,str) or old==new:
            raise ValueError('An edit must replace non-empty source with different text')
        if result.count(old)!=1:
            raise ValueError('Edit old text must match exactly once in the current source: '+old[:180])
        result=result.replace(old,new,1)
    return result


def concise_feedback(feedback):
    prefix='Verified major review findings:\n'
    if prefix in feedback:
        try:
            review=json.loads(feedback.split(prefix,1)[1])
            issues=[{k:issue.get(k,'') for k in ('problem','evidence','correction')}
                    for issue in review.get('issues',[]) if issue.get('severity')=='major']
            return json.dumps({'repair_only':issues},ensure_ascii=False)
        except (ValueError,TypeError,AttributeError):pass
    return feedback[-6500:]
